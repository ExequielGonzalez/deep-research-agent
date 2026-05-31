from __future__ import annotations

import json
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from deep_research_agent.domain.models import ModelProvider, SearchProvider


class PersistenceBackend(str, Enum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


PERSISTED_APP_SETTINGS_PATH = Path(".local/settings.json")
_RUNTIME_SETTING_KEYS = {
    "model_provider",
    "model_name",
    "openai_api_key",
    "openai_base_url",
    "ollama_base_url",
    "default_search_provider",
    "searxng_registry_url",
    "searxng_pool_size",
    "searxng_selected_instances",
    "searxng_selected_at",
    "tavily_api_key",
    "serper_api_key",
    "max_iterations",
    "max_sources_per_task",
    "total_token_budget",
    "max_notes",
    "llm_request_timeout_seconds",
}


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
    searxng_registry_url: str = "https://searx.space/data/instances.json"
    searxng_local_url: str | None = None
    searxng_pool_size: int = 5
    searxng_selected_instances: list[str] = Field(default_factory=list)
    searxng_selected_at: str | None = None
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    total_token_budget: int = 120_000
    per_source_token_budget: int = 4_000
    max_content_chars_per_source: int = 16_000
    max_sources_per_task: int = 8
    max_notes: int = 200
    max_iterations: int = 6
    llm_request_timeout_seconds: int = 600
    report_output_dir: str = ".local/reports"
    http_user_agent: str = Field(default="deep-research-agent/0.1.0")

    @field_validator(
        "total_token_budget",
        "per_source_token_budget",
        "max_content_chars_per_source",
        "max_sources_per_task",
        "max_notes",
        "max_iterations",
        "llm_request_timeout_seconds",
        "searxng_pool_size",
    )
    @classmethod
    def positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Configuration budgets and limits must be positive integers.")
        return value

    @field_validator("searxng_registry_url")
    @classmethod
    def validate_searxng_registry_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("SearXNG registry URL must not be empty.")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("SearXNG registry URL must start with http:// or https://.")
        return normalized

    @field_validator("searxng_local_url")
    @classmethod
    def validate_searxng_local_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not normalized:
            return None
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("SearXNG local URL must start with http:// or https://.")
        return normalized

    @field_validator("searxng_selected_instances", mode="before")
    @classmethod
    def normalize_searxng_selected_instances(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return []
            try:
                parsed = json.loads(normalized)
            except json.JSONDecodeError:
                return [item.strip() for item in normalized.split(",") if item.strip()]
            if isinstance(parsed, list):
                return parsed
            return [normalized]
        return value

    @field_validator("searxng_selected_instances")
    @classmethod
    def validate_searxng_selected_instances(cls, value: list[str]) -> list[str]:
        normalized_instances: list[str] = []
        seen: set[str] = set()
        for instance_url in value:
            normalized = instance_url.strip()
            if not normalized:
                continue
            if not normalized.startswith(("http://", "https://")):
                raise ValueError("SearXNG instance URLs must start with http:// or https://.")
            if not normalized.endswith("/"):
                normalized = f"{normalized}/"
            if normalized in seen:
                continue
            seen.add(normalized)
            normalized_instances.append(normalized)
        return normalized_instances

    @property
    def checkpoint_db_url(self) -> str:
        if self.persistence_backend is PersistenceBackend.POSTGRES:
            return self.postgres_db_url
        return self.sqlite_db_url


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


def load_persisted_app_settings(path: str | Path | None = None) -> dict[str, Any]:
    settings_path = Path(path) if path is not None else PERSISTED_APP_SETTINGS_PATH
    try:
        with settings_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_persisted_app_settings(data: dict[str, Any], path: str | Path | None = None) -> None:
    settings_path = Path(path) if path is not None else PERSISTED_APP_SETTINGS_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with settings_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def resolve_runtime_settings(
    base_settings: AppSettings,
    *,
    persisted: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> AppSettings:
    merged = base_settings.model_dump(mode="python")

    for source in (persisted or load_persisted_app_settings(), overrides or {}):
        for key in _RUNTIME_SETTING_KEYS:
            if key not in source:
                continue
            value = source[key]
            if value is None:
                continue
            if isinstance(value, str):
                normalized = value.strip()
                if not normalized:
                    continue
                merged[key] = normalized
                continue
            merged[key] = value

    openai_base_url = merged.get("openai_base_url")
    if isinstance(openai_base_url, str):
        merged["openai_base_url"] = openai_base_url.rstrip("/")

    return AppSettings.model_validate(merged)
