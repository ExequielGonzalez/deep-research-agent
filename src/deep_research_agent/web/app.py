from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from deep_research_agent.domain.models import (
    HumanDecisionType,
    ModelProvider,
    ResearchRequest,
    RunRecord,
    RunStatus,
)
from deep_research_agent.runtime.events import runtime_event_scope
from deep_research_agent.runtime.service import ResearchRuntimeService
from deep_research_agent.settings import AppSettings, get_settings

# Try to load Vue frontend build; fall back to legacy embedded UI
# Docker: __file__ = /usr/local/lib/python3.12/site-packages/deep_research_agent/web/app.py
# Vue dist is at /app/frontend/dist
# Local dev: __file__ = src/deep_research_agent/web/app.py, Vue at deep-research-agent/frontend/dist
_FRONTEND_DIR = "/app/frontend/dist"
_FRONTEND_INDEX = os.path.join(_FRONTEND_DIR, "index.html")
_USE_VUE_FRONTEND = os.path.isfile(_FRONTEND_INDEX)

if not _USE_VUE_FRONTEND:
    # Local dev path
    _LOCAL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist")
    _LOCAL_INDEX = os.path.join(_LOCAL_DIR, "index.html")
    if os.path.isfile(_LOCAL_INDEX):
        _FRONTEND_DIR = _LOCAL_DIR
        _FRONTEND_INDEX = _LOCAL_INDEX
        _USE_VUE_FRONTEND = True

if not _USE_VUE_FRONTEND:
    import logging
    logging.warning(
        "Vue frontend not found at %s. Falling back to legacy UI.",
        _FRONTEND_INDEX,
    )

if _USE_VUE_FRONTEND:
    INDEX_HTML = open(_FRONTEND_INDEX, "r", encoding="utf-8").read()
else:
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
    llm_request_timeout_seconds: int | None = None


class DecisionRequest(BaseModel):
    decision: HumanDecisionType
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class SettingsRequest(BaseModel):
    openai_api_key: str = ""
    openai_base_url: str = ""
    ollama_base_url: str = ""
    default_search_provider: str = "none"
    tavily_api_key: str = ""
    serper_api_key: str = ""
    max_iterations: int = 6
    max_sources_per_task: int = 8
    total_token_budget: int = 120_000
    max_notes: int = 200


_SETTINGS_PATH = ".local/settings.json"


def _load_settings() -> dict[str, Any]:
    try:
        with open(_SETTINGS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_settings(data: dict[str, Any]) -> None:
    import os

    os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    with open(_SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _default_service_factory(settings: AppSettings) -> ResearchRuntimeService:
    return ResearchRuntimeService(settings)


def _build_runtime_settings(
    base_settings: AppSettings, request: CreateRunRequest
) -> AppSettings:
    stored = _load_settings()
    update = {
        "model_provider": ModelProvider.OPENAI,
        "model_name": request.model_name or base_settings.model_name,
        "openai_base_url": (
            request.openai_base_url or base_settings.openai_base_url
        ).rstrip("/"),
        "openai_api_key": request.openai_api_key
        or base_settings.openai_api_key
        or "local",
        "llm_request_timeout_seconds": request.llm_request_timeout_seconds
        or base_settings.llm_request_timeout_seconds,
        "max_iterations": request.max_iterations
        or stored.get("max_iterations")
        or base_settings.max_iterations,
    }
    return AppSettings.model_validate(
        {**base_settings.model_dump(mode="python"), **update}
    )


def _serialize_run(
    record: RunRecord, *, is_running: bool, runtime_config: dict[str, Any] | None = None
) -> dict[str, Any]:
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
            "User-Agent": "deep-research-agent/0.1.0",
        },
        method="GET",
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(
            status_code=exc.code, detail=detail or "Model catalog request failed."
        ) from exc
    except urllib_error.URLError as exc:
        raise HTTPException(
            status_code=502, detail=f"Model catalog request failed: {exc.reason}"
        ) from exc
    return [item.get("id") for item in payload.get("data", []) if item.get("id")]


def _slugify_filename(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value)
    collapsed = "-".join(part for part in normalized.split("-") if part)
    return collapsed or "report"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sse_message(event: str, payload: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


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
        self._event_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(
            list
        )

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
            "llm_request_timeout_seconds": settings.llm_request_timeout_seconds,
        }

    def subscribe(self, thread_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[thread_id].append(queue)
        return queue

    def unsubscribe(self, thread_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subscribers = self._subscribers.get(thread_id, [])
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            self._subscribers.pop(thread_id, None)

    def recent_events(self, thread_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
        events = self._event_history.get(thread_id, [])
        return list(events[-limit:])

    def publish(self, thread_id: str, event: dict[str, Any]) -> None:
        payload = {
            "thread_id": thread_id,
            "created_at": event.get("created_at", _utc_now_iso()),
            **event,
        }
        history = self._event_history[thread_id]
        history.append(payload)
        if len(history) > 80:
            del history[:-80]
        for subscriber in list(self._subscribers.get(thread_id, [])):
            subscriber.put_nowait(payload)

    def launch_start(
        self,
        *,
        thread_id: str,
        request: ResearchRequest,
        max_iterations: int | None,
        settings: AppSettings,
    ) -> None:
        self._ensure_not_running(thread_id)
        self._settings_by_thread[thread_id] = settings
        service = self._service_factory(settings)

        async def _runner() -> None:
            await service.start_run(
                request, max_iterations=max_iterations, thread_id=thread_id
            )

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
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This run is already executing.",
            )

    def _register_task(
        self, thread_id: str, settings: AppSettings, coroutine: Any
    ) -> None:
        async def _runner_with_events() -> None:
            self.publish(
                thread_id,
                {
                    "event": "run_task_started",
                    "message": "Background execution started.",
                },
            )
            with runtime_event_scope(lambda event: self.publish(thread_id, event)):
                await coroutine

        task = asyncio.create_task(
            _runner_with_events(), name=f"deep-research:{thread_id}"
        )
        self._tasks[thread_id] = ActiveRunTask(task=task, settings=settings)

        def _cleanup(done_task: asyncio.Task[None]) -> None:
            try:
                done_task.exception()
            except asyncio.CancelledError:
                self.publish(
                    thread_id,
                    {
                        "event": "run_task_cancelled",
                        "message": "Background execution was cancelled.",
                    },
                )
            except Exception as exc:
                self.publish(
                    thread_id, {"event": "run_task_failed", "message": str(exc)}
                )
            else:
                self.publish(
                    thread_id,
                    {
                        "event": "run_task_finished",
                        "message": "Background execution finished.",
                    },
                )
            self._tasks.pop(thread_id, None)

        task.add_done_callback(_cleanup)


def create_app(
    *,
    settings: AppSettings | None = None,
    service_factory: ServiceFactory | None = None,
) -> FastAPI:
    base_settings = settings or get_settings()
    runtime_service_factory = service_factory or _default_service_factory
    manager = RunExecutionManager(
        base_settings=base_settings, service_factory=runtime_service_factory
    )

    app = FastAPI(title="Deep Research Console", version="0.1.0")

    def _read_service() -> ResearchRuntimeService:
        return runtime_service_factory(base_settings)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return {
            "default_model_name": base_settings.model_name,
            "default_openai_base_url": base_settings.openai_base_url,
            "default_llm_request_timeout_seconds": base_settings.llm_request_timeout_seconds,
            "default_report_output_dir": base_settings.report_output_dir,
            "suggested_local_base_url": "http://127.0.0.1:8085/v1",
        }

    @app.get("/api/settings")
    async def get_app_settings() -> dict[str, Any]:
        stored = _load_settings()
        return {
            "openai_api_key": stored.get("openai_api_key", ""),
            "openai_base_url": stored.get(
                "openai_base_url", base_settings.openai_base_url
            ),
            "ollama_base_url": stored.get(
                "ollama_base_url", base_settings.ollama_base_url
            ),
            "default_search_provider": stored.get("default_search_provider", "none"),
            "max_iterations": stored.get(
                "max_iterations", base_settings.max_iterations
            ),
            "max_sources_per_task": stored.get(
                "max_sources_per_task", base_settings.max_sources_per_task
            ),
            "total_token_budget": stored.get(
                "total_token_budget", base_settings.total_token_budget
            ),
            "max_notes": stored.get("max_notes", base_settings.max_notes),
        }

    @app.post("/api/settings")
    async def post_app_settings(request: SettingsRequest) -> dict[str, str]:
        stored = _load_settings()
        if request.openai_api_key:
            stored["openai_api_key"] = request.openai_api_key
        if request.openai_base_url:
            stored["openai_base_url"] = request.openai_base_url
        if request.ollama_base_url:
            stored["ollama_base_url"] = request.ollama_base_url
        if request.default_search_provider:
            stored["default_search_provider"] = request.default_search_provider
        if request.tavily_api_key:
            stored["tavily_api_key"] = request.tavily_api_key
        if request.serper_api_key:
            stored["serper_api_key"] = request.serper_api_key
        if request.max_iterations and request.max_iterations != 6:
            stored["max_iterations"] = request.max_iterations
        if request.max_sources_per_task and request.max_sources_per_task != 8:
            stored["max_sources_per_task"] = request.max_sources_per_task
        if request.total_token_budget and request.total_token_budget != 120_000:
            stored["total_token_budget"] = request.total_token_budget
        if request.max_notes and request.max_notes != 200:
            stored["max_notes"] = request.max_notes
        _save_settings(stored)
        return {"status": "ok"}

    @app.get("/api/models")
    async def model_catalog() -> dict[str, Any]:
        api_key = base_settings.openai_api_key or "local"
        base_url = base_settings.openai_base_url
        models = _fetch_model_catalog(base_url, api_key)
        return {"base_url": base_url.rstrip("/"), "models": models}

    @app.get("/api/runs")
    async def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        runs = await _read_service().list_runs(limit=limit)
        return {
            "runs": [
                _serialize_run(
                    run,
                    is_running=manager.is_running(run.thread_id),
                    runtime_config=manager.runtime_config(run.thread_id),
                )
                for run in runs
            ]
        }

    @app.get("/api/runs/{thread_id}")
    async def get_run(thread_id: str) -> dict[str, Any]:
        run = await _read_service().get_run(thread_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown thread_id"
            )
        return _serialize_run(
            run,
            is_running=manager.is_running(thread_id),
            runtime_config=manager.runtime_config(thread_id),
        )

    @app.get("/api/runs/{thread_id}/report.md")
    async def export_run_markdown(thread_id: str) -> PlainTextResponse:
        run = await _read_service().get_run(thread_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown thread_id"
            )

        markdown = run.latest_state.get("final_report_markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This run does not have a completed markdown report yet.",
            )

        title = run.latest_state.get("final_report_title") or run.query or thread_id
        filename = f"{_slugify_filename(str(title))}-{thread_id[:8]}.md"
        return PlainTextResponse(
            markdown,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/runs/{thread_id}/events")
    async def stream_run_events(
        thread_id: str,
        history: int = Query(default=25, ge=0, le=100),
        follow: bool = Query(default=True),
    ) -> StreamingResponse:
        runtime_service = _read_service()
        run = await runtime_service.get_run(thread_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown thread_id"
            )

        async def event_stream():
            current = await runtime_service.get_run(thread_id)
            if current is not None:
                yield _sse_message(
                    "snapshot",
                    _serialize_run(
                        current,
                        is_running=manager.is_running(thread_id),
                        runtime_config=manager.runtime_config(thread_id),
                    ),
                )
            for event in manager.recent_events(thread_id, limit=history):
                if event.get("event") == "snapshot":
                    continue
                yield _sse_message(event["event"], event)

            if not follow:
                return

            queue = manager.subscribe(thread_id)
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue

                    if event.get("event") == "snapshot":
                        snapshot = event.get("snapshot")
                        if snapshot is not None:
                            yield _sse_message("snapshot", snapshot)
                            status_value = snapshot.get("status")
                            if status_value in {
                                RunStatus.COMPLETED.value,
                                RunStatus.FAILED.value,
                                RunStatus.CANCELLED.value,
                            }:
                                yield _sse_message(
                                    "stream_end",
                                    {"thread_id": thread_id, "status": status_value},
                                )
                                break
                        continue

                    yield _sse_message(event["event"], event)
            finally:
                manager.unsubscribe(thread_id, queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

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
        return _serialize_run(
            run, is_running=True, runtime_config=manager.runtime_config(thread_id)
        )

    @app.post("/api/runs/{thread_id}/decisions", status_code=status.HTTP_202_ACCEPTED)
    async def submit_decision(
        thread_id: str, request: DecisionRequest
    ) -> dict[str, Any]:
        runtime_service = _read_service()
        run = await runtime_service.get_run(thread_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown thread_id"
            )
        if run.status is not RunStatus.INTERRUPTED or run.pending_human_input is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This run is not waiting for human input.",
            )
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
        return _serialize_run(
            run, is_running=True, runtime_config=manager.runtime_config(thread_id)
        )

    # ── Vue frontend static files (mounted after all API routes) ──────────
    if _USE_VUE_FRONTEND:
        # /assets/* → JS, CSS, fonts
        app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIR, "assets")), name="assets")

        # Root-level static files (manifest, SW, workbox)
        _fd = _FRONTEND_DIR  # capture for closure

        @app.get("/manifest.webmanifest", include_in_schema=False)
        async def _manifest():
            from fastapi.responses import FileResponse
            return FileResponse(os.path.join(_fd, "manifest.webmanifest"))

        @app.get("/registerSW.js", include_in_schema=False)
        async def _reg_sw():
            from fastapi.responses import FileResponse
            return FileResponse(os.path.join(_fd, "registerSW.js"))

        @app.get("/sw.js", include_in_schema=False)
        async def _sw():
            from fastapi.responses import FileResponse
            return FileResponse(os.path.join(_fd, "sw.js"))

        @app.get("/workbox-{name}.js", include_in_schema=False)
        async def _workbox(name: str):
            from fastapi.responses import FileResponse
            fp = os.path.join(_fd, f"workbox-{name}.js")
            if os.path.isfile(fp):
                return FileResponse(fp)
            return HTMLResponse(content=INDEX_HTML)

        # SPA fallback — serve index.html for any non-API route
        @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
        async def spa_fallback(full_path: str) -> str:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            return INDEX_HTML

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deep-research-agent-web",
        description="Local web console for the deep research runtime.",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    import uvicorn

    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0
