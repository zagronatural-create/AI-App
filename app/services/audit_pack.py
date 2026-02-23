from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.audit import append_audit_event, audit_events_to_csv, list_audit_events


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pack_dir(pack_id: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = Path(settings.storage_dir) / "audit_packs" / f"{ts}_{pack_id}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def generate_audit_pack(
    db: Session,
    *,
    created_by: str,
    limit: int,
    actor_id: str | None,
    action_type: str | None,
    entity_type: str | None,
    entity_id: str | None,
    from_ts: str | None,
    to_ts: str | None,
    notes: str | None,
) -> dict:
    rows = list_audit_events(
        db,
        limit=limit,
        actor_id=actor_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    pack_id = str(uuid.uuid4())
    folder = _pack_dir(pack_id)

    csv_path = folder / "audit_events.csv"
    manifest_path = folder / "manifest.json"
    checksums_path = folder / "checksums.json"

    csv_data = audit_events_to_csv(rows)
    csv_path.write_text(csv_data, encoding="utf-8")

    filters = {
        "limit": limit,
        "actor_id": actor_id,
        "action_type": action_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "from_ts": from_ts,
        "to_ts": to_ts,
    }

    manifest = {
        "pack_id": pack_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by,
        "row_count": len(rows),
        "filters": filters,
        "notes": notes,
        "files": ["audit_events.csv", "manifest.json", "checksums.json"],
        "disclaimer": "AI-assisted audit pack for documentation. Not a legal certification artifact.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    checksums = {
        "audit_events.csv": _sha256_file(csv_path),
        "manifest.json": _sha256_file(manifest_path),
    }
    checksums_path.write_text(json.dumps(checksums, indent=2, sort_keys=True), encoding="utf-8")

    manifest_hash = _sha256_file(manifest_path)
    checksums_hash = _sha256_file(checksums_path)

    db.execute(
        text(
            """
            INSERT INTO audit_packs (
              pack_id, created_at, created_by, status, filters, row_count,
              folder_path, manifest_hash, checksums_hash, notes
            ) VALUES (
              :pack_id, now(), :created_by, 'generated', CAST(:filters AS jsonb), :row_count,
              :folder_path, :manifest_hash, :checksums_hash, :notes
            )
            """
        ),
        {
            "pack_id": pack_id,
            "created_by": created_by,
            "filters": json.dumps(filters),
            "row_count": len(rows),
            "folder_path": str(folder),
            "manifest_hash": manifest_hash,
            "checksums_hash": checksums_hash,
            "notes": notes,
        },
    )

    append_audit_event(
        db,
        actor_id=created_by,
        action_type="AUDIT_PACK_GENERATED",
        entity_type="audit_pack",
        entity_id=pack_id,
        payload={"row_count": len(rows), "filters": filters, "folder_path": str(folder)},
    )
    db.commit()

    return {
        "pack_id": pack_id,
        "row_count": len(rows),
        "created_by": created_by,
        "folder_path": str(folder),
        "files": {
            "csv": str(csv_path),
            "manifest": str(manifest_path),
            "checksums": str(checksums_path),
        },
        "manifest_hash": manifest_hash,
        "checksums_hash": checksums_hash,
        "disclaimer": "Pack generation supports audit documentation and integrity checks; not a legal certification.",
    }


def verify_audit_pack(db: Session, pack_id: str, verified_by: str) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT pack_id::text AS pack_id, folder_path, manifest_hash, checksums_hash
            FROM audit_packs
            WHERE pack_id = :pack_id
            """
        ),
        {"pack_id": pack_id},
    ).mappings().first()

    if not row:
        return None

    folder = Path(row["folder_path"])
    csv_path = folder / "audit_events.csv"
    manifest_path = folder / "manifest.json"
    checksums_path = folder / "checksums.json"

    missing = [str(p) for p in [csv_path, manifest_path, checksums_path] if not p.exists()]
    mismatches: list[dict] = []

    if not missing:
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        for name, expected in checksums.items():
            file_path = folder / name
            if not file_path.exists():
                mismatches.append({"file": name, "issue": "missing"})
                continue
            actual = _sha256_file(file_path)
            if actual != expected:
                mismatches.append({"file": name, "issue": "hash_mismatch", "expected": expected, "actual": actual})

        if _sha256_file(manifest_path) != row["manifest_hash"]:
            mismatches.append({"file": "manifest.json", "issue": "manifest_hash_mismatch"})
        if _sha256_file(checksums_path) != row["checksums_hash"]:
            mismatches.append({"file": "checksums.json", "issue": "checksums_hash_mismatch"})

    valid = not missing and not mismatches

    append_audit_event(
        db,
        actor_id=verified_by,
        action_type="AUDIT_PACK_VERIFIED",
        entity_type="audit_pack",
        entity_id=pack_id,
        payload={"valid": valid, "missing": missing, "mismatches": mismatches},
    )
    db.commit()

    return {
        "pack_id": pack_id,
        "valid": valid,
        "missing_files": missing,
        "mismatches": mismatches,
        "verified_by": verified_by,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def list_audit_packs(db: Session, limit: int = 100) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT pack_id::text AS pack_id, created_at, created_by, status,
                   filters, row_count, folder_path, manifest_hash, checksums_hash, notes
            FROM audit_packs
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings()
    return [dict(r) for r in rows]


def resolve_pack_file(db: Session, pack_id: str, file_name: str) -> Path | None:
    allowed = {"audit_events.csv", "manifest.json", "checksums.json"}
    if file_name not in allowed:
        return None

    row = db.execute(
        text(
            """
            SELECT folder_path
            FROM audit_packs
            WHERE pack_id = :pack_id
            """
        ),
        {"pack_id": pack_id},
    ).mappings().first()
    if not row:
        return None

    path = Path(row["folder_path"]) / file_name
    if not path.exists() or not path.is_file():
        return None
    return path
