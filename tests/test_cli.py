from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from deep_research_agent.cli import main
from deep_research_agent.domain.models import SearchProvider
from tests.support import build_fake_bundle


def configure_env(monkeypatch, workspace: Path) -> None:
    db_path = workspace / "agent.sqlite3"
    monkeypatch.setenv("DEEP_RESEARCH_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("DEEP_RESEARCH_SQLITE_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("DEEP_RESEARCH_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("DEEP_RESEARCH_DEFAULT_SEARCH_PROVIDER", "none")
    monkeypatch.setenv("DEEP_RESEARCH_MAX_ITERATIONS", "4")


def test_cli_run_resume_and_list_pending(monkeypatch, capsys):
    workspace = Path("tests/.artifacts") / uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    configure_env(monkeypatch, workspace)
    bundle = build_fake_bundle()
    monkeypatch.setattr("deep_research_agent.runtime.service.build_service_bundle", lambda settings: bundle)

    try:
        assert main(["run", "--query", "Assess LangGraph checkpointing"]) == 0
        started = json.loads(capsys.readouterr().out)
        thread_id = started["thread_id"]
        assert started["status"] == "interrupted"
        assert started["pending_human_input"]["review_kind"] == "plan_approval"
        assert started["resume_supported"] is True

        assert main(["list-pending"]) == 0
        pending = json.loads(capsys.readouterr().out)
        assert pending["count"] == 1
        assert pending["runs"][0]["thread_id"] == thread_id

        assert main(["resume", "--thread-id", thread_id, "--decision", "approve", "--summary", "Looks good"]) == 0
        resumed = json.loads(capsys.readouterr().out)
        assert resumed["status"] == "interrupted"
        assert resumed["pending_human_input"]["review_kind"] == "sufficiency_review"
        assert resumed["state"]["iteration_count"] == 2

        assert main(["resume", "--thread-id", thread_id, "--decision", "approve", "--summary", "Sufficient"]) == 0
        finished = json.loads(capsys.readouterr().out)
        assert finished["status"] == "completed"
        assert finished["resume_supported"] is False
        assert finished["state"]["final_report_title"] == "AI Infrastructure Market Assessment"

        assert main(["list-pending"]) == 0
        pending_after = json.loads(capsys.readouterr().out)
        assert pending_after == {"count": 0, "runs": []}
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_cli_run_uses_persisted_search_settings(monkeypatch, capsys):
    workspace = (Path("tests/.artifacts") / uuid4().hex).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    configure_env(monkeypatch, workspace)
    monkeypatch.chdir(workspace)

    settings_dir = Path(".local")
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps(
            {
                "default_search_provider": "tavily",
                "tavily_api_key": "tvly-test-key",
            }
        ),
        encoding="utf-8",
    )

    captured_settings = []

    def build_bundle(settings):
        captured_settings.append(settings)
        return build_fake_bundle()

    monkeypatch.setattr("deep_research_agent.runtime.service.build_service_bundle", build_bundle)

    try:
        assert main(["run", "--query", "Assess LangGraph checkpointing"]) == 0
        assert captured_settings
        assert captured_settings[-1].default_search_provider is SearchProvider.TAVILY
        assert captured_settings[-1].tavily_api_key == "tvly-test-key"
        assert json.loads(capsys.readouterr().out)["status"] == "interrupted"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_cli_run_uses_persisted_searxng_settings(monkeypatch, capsys):
    workspace = (Path("tests/.artifacts") / uuid4().hex).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    configure_env(monkeypatch, workspace)
    monkeypatch.chdir(workspace)

    settings_dir = Path(".local")
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps(
            {
                "default_search_provider": "searxng",
                "searxng_selected_instances": [
                    "https://search-1.example/",
                    "https://search-2.example/",
                    "https://search-3.example/",
                    "https://search-4.example/",
                    "https://search-5.example/",
                ],
                "searxng_selected_at": "2026-05-31T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    captured_settings = []

    def build_bundle(settings):
        captured_settings.append(settings)
        return build_fake_bundle()

    monkeypatch.setattr("deep_research_agent.runtime.service.build_service_bundle", build_bundle)

    try:
        assert main(["run", "--query", "Assess LangGraph checkpointing"]) == 0
        assert captured_settings
        assert captured_settings[-1].default_search_provider is SearchProvider.SEARXNG
        assert captured_settings[-1].searxng_selected_instances == [
            "https://search-1.example/",
            "https://search-2.example/",
            "https://search-3.example/",
            "https://search-4.example/",
            "https://search-5.example/",
        ]
        assert json.loads(capsys.readouterr().out)["status"] == "interrupted"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
