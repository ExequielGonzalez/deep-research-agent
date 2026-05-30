#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE="${IMAGE:-deep-research-agent:compose}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-${DEEP_RESEARCH_OPENAI_BASE_URL:-http://127.0.0.1:8085/v1}}"
OPENAI_API_KEY="${OPENAI_API_KEY:-${DEEP_RESEARCH_OPENAI_API_KEY:-local}}"
LOCAL_STATE_DIR="${LOCAL_STATE_DIR:-/tmp/deep-research-agent-web}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-8000}"
MODEL_NAME="${MODEL_NAME:-${DEEP_RESEARCH_MODEL_NAME:-qwen3.5-9b-q8}}"
LLM_REQUEST_TIMEOUT_SECONDS="${LLM_REQUEST_TIMEOUT_SECONDS:-${DEEP_RESEARCH_LLM_REQUEST_TIMEOUT_SECONDS:-600}}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/host-llamacpp-web.sh

Environment overrides:
  IMAGE              default: deep-research-agent:compose
  OPENAI_BASE_URL    default: http://127.0.0.1:8085/v1
  OPENAI_API_KEY     default: local
  LOCAL_STATE_DIR    default: /tmp/deep-research-agent-web
  WEB_HOST           default: 0.0.0.0
  WEB_PORT           default: 8000
  MODEL_NAME         default form model for the web UI
  LLM_REQUEST_TIMEOUT_SECONDS  default: 600

Example:
  WEB_PORT=8010 MODEL_NAME=qwopus3.5-9b-v3-q6 ./scripts/host-llamacpp-web.sh
EOF
}

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

mkdir -p "${LOCAL_STATE_DIR}"

exec docker run --rm \
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
  -e DEEP_RESEARCH_SQLITE_DB_URL='sqlite+aiosqlite:///./.local/web.sqlite3' \
  -e DEEP_RESEARCH_LLM_REQUEST_TIMEOUT_SECONDS="${LLM_REQUEST_TIMEOUT_SECONDS}" \
  --entrypoint deep-research-agent-web \
  "${IMAGE}" \
  --host "${WEB_HOST}" \
  --port "${WEB_PORT}"