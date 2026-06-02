from __future__ import annotations

"""LangGraph runtime for the deep research MVP."""

from dataclasses import dataclass
from typing import Any, Iterable

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from deep_research_agent.domain.models import (
    EvidenceCluster,
    HumanDecision,
    HumanDecisionType,
    HumanReviewKind,
    HumanReviewRequest,
    PlanTask,
    QualityGateResult,
    ReflectionOutput,
    ResearchPlan,
    ResearchRequest,
    ReportSection,
    RunStatus,
    SearchResult,
    SectionStatus,
    TaskStatus,
    TriageDecision,
)
from deep_research_agent.domain.state import ResearchGraphState
from deep_research_agent.services import ResearchServiceBundle
from deep_research_agent.services.llm import _truncate_text
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
            plan_title=state.get("plan_title"),
            plan_summary=state.get("plan_summary"),
            coverage_matrix={},
            open_gaps=[],
            discarded_sources=[],
            conflicts=[],
            confidence_score=0.0,
            structured_options=[],
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

    async def triage_sources(self, state: ResearchGraphState) -> dict[str, Any]:
        if not self.services.source_triage:
            return {"notes": ["Source triage skipped — feature flag not enabled."]}

        sources = state.get("sources", [])
        plan_tasks = state.get("plan_tasks", [])
        request = state["request"]

        decisions = await self.services.source_triage.triage(
            sources=sources,
            plan_tasks=plan_tasks,
            request=request,
        )

        included_source_ids = {d.source_id for d in decisions if d.decision == "included"}
        excluded_source_ids = {d.source_id for d in decisions if d.decision == "excluded"}

        updated_sources = []
        for source in sources:
            if source.source_id in excluded_source_ids:
                decision = next((d for d in decisions if d.source_id == source.source_id), None)
                updated_sources.append(
                    source.model_copy(
                        update={
                            "relevance_score": decision.relevance_score if decision else 0.0,
                            "reliability_score": decision.reliability_score if decision else 0.0,
                            "authority_tier": "EXCLUDED",
                            "selection_justification": decision.justification if decision else "",
                        }
                    )
                )
            else:
                decision = next((d for d in decisions if d.source_id == source.source_id), None)
                updated_sources.append(
                    source.model_copy(
                        update={
                            "relevance_score": decision.relevance_score if decision else 0.0,
                            "reliability_score": decision.reliability_score if decision else 0.0,
                            "authority_tier": decision.authority_tier if decision else "CONTEXTUAL",
                            "selection_justification": decision.justification if decision else "",
                        }
                    )
                )

        excluded_count = len(excluded_source_ids)
        included_count = len(included_source_ids)
        notes = [f"Source triage: {included_count} included, {excluded_count} excluded."]

        return {
            "sources": updated_sources,
            "triage_decisions": decisions,
            "notes": notes,
        }

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
        evidence_summary = self._evidence_summary(state)
        coverage_metrics = self._compute_coverage_metrics(state, evidence_summary)
        reflection = await self.services.llm.reflect_research(
            request=state["request"],
            plan_tasks=state.get("plan_tasks", []),
            sources=state.get("sources", []),
            evidence_summary=evidence_summary,
            iteration_count=state["iteration_count"],
            max_iterations=state["max_iterations"],
        )
        task_updates = self._task_updates_from_reflection(
            plan_tasks=state.get("plan_tasks", []),
            reflection=reflection,
            evidence_summary=evidence_summary,
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
            "coverage_metrics": coverage_metrics,
        }

    async def prepare_sufficiency_review(self, state: ResearchGraphState) -> dict[str, Any]:
        reflection = state["reflections"][-1]
        guard_reached = state["iteration_count"] >= state["max_iterations"] and reflection.needs_more_research
        prompt = "Review the research sufficiency before final synthesis."
        if guard_reached:
            prompt = "The iteration guard was reached. Review whether to synthesize with current evidence or stop."

        coverage_matrix = state.get("coverage_metrics", {})
        task_coverage = coverage_matrix.get("task_coverage", {})
        open_gaps = []
        discarded_sources = []
        conflicts = []
        confidence_score = reflection.confidence

        for task_id, coverage in task_coverage.items():
            if coverage.get("evidence_count", 0) == 0:
                open_gaps.append(f"Task {task_id}: no evidence collected")
            if coverage.get("has_contradictions"):
                conflicts.append(f"Task {task_id}: conflicting evidence detected")

        triage_decisions = state.get("triage_decisions", [])
        for decision in triage_decisions:
            if decision.decision == "excluded":
                discarded_sources.append({
                    "source_id": decision.source_id,
                    "reason": decision.excluded_reason,
                    "relevance": decision.relevance_score,
                })

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
            plan_title=state.get("plan_title"),
            plan_summary=state.get("plan_summary"),
            coverage_matrix=coverage_matrix,
            open_gaps=open_gaps,
            discarded_sources=discarded_sources,
            conflicts=conflicts,
            confidence_score=confidence_score,
            structured_options=[
                {"type": "add_query", "label": "Add search query"},
                {"type": "extend_iterations", "label": "Extend iterations"},
                {"type": "change_source_policy", "label": "Change source policy"},
                {"type": "request_partial_replan", "label": "Request partial replan"},
            ],
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
        sources = list(state.get("sources", []))
        evidence = state.get("evidence", [])
        evidence_summary = self._evidence_summary(state)

        synthesized = await self.services.llm.synthesize_report(
            request=state["request"],
            plan_title=state.get("plan_title"),
            plan_summary=state.get("plan_summary"),
            plan_tasks=state.get("plan_tasks", []),
            sources=sources,
            evidence_summary=evidence_summary,
            reflections=state.get("reflections", []),
        )

        # Auto-assign source_ids to findings when the LLM leaves them empty.
        # Match by scanning body_markdown for title keywords, domain mentions, and URLs.
        synthesized = _auto_assign_sources(synthesized, sources)
        # Inject domain citations inline if the LLM did not include them.
        synthesized = _auto_inject_domain_citations(synthesized, sources)

        reflections = state.get("reflections", [])
        formatted = self.services.report_formatter.format(
            report=synthesized,
            sources=sources,
            confidence_score=reflections[-1].confidence if reflections else 0.0,
            evidence_count=len(evidence),
            iteration_count=state["iteration_count"],
        )
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

    async def quality_gate(self, state: ResearchGraphState) -> dict[str, Any]:
        settings = self.settings
        findings = []
        for section in state.get("report_sections", []):
            findings.append({
                "title": section.title,
                "source_ids": section.source_ids,
                "content": section.content_markdown,
            })

        evidence = state.get("evidence", [])
        reflections = state.get("reflections", [])
        last_reflection = reflections[-1] if reflections else None

        issues: list[str] = []
        min_evidence = settings.quality_gate_min_evidence
        has_min_evidence = len(evidence) >= min_evidence
        if not has_min_evidence:
            issues.append(f"Only {len(evidence)} evidence items (minimum: {min_evidence})")

        orphan_check = True
        for finding in findings:
            if not finding["source_ids"] and finding["content"].strip():
                orphan_check = False
                issues.append(f"Orphan section '{finding['title']}' has no source backing")
        max_orphans = settings.quality_gate_max_orphan_sections
        orphan_count = sum(1 for f in findings if not f["source_ids"] and f["content"].strip())
        if orphan_count > max_orphans:
            issues.append(f"{orphan_count} orphan sections exceed limit of {max_orphans}")

        conclusion_present = True
        if settings.quality_gate_require_conclusion:
            has_conclusion = any(s.title.lower() == "conclusion" for s in state.get("report_sections", []))
            if not has_conclusion:
                conclusion_present = False
                issues.append("Missing mandatory conclusion section")

        methodology_consistent = True
        if settings.quality_gate_require_methodology:
            has_methodology = any(s.title.lower() == "methodology" for s in state.get("report_sections", []))
            if not has_methodology:
                methodology_consistent = False
                issues.append("Missing mandatory methodology section")

        claim_traceability = True
        if settings.quality_gate_claim_traceability:
            for finding in findings:
                if finding["source_ids"]:
                    for sid in finding["source_ids"]:
                        if not any(f"[{i+1}]" in finding["content"] for i, _ in enumerate(state.get("citation_records", []))):
                            pass
                else:
                    if finding["content"].strip():
                        claim_traceability = False

        weak_evidence_limits = True
        if last_reflection:
            weak_count = sum(1 for e in evidence if e.confidence < settings.quality_gate_weak_evidence_limit)
            if weak_count > len(evidence) * 0.3:
                weak_evidence_limits = False
                issues.append(f"{weak_count} evidence items below weak confidence threshold")

        passed = all([
            has_min_evidence,
            orphan_count <= max_orphans,
            conclusion_present,
            methodology_consistent,
            claim_traceability,
            weak_evidence_limits,
        ])

        gate_result = QualityGateResult(
            min_usable_evidence=has_min_evidence,
            orphan_sections_check=orphan_count <= max_orphans,
            conclusion_present=conclusion_present,
            methodology_consistent=methodology_consistent,
            claim_traceability=claim_traceability,
            weak_evidence_limits=weak_evidence_limits,
            issues=issues,
            passed=passed,
        )

        notes = ["Quality gate passed."] if passed else [f"Quality gate failed: {'; '.join(issues)}"]
        return {
            "quality_gates": [gate_result],
            "notes": notes,
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
        if reflection.needs_human_input:
            return "prepare_sufficiency_review"
        if reflection.needs_more_research and state["iteration_count"] < state["max_iterations"]:
            coverage = state.get("coverage_metrics", {})
            coverage_pct = coverage.get("coverage_pct", 0)
            task_coverage = coverage.get("task_coverage", {})
            contradiction_count = sum(
                1 for tc in task_coverage.values() if tc.get("has_contradictions")
            )
            blockers = reflection.knowledge_gaps or []
            persistent_blockers = len(blockers) >= 2 or contradiction_count > 2
            if coverage_pct < 30 or persistent_blockers:
                return "prepare_sufficiency_review"
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
        from urllib import parse

        source_map = {source.source_id: source for source in state.get("sources", [])}
        summary: list[dict[str, Any]] = []
        for item in sorted(state.get("evidence", []), key=lambda evidence: (evidence.supports_task_id or "", evidence.source_id, evidence.evidence_id)):
            source = source_map.get(item.source_id)
            source_url = source.url if source else None
            try:
                source_domain = parse.urlparse(source_url).netloc.lower().removeprefix("www.") if source_url else None
            except Exception:
                source_domain = None
            summary.append(
                {
                    "evidence_id": item.evidence_id,
                    "source_id": item.source_id,
                    "source_title": _truncate_text(source.title if source else None),
                    "source_url": source_url,
                    "source_domain": source_domain,
                    "supports_task_id": item.supports_task_id,
                    "claim": _truncate_text(item.claim),
                    "excerpt": _truncate_text(item.excerpt),
                    "confidence": item.confidence,
                    "evidence_type": item.evidence_type,
                    "anchor_quotes": item.anchor_quotes,
                    "confidence_signal": item.confidence_signal,
                    "contradiction_flag": item.contradiction_flag,
                }
            )
        return summary

    def _compute_coverage_metrics(self, state: ResearchGraphState, evidence_summary: list[dict[str, Any]]) -> dict[str, Any]:
        tasks = state.get("plan_tasks", [])
        task_coverage: dict[str, Any] = {}
        for task in tasks:
            task_evidence = [e for e in evidence_summary if e.get("supports_task_id") == task.task_id]
            task_sources = list(set(e.get("source_id") for e in task_evidence))
            avg_confidence = sum(e.get("confidence", 0) for e in task_evidence) / max(len(task_evidence), 1)
            has_contradictions = any(e.get("contradiction_flag") for e in task_evidence)
            task_coverage[task.task_id] = {
                "evidence_count": len(task_evidence),
                "source_count": len(task_sources),
                "avg_confidence": round(avg_confidence, 3),
                "has_contradictions": has_contradictions,
                "primary_sources": [sid for sid in task_sources if any(
                    s.source_id == sid and s.authority_tier == "PRIMARY"
                    for s in state.get("sources", [])
                )],
            }
        total_evidence = len(evidence_summary)
        total_tasks = len(tasks)
        covered_tasks = sum(1 for v in task_coverage.values() if v["evidence_count"] > 0)
        return {
            "total_evidence": total_evidence,
            "total_tasks": total_tasks,
            "covered_tasks": covered_tasks,
            "coverage_pct": round(covered_tasks / max(total_tasks, 1) * 100, 1),
            "task_coverage": task_coverage,
        }

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


def _tokenize(value: str) -> set[str]:
    """Extract lowercase words of 3+ chars from a string."""
    import re

    return {word.lower() for word in re.findall(r"[A-Za-z0-9]{3,}", value)}


def _auto_assign_sources(report: SynthesizedReport, sources: list[SourceRecord]) -> SynthesizedReport:
    """When the LLM leaves source_ids empty, auto-assign by keyword overlap."""
    from urllib import parse

    if not sources:
        return report

    updated_findings: list = []
    source_index: list[tuple[str, set[str], str]] = []
    for src in sources:
        keywords = _tokenize(f"{src.title} {src.snippet or ''} {src.url}")
        try:
            domain = parse.urlparse(src.url).netloc.lower().removeprefix("www.")
        except Exception:
            domain = ""
        if domain:
            keywords.add(domain)
            # Also add the bare domain parts
            for part in domain.split("."):
                if len(part) >= 3:
                    keywords.add(part)
        source_index.append((src.source_id, keywords, domain))

    for finding in report.findings:
        if finding.source_ids:
            updated_findings.append(finding)
            continue

        body_tokens = _tokenize(finding.body_markdown)
        title_tokens = _tokenize(finding.title)
        all_tokens = body_tokens | title_tokens

        scored: list[tuple[str, float]] = []
        for src_id, src_keywords, domain in source_index:
            overlap = len(all_tokens & src_keywords)
            if overlap > 0:
                # Bonus if domain is mentioned in body
                domain_bonus = 2.0 if domain and (domain in finding.body_markdown.lower() or domain in finding.title.lower()) else 0.0
                scored.append((src_id, overlap + domain_bonus))

        scored.sort(key=lambda item: -item[1])
        matched_ids = [src_id for src_id, _ in scored[:5]]

        if matched_ids:
            updated_findings.append(finding.model_copy(update={"source_ids": matched_ids}))
        else:
            updated_findings.append(finding)

    return report.model_copy(update={"findings": updated_findings})


def _auto_inject_domain_citations(report: SynthesizedReport, sources: list[SourceRecord]) -> SynthesizedReport:
    """When a finding already has source_ids but body_markdown doesn't mention any domain, inject a citation block."""
    from urllib import parse

    source_map = {src.source_id: src for src in sources}
    updated_findings: list = []

    for finding in report.findings:
        body = finding.body_markdown.strip()
        sources_in_finding = [source_map[sid] for sid in finding.source_ids if sid in source_map]
        if not sources_in_finding:
            updated_findings.append(finding)
            continue

        mentioned_domains = []
        for src in sources_in_finding:
            try:
                domain = parse.urlparse(src.url).netloc.lower().removeprefix("www.")
            except Exception:
                domain = src.url.lower()
            mentioned_domains.append(domain)

        # Check if any domain is already mentioned in body
        any_mentioned = any(domain in body.lower() for domain in mentioned_domains)

        if not any_mentioned and mentioned_domains:
            citation_line = "\n\n*Sources: " + ", ".join(
                f"[{src.title}]({src.url})" for src in sources_in_finding
            ) + "*"
            body = body + citation_line

        updated_findings.append(finding.model_copy(update={"body_markdown": body}))

    return report.model_copy(update={"findings": updated_findings})


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
    builder.add_node("triage_sources", nodes.triage_sources)
    builder.add_node("extract_evidence", nodes.extract_evidence)
    builder.add_node("reflect_research", nodes.reflect_research)
    builder.add_node("prepare_sufficiency_review", nodes.prepare_sufficiency_review)
    builder.add_node("await_sufficiency_review", nodes.await_sufficiency_review)
    builder.add_node("apply_sufficiency_feedback", nodes.apply_sufficiency_feedback)
    builder.add_node("synthesize_report", nodes.synthesize_report)
    builder.add_node("quality_gate", nodes.quality_gate)
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
    builder.add_edge("search_sources", "triage_sources")
    builder.add_edge("triage_sources", "extract_evidence")
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
    builder.add_edge("synthesize_report", "quality_gate")
    builder.add_edge("quality_gate", END)
    builder.add_edge("cancel_run", END)
    return builder.compile(checkpointer=checkpointer)
