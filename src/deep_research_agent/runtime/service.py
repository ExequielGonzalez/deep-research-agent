from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from langgraph.types import Command

from deep_research_agent.domain.models import (
    HumanDecisionType,
    HumanReviewRequest,
    ResearchRequest,
    RunRecord,
    RunStatus,
    RuntimeCommandResult,
)
from deep_research_agent.domain.state import build_initial_state
from deep_research_agent.persistence import create_checkpointer, create_run_store
from deep_research_agent.runtime.events import emit_runtime_event
from deep_research_agent.runtime.graph import build_research_graph
from deep_research_agent.services import ResearchServiceBundle, build_service_bundle
from deep_research_agent.settings import AppSettings


class RunNotFoundError(RuntimeError):
    """Raised when a requested thread_id has never been started."""



def utc_now() -> datetime:
    return datetime.now(timezone.utc)



def to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value


def _slugify_report_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "report"


class ResearchRuntimeService:
    def __init__(self, settings: AppSettings, services: ResearchServiceBundle | None = None):
        self._settings = settings
        self._services = services

    async def initialize_run(
        self,
        request: ResearchRequest,
        *,
        max_iterations: int | None = None,
        thread_id: str | None = None,
    ) -> RunRecord:
        resolved_thread_id = thread_id or uuid4().hex
        initial_state = build_initial_state(resolved_thread_id, request, max_iterations or self._settings.max_iterations)
        record = RunRecord(
            thread_id=resolved_thread_id,
            query=request.query,
            status=RunStatus.CREATED,
            pending_human_input=None,
            latest_state=to_jsonable(initial_state),
            latest_interrupts=[],
            last_message="Run created and waiting to start.",
        )
        async with create_run_store(self._settings) as run_store:
            await run_store.upsert_run(record)
        return record

    async def get_run(self, thread_id: str) -> RunRecord | None:
        async with create_run_store(self._settings) as run_store:
            return await run_store.get_run(thread_id)

    async def start_run(
        self,
        request: ResearchRequest,
        *,
        max_iterations: int | None = None,
        thread_id: str | None = None,
    ) -> RuntimeCommandResult:
        thread_id = thread_id or uuid4().hex
        initial_state = build_initial_state(thread_id, request, max_iterations or self._settings.max_iterations)
        existing = await self.get_run(thread_id)
        if existing is None:
            await self.initialize_run(request, max_iterations=max_iterations, thread_id=thread_id)
        return await self._execute_graph(
            graph_input=initial_state,
            thread_id=thread_id,
            default_query=request.query,
            message_prefix="Run started",
            existing=existing,
        )

    async def resume_run(
        self,
        *,
        thread_id: str,
        decision_type: HumanDecisionType,
        summary: str = "",
        payload: dict[str, Any] | None = None,
    ) -> RuntimeCommandResult:
        async with AsyncExitStack() as stack:
            run_store = await stack.enter_async_context(create_run_store(self._settings))
            existing = await run_store.get_run(thread_id)
            if existing is None:
                raise RunNotFoundError(f"Unknown thread_id: {thread_id}")

        resume_payload = {
            "decision_type": decision_type.value,
            "summary": summary,
            "payload": payload or {},
        }
        return await self._execute_graph(
            graph_input=Command(resume=resume_payload),
            thread_id=thread_id,
            default_query=existing.query,
            message_prefix="Run resumed",
            existing=existing,
        )

    async def list_pending_runs(self, *, limit: int = 20) -> list[RunRecord]:
        async with create_run_store(self._settings) as run_store:
            return await run_store.list_pending_runs(limit=limit)

    async def list_runs(self, *, limit: int = 20) -> list[RunRecord]:
        async with create_run_store(self._settings) as run_store:
            return await run_store.list_runs(limit=limit)

    async def _execute_graph(
        self,
        *,
        graph_input: dict[str, Any] | Command,
        thread_id: str,
        default_query: str,
        message_prefix: str,
        existing: RunRecord | None,
    ) -> RuntimeCommandResult:
        async with AsyncExitStack() as stack:
            run_store = await stack.enter_async_context(create_run_store(self._settings))
            checkpointer = await stack.enter_async_context(create_checkpointer(self._settings))
            graph = build_research_graph(
                checkpointer=checkpointer,
                services=self._services or build_service_bundle(self._settings),
                settings=self._settings,
            )

            latest_result = RuntimeCommandResult(
                thread_id=thread_id,
                query=default_query,
                status=RunStatus.CREATED,
                message=f"{message_prefix} and is preparing execution.",
                state=to_jsonable(graph_input) if isinstance(graph_input, dict) else (existing.latest_state if existing else {}),
                resume_supported=False,
            )

            try:
                graph_timeout = max(60, self._settings.llm_request_timeout_seconds * 3)
                async with asyncio.timeout(graph_timeout):
                    async for state_snapshot in graph.astream(
                        graph_input,
                        config={"configurable": {"thread_id": thread_id}},
                        stream_mode="values",
                    ):
                        latest_result = self._persist_final_report_if_available(self._build_command_result(
                            result=state_snapshot,
                            thread_id=thread_id,
                            default_query=default_query,
                            message_prefix=message_prefix,
                        ))
                        await run_store.upsert_run(self._record_from_result(latest_result, existing=existing))
                        emit_runtime_event(
                            "snapshot",
                            thread_id=thread_id,
                            snapshot=latest_result.model_dump(mode="json"),
                        )
                        if existing is None:
                            existing = self._record_from_result(latest_result)
            except TimeoutError:
                timeout_state = dict(existing.latest_state) if existing else {}
                timeout_state.update({"status": RunStatus.FAILED.value, "last_error": "Graph execution timed out after reaching iteration limit or hanging on a service call."})
                timeout_result = RuntimeCommandResult(
                    thread_id=thread_id,
                    query=default_query,
                    status=RunStatus.FAILED,
                    message=f"{message_prefix} and timed out after {graph_timeout}s.",
                    state=timeout_state,
                    resume_supported=False,
                )
                await run_store.upsert_run(self._record_from_result(timeout_result, existing=existing))
                emit_runtime_event(
                    "snapshot",
                    thread_id=thread_id,
                    snapshot=timeout_result.model_dump(mode="json"),
                )
                return timeout_result
            except Exception as exc:
                failed_state = dict(existing.latest_state) if existing else {}
                failed_state.update({"status": RunStatus.FAILED.value, "last_error": str(exc)})
                failure = RuntimeCommandResult(
                    thread_id=thread_id,
                    query=default_query,
                    status=RunStatus.FAILED,
                    message=f"{message_prefix} and failed: {exc}",
                    state=failed_state,
                    resume_supported=False,
                )
                await run_store.upsert_run(self._record_from_result(failure, existing=existing))
                emit_runtime_event(
                    "snapshot",
                    thread_id=thread_id,
                    snapshot=failure.model_dump(mode="json"),
                )
                raise

            latest_result = self._persist_final_report_if_available(latest_result)
            await run_store.upsert_run(self._record_from_result(latest_result, existing=existing))
            return latest_result

    def _persist_final_report_if_available(self, result: RuntimeCommandResult) -> RuntimeCommandResult:
        if result.status is not RunStatus.COMPLETED:
            return result

        markdown = result.state.get("final_report_markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            return result

        title = result.state.get("final_report_title") or result.query or result.thread_id
        file_name = f"{result.thread_id}-{_slugify_report_name(str(title))}.md"
        output_dir = Path(self._settings.report_output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = (output_dir / file_name).resolve()
        output_path.write_text(markdown, encoding="utf-8")

        if result.state.get("final_report_path") == str(output_path):
            return result

        updated_state = dict(result.state)
        updated_state["final_report_path"] = str(output_path)
        return result.model_copy(update={"state": updated_state})

    def _build_command_result(self, *, result: dict[str, Any], thread_id: str, default_query: str, message_prefix: str) -> RuntimeCommandResult:
        interrupts = [to_jsonable(interrupt.value) for interrupt in result.get("__interrupt__", [])]
        state = {key: value for key, value in result.items() if key != "__interrupt__"}
        json_state = to_jsonable(state)
        pending_input = state.get("pending_human_input")
        query = default_query
        if state.get("request") is not None:
            query = state["request"].query

        raw_status = state.get("status", RunStatus.RUNNING)
        status = raw_status if isinstance(raw_status, RunStatus) else RunStatus(raw_status)

        if interrupts or pending_input is not None or status is RunStatus.INTERRUPTED:
            status = RunStatus.INTERRUPTED
            if pending_input is None and interrupts:
                pending_input = HumanReviewRequest.model_validate(interrupts[0])
            message = f"{message_prefix} and paused for human review."
        else:
            message = f"{message_prefix} and reached status `{status.value}`."

        return RuntimeCommandResult(
            thread_id=thread_id,
            query=query,
            status=status,
            message=message,
            pending_human_input=pending_input,
            interrupts=interrupts,
            state=json_state,
            resume_supported=status is RunStatus.INTERRUPTED,
        )

    def _record_from_result(self, result: RuntimeCommandResult, *, existing: RunRecord | None = None) -> RunRecord:
        created_at = existing.created_at if existing else utc_now()
        return RunRecord(
            thread_id=result.thread_id,
            query=result.query,
            status=result.status,
            created_at=created_at,
            updated_at=utc_now(),
            pending_human_input=result.pending_human_input,
            latest_state=result.state,
            latest_interrupts=result.interrupts,
            last_message=result.message,
        )



def render_json(data: Any) -> str:
    return json.dumps(to_jsonable(data), indent=2, sort_keys=True)
