#!/usr/bin/env python3
"""Validate regulatory parameter coverage and unit normalization."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _json_request(url: str, token: str, timeout: int = 60) -> tuple[int, dict[str, Any]]:
    req = Request(
        url=url,
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.getcode(), json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"error": raw}
        return exc.code, parsed
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Check active regulatory coverage")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.getenv("ADMIN_TOKEN", ""))
    parser.add_argument("--as-of", default="", help="YYYY-MM-DD")
    parser.add_argument("--product-category", default="")
    parser.add_argument("--release-id", default="")
    args = parser.parse_args()

    if not args.token:
        print("Missing token: pass --token or set ADMIN_TOKEN", file=sys.stderr)
        return 2

    query = {}
    if args.as_of:
        query["as_of"] = args.as_of
    if args.product_category:
        query["product_category"] = args.product_category

    base = args.base_url.rstrip("/")
    active_url = f"{base}/api/v1/compliance/regulatory/coverage/active"
    requirements_url = f"{base}/api/v1/compliance/regulatory/coverage/requirements"
    if query:
        qs = urlencode(query)
        active_url = f"{active_url}?{qs}"
        requirements_url = f"{requirements_url}?{qs}"

    code, active = _json_request(active_url, args.token)
    print(json.dumps({"step": "active_coverage", "status_code": code, "response": active}, indent=2))
    if code != 200:
        return 1

    code, reqs = _json_request(requirements_url, args.token)
    print(json.dumps({"step": "requirements", "status_code": code, "response": reqs}, indent=2))
    if code != 200:
        return 1

    if args.release_id:
        release_url = f"{base}/api/v1/compliance/regulatory/releases/{args.release_id}/coverage"
        code, release = _json_request(release_url, args.token)
        print(json.dumps({"step": "release_coverage", "status_code": code, "response": release}, indent=2))
        if code != 200:
            return 1

    summary = active.get("summary", {})
    if summary.get("requirement_rows", 0) > 0 and summary.get("fully_covered_rows", 0) != summary.get("requirement_rows", 0):
        print("Coverage incomplete for at least one required parameter row.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
