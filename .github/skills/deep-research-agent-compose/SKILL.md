---
name: deep-research-agent-compose
description: Runs this repository's deep research agent through Docker Compose, including stack bootstrap, research execution, pending-run inspection, and resume-by-thread workflow. Use when asked to operate the deep research CLI in this repository, continue an interrupted research thread, inspect pending approvals, or use the agent without relying on a local Python environment.
---

# Deep Research Agent via Docker Compose

## When to Use This Skill

- The task is to run or resume the deep research agent in this repository.
- The user wants the containerized workflow instead of a local `.venv`.
- The agent needs to inspect pending runs, capture a `thread_id`, or continue a HITL checkpoint.

## Prerequisites

1. Ensure Docker Engine and Docker Compose are available.
2. Copy `.env.example` to `.env`.
3. Set `DEEP_RESEARCH_OPENAI_API_KEY` for OpenAI, or switch to `ollama` in `.env`.

## Preferred Workflow

1. Bootstrap the stack:
   ```bash
   ./scripts/compose-agent.sh bootstrap
   ```
2. Start a research run:
   ```bash
   ./scripts/compose-agent.sh run --query "Assess the AI infrastructure market"
   ```
3. Read the JSON output and capture `thread_id` if the run is interrupted.
4. Inspect pending runs when needed:
   ```bash
   ./scripts/compose-agent.sh list-pending
   ```
5. Resume with the captured `thread_id`:
   ```bash
   ./scripts/compose-agent.sh resume --thread-id <thread_id> --decision approve --summary "Proceed"
   ```

## Operational Rules

- Prefer `./scripts/compose-agent.sh` over raw `docker compose` so Postgres readiness is handled consistently.
- Expect `run` and `resume` to emit JSON; use that output as the source of truth for `thread_id`, `status`, and `pending_human_input`.
- Use `approve`, `continue`, `clarify`, or `stop` exactly as supported by the CLI output for the current checkpoint.
- Review [the workflow reference](./references/workflow.md) for the end-to-end handoff and [the HTML implementation document](../../../docs/implementation.html) for architecture and decisions.
