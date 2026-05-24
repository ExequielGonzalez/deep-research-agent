from deep_research_agent.domain.models import SourceRecord, SynthesisSection, SynthesizedReport, SearchProvider
from deep_research_agent.services.reporting import ReportFormatter



def test_report_formatter_assigns_stable_citations_from_sorted_sources():
    formatter = ReportFormatter()
    report = SynthesizedReport(
        title="Test Report",
        executive_summary="Summary",
        methodology="Method",
        findings=[
            SynthesisSection(
                title="Finding",
                body_markdown="Important point.",
                source_ids=["src_b", "src_a"],
            )
        ],
        final_status="completed",
    )
    sources = [
        SourceRecord(
            source_id="src_b",
            title="Beta",
            url="https://example.com/beta?utm_source=x",
            canonical_url="https://example.com/beta",
            provider=SearchProvider.NONE,
        ),
        SourceRecord(
            source_id="src_a",
            title="Alpha",
            url="https://example.com/alpha",
            canonical_url="https://example.com/alpha",
            provider=SearchProvider.NONE,
        ),
    ]

    formatted = formatter.format(report=report, sources=sources)

    assert [citation.marker for citation in formatted.citations] == ["[1]", "[2]"]
    assert formatted.citations[0].source_id == "src_a"
    assert "Important point. [2] [1]" in formatted.markdown


def test_report_formatter_appends_only_missing_citations():
    formatter = ReportFormatter()
    report = SynthesizedReport(
        title="Test Report",
        executive_summary="Summary",
        methodology="Method",
        findings=[
            SynthesisSection(
                title="Finding",
                body_markdown="Important point. [2]",
                source_ids=["src_b", "src_a"],
            )
        ],
        final_status="completed",
    )
    sources = [
        SourceRecord(
            source_id="src_b",
            title="Beta",
            url="https://example.com/beta?utm_source=x",
            canonical_url="https://example.com/beta",
            provider=SearchProvider.NONE,
        ),
        SourceRecord(
            source_id="src_a",
            title="Alpha",
            url="https://example.com/alpha",
            canonical_url="https://example.com/alpha",
            provider=SearchProvider.NONE,
        ),
    ]

    formatted = formatter.format(report=report, sources=sources)

    assert "Important point. [2] [1]" in formatted.markdown
    assert "Important point. [2] [2] [1]" not in formatted.markdown
