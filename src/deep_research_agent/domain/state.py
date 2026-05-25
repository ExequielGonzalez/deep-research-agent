from __future__ import annotations

from typing import Sequence, TypeVar
from typing_extensions import Annotated, TypedDict

from pydantic import BaseModel

from deep_research_agent.domain.models import (
    CitationRecord,
    EvidenceRecord,
    HumanDecision,
    HumanReviewRequest,
    PlanTask,
    ReflectionOutput,
    ReportSection,
    ResearchRequest,
    RunStatus,
    SourceRecord,
)

ModelT = TypeVar("ModelT", bound=BaseModel)



def merge_notes(existing: Sequence[str] | None, updates: Sequence[str] | None) -> list[str]:
    """Append notes while preserving order and removing exact duplicates."""

    merged: list[str] = []
    for note in [*(existing or []), *(updates or [])]:
        normalized = note.strip()
        if normalized and normalized not in merged:
            merged.append(normalized)
    return merged



def _merge_model_list(existing: Sequence[ModelT] | None, updates: Sequence[ModelT] | None, key: str) -> list[ModelT]:
    merged: dict[str, ModelT] = {}
    for item in existing or []:
        merged[str(getattr(item, key))] = item
    for item in updates or []:
        merged[str(getattr(item, key))] = item
    return list(merged.values())


# Reducers are explicit so repeated loop iterations append/update entities instead
# of replacing previously collected tasks, sources, evidence, decisions, or sections.
def merge_plan_tasks(existing: Sequence[PlanTask] | None, updates: Sequence[PlanTask] | None) -> list[PlanTask]:
    return _merge_model_list(existing, updates, "task_id")



def merge_sources(existing: Sequence[SourceRecord] | None, updates: Sequence[SourceRecord] | None) -> list[SourceRecord]:
    merged: dict[str, SourceRecord] = {}
    for item in existing or []:
        source_key = item.canonical_url or item.url or item.source_id
        merged[source_key] = item

    for item in updates or []:
        source_key = item.canonical_url or item.url or item.source_id
        current = merged.get(source_key)
        if current is None:
            merged[source_key] = item
            continue

        merged[source_key] = current.model_copy(
            update={
                "source_id": current.source_id,
                "title": item.title or current.title,
                "url": item.url or current.url,
                "canonical_url": item.canonical_url or current.canonical_url,
                "snippet": item.snippet or current.snippet,
                "published_at": item.published_at or current.published_at,
                "task_ids": list(dict.fromkeys([*current.task_ids, *item.task_ids])),
                "metadata": {**current.metadata, **item.metadata},
            }
        )
    return list(merged.values())



def merge_evidence(existing: Sequence[EvidenceRecord] | None, updates: Sequence[EvidenceRecord] | None) -> list[EvidenceRecord]:
    return _merge_model_list(existing, updates, "evidence_id")



def merge_reflections(existing: Sequence[ReflectionOutput] | None, updates: Sequence[ReflectionOutput] | None) -> list[ReflectionOutput]:
    return _merge_model_list(existing, updates, "reflection_id")



def merge_human_decisions(existing: Sequence[HumanDecision] | None, updates: Sequence[HumanDecision] | None) -> list[HumanDecision]:
    return _merge_model_list(existing, updates, "decision_id")



def merge_report_sections(existing: Sequence[ReportSection] | None, updates: Sequence[ReportSection] | None) -> list[ReportSection]:
    return _merge_model_list(existing, updates, "section_id")



def merge_citations(existing: Sequence[CitationRecord] | None, updates: Sequence[CitationRecord] | None) -> list[CitationRecord]:
    return _merge_model_list(existing, updates, "source_id")


class ResearchGraphState(TypedDict, total=False):
    thread_id: str
    run_id: str
    status: RunStatus
    request: ResearchRequest
    plan_title: str | None
    plan_summary: str | None
    plan_tasks: Annotated[list[PlanTask], merge_plan_tasks]
    current_task_id: str | None
    sources: Annotated[list[SourceRecord], merge_sources]
    evidence: Annotated[list[EvidenceRecord], merge_evidence]
    notes: Annotated[list[str], merge_notes]
    reflections: Annotated[list[ReflectionOutput], merge_reflections]
    human_decisions: Annotated[list[HumanDecision], merge_human_decisions]
    pending_human_input: HumanReviewRequest | None
    report_sections: Annotated[list[ReportSection], merge_report_sections]
    citation_records: Annotated[list[CitationRecord], merge_citations]
    final_report_title: str | None
    final_report_markdown: str | None
    final_report_path: str | None
    final_report_status: str | None
    iteration_count: int
    max_iterations: int
    last_error: str | None



def build_initial_state(thread_id: str, request: ResearchRequest, max_iterations: int) -> ResearchGraphState:
    return ResearchGraphState(
        thread_id=thread_id,
        run_id=request.request_id,
        status=RunStatus.CREATED,
        request=request,
        plan_title=None,
        plan_summary=None,
        plan_tasks=[],
        sources=[],
        evidence=[],
        notes=[],
        reflections=[],
        human_decisions=[],
        pending_human_input=None,
        report_sections=[],
        citation_records=[],
        final_report_title=None,
        final_report_markdown=None,
        final_report_path=None,
        final_report_status=None,
        iteration_count=0,
        max_iterations=max_iterations,
        last_error=None,
    )
