#!/usr/bin/env bash
set -euo pipefail

# Auto-load staging.env when present.
if [[ -f "staging.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source staging.env
  set +a
fi

if [[ -z "${BASE_URL:-}" ]]; then
  echo "BASE_URL is required (example: https://api-staging.example.com)" >&2
  exit 1
fi

if [[ -z "${ADMIN_TOKEN:-}" || -z "${QA_TOKEN:-}" || -z "${OPS_TOKEN:-}" || -z "${VIEWER_TOKEN:-}" ]]; then
  echo "ADMIN_TOKEN, QA_TOKEN, OPS_TOKEN, and VIEWER_TOKEN are required." >&2
  exit 1
fi

BATCH_CODE="${BATCH_CODE:-BATCH-2026-02-0012}"
OUT_DIR="${OUT_DIR:-storage/reports/staging}"

echo "Running staging release gate"
echo "BASE_URL=${BASE_URL}"
echo "BATCH_CODE=${BATCH_CODE}"
echo "OUT_DIR=${OUT_DIR}"

BASE_URL="${BASE_URL}" \
ADMIN_TOKEN="${ADMIN_TOKEN}" \
QA_TOKEN="${QA_TOKEN}" \
OPS_TOKEN="${OPS_TOKEN}" \
VIEWER_TOKEN="${VIEWER_TOKEN}" \
BATCH_CODE="${BATCH_CODE}" \
OUT_DIR="${OUT_DIR}" \
./scripts/release_gate.sh
