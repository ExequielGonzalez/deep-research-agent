from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deep_research_agent.domain.models import EvidenceCluster, PlanTask, ResearchRequest, SourceRecord, TriageDecision
from deep_research_agent.services.extraction import ContentExtractor
from deep_research_agent.services.llm import ProviderConfigurationError, ResearchLLMService, build_llm_service
from deep_research_agent.services.reporting import ReportFormatter
from deep_research_agent.services.search import SearchService, build_search_service, stable_hash
from deep_research_agent.settings import AppSettings


class SourceTriageService:
    """Evaluates source quality and assigns authority tiers before extraction."""

    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._relevance_threshold = settings.source_relevance_threshold
        self._reliability_threshold = settings.source_reliability_threshold

    async def triage(
        self,
        *,
        sources: list[SourceRecord],
        plan_tasks: list[PlanTask],
        request: ResearchRequest,
    ) -> list[TriageDecision]:
        decisions: list[TriageDecision] = []
        task_keywords: dict[str, set[str]] = {}
        for task in plan_tasks:
            merged = f"{task.title} {task.description} {task.search_query}"
            task_keywords[task.task_id] = {w.lower() for w in merged.split() if len(w) >= 3}

        for source in sources:
            relevance = self._compute_relevance(source, task_keywords)
            reliability = self._compute_reliability(source)
            tier = self._assign_tier(relevance, reliability)

            if relevance >= self._relevance_threshold and reliability >= self._reliability_threshold:
                decision = "included"
                justification = f"Relevance {relevance:.2f}, reliability {reliability:.2f}"
            else:
                decision = "excluded"
                reasons = []
                if relevance < self._relevance_threshold:
                    reasons.append("low relevance")
                if reliability < self._reliability_threshold:
                    reasons.append("low reliability")
                justification = "; ".join(reasons)

            decisions.append(
                TriageDecision(
                    source_id=source.source_id,
                    decision=decision,
                    relevance_score=relevance,
                    reliability_score=reliability,
                    authority_tier=tier,
                    justification=justification,
                    excluded_reason=justification if decision == "excluded" else "",
                )
            )
        return decisions

    def _compute_relevance(self, source: SourceRecord, task_keywords: dict[str, set[str]]) -> float:
        source_text = f"{source.title} {source.snippet or ''} {source.url}".lower()
        max_overlap = 0.0
        for task_id, keywords in task_keywords.items():
            if not keywords:
                continue
            source_words = {w for w in source_text.split() if len(w) >= 3}
            overlap = len(keywords & source_words)
            score = overlap / max(len(keywords), 1)
            max_overlap = max(max_overlap, score)
        return min(1.0, max_overlap * 2.0)

    def _compute_reliability(self, source: SourceRecord) -> float:
        score = 0.5
        url = source.url.lower()
        if any(tld in url for tld in [".edu", ".gov", ".ac."]):
            score += 0.3
        if "wikipedia" in url:
            score += 0.1
        if source.provider.value in ("tavily", "serper"):
            score += 0.1
        return min(1.0, score)

    def _assign_tier(self, relevance: float, reliability: float) -> str:
        combined = (relevance + reliability) / 2.0
        if combined >= 0.7:
            return "PRIMARY"
        if combined >= 0.4:
            return "CONTEXTUAL"
        return "EXCLUDED"


@dataclass(slots=True)
class ResearchServiceBundle:
    llm: ResearchLLMService
    search: SearchService
    extractor: ContentExtractor
    report_formatter: ReportFormatter
    source_triage: SourceTriageService | None = None


def build_service_bundle(settings: AppSettings) -> ResearchServiceBundle:
    bundle = ResearchServiceBundle(
        llm=build_llm_service(settings),
        search=build_search_service(settings),
        extractor=ContentExtractor(settings),
        report_formatter=ReportFormatter(),
    )
    if settings.ff_new_evidence_model:
        bundle.source_triage = SourceTriageService(settings)
    return bundle


__all__ = [
    "ProviderConfigurationError",
    "ResearchLLMService",
    "ResearchServiceBundle",
    "SearchService",
    "SourceTriageService",
    "build_service_bundle",
]
