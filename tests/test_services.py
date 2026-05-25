import pytest

from deep_research_agent.domain.models import ModelProvider, ReflectionOutput, ResearchPlan, SearchProvider, SynthesizedReport
from deep_research_agent.services import ProviderConfigurationError, build_service_bundle
from deep_research_agent.services.search import build_search_service
from deep_research_agent.settings import AppSettings



def test_unsupported_model_provider_fails_explicitly():
    settings = AppSettings(model_provider=ModelProvider.ANTHROPIC, default_search_provider=SearchProvider.NONE)

    with pytest.raises(ProviderConfigurationError, match="not supported"):
        build_service_bundle(settings)



def test_firecrawl_search_provider_fails_explicitly():
    settings = AppSettings(model_provider=ModelProvider.OLLAMA, default_search_provider=SearchProvider.FIRECRAWL)

    with pytest.raises(ProviderConfigurationError, match="firecrawl"):
        build_search_service(settings)


def test_research_plan_accepts_local_model_style_priority_and_lists():
    plan = ResearchPlan.model_validate(
        {
            "title": "Llama.cpp viability",
            "normalized_query": "llama cpp viability",
            "plan_summary": "Check compatibility.",
            "tasks": [
                {
                    "title": "Check API compatibility",
                    "description": "Verify chat completions compatibility.",
                    "search_query": "llama.cpp openai compatible endpoint",
                    "section_title": "Compatibility",
                    "priority": "high",
                    "success_criteria": "Confirm chat completions support.",
                }
            ],
        }
    )

    assert plan.tasks[0].priority == 1
    assert plan.tasks[0].success_criteria == ["Confirm chat completions support."]


def test_synthesized_report_accepts_single_finding_and_string_source_ids():
    report = SynthesizedReport.model_validate(
        {
            "title": "Local inference report",
            "executive_summary": "Works with caveats.",
            "methodology": "Single pass.",
            "findings": {
                "title": "Compatibility",
                "body_markdown": "The endpoint responded.",
                "source_ids": "src_123",
                "summary_points": "One key finding.",
            },
            "final_status": "completed",
        }
    )

    assert len(report.findings) == 1
    assert report.findings[0].source_ids == ["src_123"]
    assert report.findings[0].summary_points == ["One key finding."]


def test_synthesized_report_accepts_local_model_style_findings():
    report = SynthesizedReport.model_validate(
        {
            "title": "Local inference report",
            "executive_summary": "Works with caveats.",
            "methodology": "Single pass.",
            "findings": [
                {
                    "section_title": "Compatibility",
                    "summary": "The endpoint responded.",
                    "key_evidence": ["Chat completions behaved as expected."],
                    "supporting_source_ids": ["src_123"],
                }
            ],
            "final_status": "completed",
        }
    )

    assert len(report.findings) == 1
    assert report.findings[0].title == "Compatibility"
    assert report.findings[0].body_markdown == "The endpoint responded.\n- Chat completions behaved as expected."
    assert report.findings[0].source_ids == ["src_123"]
    assert report.findings[0].summary_points == ["Chat completions behaved as expected."]


def test_synthesized_report_accepts_theme_alias_for_findings():
    report = SynthesizedReport.model_validate(
        {
            "title": "Cooking report",
            "executive_summary": "A concise executive summary.",
            "methodology": "A concise methodology.",
            "findings": [
                {
                    "theme": "Temperature Targets",
                    "body_markdown": "Use a thermometer.",
                    "source_ids": ["src_temp"],
                    "summary_points": ["Target 145F internal temperature."],
                }
            ],
            "final_status": "completed",
        }
    )

    assert len(report.findings) == 1
    assert report.findings[0].title == "Temperature Targets"
    assert report.findings[0].source_ids == ["src_temp"]


def test_reflection_output_accepts_local_model_style_gap_aliases_and_follow_up_tasks():
    reflection = ReflectionOutput.model_validate(
        {
            "summary": "Evidence is incomplete for the requested hardware setup.",
            "gaps": "Missing RTX Pro 4000-specific benchmarks.",
            "follow_up_tasks": [
                {
                    "description": "Obtener benchmarks reproducibles para doble RTX Pro 4000.",
                    "search_query": "llama.cpp vLLM RTX Pro 4000 dual GPU benchmark",
                    "status": "planned",
                    "task_id": "task_benchmarks",
                }
            ],
            "covered_task_ids": ["task_hardware"],
        }
    )

    assert reflection.knowledge_gaps == ["Missing RTX Pro 4000-specific benchmarks."]
    assert reflection.needs_more_research is True
    assert reflection.needs_human_input is False
    assert reflection.covered_task_ids == ["task_hardware"]
    assert len(reflection.follow_up_tasks) == 1
    assert reflection.follow_up_tasks[0].title.startswith("Obtener benchmarks reproducibles")
    assert reflection.follow_up_tasks[0].parent_task_id == "task_benchmarks"


def test_reflection_output_infers_human_input_when_research_is_sufficient():
    reflection = ReflectionOutput.model_validate(
        {
            "summary": "Evidence is sufficient for synthesis.",
            "needs_more_research": False,
        }
    )

    assert reflection.needs_more_research is False
    assert reflection.needs_human_input is True
