import json
from urllib import error

import pytest

from deep_research_agent.domain.models import ModelProvider, PlanTask, ReflectionOutput, ResearchPlan, ResearchRequest, SearchProvider, SourceRecord, SynthesizedReport
from deep_research_agent.services import ProviderConfigurationError, build_service_bundle
from deep_research_agent.services.extraction import ContentExtractor
from deep_research_agent.services.search import DuckDuckGoSearchService, SearXNGPoolSearchService, build_search_service
from deep_research_agent.settings import AppSettings, load_persisted_app_settings


class _FakeUrlOpenResponse:
    def __init__(self, body: str, *, headers: dict[str, str] | None = None):
        self._body = body.encode("utf-8")
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None



def test_unsupported_model_provider_fails_explicitly():
    settings = AppSettings(model_provider=ModelProvider.ANTHROPIC, default_search_provider=SearchProvider.NONE)

    with pytest.raises(ProviderConfigurationError, match="not supported"):
        build_service_bundle(settings)



def test_firecrawl_search_provider_fails_explicitly():
    settings = AppSettings(model_provider=ModelProvider.OLLAMA, default_search_provider=SearchProvider.FIRECRAWL)

    with pytest.raises(ProviderConfigurationError, match="firecrawl"):
        build_search_service(settings)


def test_tavily_search_provider_requires_api_key():
    settings = AppSettings(model_provider=ModelProvider.OPENAI, default_search_provider=SearchProvider.TAVILY)

    with pytest.raises(ProviderConfigurationError, match="DEEP_RESEARCH_TAVILY_API_KEY"):
        build_search_service(settings)


def test_serper_search_provider_requires_api_key():
    settings = AppSettings(model_provider=ModelProvider.OPENAI, default_search_provider=SearchProvider.SERPER)

    with pytest.raises(ProviderConfigurationError, match="DEEP_RESEARCH_SERPER_API_KEY"):
        build_search_service(settings)


def test_searxng_search_provider_builds_pool_service():
    settings = AppSettings(
        model_provider=ModelProvider.OPENAI,
        default_search_provider=SearchProvider.SEARXNG,
        searxng_selected_instances=["https://search.example/"],
    )

    service = build_search_service(settings)

    assert isinstance(service, SearXNGPoolSearchService)


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


@pytest.mark.asyncio
async def test_duckduckgo_search_transport_errors_fail_explicitly(monkeypatch):
    service = DuckDuckGoSearchService(user_agent="deep-research-agent-test")

    def raise_url_error(*args, **kwargs):
        raise error.URLError("network unavailable")

    monkeypatch.setattr("deep_research_agent.services.search.urllib_request.urlopen", raise_url_error)

    with pytest.raises(ProviderConfigurationError, match="DuckDuckGo search failed: network unavailable"):
        await service.search(
            task=PlanTask(
                title="Check market signals",
                description="Gather sources",
                search_query="ai infrastructure market 2026",
            ),
            research_request=ResearchRequest(query="Assess the AI infrastructure market"),
            limit=5,
        )


@pytest.mark.asyncio
async def test_duckduckgo_search_challenge_pages_fail_explicitly(monkeypatch):
    service = DuckDuckGoSearchService(user_agent="deep-research-agent-test")
    html = """
    <html>
        <body>
            <form id="challenge-form" action="//duckduckgo.com/anomaly.js?sv=html"></form>
            <div class="anomaly-modal__title">Unfortunately, bots use DuckDuckGo too.</div>
            <a href="https://duckduckgo.com/">here</a>
        </body>
    </html>
    """

    monkeypatch.setattr(
        "deep_research_agent.services.search.urllib_request.urlopen",
        lambda *args, **kwargs: _FakeUrlOpenResponse(html),
    )

    with pytest.raises(ProviderConfigurationError, match="human verification challenge"):
        await service.search(
            task=PlanTask(
                title="Check market signals",
                description="Gather sources",
                search_query="ai infrastructure market 2026",
            ),
            research_request=ResearchRequest(query="Assess the AI infrastructure market"),
            limit=5,
        )


@pytest.mark.asyncio
async def test_duckduckgo_search_ignores_internal_duckduckgo_links(monkeypatch):
    service = DuckDuckGoSearchService(user_agent="deep-research-agent-test")
    html = """
    <html>
        <body>
            <a href="https://duckduckgo.com/">here</a>
            <a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Farticle">Example result</a>
        </body>
    </html>
    """

    monkeypatch.setattr(
        "deep_research_agent.services.search.urllib_request.urlopen",
        lambda *args, **kwargs: _FakeUrlOpenResponse(html),
    )

    results = await service.search(
        task=PlanTask(
            title="Check market signals",
            description="Gather sources",
            search_query="ai infrastructure market 2026",
        ),
        research_request=ResearchRequest(query="Assess the AI infrastructure market"),
        limit=5,
    )

    assert len(results) == 1
    assert results[0].title == "Example result"
    assert results[0].url == "https://example.com/article"


@pytest.mark.asyncio
async def test_searxng_search_uses_selected_pool_and_falls_back(monkeypatch):
    service = SearXNGPoolSearchService(
        AppSettings(
            default_search_provider=SearchProvider.SEARXNG,
            searxng_selected_instances=[
                "https://search-1.example/",
                "https://search-2.example/",
            ],
            http_user_agent="deep-research-agent-test",
        )
    )
    calls: list[str] = []

    def fake_urlopen(req, timeout=30):
        calls.append(req.full_url)
        if req.full_url.startswith("https://search-1.example/search"):
            raise error.URLError("first instance offline")
        payload = {
            "results": [
                {
                    "url": "https://example.com/article",
                    "title": "Example result",
                    "content": "Summary",
                    "engines": ["google"],
                    "score": 1.0,
                }
            ]
        }
        return _FakeUrlOpenResponse(json.dumps(payload))

    monkeypatch.setattr("deep_research_agent.services.search.urllib_request.urlopen", fake_urlopen)
    monkeypatch.setattr("deep_research_agent.services.search.random.sample", lambda seq, k: list(seq)[:k])

    results = await service.search(
        task=PlanTask(
            title="Check market signals",
            description="Gather sources",
            search_query="ai infrastructure market 2026",
        ),
        research_request=ResearchRequest(query="Assess the AI infrastructure market"),
        limit=5,
    )

    assert len(calls) == 2
    assert results[0].provider is SearchProvider.SEARXNG
    assert results[0].metadata["instance_url"] == "https://search-2.example/"
    assert results[0].url == "https://example.com/article"


@pytest.mark.asyncio
async def test_searxng_search_keeps_empty_results_without_fallback(monkeypatch):
    service = SearXNGPoolSearchService(
        AppSettings(
            default_search_provider=SearchProvider.SEARXNG,
            searxng_selected_instances=[
                "https://search-1.example/",
                "https://search-2.example/",
            ],
            http_user_agent="deep-research-agent-test",
        )
    )
    calls: list[str] = []

    def fake_urlopen(req, timeout=30):
        calls.append(req.full_url)
        if req.full_url.startswith("https://search-2.example/search"):
            raise AssertionError("fallback should not run when an instance returns a valid empty result set")
        return _FakeUrlOpenResponse(json.dumps({"results": []}))

    monkeypatch.setattr("deep_research_agent.services.search.urllib_request.urlopen", fake_urlopen)
    monkeypatch.setattr("deep_research_agent.services.search.random.sample", lambda seq, k: list(seq)[:k])

    results = await service.search(
        task=PlanTask(
            title="Check market signals",
            description="Gather sources",
            search_query="ai infrastructure market 2026",
        ),
        research_request=ResearchRequest(query="Assess the AI infrastructure market"),
        limit=5,
    )

    assert results == []
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_searxng_search_discovers_and_persists_instance_pool(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    service = SearXNGPoolSearchService(
        AppSettings(
            default_search_provider=SearchProvider.SEARXNG,
            searxng_registry_url="https://registry.example/data/instances.json",
            searxng_pool_size=2,
            http_user_agent="deep-research-agent-test",
        )
    )

    registry_payload = {
        "instances": {
            "https://search-1.example/": {
                "main": True,
                "network_type": "normal",
                "http": {"status_code": 200, "error": None},
            },
            "https://search-2.example/": {
                "main": True,
                "network_type": "normal",
                "http": {"status_code": 200, "error": None},
            },
            "https://search-3.example/": {
                "main": True,
                "network_type": "normal",
                "http": {"status_code": 500, "error": "upstream"},
            },
            "http://search-4.example/": {
                "main": True,
                "network_type": "normal",
                "http": {"status_code": 200, "error": None},
            },
        }
    }

    def fake_urlopen(req, timeout=30):
        if req.full_url == "https://registry.example/data/instances.json":
            return _FakeUrlOpenResponse(json.dumps(registry_payload))
        return _FakeUrlOpenResponse(
            json.dumps(
                {
                    "results": [
                        {
                            "url": "https://example.com/article",
                            "title": "Example result",
                            "content": "Summary",
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr("deep_research_agent.services.search.urllib_request.urlopen", fake_urlopen)
    monkeypatch.setattr("deep_research_agent.services.search.random.sample", lambda seq, k: list(seq)[:k])

    results = await service.search(
        task=PlanTask(
            title="Check market signals",
            description="Gather sources",
            search_query="ai infrastructure market 2026",
        ),
        research_request=ResearchRequest(query="Assess the AI infrastructure market"),
        limit=5,
    )

    persisted = load_persisted_app_settings()

    assert persisted["searxng_selected_instances"] == [
        "https://search-1.example/",
        "https://search-2.example/",
    ]
    assert persisted["searxng_selected_at"]
    assert results[0].metadata["instance_url"] == "https://search-1.example/"


@pytest.mark.asyncio
async def test_searxng_search_refreshes_pool_once_when_all_instances_rate_limit(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    service = SearXNGPoolSearchService(
        AppSettings(
            default_search_provider=SearchProvider.SEARXNG,
            searxng_selected_instances=[
                "https://search-1.example/",
                "https://search-2.example/",
            ],
            searxng_pool_size=2,
            http_user_agent="deep-research-agent-test",
        )
    )
    refreshed_pools: list[list[str] | None] = []

    async def fake_refresh(settings, *, exclude_urls=None):
        refreshed_pools.append(list(exclude_urls) if exclude_urls else None)
        persisted = load_persisted_app_settings()
        persisted["searxng_selected_instances"] = [
            "https://search-3.example/",
            "https://search-4.example/",
        ]
        persisted["searxng_selected_at"] = "2026-05-31T12:00:00+00:00"
        from deep_research_agent.settings import save_persisted_app_settings
        save_persisted_app_settings(persisted)
        return {
            "instances": persisted["searxng_selected_instances"],
            "selected_at": persisted["searxng_selected_at"],
        }

    def fake_urlopen(req, timeout=30):
        if req.full_url.startswith("https://search-1.example/search"):
            raise error.HTTPError(req.full_url, 429, "Too Many Requests", hdrs=None, fp=None)
        if req.full_url.startswith("https://search-2.example/search"):
            raise error.HTTPError(req.full_url, 429, "Too Many Requests", hdrs=None, fp=None)
        return _FakeUrlOpenResponse(
            json.dumps(
                {
                    "results": [
                        {
                            "url": "https://example.com/article",
                            "title": "Recovered result",
                            "content": "Recovered after refresh",
                        }
                    ]
                }
            )
        )

    monkeypatch.setattr("deep_research_agent.services.search.refresh_searxng_instance_pool", fake_refresh)
    monkeypatch.setattr("deep_research_agent.services.search.urllib_request.urlopen", fake_urlopen)
    monkeypatch.setattr("deep_research_agent.services.search.random.sample", lambda seq, k: list(seq)[:k])

    results = await service.search(
        task=PlanTask(
            title="Check market signals",
            description="Gather sources",
            search_query="ai infrastructure market 2026",
        ),
        research_request=ResearchRequest(query="Assess the AI infrastructure market"),
        limit=5,
    )

    assert refreshed_pools == [["https://search-1.example/", "https://search-2.example/"]]
    assert results[0].metadata["instance_url"] == "https://search-3.example/"


@pytest.mark.asyncio
async def test_searxng_search_falls_back_to_local_html_instance(monkeypatch):
    service = SearXNGPoolSearchService(
        AppSettings(
            default_search_provider=SearchProvider.SEARXNG,
            searxng_selected_instances=[
                "https://search-1.example/",
                "https://search-2.example/",
            ],
            searxng_local_url="http://searxng:8080",
            http_user_agent="deep-research-agent-test",
        )
    )

    def fake_urlopen(req, timeout=30):
        if req.full_url.startswith("https://search-"):
            raise error.HTTPError(req.full_url, 429, "Too Many Requests", hdrs=None, fp=None)
        html = """
        <html><body><div id="urls" role="main">
                    <table><tr><td class="response-error">suspended: too many requests</td></tr></table>
          <article class="result result-default category-general">
            <a href="https://example.com/article" class="url_header" rel="noreferrer"></a>
            <h3><a href="https://example.com/article" rel="noreferrer">Recovered local result</a></h3>
            <p class="content">Local SearXNG fallback content.</p>
          </article>
        </div></body></html>
        """
        return _FakeUrlOpenResponse(html, headers={"Content-Type": "text/html; charset=utf-8"})

    monkeypatch.setattr("deep_research_agent.services.search.urllib_request.urlopen", fake_urlopen)
    monkeypatch.setattr("deep_research_agent.services.search.random.sample", lambda seq, k: list(seq)[:k])

    results = await service.search(
        task=PlanTask(
            title="Check market signals",
            description="Gather sources",
            search_query="ai infrastructure market 2026",
        ),
        research_request=ResearchRequest(query="Assess the AI infrastructure market"),
        limit=5,
    )

    assert results[0].title == "Recovered local result"
    assert results[0].metadata["instance_url"] == "http://searxng:8080/"
    assert results[0].metadata["search_mode"] == "html"


@pytest.mark.asyncio
async def test_content_extractor_transport_errors_fail_explicitly(monkeypatch):
    extractor = ContentExtractor(AppSettings())

    def raise_url_error(*args, **kwargs):
        raise error.URLError("network unavailable")

    monkeypatch.setattr("deep_research_agent.services.extraction.urllib_request.urlopen", raise_url_error)

    with pytest.raises(ProviderConfigurationError, match="Content extraction failed: network unavailable"):
        await extractor.extract(
            source=SourceRecord(
                title="Example source",
                url="https://example.com/article",
                provider=SearchProvider.NONE,
                task_ids=["task_example"],
            ),
            task=PlanTask(
                task_id="task_example",
                title="Check market signals",
                description="Gather sources",
                search_query="ai infrastructure market 2026",
            ),
            research_request=ResearchRequest(query="Assess the AI infrastructure market"),
        )


@pytest.mark.asyncio
async def test_content_extractor_prefers_trafilatura_for_html(monkeypatch):
    extractor = ContentExtractor(AppSettings())
    html = "<html><body><article><p>Trafilatura preferred evidence about AI infrastructure.</p></article></body></html>"

    monkeypatch.setattr(
        "deep_research_agent.services.extraction.urllib_request.urlopen",
        lambda *args, **kwargs: _FakeUrlOpenResponse(
            html,
            headers={"Content-Type": "text/html; charset=utf-8"},
        ),
    )
    monkeypatch.setattr(
        "deep_research_agent.services.extraction._extract_with_trafilatura",
        lambda raw_html: "Trafilatura preferred evidence about AI infrastructure.",
    )

    result = await extractor.extract(
        source=SourceRecord(
            title="Example source",
            url="https://example.com/article",
            provider=SearchProvider.NONE,
            task_ids=["task_example"],
        ),
        task=PlanTask(
            task_id="task_example",
            title="AI infrastructure evidence",
            description="Gather sources",
            search_query="ai infrastructure evidence",
        ),
        research_request=ResearchRequest(query="Assess AI infrastructure evidence"),
    )

    assert result.evidence
    assert "Trafilatura preferred evidence" in result.evidence[0].excerpt


@pytest.mark.asyncio
async def test_content_extractor_falls_back_to_html_parser_when_trafilatura_fails(monkeypatch):
    extractor = ContentExtractor(AppSettings())
    html = "<html><body><article><p>Parser fallback evidence about AI infrastructure.</p></article></body></html>"

    monkeypatch.setattr(
        "deep_research_agent.services.extraction.urllib_request.urlopen",
        lambda *args, **kwargs: _FakeUrlOpenResponse(
            html,
            headers={"Content-Type": "text/html; charset=utf-8"},
        ),
    )

    def raise_extract_error(raw_html: str) -> str:
        raise RuntimeError("trafilatura failed")

    monkeypatch.setattr(
        "deep_research_agent.services.extraction._extract_with_trafilatura",
        raise_extract_error,
    )

    result = await extractor.extract(
        source=SourceRecord(
            title="Example source",
            url="https://example.com/article",
            provider=SearchProvider.NONE,
            task_ids=["task_example"],
        ),
        task=PlanTask(
            task_id="task_example",
            title="AI infrastructure evidence",
            description="Gather sources",
            search_query="ai infrastructure evidence",
        ),
        research_request=ResearchRequest(query="Assess AI infrastructure evidence"),
    )

    assert result.evidence
    assert "Parser fallback evidence" in result.evidence[0].excerpt
