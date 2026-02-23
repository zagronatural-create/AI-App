from __future__ import annotations

import json
import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit import append_audit_event


def _is_outside(value: float, limit_min: Decimal | None, limit_max: Decimal | None) -> bool:
    if limit_min is not None and value < float(limit_min):
        return True
    if limit_max is not None and value > float(limit_max):
        return True
    return False


def _is_near(value: float, limit_min: Decimal | None, limit_max: Decimal | None, warn_margin_pct: float) -> bool:
    margin = warn_margin_pct / 100.0
    if limit_max is not None and value >= float(limit_max) * (1 - margin):
        return True
    if limit_min is not None and value <= float(limit_min) * (1 + margin):
        return True
    return False


def ingest_ccp_log(
    db: Session,
    *,
    batch_code: str,
    ccp_code: str,
    metric_name: str,
    metric_value: float,
    unit: str,
    measured_at: str,
    operator_id: str | None,
    source: str,
) -> dict:
    batch = db.execute(
        text("SELECT batch_id FROM production_batches WHERE batch_code = :batch_code"),
        {"batch_code": batch_code},
    ).mappings().first()
    if not batch:
        return {"error": "Batch not found"}

    batch_id = batch["batch_id"]
    ccp_log_id = uuid.uuid4()

    db.execute(
        text(
            """
            INSERT INTO ccp_logs (
              ccp_log_id, batch_id, ccp_code, metric_name, metric_value, unit,
              measured_at, operator_id, source, created_at
            ) VALUES (
              :ccp_log_id, :batch_id, :ccp_code, :metric_name, :metric_value, :unit,
              :measured_at, :operator_id, :source, now()
            )
            """
        ),
        {
            "ccp_log_id": ccp_log_id,
            "batch_id": batch_id,
            "ccp_code": ccp_code,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "unit": unit,
            "measured_at": measured_at,
            "operator_id": operator_id,
            "source": source,
        },
    )

    rules = db.execute(
        text(
            """
            SELECT rule_id::text AS rule_id, ccp_code, metric_name, unit,
                   limit_min, limit_max, warn_margin_pct, severity
            FROM ccp_rules
            WHERE active = true
              AND ccp_code = :ccp_code
              AND metric_name = :metric_name
              AND unit = :unit
            ORDER BY created_at DESC
            """
        ),
        {"ccp_code": ccp_code, "metric_name": metric_name, "unit": unit},
    ).mappings().all()

    generated_alerts = []
    for rule in rules:
        alert_type = None
        if _is_outside(metric_value, rule["limit_min"], rule["limit_max"]):
            alert_type = "CCP_DEVIATION"
        elif _is_near(metric_value, rule["limit_min"], rule["limit_max"], float(rule["warn_margin_pct"])):
            alert_type = "CCP_WARNING"

        if not alert_type:
            continue

        severity = "critical" if alert_type == "CCP_DEVIATION" else "warning"
        alert_id = uuid.uuid4()
        title = f"{alert_type} at {ccp_code}:{metric_name}"
        message = (
            f"Value {metric_value} {unit} for {ccp_code}/{metric_name} "
            f"triggered rule bounds [{rule['limit_min']}, {rule['limit_max']}]."
        )
        details = {
            "rule_id": rule["rule_id"],
            "metric_value": metric_value,
            "unit": unit,
            "limit_min": float(rule["limit_min"]) if rule["limit_min"] is not None else None,
            "limit_max": float(rule["limit_max"]) if rule["limit_max"] is not None else None,
            "warn_margin_pct": float(rule["warn_margin_pct"]),
            "batch_code": batch_code,
        }

        db.execute(
            text(
                """
                INSERT INTO alerts (
                  alert_id, batch_id, ccp_log_id, alert_type, severity, status,
                  title, message, details, detected_at
                ) VALUES (
                  :alert_id, :batch_id, :ccp_log_id, :alert_type, :severity, 'open',
                  :title, :message, CAST(:details AS jsonb), now()
                )
                """
            ),
            {
                "alert_id": alert_id,
                "batch_id": batch_id,
                "ccp_log_id": ccp_log_id,
                "alert_type": alert_type,
                "severity": severity,
                "title": title,
                "message": message,
                "details": json.dumps(details),
            },
        )

        append_audit_event(
            db,
            actor_id=operator_id or "system",
            action_type="CCP_ALERT_CREATED",
            entity_type="alert",
            entity_id=str(alert_id),
            payload=details | {"alert_type": alert_type, "severity": severity},
        )

        generated_alerts.append(
            {
                "alert_id": str(alert_id),
                "alert_type": alert_type,
                "severity": severity,
                "title": title,
            }
        )

    append_audit_event(
        db,
        actor_id=operator_id or "system",
        action_type="CCP_LOG_INGESTED",
        entity_type="ccp_log",
        entity_id=str(ccp_log_id),
        payload={
            "batch_code": batch_code,
            "ccp_code": ccp_code,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "unit": unit,
            "source": source,
            "generated_alerts": len(generated_alerts),
        },
    )

    db.commit()

    return {
        "ccp_log_id": str(ccp_log_id),
        "batch_code": batch_code,
        "ccp_code": ccp_code,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "unit": unit,
        "alerts_generated": generated_alerts,
        "disclaimer": "Operational deviation intelligence only; not a legal compliance certification outcome.",
    }


def list_alerts(db: Session, status: str = "open", limit: int = 100) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT a.alert_id::text AS alert_id,
                   pb.batch_code,
                   a.alert_type,
                   a.severity,
                   a.status,
                   a.title,
                   a.message,
                   a.details,
                   a.detected_at,
                   a.acknowledged_at,
                   a.acknowledged_by
            FROM alerts a
            LEFT JOIN production_batches pb ON pb.batch_id = a.batch_id
            WHERE (:status = 'all' OR a.status = :status)
            ORDER BY a.detected_at DESC
            LIMIT :limit
            """
        ),
        {"status": status, "limit": limit},
    ).mappings()
    return [dict(r) for r in rows]


def batch_ccp_timeline(db: Session, batch_code: str, limit: int = 200) -> dict:
    logs = db.execute(
        text(
            """
            SELECT l.ccp_log_id::text AS ccp_log_id,
                   l.ccp_code,
                   l.metric_name,
                   l.metric_value,
                   l.unit,
                   l.measured_at,
                   l.operator_id,
                   l.source
            FROM ccp_logs l
            JOIN production_batches b ON b.batch_id = l.batch_id
            WHERE b.batch_code = :batch_code
            ORDER BY l.measured_at DESC
            LIMIT :limit
            """
        ),
        {"batch_code": batch_code, "limit": limit},
    ).mappings()

    alerts = db.execute(
        text(
            """
            SELECT a.alert_id::text AS alert_id,
                   a.ccp_log_id::text AS ccp_log_id,
                   a.alert_type,
                   a.severity,
                   a.status,
                   a.title,
                   a.detected_at
            FROM alerts a
            JOIN production_batches b ON b.batch_id = a.batch_id
            WHERE b.batch_code = :batch_code
            ORDER BY a.detected_at DESC
            LIMIT :limit
            """
        ),
        {"batch_code": batch_code, "limit": limit},
    ).mappings()

    return {
        "batch_code": batch_code,
        "logs": [dict(l) for l in logs],
        "alerts": [dict(a) for a in alerts],
    }


def acknowledge_alert(db: Session, alert_id: str, acknowledged_by: str) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT a.alert_id::text AS alert_id,
                   a.status,
                   pb.batch_code
            FROM alerts a
            LEFT JOIN production_batches pb ON pb.batch_id = a.batch_id
            WHERE a.alert_id = :alert_id
            """
        ),
        {"alert_id": alert_id},
    ).mappings().first()
    if not row:
        return None

    db.execute(
        text(
            """
            UPDATE alerts
            SET status = 'acknowledged',
                acknowledged_at = now(),
                acknowledged_by = :acknowledged_by
            WHERE alert_id = :alert_id
            """
        ),
        {"alert_id": alert_id, "acknowledged_by": acknowledged_by},
    )

    append_audit_event(
        db,
        actor_id=acknowledged_by,
        action_type="CCP_ALERT_ACKNOWLEDGED",
        entity_type="alert",
        entity_id=alert_id,
        payload={"batch_code": row["batch_code"], "previous_status": row["status"]},
    )
    db.commit()

    updated = db.execute(
        text(
            """
            SELECT a.alert_id::text AS alert_id,
                   pb.batch_code,
                   a.alert_type,
                   a.severity,
                   a.status,
                   a.title,
                   a.acknowledged_at,
                   a.acknowledged_by
            FROM alerts a
            LEFT JOIN production_batches pb ON pb.batch_id = a.batch_id
            WHERE a.alert_id = :alert_id
            """
        ),
        {"alert_id": alert_id},
    ).mappings().first()
    return dict(updated) if updated else None
