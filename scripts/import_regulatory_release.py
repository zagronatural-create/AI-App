#!/usr/bin/env python3
"""Import, approve, and optionally publish regulatory threshold releases."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _json_request(
    url: str,
    *,
    token: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> tuple[int, dict]:
    req_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = Request(url=url, method=method, data=data, headers=req_headers)
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


def _encode_multipart(fields: dict[str, str], file_field: str, filename: str, file_bytes: bytes) -> tuple[str, bytes]:
    boundary = f"----supply-intel-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                (value or "").encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
                "Content-Type: text/csv\r\n\r\n"
            ).encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return boundary, b"".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import and publish regulatory thresholds")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.getenv("ADMIN_TOKEN", ""))
    parser.add_argument("--csv-file", required=True)
    parser.add_argument("--standard-name", required=True, choices=["FSSAI", "EU", "CODEX", "HACCP_INTERNAL"])
    parser.add_argument("--release-code", required=True)
    parser.add_argument("--document-title", required=True)
    parser.add_argument("--effective-from", required=True, help="YYYY-MM-DD")
    parser.add_argument("--effective-to", default="")
    parser.add_argument("--jurisdiction", default="")
    parser.add_argument("--source-authority", default="")
    parser.add_argument("--document-url", default="")
    parser.add_argument("--publication-date", default="", help="YYYY-MM-DD")
    parser.add_argument("--notes", default="")
    parser.add_argument("--imported-by", default=os.getenv("REG_IMPORT_USER", ""))
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--approval-notes", default="")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()

    if not args.token:
        print("Missing token: pass --token or set ADMIN_TOKEN", file=sys.stderr)
        return 2

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}", file=sys.stderr)
        return 2

    fields = {
        "standard_name": args.standard_name,
        "release_code": args.release_code,
        "document_title": args.document_title,
        "effective_from": args.effective_from,
        "effective_to": args.effective_to,
        "jurisdiction": args.jurisdiction,
        "source_authority": args.source_authority,
        "document_url": args.document_url,
        "publication_date": args.publication_date,
        "notes": args.notes,
        "imported_by": args.imported_by,
    }
    # Avoid sending empty form values that could overwrite defaults.
    fields = {k: v for k, v in fields.items() if v}

    boundary, payload = _encode_multipart(fields, "file", csv_path.name, csv_path.read_bytes())
    import_url = f"{args.base_url.rstrip('/')}/api/v1/compliance/regulatory/releases/import-csv"
    code = 0
    imported: dict[str, Any] = {}
    req = Request(
        url=import_url,
        method="POST",
        data=payload,
        headers={
            "Authorization": f"Bearer {args.token}",
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urlopen(req, timeout=120) as resp:
            code = resp.getcode()
            raw = resp.read().decode("utf-8")
            imported = json.loads(raw) if raw else {}
    except HTTPError as exc:
        code = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            imported = json.loads(raw)
        except Exception:
            imported = {"error": raw}
    except URLError as exc:
        print(f"Network error during import: {exc}", file=sys.stderr)
        return 2

    if code != 200:
        print(json.dumps({"step": "import", "status_code": code, "response": imported}, indent=2))
        return 1

    print(json.dumps({"step": "import", "status_code": code, "response": imported}, indent=2))
    release_id = imported.get("release_id")
    if not release_id:
        print("Import response missing release_id", file=sys.stderr)
        return 1

    coverage_url = f"{args.base_url.rstrip('/')}/api/v1/compliance/regulatory/releases/{release_id}/coverage"
    cov_code, coverage = _json_request(coverage_url, token=args.token, method="GET")
    print(json.dumps({"step": "coverage", "status_code": cov_code, "response": coverage}, indent=2))
    if cov_code != 200:
        return 1
    if (args.approve or args.publish) and not coverage.get("ready_for_approval", False) and not args.allow_incomplete:
        print(
            "Coverage check failed; refusing approve/publish. Use --allow-incomplete to override.",
            file=sys.stderr,
        )
        return 1

    if args.publish and not args.approve:
        args.approve = True

    if args.approve:
        approve_url = f"{args.base_url.rstrip('/')}/api/v1/compliance/regulatory/releases/{release_id}/approve"
        approve_payload = {"notes": args.approval_notes} if args.approval_notes else {}
        code, approved = _json_request(
            approve_url,
            token=args.token,
            method="POST",
            payload=approve_payload,
        )
        print(json.dumps({"step": "approve", "status_code": code, "response": approved}, indent=2))
        if code != 200:
            return 1

    if args.publish:
        publish_url = f"{args.base_url.rstrip('/')}/api/v1/compliance/regulatory/releases/{release_id}/publish"
        code, published = _json_request(publish_url, token=args.token, method="POST", payload={})
        print(json.dumps({"step": "publish", "status_code": code, "response": published}, indent=2))
        if code != 200:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
