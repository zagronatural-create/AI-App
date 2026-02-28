#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
QA_TOKEN="${QA_TOKEN:-}"
VIEWER_TOKEN="${VIEWER_TOKEN:-}"
WINDOW_HOURS="${WINDOW_HOURS:-24}"
LIMIT="${LIMIT:-10000}"
OUT_DIR="${OUT_DIR:-storage/reports/compliance-packs}"
NOTES="${NOTES:-scheduled compliance export pack}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ -z "${QA_TOKEN}" || -z "${VIEWER_TOKEN}" ]]; then
  echo "ERROR: QA_TOKEN and VIEWER_TOKEN are required."
  echo "Usage:"
  echo "  BASE_URL=https://your-api QA_TOKEN=<qa> VIEWER_TOKEN=<viewer> WINDOW_HOURS=24 ./scripts/compliance_pack_scheduler.sh"
  exit 2
fi

mkdir -p "${OUT_DIR}"

FROM_TS="$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
import os
h = int(os.getenv("WINDOW_HOURS", "24"))
print((datetime.now(timezone.utc) - timedelta(hours=h)).isoformat().replace("+00:00", "Z"))
PY
)"
TO_TS="$(python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
PY
)"

GEN_RESP="${OUT_DIR}/pack_generate_${TS}.json"
VERIFY_RESP="${OUT_DIR}/pack_verify_${TS}.json"
SUMMARY_OUT="${OUT_DIR}/compliance_pack_${TS}.txt"
CHECKSUMS_OUT="${OUT_DIR}/checksums_${TS}.json"

GEN_PAYLOAD="$(FROM_TS="${FROM_TS}" TO_TS="${TO_TS}" LIMIT="${LIMIT}" NOTES="${NOTES}" python3 - <<'PY'
import json
import os
print(json.dumps({
  "from_ts": os.environ["FROM_TS"],
  "to_ts": os.environ["TO_TS"],
  "limit": int(os.environ.get("LIMIT", "10000")),
  "notes": os.environ.get("NOTES", "scheduled compliance export pack")
}))
PY
)"

curl -fsS -X POST "${BASE_URL}/api/v1/audit/packs/generate" \
  -H "Authorization: Bearer ${QA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${GEN_PAYLOAD}" \
  > "${GEN_RESP}"

PACK_ID="$(GEN_RESP="${GEN_RESP}" python3 - <<'PY'
import json
import os
with open(os.environ["GEN_RESP"], "r", encoding="utf-8") as f:
    payload = json.load(f)
pack_id = payload.get("pack_id")
if not pack_id:
    raise SystemExit("Missing pack_id in generate response")
print(pack_id)
PY
)"

curl -fsS -X POST "${BASE_URL}/api/v1/audit/packs/${PACK_ID}/verify" \
  -H "Authorization: Bearer ${VIEWER_TOKEN}" \
  -H "Content-Type: application/json" \
  > "${VERIFY_RESP}"

CHECKSUMS_STATUS="$(curl -s -o "${CHECKSUMS_OUT}" -w "%{http_code}" \
  "${BASE_URL}/api/v1/audit/packs/${PACK_ID}/download/checksums.json" \
  -H "Authorization: Bearer ${VIEWER_TOKEN}")"

BASE_URL="${BASE_URL}" PACK_ID="${PACK_ID}" FROM_TS="${FROM_TS}" TO_TS="${TO_TS}" WINDOW_HOURS="${WINDOW_HOURS}" \
GEN_RESP="${GEN_RESP}" VERIFY_RESP="${VERIFY_RESP}" CHECKSUMS_STATUS="${CHECKSUMS_STATUS}" \
python3 - <<'PY' > "${SUMMARY_OUT}"
import json
import os
from datetime import datetime, timezone

gen_path = os.environ["GEN_RESP"]
verify_path = os.environ["VERIFY_RESP"]
checksums_status = os.environ["CHECKSUMS_STATUS"]
base_url = os.environ["BASE_URL"]
pack_id = os.environ["PACK_ID"]
from_ts = os.environ["FROM_TS"]
to_ts = os.environ["TO_TS"]
window_hours = os.environ["WINDOW_HOURS"]

with open(gen_path, "r", encoding="utf-8") as f:
    gen = json.load(f)
with open(verify_path, "r", encoding="utf-8") as f:
    verify = json.load(f)

valid = bool(verify.get("valid", False))
missing_files = verify.get("missing_files", [])
mismatches = verify.get("mismatches", [])

print("Compliance Export Pack Report")
print(f"Generated (UTC): {datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}")
print(f"Base URL: {base_url}")
print(f"Window hours: {window_hours}")
print(f"From: {from_ts}")
print(f"To: {to_ts}")
print(f"Pack ID: {pack_id}")
print(f"Verify valid: {valid}")
print(f"Missing files: {missing_files}")
print(f"Mismatches: {mismatches}")
print(f"checksums.json download status: {checksums_status}")
print("Disclaimer: Export pack assists audit documentation; not legal certification.")

if (not valid) or missing_files or mismatches or checksums_status != "200":
    raise SystemExit(1)
PY

echo "Artifacts:"
echo "- ${SUMMARY_OUT}"
echo "- ${GEN_RESP}"
echo "- ${VERIFY_RESP}"
echo "- ${CHECKSUMS_OUT}"
echo "Pack ID: ${PACK_ID}"
echo "Compliance pack: PASS"
