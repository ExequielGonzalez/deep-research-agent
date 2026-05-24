from __future__ import annotations

import shutil
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from deep_research_agent.runtime.service import ResearchRuntimeService
from deep_research_agent.web.app import create_app
from tests.support import build_fake_bundle, build_test_settings


def build_test_app(sqlite_url: str):
    settings = build_test_settings(sqlite_url)

    def factory(run_settings):
        return ResearchRuntimeService(run_settings, services=build_fake_bundle())

    return create_app(settings=settings, service_factory=factory)


def wait_for_run(client: TestClient, thread_id: str, predicate, *, timeout_seconds: float = 5.0):
    deadline = time.time() + timeout_seconds
    payload = None
    while time.time() < deadline:
      payload = client.get(f"/api/runs/{thread_id}").json()
      if predicate(payload):
          return payload
      time.sleep(0.05)
    raise AssertionError(payload)


def test_web_run_lifecycle_and_index():
    workspace = Path("tests/.artifacts") / uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    sqlite_url = f"sqlite+aiosqlite:///{workspace / 'agent.sqlite3'}"

    try:
        app = build_test_app(sqlite_url)
        with TestClient(app) as client:
            html = client.get("/")
            assert html.status_code == 200
            assert "Deep Research Console" in html.text

            created = client.post(
                "/api/runs",
                json={
                    "query": "Assess the AI infrastructure market",
                    "llm_request_timeout_seconds": 240,
                    "model_name": "fake-local-model",
                    "openai_base_url": "http://127.0.0.1:8085/v1",
                },
            )
            assert created.status_code == 202
            thread_id = created.json()["thread_id"]

            with client.stream("GET", f"/api/runs/{thread_id}/events?history=0&follow=false") as stream_response:
                assert stream_response.status_code == 200
                body = "\n".join(line for _, line in zip(range(4), stream_response.iter_lines()))
                assert "event: snapshot" in body
                assert thread_id in body

            started = wait_for_run(
                client,
                thread_id,
                lambda run: run["status"] == "interrupted" and run["pending_human_input"]["review_kind"] == "plan_approval",
            )
            assert started["runtime_config"]["model_name"] == "fake-local-model"
            assert started["runtime_config"]["llm_request_timeout_seconds"] == 240
            assert started["state"]["plan_title"] == "AI Infrastructure Market Assessment"

            approved = client.post(
                f"/api/runs/{thread_id}/decisions",
                json={"decision": "approve", "summary": "Proceed with the research plan"},
            )
            assert approved.status_code == 202

            sufficiency = wait_for_run(
                client,
                thread_id,
                lambda run: run["status"] == "interrupted" and run["pending_human_input"]["review_kind"] == "sufficiency_review",
            )
            assert sufficiency["state"]["iteration_count"] == 2
            assert len(sufficiency["state"]["sources"]) == 4

            finished = client.post(
                f"/api/runs/{thread_id}/decisions",
                json={"decision": "approve", "summary": "Sufficient evidence gathered"},
            )
            assert finished.status_code == 202

            completed = wait_for_run(client, thread_id, lambda run: run["status"] == "completed")
            assert completed["state"]["final_report_markdown"].startswith("# AI Infrastructure Market Assessment")

            recent = client.get("/api/runs?limit=10")
            assert recent.status_code == 200
            assert recent.json()["runs"][0]["thread_id"] == thread_id
    finally:
        shutil.rmtree(workspace, ignore_errors=True)