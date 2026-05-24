from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from deep_research_agent.domain.models import HumanDecisionType, ResearchRequest
from deep_research_agent.persistence import create_run_store
from deep_research_agent.runtime.service import ResearchRuntimeService
from tests.support import build_fake_bundle, build_test_settings


@pytest.mark.asyncio
async def test_runtime_end_to_end_resume_loop_and_report_persistence():
    workspace = Path("tests/.artifacts") / uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    sqlite_url = f"sqlite+aiosqlite:///{workspace / 'agent.sqlite3'}"
    settings = build_test_settings(sqlite_url)
    service = ResearchRuntimeService(settings, services=build_fake_bundle())

    try:
        started = await service.start_run(ResearchRequest(query="Assess the AI infrastructure market"), max_iterations=4)
        assert started.status.value == "interrupted"
        assert started.pending_human_input is not None
        assert started.pending_human_input.review_kind.value == "plan_approval"
        thread_id = started.thread_id

        pending = await service.list_pending_runs()
        assert [run.thread_id for run in pending] == [thread_id]

        resumed = await service.resume_run(
            thread_id=thread_id,
            decision_type=HumanDecisionType.APPROVE,
            summary="Proceed with the research plan",
        )
        assert resumed.status.value == "interrupted"
        assert resumed.pending_human_input is not None
        assert resumed.pending_human_input.review_kind.value == "sufficiency_review"
        assert resumed.state["iteration_count"] == 2
        assert len(resumed.state["sources"]) == 4
        assert any(task["section_title"] == "Operational Risks" for task in resumed.state["plan_tasks"])

        completed = await service.resume_run(
            thread_id=thread_id,
            decision_type=HumanDecisionType.APPROVE,
            summary="Sufficient evidence gathered",
        )
        assert completed.status.value == "completed"
        assert completed.resume_supported is False
        markdown = completed.state["final_report_markdown"]
        assert markdown.startswith("# AI Infrastructure Market Assessment")
        assert "## Executive Summary" in markdown
        assert "## Methodology" in markdown
        assert "## Sources" in markdown
        assert "[1]" in markdown and "[2]" in markdown
        assert completed.state["final_report_status"] == "completed"
        assert completed.state["citation_records"][0]["marker"] == "[1]"

        async with create_run_store(settings) as run_store:
            persisted = await run_store.get_run(thread_id)
        assert persisted is not None
        assert persisted.status.value == "completed"
        assert persisted.latest_state["final_report_title"] == "AI Infrastructure Market Assessment"
        assert persisted.latest_state["iteration_count"] == 2

        assert await service.list_pending_runs() == []
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
