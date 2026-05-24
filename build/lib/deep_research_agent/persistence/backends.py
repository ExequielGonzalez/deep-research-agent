from __future__ import annotations

import importlib
import json
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from deep_research_agent.domain.models import HumanReviewRequest, RunRecord, RunStatus
from deep_research_agent.settings import AppSettings, PersistenceBackend


class MissingOptionalDependencyError(RuntimeError):
    """Raised when an optional production dependency is not installed."""


class RunStore(ABC):
    @abstractmethod
    async def upsert_run(self, record: RunRecord) -> None: ...

    @abstractmethod
    async def get_run(self, thread_id: str) -> RunRecord | None: ...

    @abstractmethod
    async def list_pending_runs(self, limit: int = 20) -> list[RunRecord]: ...

    @abstractmethod
    async def list_runs(self, limit: int = 20) -> list[RunRecord]: ...


def sqlite_path_from_url(db_url: str) -> Path:
    parsed = urlparse(db_url)
    if parsed.scheme not in {"sqlite", "sqlite+aiosqlite"}:
        raise ValueError(f"Unsupported SQLite URL: {db_url}")

    raw_path = parsed.path or parsed.netloc
    if not raw_path:
        raise ValueError("SQLite URL must include a database path.")

    if raw_path.startswith("//"):
        path = Path(raw_path[1:])
    else:
        path = Path(raw_path.lstrip("/"))
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


class SQLiteRunStore(RunStore):
    def __init__(self, connection: aiosqlite.Connection):
        self._connection = connection
        self._connection.row_factory = aiosqlite.Row

    @classmethod
    @asynccontextmanager
    async def from_url(cls, db_url: str) -> AsyncIterator["SQLiteRunStore"]:
        path = sqlite_path_from_url(db_url)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(path)
        store = cls(connection)
        await store._setup()
        try:
            yield store
        finally:
            await connection.close()

    async def _setup(self) -> None:
        await self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                thread_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                pending_human_input_json TEXT,
                latest_state_json TEXT NOT NULL,
                latest_interrupts_json TEXT NOT NULL,
                last_message TEXT NOT NULL
            )
            """
        )
        await self._connection.commit()

    async def upsert_run(self, record: RunRecord) -> None:
        await self._connection.execute(
            """
            INSERT INTO runs (
                thread_id,
                query,
                status,
                created_at,
                updated_at,
                pending_human_input_json,
                latest_state_json,
                latest_interrupts_json,
                last_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                query = excluded.query,
                status = excluded.status,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                pending_human_input_json = excluded.pending_human_input_json,
                latest_state_json = excluded.latest_state_json,
                latest_interrupts_json = excluded.latest_interrupts_json,
                last_message = excluded.last_message
            """,
            (
                record.thread_id,
                record.query,
                record.status.value,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                json.dumps(record.pending_human_input.model_dump(mode="json")) if record.pending_human_input else None,
                json.dumps(record.latest_state),
                json.dumps(record.latest_interrupts),
                record.last_message,
            ),
        )
        await self._connection.commit()

    async def get_run(self, thread_id: str) -> RunRecord | None:
        cursor = await self._connection.execute("SELECT * FROM runs WHERE thread_id = ?", (thread_id,))
        row = await cursor.fetchone()
        return self._decode_row(row) if row else None

    async def list_pending_runs(self, limit: int = 20) -> list[RunRecord]:
        cursor = await self._connection.execute(
            "SELECT * FROM runs WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
            (RunStatus.INTERRUPTED.value, limit),
        )
        rows = await cursor.fetchall()
        return [self._decode_row(row) for row in rows]

    async def list_runs(self, limit: int = 20) -> list[RunRecord]:
        cursor = await self._connection.execute(
            "SELECT * FROM runs ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._decode_row(row) for row in rows]

    def _decode_row(self, row: aiosqlite.Row) -> RunRecord:
        pending = row["pending_human_input_json"]
        return RunRecord(
            thread_id=row["thread_id"],
            query=row["query"],
            status=RunStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            pending_human_input=HumanReviewRequest.model_validate_json(pending) if pending else None,
            latest_state=json.loads(row["latest_state_json"]),
            latest_interrupts=json.loads(row["latest_interrupts_json"]),
            last_message=row["last_message"],
        )


class PostgresRunStore(RunStore):
    def __init__(self, connection: Any):
        self._connection = connection

    async def setup(self) -> None:
        await self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                thread_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                pending_human_input_json JSONB,
                latest_state_json JSONB NOT NULL,
                latest_interrupts_json JSONB NOT NULL,
                last_message TEXT NOT NULL
            )
            """
        )

    async def upsert_run(self, record: RunRecord) -> None:
        await self._connection.execute(
            """
            INSERT INTO runs (
                thread_id,
                query,
                status,
                created_at,
                updated_at,
                pending_human_input_json,
                latest_state_json,
                latest_interrupts_json,
                last_message
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9)
            ON CONFLICT(thread_id) DO UPDATE SET
                query = excluded.query,
                status = excluded.status,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                pending_human_input_json = excluded.pending_human_input_json,
                latest_state_json = excluded.latest_state_json,
                latest_interrupts_json = excluded.latest_interrupts_json,
                last_message = excluded.last_message
            """,
            record.thread_id,
            record.query,
            record.status.value,
            record.created_at,
            record.updated_at,
            json.dumps(record.pending_human_input.model_dump(mode="json")) if record.pending_human_input else None,
            json.dumps(record.latest_state),
            json.dumps(record.latest_interrupts),
            record.last_message,
        )

    async def get_run(self, thread_id: str) -> RunRecord | None:
        row = await self._connection.fetchrow("SELECT * FROM runs WHERE thread_id = $1", thread_id)
        return self._decode_row(row) if row else None

    async def list_pending_runs(self, limit: int = 20) -> list[RunRecord]:
        rows = await self._connection.fetch(
            "SELECT * FROM runs WHERE status = $1 ORDER BY updated_at DESC LIMIT $2",
            RunStatus.INTERRUPTED.value,
            limit,
        )
        return [self._decode_row(row) for row in rows]

    async def list_runs(self, limit: int = 20) -> list[RunRecord]:
        rows = await self._connection.fetch(
            "SELECT * FROM runs ORDER BY updated_at DESC LIMIT $1",
            limit,
        )
        return [self._decode_row(row) for row in rows]

    def _decode_row(self, row: Any) -> RunRecord:
        return RunRecord(
            thread_id=row["thread_id"],
            query=row["query"],
            status=RunStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            pending_human_input=HumanReviewRequest.model_validate(row["pending_human_input_json"]) if row["pending_human_input_json"] else None,
            latest_state=row["latest_state_json"],
            latest_interrupts=row["latest_interrupts_json"],
            last_message=row["last_message"],
        )


@asynccontextmanager
async def create_run_store(settings: AppSettings) -> AsyncIterator[RunStore]:
    if settings.persistence_backend is PersistenceBackend.SQLITE:
        async with SQLiteRunStore.from_url(settings.checkpoint_db_url) as store:
            yield store
        return

    try:
        asyncpg = importlib.import_module("asyncpg")
    except ImportError as exc:  # pragma: no cover - tested via monkeypatch
        raise MissingOptionalDependencyError(
            "Postgres runtime metadata requires the optional dependencies in `deep-research-agent[postgres]`."
        ) from exc

    connection = await asyncpg.connect(settings.checkpoint_db_url)
    store = PostgresRunStore(connection)
    await store.setup()
    try:
        yield store
    finally:
        await connection.close()


@asynccontextmanager
async def create_checkpointer(settings: AppSettings) -> AsyncIterator[Any]:
    if settings.persistence_backend is PersistenceBackend.SQLITE:
        sqlite_path = sqlite_path_from_url(settings.checkpoint_db_url)
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(sqlite_path)) as saver:
            await saver.setup()
            yield saver
        return

    try:
        postgres_module = importlib.import_module("langgraph.checkpoint.postgres.aio")
    except ImportError as exc:  # pragma: no cover - tested via monkeypatch
        raise MissingOptionalDependencyError(
            "Postgres checkpointing requires the optional dependencies in `deep-research-agent[postgres]`."
        ) from exc

    async_postgres_saver = getattr(postgres_module, "AsyncPostgresSaver")
    async with async_postgres_saver.from_conn_string(settings.checkpoint_db_url) as saver:
        await saver.setup()
        yield saver
