#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE="${IMAGE:-deep-research-agent:compose}"
MODEL_NAME="${MODEL_NAME:-${DEEP_RESEARCH_MODEL_NAME:-qwen3.5-9b-q8}}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-${DEEP_RESEARCH_OPENAI_BASE_URL:-http://127.0.0.1:8085/v1}}"
OPENAI_API_KEY="${OPENAI_API_KEY:-${DEEP_RESEARCH_OPENAI_API_KEY:-local}}"
SEARCH_PROVIDER="${SEARCH_PROVIDER:-${DEEP_RESEARCH_DEFAULT_SEARCH_PROVIDER:-none}}"
LOCAL_STATE_DIR="${LOCAL_STATE_DIR:-/tmp/deep-research-agent-host}"
LLM_REQUEST_TIMEOUT_SECONDS="${LLM_REQUEST_TIMEOUT_SECONDS:-${DEEP_RESEARCH_LLM_REQUEST_TIMEOUT_SECONDS:-600}}"

slugify() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/host-llamacpp-agent.sh run --query "..."
  ./scripts/host-llamacpp-agent.sh resume --thread-id <thread_id> --decision approve --summary "..."
  ./scripts/host-llamacpp-agent.sh list-pending [--limit N]
  ./scripts/host-llamacpp-agent.sh shell

Environment overrides:
  MODEL_NAME         llama.cpp model id exposed by the OpenAI-compatible server
  OPENAI_BASE_URL    default: http://127.0.0.1:8085/v1
  OPENAI_API_KEY     default: local
  LOCAL_STATE_DIR    default: /tmp/deep-research-agent-host
  SEARCH_PROVIDER    default: none
  LLM_REQUEST_TIMEOUT_SECONDS  default: 600
  IMAGE              default: deep-research-agent:compose

Examples:
  MODEL_NAME=qwopus3.5-9b-v3-q6 ./scripts/host-llamacpp-agent.sh run --query "Evaluate llama.cpp as an OpenAI-compatible local inference backend"
  MODEL_NAME=qwen3.5-9b-q8 ./scripts/host-llamacpp-agent.sh list-pending --limit 5
EOF
}

docker_agent() {
  local model_slug db_url
  model_slug="$(slugify "${MODEL_NAME}")"
  mkdir -p "${LOCAL_STATE_DIR}"
  db_url="sqlite+aiosqlite:////app/.local/${model_slug}.sqlite3"

  docker run --rm \
    --network host \
    -v "${REPO_ROOT}:/app" \
    -v "${LOCAL_STATE_DIR}:/app/.local" \
    -w /app \
    -e PYTHONPATH=/app/src \
    -e DEEP_RESEARCH_MODEL_PROVIDER=openai \
    -e DEEP_RESEARCH_MODEL_NAME="${MODEL_NAME}" \
    -e DEEP_RESEARCH_OPENAI_BASE_URL="${OPENAI_BASE_URL}" \
    -e DEEP_RESEARCH_OPENAI_API_KEY="${OPENAI_API_KEY}" \
    -e DEEP_RESEARCH_PERSISTENCE_BACKEND=sqlite \
    -e DEEP_RESEARCH_SQLITE_DB_URL="${db_url}" \
    -e DEEP_RESEARCH_DEFAULT_SEARCH_PROVIDER="${SEARCH_PROVIDER}" \
    -e DEEP_RESEARCH_LLM_REQUEST_TIMEOUT_SECONDS="${LLM_REQUEST_TIMEOUT_SECONDS}" \
    "$@"
}

main() {
  local command="${1:-}"
  if [[ -z "${command}" ]]; then
    usage
    exit 1
  fi
  shift || true

  case "${command}" in
    run|resume|list-pending)
      docker_agent --entrypoint python "${IMAGE}" -m deep_research_agent "${command}" "$@"
      ;;
    shell)
      docker_agent --entrypoint bash "${IMAGE}" "$@"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"