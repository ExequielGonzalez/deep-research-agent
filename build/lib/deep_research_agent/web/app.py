from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error as urllib_error, request as urllib_request
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from deep_research_agent.domain.models import HumanDecisionType, ModelProvider, ResearchRequest, RunRecord, RunStatus
from deep_research_agent.runtime.service import ResearchRuntimeService
from deep_research_agent.settings import AppSettings, get_settings
from deep_research_agent.web.ui import INDEX_HTML

ServiceFactory = Callable[[AppSettings], ResearchRuntimeService]


class CreateRunRequest(BaseModel):
    query: str
    audience: str = "general"
    objective: str | None = None
    constraints: list[str] = Field(default_factory=list)
    deliverable_format: str = "markdown"
    max_iterations: int | None = None
    model_name: str | None = None
    openai_base_url: str | None = None
    openai_api_key: str | None = None


class DecisionRequest(BaseModel):
    decision: HumanDecisionType
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


def _default_service_factory(settings: AppSettings) -> ResearchRuntimeService:
    return ResearchRuntimeService(settings)


def _build_runtime_settings(base_settings: AppSettings, request: CreateRunRequest) -> AppSettings:
    update = {
        "model_provider": ModelProvider.OPENAI,
        "model_name": request.model_name or base_settings.model_name,
        "openai_base_url": (request.openai_base_url or base_settings.openai_base_url).rstrip("/"),
        "openai_api_key": request.openai_api_key or base_settings.openai_api_key or "local",
    }
    return AppSettings.model_validate({**base_settings.model_dump(mode="python"), **update})


def _serialize_run(record: RunRecord, *, is_running: bool, runtime_config: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = record.model_dump(mode="json")
    payload["state"] = payload["latest_state"]
    payload["interrupts"] = payload["latest_interrupts"]
    payload["is_running"] = is_running
    payload["runtime_config"] = runtime_config or {}
    return payload


def _fetch_model_catalog(base_url: str, api_key: str) -> list[str]:
    url = f"{base_url.rstrip('/')}/models"
    req = urllib_request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=exc.code, detail=detail or "Model catalog request failed.") from exc
    except urllib_error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Model catalog request failed: {exc.reason}") from exc
    return [item.get("id") for item in payload.get("data", []) if item.get("id")]


@dataclass(slots=True)
class ActiveRunTask:
    task: asyncio.Task[None]
    settings: AppSettings


class RunExecutionManager:
    def __init__(self, *, base_settings: AppSettings, service_factory: ServiceFactory):
        self._base_settings = base_settings
        self._service_factory = service_factory
        self._tasks: dict[str, ActiveRunTask] = {}
        self._settings_by_thread: dict[str, AppSettings] = {}

    def is_running(self, thread_id: str) -> bool:
        active = self._tasks.get(thread_id)
        return bool(active and not active.task.done())

    def runtime_config(self, thread_id: str) -> dict[str, Any]:
        settings = self._settings_by_thread.get(thread_id)
        if settings is None:
            return {}
        return {
            "model_provider": settings.model_provider.value,
            "model_name": settings.model_name,
            "openai_base_url": settings.openai_base_url,
        }

    def launch_start(self, *, thread_id: str, request: ResearchRequest, max_iterations: int | None, settings: AppSettings) -> None:
        self._ensure_not_running(thread_id)
        self._settings_by_thread[thread_id] = settings
        service = self._service_factory(settings)

        async def _runner() -> None:
            await service.start_run(request, max_iterations=max_iterations, thread_id=thread_id)

        self._register_task(thread_id, settings, _runner())

    def launch_resume(
        self,
        *,
        thread_id: str,
        decision_type: HumanDecisionType,
        summary: str,
        payload: dict[str, Any],
    ) -> None:
        self._ensure_not_running(thread_id)
        settings = self._settings_by_thread.get(thread_id, self._base_settings)
        service = self._service_factory(settings)

        async def _runner() -> None:
            await service.resume_run(
                thread_id=thread_id,
                decision_type=decision_type,
                summary=summary,
                payload=payload,
            )

        self._register_task(thread_id, settings, _runner())

    def _ensure_not_running(self, thread_id: str) -> None:
        if self.is_running(thread_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This run is already executing.")

    def _register_task(self, thread_id: str, settings: AppSettings, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine, name=f"deep-research:{thread_id}")
        self._tasks[thread_id] = ActiveRunTask(task=task, settings=settings)

        def _cleanup(done_task: asyncio.Task[None]) -> None:
            try:
                done_task.exception()
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._tasks.pop(thread_id, None)

        task.add_done_callback(_cleanup)


def create_app(*, settings: AppSettings | None = None, service_factory: ServiceFactory | None = None) -> FastAPI:
    base_settings = settings or get_settings()
    runtime_service_factory = service_factory or _default_service_factory
    manager = RunExecutionManager(base_settings=base_settings, service_factory=runtime_service_factory)

    app = FastAPI(title="Deep Research Console", version="0.1.0")

    def _read_service() -> ResearchRuntimeService:
        return runtime_service_factory(base_settings)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return INDEX_HTML

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return {
            "default_model_name": base_settings.model_name,
            "default_openai_base_url": base_settings.openai_base_url,
            "suggested_local_base_url": "http://127.0.0.1:8085/v1",
        }

    @app.get("/api/models")
    async def model_catalog(base_url: str = Query(default="http://127.0.0.1:8085/v1")) -> dict[str, Any]:
        models = _fetch_model_catalog(base_url, base_settings.openai_api_key or "local")
        return {"base_url": base_url.rstrip("/"), "models": models}

    @app.get("/api/runs")
    async def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        runs = await _read_service().list_runs(limit=limit)
        return {
            "runs": [
                _serialize_run(run, is_running=manager.is_running(run.thread_id), runtime_config=manager.runtime_config(run.thread_id))
                for run in runs
            ]
        }

    @app.get("/api/runs/{thread_id}")
    async def get_run(thread_id: str) -> dict[str, Any]:
        run = await _read_service().get_run(thread_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown thread_id")
        return _serialize_run(run, is_running=manager.is_running(thread_id), runtime_config=manager.runtime_config(thread_id))

    @app.post("/api/runs", status_code=status.HTTP_202_ACCEPTED)
    async def create_run(request: CreateRunRequest) -> dict[str, Any]:
        runtime_settings = _build_runtime_settings(base_settings, request)
        runtime_service = runtime_service_factory(runtime_settings)
        research_request = ResearchRequest(
            query=request.query,
            audience=request.audience,
            objective=request.objective,
            constraints=request.constraints,
            deliverable_format=request.deliverable_format,
        )
        thread_id = uuid4().hex
        run = await runtime_service.initialize_run(
            research_request,
            max_iterations=request.max_iterations,
            thread_id=thread_id,
        )
        manager.launch_start(
            thread_id=thread_id,
            request=research_request,
            max_iterations=request.max_iterations,
            settings=runtime_settings,
        )
        return _serialize_run(run, is_running=True, runtime_config=manager.runtime_config(thread_id))

    @app.post("/api/runs/{thread_id}/decisions", status_code=status.HTTP_202_ACCEPTED)
    async def submit_decision(thread_id: str, request: DecisionRequest) -> dict[str, Any]:
        runtime_service = _read_service()
        run = await runtime_service.get_run(thread_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown thread_id")
        if run.status is not RunStatus.INTERRUPTED or run.pending_human_input is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This run is not waiting for human input.")
        if request.decision not in run.pending_human_input.allowed_decisions:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Decision `{request.decision.value}` is not allowed for the current review.",
            )
        manager.launch_resume(
            thread_id=thread_id,
            decision_type=request.decision,
            summary=request.summary,
            payload=request.payload,
        )
        return _serialize_run(run, is_running=True, runtime_config=manager.runtime_config(thread_id))

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deep-research-agent-web", description="Local web console for the deep research runtime.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    import uvicorn

    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0
