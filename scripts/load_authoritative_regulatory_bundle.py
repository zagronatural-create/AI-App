#!/usr/bin/env python3
"""Load the authoritative regulatory bundle end-to-end (import, approve, publish, validate)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _json_request(
    url: str,
    *,
    token: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> tuple[int, dict[str, Any]]:
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
    boundary = f"----supply-intel-bundle-{uuid.uuid4().hex}"
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


def _load_bundle(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Bundle must be a JSON array")
    return data


def _find_release_id_by_code(base_url: str, token: str, release_code: str, standard_name: str) -> str | None:
    query = urlencode({"limit": 300, "standard_name": standard_name})
    url = f"{base_url}/api/v1/compliance/regulatory/releases?{query}"
    code, body = _json_request(url, token=token)
    if code != 200:
        return None
    for row in body.get("rows", []):
        if row.get("release_code") == release_code:
            return str(row.get("release_id"))
    return None


def _import_release(base_url: str, token: str, release: dict[str, Any], csv_path: Path) -> tuple[int, dict[str, Any]]:
    fields = {
        "standard_name": str(release["standard_name"]),
        "release_code": str(release["release_code"]),
        "document_title": str(release["document_title"]),
        "effective_from": str(release["effective_from"]),
        "effective_to": str(release.get("effective_to", "") or ""),
        "jurisdiction": str(release.get("jurisdiction", "") or ""),
        "source_authority": str(release.get("source_authority", "") or ""),
        "document_url": str(release.get("document_url", "") or ""),
        "publication_date": str(release.get("publication_date", "") or ""),
        "notes": str(release.get("notes", "") or ""),
    }
    fields = {k: v for k, v in fields.items() if v}

    boundary, payload = _encode_multipart(fields, "file", csv_path.name, csv_path.read_bytes())
    req = Request(
        url=f"{base_url}/api/v1/compliance/regulatory/releases/import-csv",
        method="POST",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urlopen(req, timeout=180) as resp:
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
        raise RuntimeError(f"Network error during import for {csv_path.name}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Load authoritative regulatory bundle")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.getenv("ADMIN_TOKEN", ""))
    parser.add_argument(
        "--bundle-file",
        default="data/regulatory/authoritative/authoritative_bundle.json",
        help="Path to bundle manifest JSON",
    )
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.token:
        print("Missing token: pass --token or set ADMIN_TOKEN", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    repo_root = Path(__file__).resolve().parent.parent
    bundle_path = Path(args.bundle_file)
    if not bundle_path.exists():
        print(f"Bundle file not found: {bundle_path}", file=sys.stderr)
        return 2

    if args.publish and not args.approve:
        args.approve = True

    try:
        releases = _load_bundle(bundle_path)
    except Exception as exc:
        print(f"Failed to read bundle: {exc}", file=sys.stderr)
        return 2

    overall_ok = True

    for release in releases:
        try:
            release_code = str(release["release_code"])
            standard_name = str(release["standard_name"])
            csv_path_raw = Path(str(release["csv_file"]))
            csv_path = csv_path_raw if csv_path_raw.is_absolute() else (repo_root / csv_path_raw)
        except KeyError as exc:
            print(json.dumps({"step": "bundle_row", "status": "error", "error": f"Missing key {exc}"}, indent=2))
            overall_ok = False
            continue

        if not csv_path.exists():
            print(
                json.dumps(
                    {
                        "step": "bundle_row",
                        "status": "error",
                        "release_code": release_code,
                        "error": f"CSV not found: {csv_path}",
                    },
                    indent=2,
                )
            )
            overall_ok = False
            continue

        if args.dry_run:
            print(
                json.dumps(
                    {
                        "step": "dry_run",
                        "release_code": release_code,
                        "standard_name": standard_name,
                        "csv_file": str(csv_path),
                    },
                    indent=2,
                )
            )
            continue

        release_id = None
        if args.skip_existing:
            release_id = _find_release_id_by_code(base_url, args.token, release_code, standard_name)

        if not release_id:
            code, imported = _import_release(base_url, args.token, release, csv_path)
            print(json.dumps({"step": "import", "status_code": code, "release_code": release_code, "response": imported}, indent=2))
            if code == 200:
                release_id = imported.get("release_id")
            else:
                existing = _find_release_id_by_code(base_url, args.token, release_code, standard_name)
                if existing:
                    release_id = existing
                else:
                    overall_ok = False
                    continue

        coverage_url = f"{base_url}/api/v1/compliance/regulatory/releases/{release_id}/coverage"
        cov_code, cov_body = _json_request(coverage_url, token=args.token)
        print(json.dumps({"step": "coverage", "status_code": cov_code, "release_id": release_id, "response": cov_body}, indent=2))
        if cov_code != 200:
            overall_ok = False
            continue

        if (args.approve or args.publish) and not cov_body.get("ready_for_approval", False) and not args.allow_incomplete:
            print(
                json.dumps(
                    {
                        "step": "coverage_gate",
                        "status": "blocked",
                        "release_id": release_id,
                        "reason": "Coverage not complete and --allow-incomplete not set",
                    },
                    indent=2,
                )
            )
            overall_ok = False
            continue

        if args.approve:
            approve_url = f"{base_url}/api/v1/compliance/regulatory/releases/{release_id}/approve"
            ap_code, ap_body = _json_request(approve_url, token=args.token, method="POST", payload={})
            print(json.dumps({"step": "approve", "status_code": ap_code, "release_id": release_id, "response": ap_body}, indent=2))
            if ap_code != 200:
                overall_ok = False
                continue

        if args.publish:
            publish_url = f"{base_url}/api/v1/compliance/regulatory/releases/{release_id}/publish"
            pub_code, pub_body = _json_request(publish_url, token=args.token, method="POST", payload={})
            print(json.dumps({"step": "publish", "status_code": pub_code, "release_id": release_id, "response": pub_body}, indent=2))
            if pub_code != 200:
                overall_ok = False
            continue

    if args.dry_run:
        return 0 if overall_ok else 1

    active_url = f"{base_url}/api/v1/compliance/regulatory/coverage/active"
    active_code, active_body = _json_request(active_url, token=args.token)
    print(json.dumps({"step": "active_coverage", "status_code": active_code, "response": active_body}, indent=2))

    if active_code != 200:
        return 1

    summary = active_body.get("summary", {})
    if summary.get("requirement_rows", 0) > 0 and summary.get("fully_covered_rows", 0) != summary.get("requirement_rows", 0):
        overall_ok = False

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
