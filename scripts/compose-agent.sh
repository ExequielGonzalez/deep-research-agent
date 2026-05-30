#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

compose() {
  docker compose "$@"
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/compose-agent.sh bootstrap
  ./scripts/compose-agent.sh run --query "..."
  ./scripts/compose-agent.sh resume --thread-id <thread_id> --decision approve --summary "..."
  ./scripts/compose-agent.sh list-pending [--limit N]
  ./scripts/compose-agent.sh shell
  ./scripts/compose-agent.sh logs [service]
  ./scripts/compose-agent.sh down

Commands:
  bootstrap     Start postgres and wait until it is ready.
  run           Execute `deep-research-agent run` inside the app container.
  resume        Execute `deep-research-agent resume` inside the app container.
  list-pending  Execute `deep-research-agent list-pending` inside the app container.
  shell         Open an interactive bash shell inside the app image.
  logs          Show docker compose logs.
  down          Stop the compose stack.
EOF
}

ensure_postgres() {
  compose up -d postgres >/dev/null

  local attempts=30
  until compose exec -T postgres pg_isready \
    -U "${POSTGRES_USER:-postgres}" \
    -d "${POSTGRES_DB:-deep_research}" >/dev/null 2>&1; do
    attempts=$((attempts - 1))
    if [[ "${attempts}" -le 0 ]]; then
      echo "Postgres did not become ready in time." >&2
      exit 1
    fi
    sleep 2
  done
}

main() {
  local command="${1:-}"
  if [[ -z "${command}" ]]; then
    usage
    exit 1
  fi

  shift || true

  case "${command}" in
    bootstrap)
      ensure_postgres
      compose ps
      ;;
    run)
      ensure_postgres
      compose run --rm -T app run "$@"
      ;;
    resume)
      ensure_postgres
      compose run --rm -T app resume "$@"
      ;;
    list-pending)
      ensure_postgres
      compose run --rm -T app list-pending "$@"
      ;;
    shell)
      ensure_postgres
      compose run --rm --entrypoint bash app "$@"
      ;;
    logs)
      compose logs "$@"
      ;;
    down)
      compose down "$@"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
