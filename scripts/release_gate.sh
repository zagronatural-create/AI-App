#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
BATCH_CODE="${BATCH_CODE:-BATCH-2026-02-0012}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
QA_TOKEN="${QA_TOKEN:-}"
OPS_TOKEN="${OPS_TOKEN:-}"
VIEWER_TOKEN="${VIEWER_TOKEN:-}"
OUT_DIR="${OUT_DIR:-storage/reports}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

SECURITY_OUT="${OUT_DIR}/security_regression_${TS}.txt"
ACCEPTANCE_OUT="${OUT_DIR}/go_live_acceptance_${TS}.json"
SUMMARY_OUT="${OUT_DIR}/release_gate_${TS}.txt"

mkdir -p "${OUT_DIR}"

{
  echo "Release Gate"
  echo "Timestamp (UTC): ${TS}"
  echo "Base URL: ${BASE_URL}"
  echo "Batch: ${BATCH_CODE}"
  echo
  echo "[1/2] Running security regression..."
} | tee "${SUMMARY_OUT}"

set +e
python3 scripts/security_regression.py \
  --base-url "${BASE_URL}" \
  --batch-code "${BATCH_CODE}" \
  --admin-token "${ADMIN_TOKEN}" \
  --qa-token "${QA_TOKEN}" \
  --ops-token "${OPS_TOKEN}" \
  --viewer-token "${VIEWER_TOKEN}" \
  > "${SECURITY_OUT}" 2>&1
SECURITY_RC=$?
set -e

if [[ ${SECURITY_RC} -eq 0 ]]; then
  echo "Security regression: PASS" | tee -a "${SUMMARY_OUT}"
else
  echo "Security regression: FAIL (see ${SECURITY_OUT})" | tee -a "${SUMMARY_OUT}"
fi

echo "[2/2] Running go-live acceptance..." | tee -a "${SUMMARY_OUT}"

set +e
python3 scripts/go_live_acceptance.py \
  --base-url "${BASE_URL}" \
  --batch-code "${BATCH_CODE}" \
  --admin-token "${ADMIN_TOKEN}" \
  --qa-token "${QA_TOKEN}" \
  --ops-token "${OPS_TOKEN}" \
  --viewer-token "${VIEWER_TOKEN}" \
  --out "${ACCEPTANCE_OUT}" \
  >> "${SUMMARY_OUT}" 2>&1
ACCEPTANCE_RC=$?
set -e

if [[ ${ACCEPTANCE_RC} -eq 0 ]]; then
  echo "Go-live acceptance: PASS" | tee -a "${SUMMARY_OUT}"
else
  echo "Go-live acceptance: FAIL (see ${SUMMARY_OUT} and ${ACCEPTANCE_OUT})" | tee -a "${SUMMARY_OUT}"
fi

echo "Artifacts:" | tee -a "${SUMMARY_OUT}"
echo "- ${SUMMARY_OUT}" | tee -a "${SUMMARY_OUT}"
echo "- ${SECURITY_OUT}" | tee -a "${SUMMARY_OUT}"
echo "- ${ACCEPTANCE_OUT}" | tee -a "${SUMMARY_OUT}"

if [[ ${SECURITY_RC} -ne 0 || ${ACCEPTANCE_RC} -ne 0 ]]; then
  echo "Release gate: FAIL" | tee -a "${SUMMARY_OUT}"
  exit 1
fi

echo "Release gate: PASS" | tee -a "${SUMMARY_OUT}"
