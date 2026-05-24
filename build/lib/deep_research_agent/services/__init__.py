from __future__ import annotations

from dataclasses import dataclass

from deep_research_agent.services.extraction import ContentExtractor
from deep_research_agent.services.llm import ProviderConfigurationError, ResearchLLMService, build_llm_service
from deep_research_agent.services.reporting import ReportFormatter
from deep_research_agent.services.search import SearchService, build_search_service
from deep_research_agent.settings import AppSettings


@dataclass(slots=True)
class ResearchServiceBundle:
    llm: ResearchLLMService
    search: SearchService
    extractor: ContentExtractor
    report_formatter: ReportFormatter



def build_service_bundle(settings: AppSettings) -> ResearchServiceBundle:
    return ResearchServiceBundle(
        llm=build_llm_service(settings),
        search=build_search_service(settings),
        extractor=ContentExtractor(settings),
        report_formatter=ReportFormatter(),
    )


__all__ = [
    "ProviderConfigurationError",
    "ResearchLLMService",
    "ResearchServiceBundle",
    "SearchService",
    "build_service_bundle",
]
