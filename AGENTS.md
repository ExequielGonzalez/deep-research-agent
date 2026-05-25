# deep-research-agent — AGENTS.md

## Entrypoints & package layout

- Source under `src/` (setuptools `packages.find {where = ["src"]}`).
- CLI: `deep-research-agent` → `deep_research_agent.cli:main`. Also `python -m deep_research_agent`.
- Web: `deep-research-agent-web` → `deep_research_agent.web.app:main` (FastAPI + uvicorn on `0.0.0.0:8000`).
- App settings: pydantic-settings `AppSettings` at `settings.py:17`. All env vars prefixed `DEEP_RESEARCH_`. Loads `.env` automatically.
- `research-context.md` is the project readme (set in `pyproject.toml`).

## Dev commands

```bash
pip install -e ".[dev]"              # install + dev deps (pytest, httpx)
pytest [-v] [-k test_name]           # asyncio_mode=auto, pythonpath=src
```

Single test file: `pytest tests/test_runtime_flow.py -v`.

## Architecture essentials

- **LangGraph StateGraph** with typed state (keys with reducer functions for append/merge semantics).
- **Two HITL interrupt points**: after planning (`plan_approval`) and after reflection when done/guard-reached (`sufficiency_review`).
- Graph nodes: `plan → plan_review → (loop: search/extract/reflect) → sufficiency_review → synthesize`.
- `runtime/placeholders.py` contains **stubs** (`NotImplementedError`) — these are NOT wired into the compiled graph. The real graph lives in `runtime/graph.py`.
- Service bundle (`services/__init__.py`) wired at graph build time.

## Provider constraints (important!)

- **LLM**: Only `openai` and `ollama` providers supported. Anthropic, Google, Azure OpenAI raise `ProviderConfigurationError`.
- **Search**: DuckDuckGo (free, default when `provider=none`). Tavily and Serper supported. **Firecrawl is NOT supported** as a search backend.
- Tests use fake services (`tests/support.py`) — no API keys needed.

## Persistence

- SQLite default (`sqlite+aiosqlite:///./.local/deep_research.sqlite3`).
- Postgres with `[postgres]` extra (`asyncpg`, `langgraph-checkpoint-postgres`).
- Checkpointer + RunStore (run metadata table) both use same DB URL via `checkpoint_db_url`.
- Docker Compose workflow defaults to Postgres. Use `./scripts/compose-agent.sh`.

## CLI usage

```bash
deep-research-agent run --query "..." [--max-iterations N]
deep-research-agent resume --thread-id <id> --decision approve|clarify|continue|stop [--summary "..."]
deep-research-agent list-pending [--limit N]
```

## Docker workflow

```bash
cp .env.example .env   # then set API keys
./scripts/compose-agent.sh bootstrap   # starts postgres, waits for pg_isready
./scripts/compose-agent.sh run --query "..."
./scripts/compose-agent.sh resume --thread-id <id> --decision approve
./scripts/compose-agent.sh list-pending
./scripts/compose-agent.sh down
```

Prefer the script over raw `docker compose` — it handles postgres readiness.

## Test quirks

- Some tests write artifacts under `tests/.artifacts/` (gitignored).
- `test_compose_integration.py` requires Docker (skipped otherwise).
- `test_persistence.py` monkeypatches `importlib` to simulate missing optional deps.
- Runtime integration tests (`test_runtime_flow.py`, `test_web_app.py`, `test_cli.py`) exercise the full loop end-to-end with fake services.

## State reducers (important for graph correctness)

- `sources`: deduplicated by `canonical_url` → `url` → `source_id`; merges `task_ids`.
- `notes`: appends, deduplicates exact matches, preserves order.
- `plan_tasks`, `evidence`, `reflections`, `human_decisions`, `report_sections`, `citation_records`: merged by respective ID keys.
- Key environment limits: `max_iterations` (default 6), `max_sources_per_task` (8), `total_token_budget` (120k).

## Events & observability

- Runtime emits events via `emit_runtime_event()` → SSE for web subscribers.
- Event types: `llm_stage_started`, `llm_reasoning`, `llm_output_preview`, `run_task_failed`.
- Report markdown persisted to `report_output_dir` (default `.local/reports/`).