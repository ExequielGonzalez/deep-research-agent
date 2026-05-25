from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator



def utc_now() -> datetime:
    return datetime.now(timezone.utc)



def new_id() -> str:
    return uuid4().hex


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


_PRIORITY_LABELS = {
    "critical": 1,
    "urgent": 1,
    "high": 1,
    "medium": 2,
    "normal": 2,
    "default": 3,
    "low": 3,
}


def _coerce_string_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    return value


def _coerce_model_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return value


def _coerce_priority(value: Any) -> Any:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _PRIORITY_LABELS:
            return _PRIORITY_LABELS[normalized]
        if normalized.isdigit():
            return int(normalized)
    return value


def _coerce_bool(value: Any) -> Any:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1"}:
            return True
        if normalized in {"false", "no", "n", "0"}:
            return False
    return value


def _coerce_float(value: Any) -> Any:
    if isinstance(value, str):
        normalized = value.strip()
        try:
            return float(normalized)
        except ValueError:
            return value
    return value


def _fallback_title(*candidates: Any, default: str = "Follow-up research") -> str:
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        normalized = " ".join(candidate.split()).strip()
        if normalized:
            return normalized[:80].rstrip(" .:-") or default
    return default


class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    AZURE_OPENAI = "azure_openai"


class SearchProvider(str, Enum):
    TAVILY = "tavily"
    SERPER = "serper"
    FIRECRAWL = "firecrawl"
    NONE = "none"


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class SourceType(str, Enum):
    WEB = "web"
    NEWS = "news"
    ACADEMIC = "academic"
    INTERNAL = "internal"
    MANUAL = "manual"


class HumanDecisionType(str, Enum):
    APPROVE = "approve"
    CLARIFY = "clarify"
    CONTINUE = "continue"
    STOP = "stop"


class HumanReviewKind(str, Enum):
    PLAN_APPROVAL = "plan_approval"
    RESUME_CONFIRMATION = "resume_confirmation"
    CLARIFICATION = "clarification"
    SUFFICIENCY_REVIEW = "sufficiency_review"


class SectionStatus(str, Enum):
    PLANNED = "planned"
    DRAFT = "draft"
    COMPLETE = "complete"


class ResearchRequest(DomainModel):
    request_id: str = Field(default_factory=new_id)
    query: str
    audience: str = "general"
    objective: str | None = None
    constraints: list[str] = Field(default_factory=list)
    deliverable_format: str = "markdown"
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("constraints", mode="before")
    @classmethod
    def normalize_constraints(cls, value: Any) -> Any:
        return _coerce_string_list(value)


class PlanTask(DomainModel):
    task_id: str = Field(default_factory=new_id)
    title: str
    description: str
    search_query: str
    section_title: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: int = 3
    depends_on: list[str] = Field(default_factory=list)
    parent_task_id: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    assigned_node: str | None = None

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: Any) -> Any:
        return _coerce_priority(value)

    @field_validator("success_criteria", mode="before")
    @classmethod
    def normalize_success_criteria(cls, value: Any) -> Any:
        return _coerce_string_list(value)


class ResearchPlan(DomainModel):
    title: str
    normalized_query: str
    plan_summary: str
    tasks: list[PlanTask] = Field(default_factory=list)

    @field_validator("tasks", mode="before")
    @classmethod
    def normalize_tasks(cls, value: Any) -> Any:
        return _coerce_model_list(value)


class SearchResult(DomainModel):
    title: str
    url: str
    canonical_url: str | None = None
    provider: SearchProvider
    source_type: SourceType = SourceType.WEB
    snippet: str | None = None
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceRecord(DomainModel):
    source_id: str = Field(default_factory=new_id)
    title: str
    url: str
    canonical_url: str | None = None
    provider: SearchProvider
    source_type: SourceType = SourceType.WEB
    snippet: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=utc_now)
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(DomainModel):
    evidence_id: str = Field(default_factory=new_id)
    source_id: str
    claim: str
    excerpt: str
    rationale: str | None = None
    confidence: float = 0.0
    supports_task_id: str | None = None


class HumanReviewRequest(DomainModel):
    review_id: str = Field(default_factory=new_id)
    review_kind: HumanReviewKind
    prompt: str
    allowed_decisions: list[HumanDecisionType] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class HumanDecision(DomainModel):
    decision_id: str = Field(default_factory=new_id)
    decision_type: HumanDecisionType
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    made_at: datetime = Field(default_factory=utc_now)

    @classmethod
    def from_resume_payload(cls, payload: dict[str, Any] | str | None) -> "HumanDecision":
        if payload is None:
            return cls(decision_type=HumanDecisionType.CONTINUE)
        if isinstance(payload, str):
            return cls(decision_type=HumanDecisionType.CONTINUE, summary=payload)
        decision_value = payload.get("decision_type") or payload.get("decision") or HumanDecisionType.CONTINUE.value
        return cls(
            decision_type=HumanDecisionType(decision_value),
            summary=payload.get("summary", ""),
            payload=payload.get("payload", {}),
        )


class FollowUpTaskSuggestion(DomainModel):
    title: str
    description: str
    search_query: str
    section_title: str | None = None
    parent_task_id: str | None = None
    priority: int = 3
    success_criteria: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_local_model_keys(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        description = value.get("description") or value.get("details") or value.get("summary")
        search_query = value.get("search_query") or value.get("query") or value.get("web_search_query")
        title = value.get("title") or value.get("task_title") or value.get("name")

        return {
            "title": _fallback_title(title, description, search_query),
            "description": description or title or "Investigate the remaining evidence gap.",
            "search_query": search_query or title or description or "follow-up research",
            "section_title": value.get("section_title") or value.get("section"),
            "parent_task_id": value.get("parent_task_id") or value.get("task_id"),
            "priority": value.get("priority", 3),
            "success_criteria": value.get("success_criteria") or value.get("acceptance_criteria") or value.get("criteria") or [],
        }

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: Any) -> Any:
        return _coerce_priority(value)

    @field_validator("success_criteria", mode="before")
    @classmethod
    def normalize_success_criteria(cls, value: Any) -> Any:
        return _coerce_string_list(value)


class ReflectionOutput(DomainModel):
    reflection_id: str = Field(default_factory=new_id)
    summary: str
    knowledge_gaps: list[str] = Field(default_factory=list)
    follow_up_tasks: list[FollowUpTaskSuggestion] = Field(default_factory=list)
    covered_task_ids: list[str] = Field(default_factory=list)
    needs_more_research: bool = True
    needs_human_input: bool = False
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def normalize_local_model_keys(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        knowledge_gaps = value.get("knowledge_gaps")
        if knowledge_gaps in (None, [], ""):
            knowledge_gaps = value.get("gaps")
        if knowledge_gaps in (None, [], ""):
            knowledge_gaps = value.get("evidence_gaps")

        needs_more_research = value.get("needs_more_research")
        if needs_more_research is None:
            needs_more_research = True
        needs_more_research = _coerce_bool(needs_more_research)

        needs_human_input = value.get("needs_human_input")
        if needs_human_input is None and needs_more_research is False:
            needs_human_input = True
        if needs_human_input is None:
            needs_human_input = False

        return {
            "reflection_id": value.get("reflection_id", new_id()),
            "summary": value.get("summary") or value.get("assessment") or value.get("analysis") or "Evidence review completed.",
            "knowledge_gaps": knowledge_gaps,
            "follow_up_tasks": value.get("follow_up_tasks") or value.get("next_steps") or value.get("recommended_searches") or [],
            "covered_task_ids": value.get("covered_task_ids") or value.get("supported_task_ids") or value.get("completed_task_ids") or [],
            "needs_more_research": needs_more_research,
            "needs_human_input": needs_human_input,
            "confidence": value.get("confidence", 0.0),
            "created_at": value.get("created_at", utc_now()),
        }

    @field_validator("knowledge_gaps", "covered_task_ids", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: Any) -> Any:
        return _coerce_string_list(value)

    @field_validator("follow_up_tasks", mode="before")
    @classmethod
    def normalize_follow_up_tasks(cls, value: Any) -> Any:
        return _coerce_model_list(value)

    @field_validator("needs_more_research", "needs_human_input", mode="before")
    @classmethod
    def normalize_bools(cls, value: Any) -> Any:
        return _coerce_bool(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> Any:
        return _coerce_float(value)


class ReportSection(DomainModel):
    section_id: str = Field(default_factory=new_id)
    title: str
    status: SectionStatus = SectionStatus.PLANNED
    content_markdown: str = ""
    citations: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    summary_points: list[str] = Field(default_factory=list)

    @field_validator("citations", "source_ids", "summary_points", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: Any) -> Any:
        return _coerce_string_list(value)


class SynthesisSection(DomainModel):
    section_id: str = Field(default_factory=new_id)
    title: str
    body_markdown: str
    source_ids: list[str] = Field(default_factory=list)
    summary_points: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_local_model_keys(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        title = value.get("title") or value.get("section_title") or value.get("theme")
        summary_points = value.get("summary_points")
        if summary_points in (None, [], ""):
            summary_points = value.get("key_evidence", [])

        body_markdown = value.get("body_markdown")
        if not body_markdown:
            summary = value.get("summary")
            evidence_points = _coerce_string_list(value.get("key_evidence"))
            body_parts = []
            if isinstance(summary, str) and summary.strip():
                body_parts.append(summary.strip())
            if evidence_points:
                body_parts.extend(f"- {point}" for point in evidence_points)
            body_markdown = "\n".join(body_parts).strip()

        return {
            "section_id": value.get("section_id", new_id()),
            "title": title,
            "body_markdown": body_markdown,
            "source_ids": value.get("source_ids") or value.get("supporting_source_ids", []),
            "summary_points": summary_points,
        }

    @field_validator("source_ids", "summary_points", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: Any) -> Any:
        return _coerce_string_list(value)


class SynthesizedReport(DomainModel):
    title: str
    executive_summary: str
    methodology: str
    findings: list[SynthesisSection] = Field(default_factory=list)
    conclusion: str | None = None
    final_status: str = "completed"

    @field_validator("findings", mode="before")
    @classmethod
    def normalize_findings(cls, value: Any) -> Any:
        return _coerce_model_list(value)


class CitationRecord(DomainModel):
    marker: str
    source_id: str
    title: str
    url: str
    canonical_url: str | None = None


class RunRecord(DomainModel):
    thread_id: str
    query: str
    status: RunStatus
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    pending_human_input: HumanReviewRequest | None = None
    latest_state: dict[str, Any] = Field(default_factory=dict)
    latest_interrupts: list[dict[str, Any]] = Field(default_factory=list)
    last_message: str = ""


class RuntimeCommandResult(DomainModel):
    thread_id: str
    query: str
    status: RunStatus
    message: str
    pending_human_input: HumanReviewRequest | None = None
    interrupts: list[dict[str, Any]] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    resume_supported: bool = False
