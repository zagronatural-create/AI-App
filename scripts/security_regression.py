#!/usr/bin/env python3
"""Security regression checks for auth and role policy.

Validates unauthenticated and role-restricted behavior against critical endpoints.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass
class Case:
    name: str
    method: str
    path: str
    token: str | None
    body: dict | None
    expected_codes: tuple[int, ...]


def request(base_url: str, case: Case) -> tuple[int, str]:
    url = f"{base_url.rstrip('/')}{case.path}"
    headers = {"Accept": "application/json"}
    data = None
    if case.body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(case.body).encode("utf-8")
    if case.token:
        headers["Authorization"] = f"Bearer {case.token}"

    req = Request(url, method=case.method, headers=headers, data=data)
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--batch-code", default="BATCH-2026-02-0012")
    parser.add_argument("--admin-token", default="dev-admin-token")
    parser.add_argument("--viewer-token", default="viewer-token")
    parser.add_argument("--qa-token", default="qa-token")
    parser.add_argument("--ops-token", default="ops-token")
    args = parser.parse_args()

    cases = [
        Case(
            name="unauth_write_blocked",
            method="POST",
            path="/api/v1/automation/run-daily-async?actor_id=security_check",
            token=None,
            body=None,
            expected_codes=(401,),
        ),
        Case(
            name="viewer_cannot_run_automation",
            method="POST",
            path="/api/v1/automation/run-daily-async?actor_id=security_check",
            token=args.viewer_token,
            body=None,
            expected_codes=(403,),
        ),
        Case(
            name="ops_can_run_automation",
            method="POST",
            path="/api/v1/automation/run-daily-async?actor_id=security_check",
            token=args.ops_token,
            body=None,
            expected_codes=(200,),
        ),
        Case(
            name="viewer_cannot_ingest_ccp",
            method="POST",
            path="/api/v1/ccp/logs",
            token=args.viewer_token,
            body={
                "batch_code": args.batch_code,
                "ccp_code": "DRYING",
                "metric_name": "temperature",
                "metric_value": 65.8,
                "unit": "C",
                "measured_at": "2026-02-23T09:30:00Z",
                "operator_id": "security_check",
                "source": "script",
            },
            expected_codes=(403,),
        ),
        Case(
            name="qa_can_ingest_ccp",
            method="POST",
            path="/api/v1/ccp/logs",
            token=args.qa_token,
            body={
                "batch_code": args.batch_code,
                "ccp_code": "DRYING",
                "metric_name": "temperature",
                "metric_value": 65.8,
                "unit": "C",
                "measured_at": "2026-02-23T09:30:00Z",
                "operator_id": "security_check",
                "source": "script",
            },
            expected_codes=(200,),
        ),
        Case(
            name="viewer_can_read_audit",
            method="GET",
            path="/api/v1/audit/events?limit=2",
            token=args.viewer_token,
            body=None,
            expected_codes=(200,),
        ),
        Case(
            name="admin_can_generate_pack",
            method="POST",
            path="/api/v1/audit/packs/generate",
            token=args.admin_token,
            body={"limit": 100, "notes": "security regression"},
            expected_codes=(200,),
        ),
    ]

    passed = 0
    for case in cases:
        code, body = request(args.base_url, case)
        ok = code in case.expected_codes
        state = "PASS" if ok else "FAIL"
        print(f"[{state}] {case.name}: status={code}, expected={case.expected_codes}")
        if not ok:
            print(f"  body={body[:500]}")
        else:
            passed += 1

    total = len(cases)
    print(f"Security regression result: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
