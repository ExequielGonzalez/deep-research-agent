# Deep Research Agent Compose Workflow

## Core commands

```bash
./scripts/compose-agent.sh bootstrap
./scripts/compose-agent.sh run --query "Assess the AI infrastructure market"
./scripts/compose-agent.sh list-pending
./scripts/compose-agent.sh resume --thread-id <thread_id> --decision approve --summary "Proceed"
./scripts/compose-agent.sh down
```

## Execution model

1. `bootstrap` starts the `postgres` service and waits for `pg_isready`.
2. `run` starts an ephemeral `app` container and executes `deep-research-agent run`.
3. The CLI persists state in Postgres and returns JSON.
4. If the runtime pauses for human input, the JSON includes the `thread_id`.
5. `resume` restarts an ephemeral `app` container and continues the same persisted thread.

## Environment expectations

- `.env` should be created from `.env.example`.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` drive both the database container and the runtime DSN inside Compose.
- `DEEP_RESEARCH_OPENAI_API_KEY` is the expected variable for OpenAI mode.
- Compose defaults use Postgres on the internal hostname `postgres`.
- SQLite remains supported by the application, but the compose workflow defaults to Postgres so checkpoints and run metadata survive container lifecycles.

## Troubleshooting

| Problem | Likely cause | Fix |
| --- | --- | --- |
| App cannot connect to Postgres | Stack not bootstrapped yet | Run `./scripts/compose-agent.sh bootstrap` |
| OpenAI provider error | `DEEP_RESEARCH_OPENAI_API_KEY` missing | Add the key to `.env` |
| No API-backed search provider configured | Search provider defaults to `none` | Keep `none` for DuckDuckGo fallback, or set Tavily/Serper keys |
| Need an interactive container | CLI entrypoint is active by default | Run `./scripts/compose-agent.sh shell` |
