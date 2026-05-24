from __future__ import annotations

"""LangGraph runtime for the deep research MVP."""

from dataclasses import dataclass
from typing import Any, Iterable

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from deep_research_agent.domain.models import (
    HumanDecision,
    HumanDecisionType,
    HumanReviewKind,
    HumanReviewRequest,
    PlanTask,
    ReflectionOutput,
    ResearchPlan,
    ResearchRequest,
    ReportSection,
    RunStatus,
    SearchResult,
    SectionStatus,
    TaskStatus,
)
from deep_research_agent.domain.state import ResearchGraphState
from deep_research_agent.services import ResearchServiceBundle
from deep_research_agent.services.search import canonicalize_url, stable_hash
from deep_research_agent.settings import AppSettings


@dataclass(slots=True)
class ResearchGraphNodes:
    services: ResearchServiceBundle
    settings: AppSettings

    async def plan_research(self, state: ResearchGraphState) -> dict[str, Any]:
        request = state["request"]
        plan = await self.services.llm.plan_research(
            request=request,
            prior_tasks=state.get("plan_tasks", []),
            human_decisions=state.get("human_decisions", []),
        )
        normalized_plan = self._normalize_plan(plan)
        return {
            "status": RunStatus.RUNNING,
            "plan_title": normalized_plan.title,
            "plan_summary": normalized_plan.plan_summary,
            "plan_tasks": normalized_plan.tasks,
            "report_sections": self._planned_sections(normalized_plan.tasks),
            "notes": [f"Planned {len(normalized_plan.tasks)} research task(s) for '{normalized_plan.title}'."],
            "last_error": None,
        }

    async def prepare_plan_review(self, state: ResearchGraphState) -> dict[str, Any]:
        review = HumanReviewRequest(
            review_kind=HumanReviewKind.PLAN_APPROVAL,
            prompt="Review and approve the research plan before retrieval starts.",
            allowed_decisions=[
                HumanDecisionType.APPROVE,
                HumanDecisionType.CLARIFY,
                HumanDecisionType.STOP,
            ],
            context={
                "title": state.get("plan_title"),
                "plan_summary": state.get("plan_summary"),
                "tasks": [task.model_dump(mode="json") for task in state.get("plan_tasks", [])],
                "max_iterations": state["max_iterations"],
            },
        )
        return {
            "status": RunStatus.INTERRUPTED,
            "pending_human_input": review,
            "notes": ["Awaiting human plan approval."],
        }

    async def await_plan_review(self, state: ResearchGraphState) -> dict[str, Any]:
        review_request = state["pending_human_input"]
        resume_payload = interrupt(review_request.model_dump(mode="json"))
        decision = HumanDecision.from_resume_payload(resume_payload)
        return {
            "status": RunStatus.RUNNING,
            "human_decisions": [decision],
            "pending_human_input": None,
            "notes": [f"Received plan review decision: {decision.decision_type.value}."],
        }

    async def apply_plan_feedback(self, state: ResearchGraphState) -> dict[str, Any]:
        request = state["request"]
        last_decision = state["human_decisions"][-1]
        updated_constraints = [*request.constraints]
        if last_decision.summary.strip():
            updated_constraints.append(f"Human clarification: {last_decision.summary.strip()}")
        payload_constraints = last_decision.payload.get("constraints", [])
        if isinstance(payload_constraints, list):
            updated_constraints.extend(str(item) for item in payload_constraints)
        updated_request = request.model_copy(
            update={
                "objective": last_decision.payload.get("objective", request.objective),
                "audience": last_decision.payload.get("audience", request.audience),
                "constraints": updated_constraints,
            }
        )
        return {
            "request": updated_request,
            "notes": ["Applied human clarification and re-planning the research request."],
        }

    async def begin_iteration(self, state: ResearchGraphState) -> dict[str, Any]:
        next_iteration = state["iteration_count"] + 1
        return {
            "status": RunStatus.RUNNING,
            "iteration_count": next_iteration,
            "notes": [f"Starting research iteration {next_iteration} of {state['max_iterations']}."],
        }

    async def search_sources(self, state: ResearchGraphState) -> dict[str, Any]:
        plan_tasks = state.get("plan_tasks", [])
        task_updates: list[PlanTask] = []
        new_sources = []
        search_notes: list[str] = []
        active_tasks = self._active_tasks(plan_tasks)
        if not active_tasks:
            return {"notes": ["No active research tasks require additional search."]}

        for task in active_tasks:
            results = await self.services.search.search(
                task=task,
                research_request=state["request"],
                limit=self.settings.max_sources_per_task,
            )
            if not results:
                task_updates.append(task.model_copy(update={"status": TaskStatus.BLOCKED}))
                search_notes.append(f"No search hits found for task {task.task_id}.")
                continue

            task_updates.append(task.model_copy(update={"status": TaskStatus.IN_PROGRESS}))
            for result in results:
                canonical_url = result.canonical_url or canonicalize_url(result.url)
                new_sources.append(
                    self._source_from_result(
                        task=task,
                        result=result.model_copy(update={"canonical_url": canonical_url}),
                    )
                )
            search_notes.append(f"Retrieved {len(results)} source candidate(s) for task {task.task_id}.")

        return {"plan_tasks": task_updates, "sources": new_sources, "notes": search_notes}

    async def extract_evidence(self, state: ResearchGraphState) -> dict[str, Any]:
        evidence = []
        notes: list[str] = []
        task_updates: list[PlanTask] = []
        existing_evidence_ids = {item.evidence_id for item in state.get("evidence", [])}
        sources = state.get("sources", [])

        for task in self._active_tasks(state.get("plan_tasks", [])):
            task_sources = [source for source in sources if task.task_id in source.task_ids]
            extracted_for_task = 0
            for source in sorted(task_sources, key=lambda item: (item.canonical_url or item.url, item.source_id)):
                extraction_result = await self.services.extractor.extract(
                    source=source,
                    task=task,
                    research_request=state["request"],
                )
                notes.extend(extraction_result.notes)
                for item in extraction_result.evidence:
                    if item.evidence_id in existing_evidence_ids:
                        continue
                    evidence.append(item)
                    existing_evidence_ids.add(item.evidence_id)
                    extracted_for_task += 1
            if extracted_for_task == 0 and task.status is TaskStatus.BLOCKED:
                task_updates.append(task)
            elif extracted_for_task == 0:
                task_updates.append(task.model_copy(update={"status": TaskStatus.BLOCKED}))
            else:
                task_updates.append(task.model_copy(update={"status": TaskStatus.IN_PROGRESS}))

        return {"evidence": evidence, "plan_tasks": task_updates, "notes": notes}

    async def reflect_research(self, state: ResearchGraphState) -> dict[str, Any]:
        reflection = await self.services.llm.reflect_research(
            request=state["request"],
            plan_tasks=state.get("plan_tasks", []),
            sources=state.get("sources", []),
            evidence_summary=self._evidence_summary(state),
            iteration_count=state["iteration_count"],
            max_iterations=state["max_iterations"],
        )
        task_updates = self._task_updates_from_reflection(
            plan_tasks=state.get("plan_tasks", []),
            reflection=reflection,
            evidence_summary=self._evidence_summary(state),
        )
        follow_up_tasks = self._follow_up_tasks(reflection)
        notes = [reflection.summary]
        if reflection.knowledge_gaps:
            notes.extend(f"Knowledge gap: {gap}" for gap in reflection.knowledge_gaps)
        if follow_up_tasks:
            notes.append(f"Added {len(follow_up_tasks)} follow-up task(s) from reflection.")
        return {
            "reflections": [reflection],
            "plan_tasks": [*task_updates, *follow_up_tasks],
            "notes": notes,
        }

    async def prepare_sufficiency_review(self, state: ResearchGraphState) -> dict[str, Any]:
        reflection = state["reflections"][-1]
        guard_reached = state["iteration_count"] >= state["max_iterations"] and reflection.needs_more_research
        prompt = "Review the research sufficiency before final synthesis."
        if guard_reached:
            prompt = "The iteration guard was reached. Review whether to synthesize with current evidence or stop."
        review = HumanReviewRequest(
            review_kind=HumanReviewKind.SUFFICIENCY_REVIEW,
            prompt=prompt,
            allowed_decisions=[HumanDecisionType.APPROVE, HumanDecisionType.CONTINUE, HumanDecisionType.STOP],
            context={
                "plan_title": state.get("plan_title"),
                "plan_summary": state.get("plan_summary"),
                "iteration_count": state["iteration_count"],
                "max_iterations": state["max_iterations"],
                "reflection": reflection.model_dump(mode="json"),
                "evidence_summary": self._evidence_summary(state),
            },
        )
        return {
            "status": RunStatus.INTERRUPTED,
            "pending_human_input": review,
            "notes": ["Awaiting human sufficiency review."],
        }

    async def await_sufficiency_review(self, state: ResearchGraphState) -> dict[str, Any]:
        review_request = state["pending_human_input"]
        resume_payload = interrupt(review_request.model_dump(mode="json"))
        decision = HumanDecision.from_resume_payload(resume_payload)
        return {
            "status": RunStatus.RUNNING,
            "human_decisions": [decision],
            "pending_human_input": None,
            "notes": [f"Received sufficiency review decision: {decision.decision_type.value}."],
        }

    async def apply_sufficiency_feedback(self, state: ResearchGraphState) -> dict[str, Any]:
        decision = state["human_decisions"][-1]
        follow_up_tasks: list[PlanTask] = []
        if decision.summary.strip():
            follow_up_tasks.append(
                PlanTask(
                    task_id=stable_hash(f"human:{decision.summary.strip()}", prefix="task_"),
                    title="Human requested follow-up",
                    description=decision.summary.strip(),
                    search_query=decision.summary.strip(),
                    section_title="Additional Research",
                    priority=2,
                    success_criteria=["Address the human review feedback."],
                )
            )
        payload_queries = decision.payload.get("queries", [])
        if isinstance(payload_queries, list):
            for query in payload_queries:
                if not str(query).strip():
                    continue
                follow_up_tasks.append(
                    PlanTask(
                        task_id=stable_hash(f"human:{query}", prefix="task_"),
                        title=str(query).strip(),
                        description=f"Human requested additional research for: {query}",
                        search_query=str(query).strip(),
                        section_title="Additional Research",
                        priority=2,
                        success_criteria=["Resolve the explicitly requested follow-up question."],
                    )
                )
        return {
            "plan_tasks": follow_up_tasks,
            "notes": ["Applied sufficiency-review feedback and continuing the research loop."],
        }

    async def synthesize_report(self, state: ResearchGraphState) -> dict[str, Any]:
        synthesized = await self.services.llm.synthesize_report(
            request=state["request"],
            plan_title=state.get("plan_title"),
            plan_summary=state.get("plan_summary"),
            plan_tasks=state.get("plan_tasks", []),
            sources=state.get("sources", []),
            evidence_summary=self._evidence_summary(state),
            reflections=state.get("reflections", []),
        )
        formatted = self.services.report_formatter.format(report=synthesized, sources=state.get("sources", []))
        return {
            "status": RunStatus.COMPLETED,
            "report_sections": formatted.sections,
            "citation_records": formatted.citations,
            "final_report_title": formatted.title,
            "final_report_markdown": formatted.markdown,
            "final_report_status": formatted.final_status,
            "pending_human_input": None,
            "notes": [f"Synthesized final report '{formatted.title}'."],
        }

    async def cancel_run(self, state: ResearchGraphState) -> dict[str, Any]:
        return {
            "status": RunStatus.CANCELLED,
            "pending_human_input": None,
            "notes": ["Run cancelled by human review."],
        }

    def route_after_plan_review(self, state: ResearchGraphState) -> str:
        last_decision = state["human_decisions"][-1]
        if last_decision.decision_type is HumanDecisionType.STOP:
            return "cancel_run"
        if last_decision.decision_type is HumanDecisionType.CLARIFY:
            return "apply_plan_feedback"
        return "begin_iteration"

    def route_after_reflection(self, state: ResearchGraphState) -> str:
        reflection = state["reflections"][-1]
        if reflection.needs_more_research and state["iteration_count"] < state["max_iterations"] and not reflection.needs_human_input:
            return "begin_iteration"
        return "prepare_sufficiency_review"

    def route_after_sufficiency_review(self, state: ResearchGraphState) -> str:
        last_decision = state["human_decisions"][-1]
        if last_decision.decision_type is HumanDecisionType.STOP:
            return "cancel_run"
        if last_decision.decision_type is HumanDecisionType.APPROVE:
            return "synthesize_report"
        if state["iteration_count"] >= state["max_iterations"]:
            return "synthesize_report"
        return "apply_sufficiency_feedback"

    def _normalize_plan(self, plan: ResearchPlan) -> ResearchPlan:
        normalized_tasks: list[PlanTask] = []
        for index, task in enumerate(plan.tasks, start=1):
            section_title = task.section_title or task.title
            task_key = f"{plan.normalized_query}:{index}:{task.search_query}:{section_title}"
            normalized_tasks.append(
                task.model_copy(
                    update={
                        "task_id": stable_hash(task_key, prefix="task_"),
                        "search_query": task.search_query.strip() or task.title,
                        "section_title": section_title,
                        "status": TaskStatus.TODO,
                    }
                )
            )
        return plan.model_copy(update={"tasks": normalized_tasks})

    def _planned_sections(self, tasks: Iterable[PlanTask]) -> list[ReportSection]:
        seen_titles: set[str] = set()
        sections: list[ReportSection] = []
        for task in tasks:
            section_title = task.section_title or task.title
            if section_title in seen_titles:
                continue
            seen_titles.add(section_title)
            sections.append(
                ReportSection(
                    section_id=stable_hash(f"section:{section_title}", prefix="section_"),
                    title=section_title,
                    status=SectionStatus.PLANNED,
                )
            )
        return sections

    def _active_tasks(self, tasks: list[PlanTask]) -> list[PlanTask]:
        return sorted(
            [task for task in tasks if task.status in {TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED}],
            key=lambda item: (item.priority, item.task_id),
        )

    def _source_from_result(self, *, task: PlanTask, result: SearchResult):
        canonical_url = result.canonical_url or canonicalize_url(result.url)
        return state_source_record(
            title=result.title,
            url=result.url,
            canonical_url=canonical_url,
            provider=result.provider,
            snippet=result.snippet,
            published_at=result.published_at,
            metadata=result.metadata,
            task_ids=[task.task_id],
        )

    def _evidence_summary(self, state: ResearchGraphState) -> list[dict[str, Any]]:
        source_map = {source.source_id: source for source in state.get("sources", [])}
        summary: list[dict[str, Any]] = []
        for item in sorted(state.get("evidence", []), key=lambda evidence: (evidence.supports_task_id or "", evidence.source_id, evidence.evidence_id)):
            source = source_map.get(item.source_id)
            summary.append(
                {
                    "evidence_id": item.evidence_id,
                    "source_id": item.source_id,
                    "source_title": source.title if source else None,
                    "supports_task_id": item.supports_task_id,
                    "claim": item.claim,
                    "excerpt": item.excerpt,
                    "confidence": item.confidence,
                }
            )
        return summary

    def _task_updates_from_reflection(
        self,
        *,
        plan_tasks: list[PlanTask],
        reflection: ReflectionOutput,
        evidence_summary: list[dict[str, Any]],
    ) -> list[PlanTask]:
        evidence_by_task: dict[str, int] = {}
        for item in evidence_summary:
            task_id = item.get("supports_task_id")
            if task_id:
                evidence_by_task[task_id] = evidence_by_task.get(task_id, 0) + 1

        follow_up_parents = {suggestion.parent_task_id for suggestion in reflection.follow_up_tasks if suggestion.parent_task_id}
        updates: list[PlanTask] = []
        for task in plan_tasks:
            if task.task_id in reflection.covered_task_ids:
                updates.append(task.model_copy(update={"status": TaskStatus.DONE}))
                continue
            if task.task_id in follow_up_parents:
                updates.append(task.model_copy(update={"status": TaskStatus.IN_PROGRESS}))
                continue
            if evidence_by_task.get(task.task_id):
                updates.append(task.model_copy(update={"status": TaskStatus.IN_PROGRESS}))
                continue
            updates.append(task)
        return updates

    def _follow_up_tasks(self, reflection: ReflectionOutput) -> list[PlanTask]:
        follow_up_tasks: list[PlanTask] = []
        for suggestion in reflection.follow_up_tasks:
            task_key = f"{suggestion.parent_task_id or 'root'}:{suggestion.search_query}:{suggestion.title}"
            follow_up_tasks.append(
                PlanTask(
                    task_id=stable_hash(task_key, prefix="task_"),
                    title=suggestion.title,
                    description=suggestion.description,
                    search_query=suggestion.search_query,
                    section_title=suggestion.section_title or suggestion.title,
                    priority=suggestion.priority,
                    parent_task_id=suggestion.parent_task_id,
                    success_criteria=suggestion.success_criteria,
                    status=TaskStatus.TODO,
                )
            )
        return follow_up_tasks


def state_source_record(**kwargs: Any):
    from deep_research_agent.domain.models import SourceRecord

    canonical_url = kwargs.get("canonical_url") or canonicalize_url(kwargs["url"])
    source_id = stable_hash(canonical_url, prefix="src_")
    source_kwargs = {**kwargs, "canonical_url": canonical_url}
    return SourceRecord(source_id=source_id, **source_kwargs)



def build_research_graph(*, checkpointer: Any, services: ResearchServiceBundle, settings: AppSettings):
    nodes = ResearchGraphNodes(services=services, settings=settings)
    builder = StateGraph(ResearchGraphState)
    builder.add_node("plan_research", nodes.plan_research)
    builder.add_node("prepare_plan_review", nodes.prepare_plan_review)
    builder.add_node("await_plan_review", nodes.await_plan_review)
    builder.add_node("apply_plan_feedback", nodes.apply_plan_feedback)
    builder.add_node("begin_iteration", nodes.begin_iteration)
    builder.add_node("search_sources", nodes.search_sources)
    builder.add_node("extract_evidence", nodes.extract_evidence)
    builder.add_node("reflect_research", nodes.reflect_research)
    builder.add_node("prepare_sufficiency_review", nodes.prepare_sufficiency_review)
    builder.add_node("await_sufficiency_review", nodes.await_sufficiency_review)
    builder.add_node("apply_sufficiency_feedback", nodes.apply_sufficiency_feedback)
    builder.add_node("synthesize_report", nodes.synthesize_report)
    builder.add_node("cancel_run", nodes.cancel_run)

    builder.add_edge(START, "plan_research")
    builder.add_edge("plan_research", "prepare_plan_review")
    builder.add_edge("prepare_plan_review", "await_plan_review")
    builder.add_conditional_edges(
        "await_plan_review",
        nodes.route_after_plan_review,
        {
            "cancel_run": "cancel_run",
            "apply_plan_feedback": "apply_plan_feedback",
            "begin_iteration": "begin_iteration",
        },
    )
    builder.add_edge("apply_plan_feedback", "plan_research")
    builder.add_edge("begin_iteration", "search_sources")
    builder.add_edge("search_sources", "extract_evidence")
    builder.add_edge("extract_evidence", "reflect_research")
    builder.add_conditional_edges(
        "reflect_research",
        nodes.route_after_reflection,
        {
            "begin_iteration": "begin_iteration",
            "prepare_sufficiency_review": "prepare_sufficiency_review",
        },
    )
    builder.add_edge("prepare_sufficiency_review", "await_sufficiency_review")
    builder.add_conditional_edges(
        "await_sufficiency_review",
        nodes.route_after_sufficiency_review,
        {
            "cancel_run": "cancel_run",
            "apply_sufficiency_feedback": "apply_sufficiency_feedback",
            "synthesize_report": "synthesize_report",
        },
    )
    builder.add_edge("apply_sufficiency_feedback", "begin_iteration")
    builder.add_edge("synthesize_report", END)
    builder.add_edge("cancel_run", END)
    return builder.compile(checkpointer=checkpointer)
