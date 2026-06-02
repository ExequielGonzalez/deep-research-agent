from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from deep_research_agent.domain.models import (
    EvidenceRecord,
    FollowUpTaskSuggestion,
    ModelProvider,
    PlanTask,
    ReflectionOutput,
    ResearchPlan,
    ResearchRequest,
    SearchProvider,
    SearchResult,
    SourceRecord,
    SynthesisSection,
    SynthesizedReport,
    TriageDecision,
)
from deep_research_agent.services import ResearchServiceBundle
from deep_research_agent.services.extraction import ExtractionResult
from deep_research_agent.services.reporting import ReportFormatter
from deep_research_agent.services.search import canonicalize_url, stable_hash
from deep_research_agent.settings import AppSettings


class FakeLLMService:
    def __init__(self) -> None:
        self.reflection_calls = 0

    async def plan_research(self, *, request: ResearchRequest, prior_tasks: list[PlanTask], human_decisions: list) -> ResearchPlan:
        return ResearchPlan(
            title="AI Infrastructure Market Assessment",
            normalized_query=request.query.lower(),
            plan_summary="Assess market drivers, competition, and operational risks.",
            tasks=[
                PlanTask(
                    title="Map market drivers",
                    description="Identify demand drivers and spending momentum.",
                    search_query="AI infrastructure market demand drivers 2025",
                    section_title="Market Drivers",
                    priority=1,
                    success_criteria=["At least two credible market signals."],
                    expected_sections=["Market size", "Demand trends", "Key drivers"],
                    preferred_source_types=["academic", "news"],
                    sufficiency_criteria={"min_evidence": 2, "min_sources": 2},
                ),
                PlanTask(
                    title="Review competitive positioning",
                    description="Compare leading vendors and strategic moves.",
                    search_query="AI infrastructure vendor competition 2025",
                    section_title="Competitive Positioning",
                    priority=2,
                    success_criteria=["Evidence for at least two vendors."],
                    expected_sections=["Vendor landscape", "Market share"],
                    preferred_source_types=["web", "news"],
                    sufficiency_criteria={"min_evidence": 2, "min_sources": 2},
                ),
            ],
            mandatory_questions=[
                "What are the primary demand drivers for AI infrastructure in 2025?",
                "Which vendors dominate the market and what are their strategic moves?",
            ],
            working_hypotheses=[
                "Demand is driven by generative AI adoption in enterprise.",
                "Supply-chain constraints are a key bottleneck.",
            ],
            search_strategy="Prioritize academic and news sources for market data, supplement with industry blogs.",
            source_type_preferences=["academic", "news", "web"],
            coverage_risks=["Supply-chain data may be sparse", "Vendor financials may be proprietary"],
            closure_conditions=["At least 2 sources per section with evidence confidence > 0.6"],
        )

    async def reflect_research(
        self,
        *,
        request: ResearchRequest,
        plan_tasks: list[PlanTask],
        sources: list[SourceRecord],
        evidence_summary: list[dict],
        iteration_count: int,
        max_iterations: int,
    ) -> ReflectionOutput:
        self.reflection_calls += 1
        task_ids = [task.task_id for task in plan_tasks if task.parent_task_id is None]
        if self.reflection_calls == 1:
            return ReflectionOutput(
                summary="Initial evidence covers market drivers, but risk coverage is still thin.",
                knowledge_gaps=["Need clearer evidence on deployment and supply-chain risks."],
                covered_task_ids=task_ids[:1],
                follow_up_tasks=[
                    FollowUpTaskSuggestion(
                        title="Assess deployment risks",
                        description="Gather evidence about supply-chain and deployment bottlenecks.",
                        search_query="AI infrastructure supply chain deployment risks 2025",
                        section_title="Operational Risks",
                        parent_task_id=task_ids[1],
                        priority=2,
                        success_criteria=["At least one source on supply-chain or deployment risks."],
                    )
                ],
                needs_more_research=True,
                needs_human_input=False,
                confidence=0.58,
            )
        return ReflectionOutput(
            summary="Evidence now covers market drivers, competition, and operational risks sufficiently for synthesis.",
            knowledge_gaps=[],
            covered_task_ids=[task.task_id for task in plan_tasks],
            follow_up_tasks=[],
            needs_more_research=False,
            needs_human_input=True,
            confidence=0.88,
        )

    async def synthesize_report(
        self,
        *,
        request: ResearchRequest,
        plan_title: str | None,
        plan_summary: str | None,
        plan_tasks: list[PlanTask],
        sources: list[SourceRecord],
        evidence_summary: list[dict],
        reflections: list[ReflectionOutput],
    ) -> SynthesizedReport:
        evidence_by_task: dict[str, list[dict]] = defaultdict(list)
        for item in evidence_summary:
            evidence_by_task[item["supports_task_id"]].append(item)

        findings: list[SynthesisSection] = []
        for task in plan_tasks:
            task_evidence = evidence_by_task.get(task.task_id, [])
            if not task_evidence:
                continue
            source_ids = list(dict.fromkeys(item["source_id"] for item in task_evidence))
            findings.append(
                SynthesisSection(
                    title=task.section_title or task.title,
                    body_markdown=f"{task.description} Key evidence: {task_evidence[0]['claim']}",
                    source_ids=list(reversed(source_ids)),
                    summary_points=[f"{len(task_evidence)} evidence item(s) supported this section."],
                )
            )

        return SynthesizedReport(
            title=plan_title or "Research Report",
            executive_summary="The market shows strong demand, active competition, and manageable but real operational risks.",
            methodology="The agent planned the work, searched for sources, extracted evidence, reflected on gaps, and synthesized only after review.",
            findings=findings,
            conclusion="Overall, the market remains attractive provided deployment constraints are monitored.",
            final_status="completed",
        )


class FakeSearchService:
    async def search(self, *, task: PlanTask, research_request: ResearchRequest, limit: int) -> list[SearchResult]:
        dataset = {
            "AI infrastructure market demand drivers 2025": [
                SearchResult(
                    title="Demand Drivers Overview",
                    url="https://example.com/market-drivers?utm_source=newsletter",
                    canonical_url="https://example.com/market-drivers",
                    provider=SearchProvider.NONE,
                    snippet="Demand for AI compute and data-center upgrades is rising.",
                    metadata={
                        "content": "AI compute spending is rising quickly because model training and inference demand more infrastructure.",
                    },
                ),
                SearchResult(
                    title="Vendor Landscape Snapshot",
                    url="https://example.com/vendor-landscape",
                    canonical_url="https://example.com/vendor-landscape",
                    provider=SearchProvider.NONE,
                    snippet="Leading vendors are expanding capacity.",
                    metadata={
                        "content": "Leading AI infrastructure vendors are expanding capacity and competing on performance and availability.",
                    },
                ),
            ],
            "AI infrastructure vendor competition 2025": [
                SearchResult(
                    title="Vendor Landscape Snapshot Duplicate",
                    url="https://example.com/vendor-landscape?ref=duplicate",
                    canonical_url="https://example.com/vendor-landscape",
                    provider=SearchProvider.NONE,
                    snippet="Duplicate URL to verify canonical dedupe.",
                    metadata={
                        "content": "Leading AI infrastructure vendors are expanding capacity and competing on performance and availability.",
                    },
                ),
                SearchResult(
                    title="Competitive Moves",
                    url="https://example.com/competitive-moves",
                    canonical_url="https://example.com/competitive-moves",
                    provider=SearchProvider.NONE,
                    snippet="Strategic partnerships are accelerating deployments.",
                    metadata={
                        "content": "Strategic partnerships and accelerator launches are intensifying AI infrastructure competition.",
                    },
                ),
            ],
            "AI infrastructure supply chain deployment risks 2025": [
                SearchResult(
                    title="Operational Risks",
                    url="https://example.com/operational-risks#overview",
                    canonical_url="https://example.com/operational-risks",
                    provider=SearchProvider.NONE,
                    snippet="Supply-chain and power constraints remain important risks.",
                    metadata={
                        "content": "Supply-chain bottlenecks, power availability, and deployment delays remain key operational risks for AI infrastructure projects.",
                    },
                )
            ],
        }
        return dataset.get(task.search_query, [])[:limit]


class FakeExtractor:
    async def extract(self, *, source: SourceRecord, task: PlanTask, research_request: ResearchRequest) -> ExtractionResult:
        content = source.metadata.get("content", "")
        if not content:
            return ExtractionResult(evidence=[], notes=[])
        claim = content.split(".")[0].strip()
        evidence = EvidenceRecord(
            evidence_id=stable_hash(f"{source.source_id}:{task.task_id}:{claim}", prefix="evi_"),
            source_id=source.source_id,
            claim=claim,
            excerpt=content,
            rationale=f"Matched fake content for task {task.task_id}.",
            confidence=0.82,
            supports_task_id=task.task_id,
        )
        return ExtractionResult(
            evidence=[evidence],
            notes=[f"Fake extractor produced evidence for {canonicalize_url(source.url)}."],
        )



class FakeTriageService:
    async def triage(self, *, sources: list[SourceRecord], plan_tasks: list[PlanTask], request: Any) -> list[TriageDecision]:
        decisions = []
        for source in sources:
            decisions.append(
                TriageDecision(
                    source_id=source.source_id,
                    decision="included",
                    relevance_score=0.75,
                    reliability_score=0.70,
                    authority_tier="PRIMARY",
                    justification="Fake triage: source accepted.",
                )
            )
        return decisions


def build_fake_bundle() -> ResearchServiceBundle:
    return ResearchServiceBundle(
        llm=FakeLLMService(),
        search=FakeSearchService(),
        extractor=FakeExtractor(),
        report_formatter=ReportFormatter(),
        source_triage=FakeTriageService(),
    )



def build_test_settings(sqlite_url: str) -> AppSettings:
    report_output_dir = ".local/reports"
    sqlite_prefix = "sqlite+aiosqlite:///"
    if sqlite_url.startswith(sqlite_prefix):
        sqlite_path = Path(sqlite_url[len(sqlite_prefix):])
        report_output_dir = str(sqlite_path.parent / "reports")

    return AppSettings(
        model_provider=ModelProvider.OPENAI,
        model_name="gpt-4.1-mini",
        sqlite_db_url=sqlite_url,
        report_output_dir=report_output_dir,
        default_search_provider=SearchProvider.NONE,
        max_iterations=4,
    )
