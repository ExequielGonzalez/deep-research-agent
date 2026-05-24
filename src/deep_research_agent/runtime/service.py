from __future__ import annotations

import json
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from enum import Enum
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


class ResearchRuntimeService:
    def __init__(self, settings: AppSettings, services: ResearchServiceBundle | None = None):
        self._settings = settings
        self._services = services

    async def start_run(self, request: ResearchRequest, *, max_iterations: int | None = None) -> RuntimeCommandResult:
        thread_id = uuid4().hex
        initial_state = build_initial_state(thread_id, request, max_iterations or self._settings.max_iterations)
        async with AsyncExitStack() as stack:
            run_store = await stack.enter_async_context(create_run_store(self._settings))
            checkpointer = await stack.enter_async_context(create_checkpointer(self._settings))
            graph = build_research_graph(
                checkpointer=checkpointer,
                services=self._services or build_service_bundle(self._settings),
                settings=self._settings,
            )
            result = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": thread_id}})
            command_result = self._build_command_result(result=result, thread_id=thread_id, default_query=request.query, message_prefix="Run started")
            await run_store.upsert_run(self._record_from_result(command_result))
            return command_result

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
            checkpointer = await stack.enter_async_context(create_checkpointer(self._settings))
            existing = await run_store.get_run(thread_id)
            if existing is None:
                raise RunNotFoundError(f"Unknown thread_id: {thread_id}")

            graph = build_research_graph(
                checkpointer=checkpointer,
                services=self._services or build_service_bundle(self._settings),
                settings=self._settings,
            )
            resume_payload = {
                "decision_type": decision_type.value,
                "summary": summary,
                "payload": payload or {},
            }
            result = await graph.ainvoke(Command(resume=resume_payload), config={"configurable": {"thread_id": thread_id}})
            command_result = self._build_command_result(
                result=result,
                thread_id=thread_id,
                default_query=existing.query,
                message_prefix="Run resumed",
            )
            await run_store.upsert_run(self._record_from_result(command_result, existing=existing))
            return command_result

    async def list_pending_runs(self, *, limit: int = 20) -> list[RunRecord]:
        async with create_run_store(self._settings) as run_store:
            return await run_store.list_pending_runs(limit=limit)

    def _build_command_result(self, *, result: dict[str, Any], thread_id: str, default_query: str, message_prefix: str) -> RuntimeCommandResult:
        interrupts = [to_jsonable(interrupt.value) for interrupt in result.get("__interrupt__", [])]
        state = {key: value for key, value in result.items() if key != "__interrupt__"}
        json_state = to_jsonable(state)
        pending_input = state.get("pending_human_input")
        query = default_query
        if state.get("request") is not None:
            query = state["request"].query

        if interrupts:
            status = RunStatus.INTERRUPTED
            if pending_input is None and interrupts:
                pending_input = HumanReviewRequest.model_validate(interrupts[0])
            message = f"{message_prefix} and paused for human review."
        else:
            status = state.get("status", RunStatus.RUNNING)
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
