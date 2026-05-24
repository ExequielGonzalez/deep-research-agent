from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from deep_research_agent.domain.models import ModelProvider, SearchProvider


class PersistenceBackend(str, Enum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DEEP_RESEARCH_",
        extra="ignore",
    )

    environment: str = "development"
    model_provider: ModelProvider = ModelProvider.OPENAI
    model_name: str = "gpt-4.1-mini"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_base_url: str = "http://localhost:11434"
    persistence_backend: PersistenceBackend = PersistenceBackend.SQLITE
    sqlite_db_url: str = "sqlite+aiosqlite:///./.local/deep_research.sqlite3"
    postgres_db_url: str = "postgresql://postgres:postgres@localhost:5432/deep_research"
    default_search_provider: SearchProvider = SearchProvider.NONE
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    total_token_budget: int = 120_000
    per_source_token_budget: int = 4_000
    max_content_chars_per_source: int = 16_000
    max_sources_per_task: int = 8
    max_notes: int = 200
    max_iterations: int = 6
    http_user_agent: str = Field(default="deep-research-agent/0.1.0")

    @field_validator(
        "total_token_budget",
        "per_source_token_budget",
        "max_content_chars_per_source",
        "max_sources_per_task",
        "max_notes",
        "max_iterations",
    )
    @classmethod
    def positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Configuration budgets and limits must be positive integers.")
        return value

    @property
    def checkpoint_db_url(self) -> str:
        if self.persistence_backend is PersistenceBackend.POSTGRES:
            return self.postgres_db_url
        return self.sqlite_db_url


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
