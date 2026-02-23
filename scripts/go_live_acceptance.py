#!/usr/bin/env python3
"""Go-live acceptance check for Supply Intelligence platform.

Runs critical API checks and outputs a machine-readable + human-readable summary.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class CheckResult:
    name: str
    ok: bool
    status_code: int | None
    detail: str


def _headers(token: str | None = None, content_type: str | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(
    base_url: str,
    method: str,
    path: str,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    accept_csv: bool = False,
) -> tuple[int, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    data = None
    content_type = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        content_type = "application/json"

    req = Request(url=url, method=method, data=data, headers=_headers(token, content_type))
    try:
        with urlopen(req, timeout=30) as resp:
            payload = resp.read()
            code = resp.getcode()
            ctype = resp.headers.get("Content-Type", "")
            if accept_csv or "text/csv" in ctype:
                return code, payload.decode("utf-8", errors="replace")
            if payload:
                return code, json.loads(payload.decode("utf-8"))
            return code, {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return exc.code, parsed
    except URLError as exc:
        raise RuntimeError(f"Network error for {method} {url}: {exc}") from exc


def run_checks(args: argparse.Namespace) -> tuple[list[CheckResult], dict[str, Any]]:
    results: list[CheckResult] = []
    context: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "batch_code": args.batch_code,
        "pack_id": None,
    }

    def add(name: str, ok: bool, status_code: int | None, detail: str) -> None:
        results.append(CheckResult(name=name, ok=ok, status_code=status_code, detail=detail))

    # 1. Health
    code, payload = _request_json(args.base_url, "GET", "/health")
    add("health", code == 200 and payload.get("status") == "ok", code, str(payload))

    # 2. Auth check (optional)
    if args.admin_token:
        code, payload = _request_json(args.base_url, "GET", "/api/v1/auth/whoami", token=args.admin_token)
        add("auth_whoami", code == 200, code, str(payload))
    else:
        add("auth_whoami", True, None, "Skipped (no admin token provided)")

    # 3. Trace full
    code, payload = _request_json(args.base_url, "GET", f"/api/v1/trace/batch/{args.batch_code}/full")
    ok = code == 200 and payload.get("batch_code") == args.batch_code
    add("trace_full", ok, code, f"customers={len(payload.get('forward', {}).get('customers', [])) if isinstance(payload, dict) else 'n/a'}")

    # 4. Compliance comparison
    code, payload = _request_json(args.base_url, "GET", f"/api/v1/compliance/batch/{args.batch_code}/comparison")
    ok = code == 200 and isinstance(payload.get("comparison"), list)
    add("compliance_comparison", ok, code, f"params={payload.get('summary', {}).get('total_parameters') if isinstance(payload, dict) else 'n/a'}")

    # 5. CCP log ingest (requires QA token if auth enabled)
    ccp_token = args.qa_token or args.admin_token
    ccp_body = {
        "batch_code": args.batch_code,
        "ccp_code": "DRYING",
        "metric_name": "temperature",
        "metric_value": 66.5,
        "unit": "C",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": "go_live_check",
        "source": "script",
    }
    code, payload = _request_json(args.base_url, "POST", "/api/v1/ccp/logs", token=ccp_token, body=ccp_body)
    add("ccp_log_ingest", code == 200, code, str(payload))

    # 6. AI batch score + anomaly run
    ai_token = args.qa_token or args.admin_token
    code, payload = _request_json(args.base_url, "POST", f"/api/v1/ai/batch/{args.batch_code}/score", token=ai_token)
    add("ai_batch_score", code == 200, code, str(payload))

    code, payload = _request_json(
        args.base_url,
        "POST",
        "/api/v1/ai/anomalies/run",
        token=ai_token,
        body={"lookback_hours": 24, "z_threshold": 2.5, "actor_id": "go_live_check"},
    )
    add("ai_anomaly_run", code == 200, code, str(payload))

    # 7. Automation async trigger + status
    ops_token = args.ops_token or args.admin_token
    code, payload = _request_json(
        args.base_url,
        "POST",
        "/api/v1/automation/run-daily-async?actor_id=go_live_check",
        token=ops_token,
    )
    add("automation_trigger", code == 200, code, str(payload))

    code, payload = _request_json(args.base_url, "GET", "/api/v1/automation/status", token=ops_token)
    add("automation_status", code == 200, code, str(payload))

    # 8. Audit pack generate + verify + download
    qa_mgr_token = args.qa_token or args.admin_token
    code, payload = _request_json(
        args.base_url,
        "POST",
        "/api/v1/audit/packs/generate",
        token=qa_mgr_token,
        body={
            "limit": 1000,
            "from_ts": "2026-01-01T00:00:00Z",
            "to_ts": datetime.now(timezone.utc).isoformat(),
            "notes": "Go-live acceptance check",
        },
    )
    pack_ok = code == 200 and isinstance(payload, dict) and payload.get("pack_id")
    pack_id = payload.get("pack_id") if isinstance(payload, dict) else None
    context["pack_id"] = pack_id
    add("audit_pack_generate", pack_ok, code, f"pack_id={pack_id}")

    viewer_token = args.viewer_token or args.admin_token
    if pack_id:
        code, payload = _request_json(
            args.base_url,
            "POST",
            f"/api/v1/audit/packs/{pack_id}/verify",
            token=viewer_token,
        )
        add("audit_pack_verify", code == 200 and payload.get("valid") is True, code, str(payload))

        code, payload = _request_json(
            args.base_url,
            "GET",
            f"/api/v1/audit/packs/{pack_id}/download/checksums.json",
            token=viewer_token,
            accept_csv=True,
        )
        add("audit_pack_download", code == 200 and "audit_events.csv" in str(payload), code, "checksums.json downloaded")
    else:
        add("audit_pack_verify", False, None, "Skipped (no pack_id)")
        add("audit_pack_download", False, None, "Skipped (no pack_id)")

    return results, context


def write_report(out_path: Path, results: list[CheckResult], context: dict[str, Any]) -> None:
    report = {
        "context": context,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.ok),
            "failed": sum(1 for r in results if not r.ok),
        },
        "results": [
            {
                "name": r.name,
                "ok": r.ok,
                "status_code": r.status_code,
                "detail": r.detail,
            }
            for r in results
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run go-live acceptance checks")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--batch-code", default="BATCH-2026-02-0012")
    parser.add_argument("--admin-token", default="")
    parser.add_argument("--qa-token", default="")
    parser.add_argument("--ops-token", default="")
    parser.add_argument("--viewer-token", default="")
    parser.add_argument("--out", default="storage/reports/go_live_acceptance.json")
    args = parser.parse_args()

    try:
        results, context = run_checks(args)
    except Exception:
        print("Fatal error during go-live acceptance run", file=sys.stderr)
        traceback.print_exc()
        return 2

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed

    print("Go-Live Acceptance Report")
    print(f"Base URL: {args.base_url}")
    print(f"Batch: {args.batch_code}")
    print(f"Passed: {passed} / {len(results)}")
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"- [{mark}] {r.name} | status={r.status_code} | {r.detail}")

    out_path = Path(args.out)
    write_report(out_path, results, context)
    print(f"Wrote report: {out_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
