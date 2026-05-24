from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from deep_research_agent.domain.models import CitationRecord, ReportSection, SectionStatus, SourceRecord, SynthesizedReport
from deep_research_agent.services.search import stable_hash


@dataclass(slots=True)
class FormattedReport:
    title: str
    markdown: str
    sections: list[ReportSection]
    citations: list[CitationRecord]
    final_status: str


class ReportFormatter:
    def format(self, *, report: SynthesizedReport, sources: Sequence[SourceRecord]) -> FormattedReport:
        source_map = {source.source_id: source for source in sources}
        ordered_sources = sorted(
            source_map.values(),
            key=lambda source: (source.canonical_url or source.url, source.title.lower(), source.source_id),
        )
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
                content_markdown=report.executive_summary.strip(),
            ),
            ReportSection(
                section_id=stable_hash("section:Methodology", prefix="section_"),
                title="Methodology",
                status=SectionStatus.COMPLETE,
                content_markdown=report.methodology.strip(),
            ),
        ]

        for finding in report.findings:
            markers = [citation_map[source_id] for source_id in finding.source_ids if source_id in citation_map]
            content = finding.body_markdown.strip()
            missing_markers = [marker for marker in markers if marker not in content]
            if missing_markers:
                content = f"{content} {' '.join(missing_markers)}".strip()
            sections.append(
                ReportSection(
                    section_id=stable_hash(f"section:{finding.title}", prefix="section_"),
                    title=finding.title,
                    status=SectionStatus.COMPLETE,
                    content_markdown=content,
                    citations=markers,
                    source_ids=[source_id for source_id in finding.source_ids if source_id in citation_map],
                    summary_points=finding.summary_points,
                )
            )

        if report.conclusion:
            sections.append(
                ReportSection(
                    section_id=stable_hash("section:Conclusion", prefix="section_"),
                    title="Conclusion",
                    status=SectionStatus.COMPLETE,
                    content_markdown=report.conclusion.strip(),
                )
            )

        body_lines = [f"# {report.title}", "", f"**Final Status:** {report.final_status}", ""]
        for section in sections:
            body_lines.extend([f"## {section.title}", "", section.content_markdown, ""])
            if section.summary_points:
                body_lines.extend([*(f"- {point}" for point in section.summary_points), ""])
        body_lines.extend(["## Sources", ""])
        for citation in citations:
            body_lines.append(f"- {citation.marker} [{citation.title}]({citation.url})")
        body_lines.append("")

        return FormattedReport(
            title=report.title,
            markdown="\n".join(body_lines).strip() + "\n",
            sections=sections,
            citations=citations,
            final_status=report.final_status,
        )
