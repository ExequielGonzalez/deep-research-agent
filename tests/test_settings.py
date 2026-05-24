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
