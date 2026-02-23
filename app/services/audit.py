from __future__ import annotations

import hashlib
import json
from io import StringIO
import csv
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session


def append_audit_event(
    db: Session,
    *,
    actor_id: str,
    action_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
) -> str:
    prev = db.execute(
        text(
            """
            SELECT event_hash
            FROM audit_logs
            ORDER BY event_time DESC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()

    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    base = f"{prev or ''}|{action_type}|{entity_type}|{entity_id}|{canonical_payload}|{datetime.now(timezone.utc).isoformat()}"
    event_hash = hashlib.sha256(base.encode("utf-8")).hexdigest()

    db.execute(
        text(
            """
            INSERT INTO audit_logs (
              audit_id, actor_id, action_type, entity_type, entity_id,
              event_time, payload, prev_hash, event_hash
            ) VALUES (
              :audit_id, :actor_id, :action_type, :entity_type, :entity_id,
              now(), CAST(:payload AS jsonb), :prev_hash, :event_hash
            )
            """
        ),
        {
            "audit_id": uuid.uuid4(),
            "actor_id": actor_id,
            "action_type": action_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": canonical_payload,
            "prev_hash": prev,
            "event_hash": event_hash,
        },
    )
    return event_hash


def list_audit_events(
    db: Session,
    *,
    limit: int = 200,
    actor_id: str | None = None,
    action_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> list[dict]:
    where_clauses: list[str] = []
    params: dict[str, object] = {"limit": limit}

    if actor_id is not None:
        where_clauses.append("actor_id = :actor_id")
        params["actor_id"] = actor_id
    if action_type is not None:
        where_clauses.append("action_type = :action_type")
        params["action_type"] = action_type
    if entity_type is not None:
        where_clauses.append("entity_type = :entity_type")
        params["entity_type"] = entity_type
    if entity_id is not None:
        where_clauses.append("entity_id = :entity_id")
        params["entity_id"] = entity_id
    if from_ts is not None:
        where_clauses.append("event_time >= CAST(:from_ts AS timestamptz)")
        params["from_ts"] = from_ts
    if to_ts is not None:
        where_clauses.append("event_time <= CAST(:to_ts AS timestamptz)")
        params["to_ts"] = to_ts

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    rows = db.execute(
        text(
            f"""
            SELECT audit_id::text AS audit_id, actor_id, action_type, entity_type, entity_id,
                   event_time, payload, prev_hash, event_hash
            FROM audit_logs
            {where_sql}
            ORDER BY event_time DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return [dict(r) for r in rows]


def get_audit_event(db: Session, audit_id: str) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT audit_id::text AS audit_id, actor_id, action_type, entity_type, entity_id,
                   event_time, payload, prev_hash, event_hash
            FROM audit_logs
            WHERE audit_id = :audit_id
            """
        ),
        {"audit_id": audit_id},
    ).mappings().first()
    return dict(row) if row else None


def audit_events_to_csv(events: list[dict]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "audit_id",
            "event_time",
            "actor_id",
            "action_type",
            "entity_type",
            "entity_id",
            "prev_hash",
            "event_hash",
            "payload_json",
        ]
    )
    for event in events:
        payload = event.get("payload")
        if payload is None:
            payload_json = ""
        elif isinstance(payload, str):
            payload_json = payload
        else:
            payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        writer.writerow(
            [
                event.get("audit_id", ""),
                event.get("event_time", ""),
                event.get("actor_id", ""),
                event.get("action_type", ""),
                event.get("entity_type", ""),
                event.get("entity_id", ""),
                event.get("prev_hash", ""),
                event.get("event_hash", ""),
                payload_json,
            ]
        )
    return output.getvalue()
