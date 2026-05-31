from deep_research_agent.domain.models import ModelProvider, SearchProvider
from deep_research_agent.settings import AppSettings, PersistenceBackend


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("DEEP_RESEARCH_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("DEEP_RESEARCH_MODEL_NAME", "claude-sonnet-4-5")
    monkeypatch.setenv("DEEP_RESEARCH_PERSISTENCE_BACKEND", "postgres")
    monkeypatch.setenv("DEEP_RESEARCH_POSTGRES_DB_URL", "postgresql://user:pass@localhost:5432/research")
    monkeypatch.setenv("DEEP_RESEARCH_DEFAULT_SEARCH_PROVIDER", "firecrawl")
    monkeypatch.setenv("DEEP_RESEARCH_TOTAL_TOKEN_BUDGET", "64000")
    monkeypatch.setenv("DEEP_RESEARCH_MAX_ITERATIONS", "9")

    settings = AppSettings()

    assert settings.model_provider is ModelProvider.ANTHROPIC
    assert settings.model_name == "claude-sonnet-4-5"
    assert settings.persistence_backend is PersistenceBackend.POSTGRES
    assert settings.checkpoint_db_url == "postgresql://user:pass@localhost:5432/research"
    assert settings.default_search_provider is SearchProvider.FIRECRAWL
    assert settings.total_token_budget == 64_000
    assert settings.max_iterations == 9


def test_settings_parse_searxng_pool_from_environment(monkeypatch):
    monkeypatch.setenv("DEEP_RESEARCH_DEFAULT_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("DEEP_RESEARCH_SEARXNG_LOCAL_URL", "http://searxng:8080/")
    monkeypatch.setenv("DEEP_RESEARCH_SEARXNG_POOL_SIZE", "5")
    monkeypatch.setenv(
        "DEEP_RESEARCH_SEARXNG_SELECTED_INSTANCES",
        '["https://search-1.example/", "https://search-2.example"]',
    )

    settings = AppSettings()

    assert settings.default_search_provider is SearchProvider.SEARXNG
    assert settings.searxng_local_url == "http://searxng:8080"
    assert settings.searxng_pool_size == 5
    assert settings.searxng_selected_instances == [
        "https://search-1.example/",
        "https://search-2.example/",
    ]
