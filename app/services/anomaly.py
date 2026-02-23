from __future__ import annotations

import json
import math
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit import append_audit_event


def run_anomaly_scan(
    db: Session,
    *,
    lookback_hours: int = 72,
    z_threshold: float = 2.5,
    actor_id: str = "system",
) -> dict:
    rows = db.execute(
        text(
            """
            SELECT l.ccp_log_id::text AS ccp_log_id,
                   l.batch_id::text AS batch_id,
                   b.batch_code,
                   l.ccp_code,
                   l.metric_name,
                   l.unit,
                   l.metric_value::float AS metric_value,
                   l.measured_at
            FROM ccp_logs l
            JOIN production_batches b ON b.batch_id = l.batch_id
            WHERE l.measured_at >= now() - interval '30 day'
            ORDER BY l.measured_at ASC
            """
        )
    ).mappings().all()

    baseline: dict[tuple[str, str, str], deque] = defaultdict(lambda: deque(maxlen=20))
    created = 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    for row in rows:
        key = (row["ccp_code"], row["metric_name"], row["unit"])
        history = baseline[key]
        val = float(row["metric_value"])

        in_detection_window = row["measured_at"] >= cutoff

        if in_detection_window and len(history) >= 10:
            mu = mean(history)
            sigma = stdev(history) if len(history) > 1 else 0.0
            if sigma > 0:
                z = (val - mu) / sigma
                if math.fabs(z) >= z_threshold:
                    severity = "critical" if math.fabs(z) >= 4 else "warning"
                    anomaly_id = uuid.uuid4()
                    details = {
                        "batch_code": row["batch_code"],
                        "unit": row["unit"],
                        "history_window": len(history),
                        "lookback_hours": lookback_hours,
                        "z_threshold": z_threshold,
                    }

                    db.execute(
                        text(
                            """
                            INSERT INTO anomaly_events (
                              anomaly_id, source_ccp_log_id, batch_id, anomaly_type,
                              metric_name, ccp_code, observed_value, baseline_mean,
                              baseline_stddev, z_score, severity, details, detected_at
                            ) VALUES (
                              :anomaly_id, :source_ccp_log_id, :batch_id, :anomaly_type,
                              :metric_name, :ccp_code, :observed_value, :baseline_mean,
                              :baseline_stddev, :z_score, :severity, CAST(:details AS jsonb), now()
                            )
                            ON CONFLICT (source_ccp_log_id, anomaly_type) DO NOTHING
                            """
                        ),
                        {
                            "anomaly_id": anomaly_id,
                            "source_ccp_log_id": row["ccp_log_id"],
                            "batch_id": row["batch_id"],
                            "anomaly_type": "PROCESS_DRIFT",
                            "metric_name": row["metric_name"],
                            "ccp_code": row["ccp_code"],
                            "observed_value": val,
                            "baseline_mean": mu,
                            "baseline_stddev": sigma,
                            "z_score": z,
                            "severity": severity,
                            "details": json.dumps(details),
                        },
                    )

                    db.execute(
                        text(
                            """
                            INSERT INTO alerts (
                              alert_id, batch_id, ccp_log_id, alert_type, severity, status,
                              title, message, details, detected_at
                            ) VALUES (
                              :alert_id, :batch_id, :ccp_log_id, 'PROCESS_ANOMALY', :severity, 'open',
                              :title, :message, CAST(:details AS jsonb), now()
                            )
                            """
                        ),
                        {
                            "alert_id": uuid.uuid4(),
                            "batch_id": row["batch_id"],
                            "ccp_log_id": row["ccp_log_id"],
                            "severity": severity,
                            "title": f"Anomaly at {row['ccp_code']}:{row['metric_name']}",
                            "message": f"Observed {val} {row['unit']} deviates from baseline (z={round(z, 2)}).",
                            "details": json.dumps(details | {"z_score": round(z, 4)}),
                        },
                    )
                    created += 1

        history.append(val)

    append_audit_event(
        db,
        actor_id=actor_id,
        action_type="ANOMALY_SCAN_RUN",
        entity_type="anomaly_scan",
        entity_id=str(uuid.uuid4()),
        payload={"lookback_hours": lookback_hours, "z_threshold": z_threshold, "created": created},
    )
    db.commit()

    return {
        "created_anomalies": created,
        "lookback_hours": lookback_hours,
        "z_threshold": z_threshold,
        "disclaimer": "Anomaly detection is decision-support intelligence and not regulatory certification.",
    }


def list_anomalies(db: Session, limit: int = 200) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT ae.anomaly_id::text AS anomaly_id,
                   b.batch_code,
                   ae.anomaly_type,
                   ae.ccp_code,
                   ae.metric_name,
                   ae.observed_value,
                   ae.baseline_mean,
                   ae.baseline_stddev,
                   ae.z_score,
                   ae.severity,
                   ae.details,
                   ae.detected_at
            FROM anomaly_events ae
            LEFT JOIN production_batches b ON b.batch_id = ae.batch_id
            ORDER BY ae.detected_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings()
    return [dict(r) for r in rows]
