#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
ACTOR_ID="${ACTOR_ID:-ops.scheduler}"
AUTH_TOKEN="${AUTH_TOKEN:-}"

AUTH_ARGS=()
if [[ -n "${AUTH_TOKEN}" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer ${AUTH_TOKEN}")
fi

curl -fsS -X POST "${API_BASE_URL}/api/v1/automation/run-daily-async?actor_id=${ACTOR_ID}" \
  -H 'Accept: application/json' \
  "${AUTH_ARGS[@]}"
