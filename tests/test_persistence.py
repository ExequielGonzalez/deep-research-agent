import importlib

import pytest

from deep_research_agent.persistence import MissingOptionalDependencyError, create_checkpointer
from deep_research_agent.settings import AppSettings, PersistenceBackend


@pytest.mark.asyncio
async def test_postgres_checkpointer_requires_optional_dependency(monkeypatch):
    settings = AppSettings(
        persistence_backend=PersistenceBackend.POSTGRES,
        postgres_db_url="postgresql://user:pass@localhost:5432/research",
    )
    original_import_module = importlib.import_module

    def fake_import(name: str):
        if name == "langgraph.checkpoint.postgres.aio":
            raise ImportError("missing")
        return original_import_module(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    with pytest.raises(MissingOptionalDependencyError):
        async with create_checkpointer(settings):
            pass
