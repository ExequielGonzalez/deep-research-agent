from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from urllib import parse

from deep_research_agent.domain.models import CitationRecord, ReportSection, SectionStatus, SourceRecord, SynthesizedReport
from deep_research_agent.services.search import stable_hash


@dataclass(slots=True)
class FormattedReport:
    title: str
    markdown: str
    sections: list[ReportSection]
    citations: list[CitationRecord]
    final_status: str
    methodology: str = ""
    confidence_score: float = 0.0
    evidence_count: int = 0
    iteration_count: int = 0


class ReportFormatter:
    def format(
        self,
        *,
        report: SynthesizedReport,
        sources: Sequence[SourceRecord],
        confidence_score: float = 0.0,
        evidence_count: int = 0,
        iteration_count: int = 0,
    ) -> FormattedReport:
        source_map = {source.source_id: source for source in sources}
        ordered_sources = sorted(
            source_map.values(),
            key=lambda source: (source.canonical_url or source.url, source.title.lower(), source.source_id),
        )
        # Assign citation markers and distinguish PRIMARY vs CONTEXTUAL
        citation_map = {source.source_id: f"[{index}]" for index, source in enumerate(ordered_sources, start=1)}
        citations = [
            CitationRecord(
                marker=citation_map[source.source_id],
                source_id=source.source_id,
                title=source.title,
                url=source.url,
                canonical_url=source.canonical_url,
            )
            for source in ordered_sources
        ]

        sections: list[ReportSection] = [
            ReportSection(
                section_id=stable_hash("section:Executive Summary", prefix="section_"),
                title="Executive Summary",
                status=SectionStatus.COMPLETE,
                content_markdown=self._format_executive_summary(report),
                source_ids=[],
                summary_points=self._extract_summary_points(report.executive_summary),
            ),
            ReportSection(
                section_id=stable_hash("section:Methodology", prefix="section_"),
                title="Methodology",
                status=SectionStatus.COMPLETE,
                content_markdown=self._format_methodology(report, sources),
                source_ids=[],
                summary_points=["Evidence-based synthesis with citation traceability."],
            ),
        ]

        for finding in report.findings:
            markers = [citation_map[source_id] for source_id in finding.source_ids if source_id in citation_map]
            content = self._enrich_finding_content(finding, markers, source_map)
            sections.append(
                ReportSection(
                    section_id=stable_hash(f"section:{finding.title}", prefix="section_"),
                    title=finding.title,
                    status=SectionStatus.COMPLETE,
                    content_markdown=content,
                    citations=markers,
                    source_ids=[source_id for source_id in finding.source_ids if source_id in citation_map],
                    summary_points=finding.summary_points or self._extract_summary_points(finding.body_markdown),
                )
            )

        if report.conclusion:
            sections.append(
                ReportSection(
                    section_id=stable_hash("section:Conclusion", prefix="section_"),
                    title="Conclusion",
                    status=SectionStatus.COMPLETE,
                    content_markdown=report.conclusion.strip(),
                    source_ids=[],
                    summary_points=self._extract_summary_points(report.conclusion),
                )
            )

        body_lines = self._build_report_body(report, sections, ordered_sources, source_map, citation_map)

        return FormattedReport(
            title=report.title,
            markdown="\n".join(body_lines).strip() + "\n",
            sections=sections,
            citations=citations,
            final_status=report.final_status,
            methodology=report.methodology,
            confidence_score=confidence_score,
            evidence_count=evidence_count,
            iteration_count=iteration_count,
        )

    def _format_executive_summary(self, report: SynthesizedReport) -> str:
        summary = report.executive_summary.strip()
        stance = f"**Research Stance:** This report presents findings based on evidence gathered through systematic source evaluation and multi-pass synthesis.\n\n"
        return stance + summary

    def _format_methodology(self, report: SynthesizedReport, sources: Sequence[SourceRecord]) -> str:
        primary_count = sum(1 for s in sources if getattr(s, "authority_tier", "CONTEXTUAL") == "PRIMARY")
        contextual_count = sum(1 for s in sources if getattr(s, "authority_tier", "CONTEXTUAL") == "CONTEXTUAL")
        excluded_count = sum(1 for s in sources if getattr(s, "authority_tier", "CONTEXTUAL") == "EXCLUDED")
        lines = [
            report.methodology.strip(),
            "",
            f"**Source Distribution:** {primary_count} PRIMARY, {contextual_count} CONTEXTUAL, {excluded_count} EXCLUDED sources evaluated.",
            "",
            "**Evaluation Criteria:** Each source was assessed for relevance to research tasks and reliability based on domain authority (educational, governmental, or commercial).",
            "",
            "**Limitations:** Evidence is limited to sources accessible at research time. Claims are traceable to specific source excerpts with citation markers.",
        ]
        return "\n".join(lines)

    def _enrich_finding_content(self, finding: SynthesisSection, markers: list[str], source_map: dict) -> str:
        content = finding.body_markdown.strip()
        # If claim-level citations exist, format them
        if finding.claim_citations:
            for citation in finding.claim_citations:
                claim = citation.get("claim", "")
                cited_ids = citation.get("source_ids", [])
                for sid in cited_ids:
                    if sid in source_map:
                        marker = f"[{list(source_map.keys()).index(sid) + 1}]"
                        if marker not in content:
                            content += f" {marker}"
        # Append missing citation markers
        missing_markers = [m for m in markers if m not in content]
        if missing_markers:
            content = f"{content} {' '.join(missing_markers)}".strip()
        return content

    def _extract_summary_points(self, text: str, *, max_points: int = 5) -> list[str]:
        if not text:
            return []
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        points = []
        for s in sentences[:max_points]:
            if len(s) > 20:
                points.append(s if s.endswith(".") else f"{s}.")
            if len(points) >= max_points:
                break
        return points if points else [text[:200] + "..." if len(text) > 200 else text]

    def _build_report_body(
        self,
        report: SynthesizedReport,
        sections: list[ReportSection],
        ordered_sources: list[SourceRecord],
        source_map: dict,
        citation_map: dict[str, str] | None = None,
    ) -> list[str]:
        if citation_map is None:
            citation_map = {}
        body_lines = [f"# {report.title}", ""]
        body_lines.extend([
            f"**Final Status:** {report.final_status}",
            f"**Evidence Base:** {len(ordered_sources)} sources evaluated",
            "",
        ])
        for section in sections:
            body_lines.extend([f"## {section.title}", "", section.content_markdown, ""])
            if section.summary_points:
                body_lines.extend(["### Key Points", "", *(f"- {point}" for point in section.summary_points), ""])
        body_lines.extend(["## Sources", ""])
        # Group by tier
        primary_sources = [s for s in ordered_sources if getattr(s, "authority_tier", "CONTEXTUAL") == "PRIMARY"]
        contextual_sources = [s for s in ordered_sources if getattr(s, "authority_tier", "CONTEXTUAL") == "CONTEXTUAL"]
        excluded_sources = [s for s in ordered_sources if getattr(s, "authority_tier", "CONTEXTUAL") == "EXCLUDED"]

        if primary_sources:
            body_lines.append("### PRIMARY Sources")
            for src in primary_sources:
                marker = citation_map.get(src.source_id, "")
                try:
                    domain = parse.urlparse(src.url).netloc.lower().removeprefix("www.")
                except Exception:
                    domain = src.url
                body_lines.append(f"- {marker} [{src.title}]({src.url}) — *{domain}* (PRIMARY)")
            body_lines.append("")

        if contextual_sources:
            body_lines.append("### CONTEXTUAL Sources")
            for src in contextual_sources:
                marker = citation_map.get(src.source_id, "")
                try:
                    domain = parse.urlparse(src.url).netloc.lower().removeprefix("www.")
                except Exception:
                    domain = src.url
                body_lines.append(f"- {marker} [{src.title}]({src.url}) — *{domain}* (CONTEXTUAL)")
            body_lines.append("")

        if excluded_sources:
            body_lines.append("### EXCLUDED Sources")
            for src in excluded_sources:
                body_lines.append(f"- [{src.title}]({src.url}) — Excluded: {getattr(src, 'selection_justification', 'Low quality')}")
            body_lines.append("")

        body_lines.append("")
        return body_lines
