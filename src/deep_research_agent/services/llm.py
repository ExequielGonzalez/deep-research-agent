from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar
from urllib import error
from urllib import request as urllib_request

from pydantic import BaseModel, ValidationError

from deep_research_agent.domain.models import (
    HumanDecision,
    PlanTask,
    ReflectionOutput,
    ResearchPlan,
    ResearchRequest,
    SourceRecord,
    SynthesizedReport,
)
from deep_research_agent.runtime.events import emit_runtime_event
from deep_research_agent.settings import AppSettings

SchemaT = TypeVar("SchemaT", bound=BaseModel)

_MAX_TASKS_IN_CONTEXT = 12
_MAX_SOURCES_IN_CONTEXT = 12
_MAX_EVIDENCE_IN_CONTEXT = 24
_MAX_TEXT_FIELD_CHARS = 320
_MAX_EVENT_TEXT_CHARS = 6000
_SYNTHESIS_MAX_TASKS_IN_CONTEXT = 20
_SYNTHESIS_MAX_SOURCES_IN_CONTEXT = 40
_SYNTHESIS_MAX_EVIDENCE_IN_CONTEXT = 80
_SYNTHESIS_TEXT_FIELD_CHARS = 900


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider or provider configuration is unsupported."""


def _truncate_text(value: Any, *, limit: int = _MAX_TEXT_FIELD_CHARS) -> Any:
    if not isinstance(value, str):
        return value
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


def _request_context(request: ResearchRequest) -> dict[str, Any]:
    return {
        "query": _truncate_text(request.query),
        "audience": _truncate_text(request.audience),
        "objective": _truncate_text(request.objective),
        "constraints": [_truncate_text(item) for item in request.constraints[:6]],
        "deliverable_format": request.deliverable_format,
    }


def _decision_context(decision: HumanDecision) -> dict[str, Any]:
    return {
        "decision_type": decision.decision_type.value,
        "summary": _truncate_text(decision.summary),
        "payload": decision.payload,
    }


def _task_context(task: PlanTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "title": _truncate_text(task.title),
        "description": _truncate_text(task.description),
        "search_query": _truncate_text(task.search_query),
        "section_title": _truncate_text(task.section_title),
        "status": task.status.value,
        "priority": task.priority,
        "parent_task_id": task.parent_task_id,
        "success_criteria": [
            _truncate_text(item) for item in task.success_criteria[:3]
        ],
    }


def _source_context(source: SourceRecord) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "title": _truncate_text(source.title),
        "url": source.url,
        "canonical_url": source.canonical_url,
        "provider": source.provider.value,
        "source_type": source.source_type.value,
        "task_ids": source.task_ids,
        "snippet": _truncate_text(source.snippet),
        "published_at": source.published_at.isoformat()
        if source.published_at
        else None,
    }


def _evidence_context(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": item.get("evidence_id"),
        "source_id": item.get("source_id"),
        "source_title": _truncate_text(item.get("source_title")),
        "source_url": item.get("source_url"),
        "source_domain": item.get("source_domain"),
        "supports_task_id": item.get("supports_task_id"),
        "claim": _truncate_text(item.get("claim")),
        "excerpt": _truncate_text(item.get("excerpt")),
        "confidence": item.get("confidence"),
    }


def _reflection_context(reflection: ReflectionOutput) -> dict[str, Any]:
    return {
        "summary": _truncate_text(reflection.summary),
        "knowledge_gaps": [
            _truncate_text(item) for item in reflection.knowledge_gaps[:6]
        ],
        "covered_task_ids": reflection.covered_task_ids,
        "needs_more_research": reflection.needs_more_research,
        "needs_human_input": reflection.needs_human_input,
        "confidence": reflection.confidence,
        "follow_up_tasks": [
            {
                "title": _truncate_text(task.title),
                "description": _truncate_text(task.description),
                "search_query": _truncate_text(task.search_query),
                "section_title": _truncate_text(task.section_title),
                "parent_task_id": task.parent_task_id,
                "priority": task.priority,
                "success_criteria": [
                    _truncate_text(item) for item in task.success_criteria[:3]
                ],
            }
            for task in reflection.follow_up_tasks[:6]
        ],
    }


def _compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _event_text(value: Any, *, limit: int = _MAX_EVENT_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in value
        )
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


def _request_context_for_synthesis(request: ResearchRequest) -> dict[str, Any]:
    return {
        "query": _truncate_text(request.query, limit=_SYNTHESIS_TEXT_FIELD_CHARS),
        "audience": _truncate_text(request.audience, limit=_SYNTHESIS_TEXT_FIELD_CHARS),
        "objective": _truncate_text(
            request.objective, limit=_SYNTHESIS_TEXT_FIELD_CHARS
        ),
        "constraints": [
            _truncate_text(item, limit=_SYNTHESIS_TEXT_FIELD_CHARS)
            for item in request.constraints[:10]
        ],
        "deliverable_format": request.deliverable_format,
    }


def _task_context_for_synthesis(task: PlanTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "title": _truncate_text(task.title, limit=_SYNTHESIS_TEXT_FIELD_CHARS),
        "description": _truncate_text(
            task.description, limit=_SYNTHESIS_TEXT_FIELD_CHARS
        ),
        "search_query": _truncate_text(
            task.search_query, limit=_SYNTHESIS_TEXT_FIELD_CHARS
        ),
        "section_title": _truncate_text(
            task.section_title, limit=_SYNTHESIS_TEXT_FIELD_CHARS
        ),
        "status": task.status.value,
        "priority": task.priority,
        "parent_task_id": task.parent_task_id,
        "success_criteria": [
            _truncate_text(item, limit=_SYNTHESIS_TEXT_FIELD_CHARS)
            for item in task.success_criteria[:6]
        ],
    }


def _source_context_for_synthesis(source: SourceRecord) -> dict[str, Any]:
    from urllib import parse

    try:
        domain = parse.urlparse(source.url).netloc.lower().removeprefix("www.")
    except Exception:
        domain = source.canonical_url or source.url
    return {
        "source_id": source.source_id,
        "title": _truncate_text(source.title, limit=_SYNTHESIS_TEXT_FIELD_CHARS),
        "url": source.url,
        "canonical_url": source.canonical_url,
        "domain": domain,
        "provider": source.provider.value,
        "source_type": source.source_type.value,
        "task_ids": source.task_ids,
        "snippet": _truncate_text(source.snippet, limit=_SYNTHESIS_TEXT_FIELD_CHARS),
        "published_at": source.published_at.isoformat()
        if source.published_at
        else None,
    }


def _evidence_context_for_synthesis(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": item.get("evidence_id"),
        "source_id": item.get("source_id"),
        "source_title": _truncate_text(
            item.get("source_title"), limit=_SYNTHESIS_TEXT_FIELD_CHARS
        ),
        "source_url": item.get("source_url"),
        "source_domain": item.get("source_domain"),
        "supports_task_id": item.get("supports_task_id"),
        "claim": _truncate_text(item.get("claim"), limit=_SYNTHESIS_TEXT_FIELD_CHARS),
        "excerpt": _truncate_text(
            item.get("excerpt"), limit=_SYNTHESIS_TEXT_FIELD_CHARS
        ),
        "confidence": item.get("confidence"),
    }


def _reflection_context_for_synthesis(reflection: ReflectionOutput) -> dict[str, Any]:
    return {
        "summary": _truncate_text(
            reflection.summary, limit=_SYNTHESIS_TEXT_FIELD_CHARS
        ),
        "knowledge_gaps": [
            _truncate_text(item, limit=_SYNTHESIS_TEXT_FIELD_CHARS)
            for item in reflection.knowledge_gaps[:10]
        ],
        "covered_task_ids": reflection.covered_task_ids,
        "needs_more_research": reflection.needs_more_research,
        "needs_human_input": reflection.needs_human_input,
        "confidence": reflection.confidence,
        "follow_up_tasks": [
            {
                "title": _truncate_text(task.title, limit=_SYNTHESIS_TEXT_FIELD_CHARS),
                "description": _truncate_text(
                    task.description, limit=_SYNTHESIS_TEXT_FIELD_CHARS
                ),
                "search_query": _truncate_text(
                    task.search_query, limit=_SYNTHESIS_TEXT_FIELD_CHARS
                ),
                "section_title": _truncate_text(
                    task.section_title, limit=_SYNTHESIS_TEXT_FIELD_CHARS
                ),
                "parent_task_id": task.parent_task_id,
                "priority": task.priority,
                "success_criteria": [
                    _truncate_text(item, limit=_SYNTHESIS_TEXT_FIELD_CHARS)
                    for item in task.success_criteria[:6]
                ],
            }
            for task in reflection.follow_up_tasks[:8]
        ],
    }


class ResearchLLMService(ABC):
    @abstractmethod
    async def plan_research(
        self,
        *,
        request: ResearchRequest,
        prior_tasks: list[PlanTask],
        human_decisions: list[HumanDecision],
    ) -> ResearchPlan: ...

    @abstractmethod
    async def reflect_research(
        self,
        *,
        request: ResearchRequest,
        plan_tasks: list[PlanTask],
        sources: list[SourceRecord],
        evidence_summary: list[dict[str, Any]],
        iteration_count: int,
        max_iterations: int,
    ) -> ReflectionOutput: ...

    @abstractmethod
    async def synthesize_report(
        self,
        *,
        request: ResearchRequest,
        plan_title: str | None,
        plan_summary: str | None,
        plan_tasks: list[PlanTask],
        sources: list[SourceRecord],
        evidence_summary: list[dict[str, Any]],
        reflections: list[ReflectionOutput],
    ) -> SynthesizedReport: ...


class JSONSchemaLLMService(ResearchLLMService, ABC):
    def __init__(self, *, model_name: str):
        self._model_name = model_name

    async def plan_research(
        self,
        *,
        request: ResearchRequest,
        prior_tasks: list[PlanTask],
        human_decisions: list[HumanDecision],
    ) -> ResearchPlan:
        context = {
            "request": _request_context(request),
            "prior_tasks": [
                _task_context(task) for task in prior_tasks[:_MAX_TASKS_IN_CONTEXT]
            ],
            "human_decisions": [
                _decision_context(decision) for decision in human_decisions[-3:]
            ],
        }
        return await self._generate_structured(
            ResearchPlan,
            system_prompt=(
                "You are a deterministic research planner. Produce a concise, executable plan for a deep research workflow. "
                "Return only structured JSON matching the schema. Tasks must be specific, evidence-oriented, and suitable for web research."
            ),
            user_prompt=(
                "Normalize the research request into a title, normalized_query, short plan_summary, and 2-5 plan tasks. "
                "Each task must include title, description, search_query, optional section_title, priority, and success_criteria.\n"
                f"Context:\n{_compact_json(context)}"
            ),
        )

    async def reflect_research(
        self,
        *,
        request: ResearchRequest,
        plan_tasks: list[PlanTask],
        sources: list[SourceRecord],
        evidence_summary: list[dict[str, Any]],
        iteration_count: int,
        max_iterations: int,
    ) -> ReflectionOutput:
        context = {
            "request": _request_context(request),
            "iteration_count": iteration_count,
            "max_iterations": max_iterations,
            "plan_tasks": [
                _task_context(task) for task in plan_tasks[:_MAX_TASKS_IN_CONTEXT]
            ],
            "sources": [
                _source_context(source) for source in sources[:_MAX_SOURCES_IN_CONTEXT]
            ],
            "evidence_summary": [
                _evidence_context(item)
                for item in evidence_summary[:_MAX_EVIDENCE_IN_CONTEXT]
            ],
        }
        return await self._generate_structured(
            ReflectionOutput,
            system_prompt=(
                "You are a research reflection engine. Evaluate evidence sufficiency task by task. "
                "Return only structured JSON matching the schema. Use these exact keys: summary, knowledge_gaps, follow_up_tasks, covered_task_ids, needs_more_research, needs_human_input, confidence. "
                "Do not rename knowledge_gaps to gaps or evidence_gaps. Each follow_up_task must include title, description, search_query, optional section_title, optional parent_task_id, priority, and success_criteria. Do not include status. "
                "Keep covered_task_ids factual and propose follow_up_tasks only when evidence is missing."
            ),
            user_prompt=(
                "Assess whether more research is needed. If evidence is sufficient, set needs_more_research to false and set needs_human_input to true. "
                "If more research is needed, explain the gaps and propose targeted follow_up_tasks.\n"
                f"Context:\n{_compact_json(context)}"
            ),
        )

    async def synthesize_report(
        self,
        *,
        request: ResearchRequest,
        plan_title: str | None,
        plan_summary: str | None,
        plan_tasks: list[PlanTask],
        sources: list[SourceRecord],
        evidence_summary: list[dict[str, Any]],
        reflections: list[ReflectionOutput],
    ) -> SynthesizedReport:
        context = {
            "request": _request_context_for_synthesis(request),
            "plan_title": _truncate_text(plan_title, limit=_SYNTHESIS_TEXT_FIELD_CHARS),
            "plan_summary": _truncate_text(
                plan_summary, limit=_SYNTHESIS_TEXT_FIELD_CHARS
            ),
            "plan_tasks": [
                _task_context_for_synthesis(task)
                for task in plan_tasks[:_SYNTHESIS_MAX_TASKS_IN_CONTEXT]
            ],
            "sources": [
                _source_context_for_synthesis(source)
                for source in sources[:_SYNTHESIS_MAX_SOURCES_IN_CONTEXT]
            ],
            "evidence_summary": [
                _evidence_context_for_synthesis(item)
                for item in evidence_summary[:_SYNTHESIS_MAX_EVIDENCE_IN_CONTEXT]
            ],
            "reflections": [
                _reflection_context_for_synthesis(reflection)
                for reflection in reflections[-6:]
            ],
        }
        return await self._generate_structured(
            SynthesizedReport,
            system_prompt=(
                "You are a RESEARCH SYNTHESIS ENGINE — not a general-purpose writer. "
                "Your ONLY source of truth is the EVIDENCE and SOURCES provided in the context below. "
                "You MUST NOT use any of your pre-existing knowledge, training data, or general information to write the report. "
                "If the provided evidence does not contain sufficient information to support a claim, you MUST NOT make that claim. "
                "Return structured JSON matching the schema. Use these exact top-level keys: title, executive_summary, methodology, findings, optional conclusion, final_status. "
                "Each finding must use title, body_markdown, source_ids, and summary_points. Do not use theme instead of title. "
                ""
                "HARD CONSTRAINTS (never violate):\n"
                "1. source_ids in EVERY finding MUST contain at least one real source_id from the provided sources context.\n"
                "2. body_markdown in each finding MUST reference the source domain(s) inline (e.g., 'According to Nature.com...', 'Data from arXiv.org...').\n"
                "3. NEVER leave source_ids empty — if you cannot find supporting evidence, do NOT include that finding.\n"
                "4. NEVER invent source_ids — only use source_id values that exist in the context provided.\n"
                "5. Every claim in body_markdown MUST be traceable to a specific evidence excerpt or source snippet in the context."
            ),
            user_prompt=(
                "Write a Markdown-ready final research report using ONLY the evidence, source excerpts, and data provided in the Context below.\n"
                ""
                "RULES (follow exactly):\n"
                "1. For EACH finding, identify which source_ids from the 'sources' array support that finding.\n"
                "2. In the finding's body_markdown, explicitly name the source domain(s) in your text. Example format:\n"
                "   'According to arXiv.org, ...' or 'A study published on Nature.com found that ...' or 'Wikipedia reports that ...'\n"
                "3. Every finding's source_ids array must contain at least one valid source_id from the context.\n"
                "4. If the context has fewer than 2 sources with evidence, generate fewer findings — do NOT fabricate.\n"
                "5. Executive_summary should summarize key findings and their sources (2-4 paragraphs).\n"
                "6. Methodology should describe which sources were searched and what evidence was extracted.\n"
                "7. summary_points must be specific, factual claims backed by evidence — not generic statements.\n"
                ""
                "DO NOT write an outline. Deliver a full report.\n"
                "DO NOT use general knowledge — use ONLY the context below.\n"
                ""
                "Context:\n"
                f"{_compact_json(context)}"
            ),
        )

    @abstractmethod
    async def _generate_structured(
        self, schema: type[SchemaT], *, system_prompt: str, user_prompt: str
    ) -> SchemaT: ...


class OpenAIResearchLLMService(JSONSchemaLLMService):
    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        request_timeout_seconds: int,
    ):
        super().__init__(model_name=model_name)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._request_timeout_seconds = request_timeout_seconds

    async def _generate_structured(
        self, schema: type[SchemaT], *, system_prompt: str, user_prompt: str
    ) -> SchemaT:
        emit_runtime_event(
            "llm_stage_started",
            provider="openai",
            model=self._model_name,
            phase=schema.__name__,
        )
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            },
        }
        response = await _http_json_request(
            f"{self._base_url}/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout_seconds=self._request_timeout_seconds,
        )
        try:
            message = response["choices"][0]["message"]
            raw_content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderConfigurationError(
                "OpenAI response did not contain structured message content."
            ) from exc
        reasoning_content = _event_text(message.get("reasoning_content"))
        if reasoning_content:
            emit_runtime_event(
                "llm_reasoning",
                provider="openai",
                model=self._model_name,
                phase=schema.__name__,
                content=reasoning_content,
            )
        output_preview = _event_text(raw_content)
        if output_preview:
            emit_runtime_event(
                "llm_output_preview",
                provider="openai",
                model=self._model_name,
                phase=schema.__name__,
                content=output_preview,
            )
        return _parse_schema_response(schema, raw_content)


class OllamaResearchLLMService(JSONSchemaLLMService):
    def __init__(self, *, model_name: str, base_url: str, request_timeout_seconds: int):
        super().__init__(model_name=model_name)
        self._base_url = base_url.rstrip("/")
        self._request_timeout_seconds = request_timeout_seconds

    async def _generate_structured(
        self, schema: type[SchemaT], *, system_prompt: str, user_prompt: str
    ) -> SchemaT:
        emit_runtime_event(
            "llm_stage_started",
            provider="ollama",
            model=self._model_name,
            phase=schema.__name__,
        )
        payload = {
            "model": self._model_name,
            "stream": False,
            "format": schema.model_json_schema(),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        response = await _http_json_request(
            f"{self._base_url}/api/chat",
            payload,
            timeout_seconds=self._request_timeout_seconds,
        )
        try:
            raw_content = response["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderConfigurationError(
                "Ollama response did not contain structured message content."
            ) from exc
        output_preview = _event_text(raw_content)
        if output_preview:
            emit_runtime_event(
                "llm_output_preview",
                provider="ollama",
                model=self._model_name,
                phase=schema.__name__,
                content=output_preview,
            )
        return _parse_schema_response(schema, raw_content)


async def _http_json_request(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    *,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": "deep-research-agent/0.1.0",
        **(headers or {}),
    }

    def _send() -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url, data=body, headers=request_headers, method="POST"
        )
        try:
            with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - network/provider behavior
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ProviderConfigurationError(
                f"Provider request failed with HTTP {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:  # pragma: no cover - network/provider behavior
            raise ProviderConfigurationError(
                f"Provider request failed: {exc.reason}"
            ) from exc

    task = asyncio.create_task(asyncio.to_thread(_send))
    try:
        return await asyncio.wait_for(task, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        task.cancel()
        raise ProviderConfigurationError(
            f"Provider request timed out after {timeout_seconds}s: {url}"
        )


def _parse_schema_response(schema: type[SchemaT], raw_content: Any) -> SchemaT:
    if isinstance(raw_content, list):
        raw_content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw_content
        )
    if not isinstance(raw_content, str):
        raise ProviderConfigurationError(
            "Provider returned non-string structured content."
        )
    try:
        return schema.model_validate_json(raw_content)
    except ValidationError as exc:
        raise ProviderConfigurationError(
            f"Provider returned invalid structured JSON for {schema.__name__}."
        ) from exc


def build_llm_service(settings: AppSettings) -> ResearchLLMService:
    if settings.model_provider.value == "openai":
        if not settings.openai_api_key:
            raise ProviderConfigurationError(
                "OpenAI provider requires DEEP_RESEARCH_OPENAI_API_KEY."
            )
        return OpenAIResearchLLMService(
            api_key=settings.openai_api_key,
            model_name=settings.model_name,
            base_url=settings.openai_base_url,
            request_timeout_seconds=settings.llm_request_timeout_seconds,
        )
    if settings.model_provider.value == "ollama":
        return OllamaResearchLLMService(
            model_name=settings.model_name,
            base_url=settings.ollama_base_url,
            request_timeout_seconds=settings.llm_request_timeout_seconds,
        )
    raise ProviderConfigurationError(
        f"Model provider `{settings.model_provider.value}` is not supported by the MVP runtime. "
        "Supported providers: openai, ollama."
    )
