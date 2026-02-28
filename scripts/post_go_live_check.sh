#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
RUN_LIMIT="${RUN_LIMIT:-10}"
OUT_DIR="${OUT_DIR:-storage/reports/post-go-live}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

SUMMARY_OUT="${OUT_DIR}/post_go_live_check_${TS}.txt"
JSON_OUT="${OUT_DIR}/post_go_live_check_${TS}.json"

if [[ -z "${ADMIN_TOKEN}" ]]; then
  echo "ERROR: ADMIN_TOKEN is required."
  echo "Usage:"
  echo "  BASE_URL=https://your-api ADMIN_TOKEN=<token> ./scripts/post_go_live_check.sh"
  exit 2
fi

mkdir -p "${OUT_DIR}"

set +e
python3 - "${BASE_URL}" "${ADMIN_TOKEN}" "${RUN_LIMIT}" "${JSON_OUT}" <<'PY' | tee "${SUMMARY_OUT}"
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

base_url = sys.argv[1].rstrip("/")
admin_token = sys.argv[2]
run_limit = int(sys.argv[3])
json_out = sys.argv[4]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    normalized = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _decode_body(raw: bytes) -> object:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text[:500]}


def _get(path: str, token: str | None = None) -> tuple[int | None, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"{base_url}{path}", headers=headers, method="GET")
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.getcode(), _decode_body(resp.read())
    except HTTPError as exc:
        return exc.code, _decode_body(exc.read())
    except URLError as exc:
        return None, {"error": str(exc.reason)}


results: list[dict] = []
now = datetime.now(timezone.utc)
today_utc = now.date().isoformat()
window_start = now - timedelta(hours=24)


def add_result(name: str, ok: bool, status_code: int | None, detail: object) -> None:
    results.append(
        {
            "name": name,
            "ok": ok,
            "status_code": status_code,
            "detail": detail,
        }
    )


# 1) Health check
code, payload = _get("/health")
ok = code == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
add_result("health", ok, code, payload)

# 2) Automation status
code, payload = _get("/api/v1/automation/status", token=admin_token)
last_status = None
if isinstance(payload, dict):
    last_run = payload.get("last_run")
    if isinstance(last_run, dict):
        last_status = last_run.get("status")
ok = (
    code == 200
    and isinstance(payload, dict)
    and isinstance(payload.get("daily_cycle_running"), bool)
    and last_status != "failed"
)
add_result(
    "automation_status",
    ok,
    code,
    {
        "daily_cycle_running": payload.get("daily_cycle_running") if isinstance(payload, dict) else None,
        "last_run_status": last_status,
    },
)

# 3) Recent automation runs (24h)
code, payload = _get(f"/api/v1/automation/runs?limit={run_limit}", token=admin_token)
rows = payload.get("rows", []) if isinstance(payload, dict) else []
recent_rows = []
for row in rows:
    if not isinstance(row, dict):
        continue
    started_at = _parse_iso(str(row.get("started_at")))
    if started_at and started_at >= window_start:
        recent_rows.append(row)

failed_recent = [r for r in recent_rows if str(r.get("status", "")).lower() == "failed"]
ok = code == 200 and isinstance(rows, list) and len(failed_recent) == 0
add_result(
    "automation_runs_recent_24h",
    ok,
    code,
    {
        "run_limit": run_limit,
        "rows_total": len(rows) if isinstance(rows, list) else None,
        "rows_recent_24h": len(recent_rows),
        "failed_recent_24h": len(failed_recent),
        "failed_run_ids": [str(r.get("run_id")) for r in failed_recent][:5],
    },
)

# 4) KPI freshness + recall KPI threshold
code, payload = _get("/api/v1/kpi/daily", token=admin_token)
kpi_rows = payload.get("rows", []) if isinstance(payload, dict) else []
today_rows = [r for r in kpi_rows if isinstance(r, dict) and str(r.get("kpi_date")) == today_utc]
latest_row = kpi_rows[0] if isinstance(kpi_rows, list) and kpi_rows else {}
recall_ms = latest_row.get("avg_recall_trace_time_ms") if isinstance(latest_row, dict) else None

recall_ok = False
if recall_ms is not None:
    try:
        recall_ok = float(recall_ms) < 10_000
    except (TypeError, ValueError):
        recall_ok = False

ok = (
    code == 200
    and isinstance(kpi_rows, list)
    and len(kpi_rows) > 0
    and len(today_rows) > 0
    and recall_ok
)
add_result(
    "kpi_daily_freshness",
    ok,
    code,
    {
        "rows_total": len(kpi_rows) if isinstance(kpi_rows, list) else None,
        "today_rows": len(today_rows),
        "latest_kpi_date": latest_row.get("kpi_date") if isinstance(latest_row, dict) else None,
        "latest_avg_recall_trace_time_ms": recall_ms,
        "recall_target_ms": "<10000",
    },
)

passed = sum(1 for r in results if r["ok"])
total = len(results)

report = {
    "context": {
        "generated_at": _iso_now(),
        "base_url": base_url,
        "run_limit": run_limit,
        "window_hours": 24,
    },
    "summary": {
        "total": total,
        "passed": passed,
        "failed": total - passed,
    },
    "results": results,
}

with open(json_out, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("Post-Go-Live Health Check")
print(f"Timestamp (UTC): {report['context']['generated_at']}")
print(f"Base URL: {base_url}")
print(f"Checks passed: {passed}/{total}")
for result in results:
    state = "PASS" if result["ok"] else "FAIL"
    print(
        f"- [{state}] {result['name']} | status={result['status_code']} | "
        f"{json.dumps(result['detail'], ensure_ascii=True)}"
    )
print(f"Wrote report: {json_out}")

sys.exit(0 if passed == total else 1)
PY
PY_RC=$?
set -e

echo "Artifacts:"
echo "- ${SUMMARY_OUT}"
echo "- ${JSON_OUT}"

if [[ ${PY_RC} -ne 0 ]]; then
  echo "Post-go-live check: FAIL"
  exit 1
fi

echo "Post-go-live check: PASS"
