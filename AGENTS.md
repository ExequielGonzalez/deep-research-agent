# deep-research-agent — AGENTS.md

## Entrypoints & package layout

- Source under `src/` (setuptools `packages.find {where = ["src"]}`).
- CLI: `deep-research-agent` → [`deep_research_agent.cli:main`](src/deep_research_agent/__main__.py). Also `python -m deep_research_agent`.
- Web: `deep-research-agent-web` → [`deep_research_agent.web.app:main`](src/deep_research_agent/web/__main__.py) (FastAPI + uvicorn on `0.0.0.0:8000`).
- App settings: pydantic-settings [`AppSettings`](src/deep_research_agent/settings.py:17). All env vars prefixed `DEEP_RESEARCH_`. Loads `.env` automatically.
- `research-context.md` is the project readme (set in `pyproject.toml`).

### Directory tree

```
src/deep_research_agent/
├── cli.py              # CLI argument parsing and orchestration
├── settings.py         # Pydantic settings (env-based config)
├── __init__.py
├── __main__.py         # python -m entrypoint
├── domain/
│   ├── models.py       # All domain models (PlanTask, SourceRecord, etc.)
│   └── state.py        # LangGraph state (TypedDict + reducers)
├── runtime/
│   ├── graph.py        # StateGraph definition, nodes, routing
│   ├── service.py      # ResearchRuntimeService (start, resume, execute)
│   ├── events.py       # Event emitter (ContextVar-based SSE bus)
│   └── placeholders.py # Unused stubs
├── services/
│   ├── __init__.py     # ResearchServiceBundle + factory
│   ├── llm.py          # LLM service (OpenAI, Ollama)
│   ├── search.py       # Search providers (DuckDuckGo, Tavily, Serper)
│   ├── extraction.py   # Content extraction from URLs
│   └── reporting.py    # Report formatting (markdown + citations)
└── web/
    ├── app.py          # FastAPI app + SSE + run manager
    ├── ui.py           # Legacy embedded HTML UI
    └── __main__.py     # uvicorn runner
tests/
├── test_cli.py
├── test_runtime_flow.py
├── test_web_app.py
├── test_services.py
├── test_state.py
├── test_settings.py
├── test_report_formatting.py
├── test_persistence.py
├── test_compose_integration.py
└── support.py          # Fake services for testing
```

## Dev commands

```bash
pip install -e ".[dev]"              # install + dev deps (pytest, httpx)
pytest [-v] [-k test_name]           # asyncio_mode=auto, pythonpath=src
```

Single test file: `pytest tests/test_runtime_flow.py -v`.

## Architecture essentials

### Graph structure

**LangGraph StateGraph** with typed state (keys with reducer functions for append/merge semantics).

- **Two HITL interrupt points**: after planning (`plan_approval`) and after reflection when done/guard-reached (`sufficiency_review`).
- Graph nodes: `plan → plan_review → (loop: search/extract/reflect) → sufficiency_review → synthesize`.
- [`runtime/placeholders.py`](src/deep_research_agent/runtime/placeholders.py) contains **stubs** (`NotImplementedError`) — these are NOT wired into the compiled graph. The real graph lives in [`runtime/graph.py`](src/deep_research_agent/runtime/graph.py).
- Service bundle ([`services/__init__.py`](src/deep_research_agent/services/__init__.py)) wired at graph build time.

### Graph routing logic (node → node transitions)

Defined in [`build_research_graph()`](src/deep_research_agent/runtime/graph.py:462):

| From | To | Condition |
|------|----|-----------|
| `START` | `plan_research` | Always |
| `plan_research` | `prepare_plan_review` | Always |
| `prepare_plan_review` | `await_plan_review` | Always |
| `await_plan_review` | `cancel_run` | If decision is `STOP` |
| `await_plan_review` | `apply_plan_feedback` | If decision is `CLARIFY` |
| `await_plan_review` | `begin_iteration` | If decision is `APPROVE` |
| `apply_plan_feedback` | `plan_research` | Always (re-plan) |
| `begin_iteration` | `search_sources` | Always (increment count) |
| `search_sources` | `extract_evidence` | Always |
| `extract_evidence` | `reflect_research` | Always |
| `reflect_research` | `begin_iteration` | If `needs_more_research` AND iteration < max AND no human input needed |
| `reflect_research` | `prepare_sufficiency_review` | Otherwise |
| `prepare_sufficiency_review` | `await_sufficiency_review` | Always |
| `await_sufficiency_review` | `cancel_run` | If decision is `STOP` |
| `await_sufficiency_review` | `synthesize_report` | If decision is `APPROVE` |
| `await_sufficiency_review` | `apply_sufficiency_feedback` | If decision is `CONTINUE` |
| `await_sufficiency_review` | `synthesize_report` | If iteration >= max (force synthesize) |
| `synthesize_report` | `END` | Always |
| `cancel_run` | `END` | Always |

### State reducers (important for graph correctness)

- [`sources`](src/deep_research_agent/domain/state.py:53): deduplicated by `canonical_url` → `url` → `source_id`; merges `task_ids`.
- [`notes`](src/deep_research_agent/domain/state.py:25): appends, deduplicates exact matches, preserves order.
- [`plan_tasks`](src/deep_research_agent/domain/state.py:48), `evidence` (line 82), `reflections` (line 87), `human_decisions` (line 92), `report_sections` (line 97), `citation_records` (line 102): merged by respective ID keys.
- Key environment limits: `max_iterations` (default 6), `max_sources_per_task` (8), `total_token_budget` (120k).

## Provider constraints (important!)

- **LLM**: Only `openai` and `ollama` providers supported. Anthropic, Google, Azure OpenAI raise [`ProviderConfigurationError`](src/deep_research_agent/services/llm.py:37).
- **Search**: DuckDuckGo (free, default when `provider=none`). Tavily and Serper supported. **Firecrawl is NOT supported** as a search backend.
- Tests use fake services ([`tests/support.py`](tests/support.py)) — no API keys needed.

## Persistence

- SQLite default (`sqlite+aiosqlite:///./.local/deep_research.sqlite3`).
- Postgres with `[postgres]` extra (`asyncpg`, `langgraph-checkpoint-postgres`).
- Checkpointer + RunStore (run metadata table) both use same DB URL via [`checkpoint_db_url`](src/deep_research_agent/settings.py:62).
- Docker Compose workflow defaults to Postgres. Use [`./scripts/compose-agent.sh`](scripts/compose-agent.sh).

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

## Web API & SSE

The FastAPI web app ([`web/app.py`](src/deep_research_agent/web/app.py)) exposes:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Health check |
| `/api/config` | GET | Default configuration |
| `/api/runs` | GET | List all runs |
| `/api/runs/pending` | GET | List runs waiting for human input |
| `/api/runs` | POST | Create and start a new run |
| `/api/runs/{thread_id}` | GET | Get run status + latest state |
| `/api/runs/{thread_id}/decision` | POST | Submit human decision (resume) |
| `/api/runs/{thread_id}/events` | GET | SSE stream of runtime events |
| `/api/runs/{thread_id}/report` | GET | Download final report markdown |
| `/api/settings` | GET/POST | Persistent app settings |
| `/api/models` | GET | Fetch model catalog from provider |
| `/` | GET | Vue frontend (if built) or legacy HTML UI |

### SSE event types

Runtime events flow through a `ContextVar`-based emitter ([`events.py`](src/deep_research_agent/runtime/events.py:26)):

- `snapshot` — Full state snapshot after each graph node completes
- `llm_stage_started` — LLM call began (with phase name)
- `llm_reasoning` — Intermediate reasoning text (OpenAI only)
- `llm_output_preview` — Preview of LLM output
- `run_task_started/finished/cancelled/failed` — Background task lifecycle

The [`RunExecutionManager`](src/deep_research_agent/web/app.py:195) manages background `asyncio.Task` instances, subscriber queues, and event history (last 80 events per thread).

## Events & observability

- Runtime emits events via [`emit_runtime_event()`](src/deep_research_agent/runtime/events.py:26) → SSE for web subscribers.
- Report markdown persisted to `report_output_dir` (default `.local/reports/`).

## Service layer

Each service is an abstract base class / concrete implementation, wired via [`ResearchServiceBundle`](src/deep_research_agent/services/__init__.py:13):

| Service | File | Implementations |
|---------|------|-----------------|
| LLM | [`services/llm.py`](src/deep_research_agent/services/llm.py:434) | `OpenAIResearchLLMService`, `OllamaResearchLLMService` |
| Search | [`services/search.py`](src/deep_research_agent/services/search.py:21) | `DuckDuckGoSearchService`, `TavilySearchService`, `SerperSearchService` |
| Extraction | [`services/extraction.py`](src/deep_research_agent/services/extraction.py:35) | `ContentExtractor` |
| Reporting | [`services/reporting.py`](src/deep_research_agent/services/reporting.py:19) | `ReportFormatter` |

LLM service uses structured JSON output via Pydantic schema validation. All network calls use `urllib` with `asyncio.to_thread()` (no `httpx`/`aiohttp`).

## Reliability & timeout architecture (critical lesson)

The graph execution loop ([`_execute_graph`](src/deep_research_agent/runtime/service.py:147)) and all service calls **must** have explicit `asyncio.wait_for` / `asyncio.timeout` wrappers. Relying solely on `urllib_request.urlopen(timeout=...)` is **not sufficient** — the TCP socket timeout does not propagate to the asyncio coroutine level and the `astream` loop hangs indefinitely.

### Three-layer timeout strategy

| Layer | Where | Mechanism | Default |
|-------|-------|-----------|---------|
| Graph-level | [`_execute_graph`](src/deep_research_agent/runtime/service.py:176) in `runtime/service.py` | `asyncio.timeout(max(60, llm_request_timeout_seconds * 3))` wraps the `astream()` loop | 1800s (30min) with 600s LLM timeout |
| LLM call | [`_http_json_request`](src/deep_research_agent/services/llm.py:584) in `services/llm.py` | `asyncio.wait_for(task, timeout=timeout_seconds)` + `task.cancel()` on timeout | Configured by `DEEP_RESEARCH_LLM_REQUEST_TIMEOUT_SECONDS` (default 600) |
| Search & extraction | [`_post_json`](src/deep_research_agent/services/search.py:162) / [`_fetch_text`](src/deep_research_agent/services/extraction.py:81) | `asyncio.wait_for(asyncio.to_thread(...), timeout=35)` | 35s |

### Rule
Every `asyncio.to_thread()` performing a network-blocking call **must** be wrapped in `asyncio.wait_for()`. This is the single most important reliability pattern in the codebase.

## Test quirks

- Some tests write artifacts under `tests/.artifacts/` (gitignored).
- `test_compose_integration.py` requires Docker (skipped otherwise / fails on Windows).
- `test_persistence.py` monkeypatches `importlib` to simulate missing optional deps.
- Runtime integration tests (`test_runtime_flow.py`, `test_web_app.py`, `test_cli.py`) exercise the full loop end-to-end with fake services.
- `test_web_app.py` requires the Vue frontend build at `frontend/dist/` — falls back to 404 if not built.
