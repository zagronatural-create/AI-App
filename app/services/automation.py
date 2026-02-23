from __future__ import annotations

import json
import uuid
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.anomaly import run_anomaly_scan
from app.services.audit import append_audit_event
from app.services.risk import load_supplier_features, score_batch_and_store, supplier_risk_score


def _insert_supplier_score(db: Session, supplier_id: str, score_payload: dict) -> None:
    db.execute(
        text(
            """
            INSERT INTO ai_risk_scores (
              risk_id, entity_type, entity_id, model_name, model_version,
              score, risk_band, explanation, scored_at
            ) VALUES (
              :risk_id, 'supplier', :entity_id, 'supplier_risk_logistic_baseline', 'v1',
              :score, :risk_band, CAST(:explanation AS jsonb), now()
            )
            """
        ),
        {
            "risk_id": uuid.uuid4(),
            "entity_id": supplier_id,
            "score": score_payload["risk_score"],
            "risk_band": score_payload["risk_band"],
            "explanation": json.dumps(score_payload["explanation"]),
        },
    )


def upsert_kpi_snapshot(db: Session) -> dict:
    supplier_coverage = db.execute(
        text(
            """
            WITH active_suppliers AS (
              SELECT supplier_id FROM suppliers WHERE status = 'active'
            ), latest AS (
              SELECT entity_id, MAX(scored_at) AS max_scored
              FROM ai_risk_scores
              WHERE entity_type = 'supplier'
              GROUP BY entity_id
            )
            SELECT
              CASE WHEN COUNT(a.supplier_id) = 0 THEN 0
              ELSE ROUND(100.0 * COUNT(l.entity_id) / COUNT(a.supplier_id), 2)
              END AS coverage_pct
            FROM active_suppliers a
            LEFT JOIN latest l ON l.entity_id = a.supplier_id
            """
        )
    ).scalar_one()

    batch_auto_validation = db.execute(
        text(
            """
            WITH released AS (
              SELECT batch_id FROM production_batches WHERE status = 'released'
            ), tested AS (
              SELECT DISTINCT batch_id FROM quality_test_records
            )
            SELECT
              CASE WHEN COUNT(r.batch_id) = 0 THEN 0
              ELSE ROUND(100.0 * COUNT(t.batch_id) / COUNT(r.batch_id), 2)
              END AS auto_pct
            FROM released r
            LEFT JOIN tested t ON t.batch_id = r.batch_id
            """
        )
    ).scalar_one()

    quality_deviation_rate = db.execute(
        text(
            """
            WITH evals AS (
              SELECT q.test_id,
                     CASE WHEN ((t.limit_max IS NOT NULL AND q.observed_value > t.limit_max)
                             OR (t.limit_min IS NOT NULL AND q.observed_value < t.limit_min))
                          THEN 1 ELSE 0 END AS is_fail
              FROM quality_test_records q
              JOIN production_batches b ON b.batch_id = q.batch_id
              LEFT JOIN compliance_thresholds t
                     ON t.parameter_code = q.parameter_code
                    AND t.product_category = b.product_sku
                    AND t.effective_to IS NULL
            )
            SELECT COALESCE(ROUND(AVG(is_fail::numeric), 3), 0) FROM evals
            """
        )
    ).scalar_one()

    last_recall_ms = db.execute(
        text("SELECT COALESCE(avg_recall_trace_time_ms, 0) FROM kpi_daily ORDER BY kpi_date DESC LIMIT 1")
    ).scalar_one()

    avg_audit_report_gen_time_sec = db.execute(
        text(
            """
            SELECT COALESCE(ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - started_at))), 2), 300)
            FROM automation_runs
            WHERE run_type = 'DAILY_CYCLE' AND status = 'completed'
            """
        )
    ).scalar_one()

    db.execute(
        text(
            """
            INSERT INTO kpi_daily (
              kpi_date, avg_recall_trace_time_ms, supplier_risk_coverage_pct,
              batch_compliance_auto_validation_pct, avg_audit_report_gen_time_sec,
              quality_deviation_rate
            ) VALUES (
              :kpi_date, :avg_recall_trace_time_ms, :supplier_risk_coverage_pct,
              :batch_compliance_auto_validation_pct, :avg_audit_report_gen_time_sec,
              :quality_deviation_rate
            )
            ON CONFLICT (kpi_date) DO UPDATE SET
              avg_recall_trace_time_ms = EXCLUDED.avg_recall_trace_time_ms,
              supplier_risk_coverage_pct = EXCLUDED.supplier_risk_coverage_pct,
              batch_compliance_auto_validation_pct = EXCLUDED.batch_compliance_auto_validation_pct,
              avg_audit_report_gen_time_sec = EXCLUDED.avg_audit_report_gen_time_sec,
              quality_deviation_rate = EXCLUDED.quality_deviation_rate
            """
        ),
        {
            "kpi_date": date.today(),
            "avg_recall_trace_time_ms": last_recall_ms,
            "supplier_risk_coverage_pct": float(supplier_coverage),
            "batch_compliance_auto_validation_pct": float(batch_auto_validation),
            "avg_audit_report_gen_time_sec": float(avg_audit_report_gen_time_sec),
            "quality_deviation_rate": float(quality_deviation_rate),
        },
    )

    return {
        "kpi_date": str(date.today()),
        "supplier_risk_coverage_pct": float(supplier_coverage),
        "batch_compliance_auto_validation_pct": float(batch_auto_validation),
        "quality_deviation_rate": float(quality_deviation_rate),
    }


def run_daily_cycle(db: Session, actor_id: str = "system.scheduler") -> dict:
    running = db.execute(
        text(
            """
            SELECT run_id::text
            FROM automation_runs
            WHERE run_type = 'DAILY_CYCLE' AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if running:
        return {
            "status": "skipped",
            "reason": "daily cycle already running",
            "running_run_id": running,
        }

    run_id = uuid.uuid4()
    try:
        db.execute(
            text(
                """
                INSERT INTO automation_runs (run_id, run_type, status, actor_id, started_at)
                VALUES (:run_id, 'DAILY_CYCLE', 'running', :actor_id, now())
                """
            ),
            {"run_id": run_id, "actor_id": actor_id},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        running = db.execute(
            text(
                """
                SELECT run_id::text
                FROM automation_runs
                WHERE run_type = 'DAILY_CYCLE' AND status = 'running'
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
        ).scalar_one_or_none()
        return {
            "status": "skipped",
            "reason": "daily cycle already running",
            "running_run_id": running,
        }

    try:
        supplier_ids = db.execute(
            text("SELECT supplier_id::text FROM suppliers WHERE status = 'active'")
        ).scalars().all()

        supplier_scored = 0
        for supplier_id in supplier_ids:
            features = load_supplier_features(db, supplier_id)
            score_payload = supplier_risk_score(features)
            _insert_supplier_score(db, supplier_id, score_payload)
            supplier_scored += 1

        batch_codes = db.execute(
            text(
                """
                SELECT batch_code
                FROM production_batches
                WHERE produced_at >= now() - interval '60 day'
                ORDER BY produced_at DESC
                """
            )
        ).scalars().all()

        batch_scored = 0
        for batch_code in batch_codes:
            scored = score_batch_and_store(db, batch_code=batch_code, actor_id=actor_id)
            if not scored.get("error"):
                batch_scored += 1

        anomaly_result = run_anomaly_scan(db, lookback_hours=24, z_threshold=2.5, actor_id=actor_id)
        kpi_snapshot = upsert_kpi_snapshot(db)

        summary = {
            "supplier_scored": supplier_scored,
            "batch_scored": batch_scored,
            "anomalies_created": anomaly_result["created_anomalies"],
            "kpi_snapshot": kpi_snapshot,
        }

        db.execute(
            text(
                """
                UPDATE automation_runs
                SET status = 'completed', completed_at = now(), summary = CAST(:summary AS jsonb)
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id, "summary": json.dumps(summary)},
        )

        append_audit_event(
            db,
            actor_id=actor_id,
            action_type="DAILY_AUTOMATION_COMPLETED",
            entity_type="automation_run",
            entity_id=str(run_id),
            payload=summary,
        )
        db.commit()

        return {"run_id": str(run_id), "status": "completed", **summary}
    except Exception as exc:
        db.rollback()
        db.execute(
            text(
                """
                UPDATE automation_runs
                SET status = 'failed', completed_at = now(), error_message = :error
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id, "error": str(exc)},
        )
        db.commit()
        return {"run_id": str(run_id), "status": "failed", "error": str(exc)}


def list_automation_runs(db: Session, limit: int = 50) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT run_id::text AS run_id, run_type, status, started_at,
                   completed_at, actor_id, summary, error_message
            FROM automation_runs
            ORDER BY started_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings()
    return [dict(r) for r in rows]


def mark_stuck_runs_failed(db: Session, timeout_minutes: int = 120) -> int:
    updated = db.execute(
        text(
            """
            UPDATE automation_runs
            SET status = 'failed',
                completed_at = now(),
                error_message = COALESCE(error_message, 'Marked failed by watchdog timeout')
            WHERE run_type = 'DAILY_CYCLE'
              AND status = 'running'
              AND started_at < now() - (:timeout_minutes || ' minute')::interval
            """
        ),
        {"timeout_minutes": timeout_minutes},
    )
    db.commit()
    return updated.rowcount or 0


def run_daily_cycle_detached(actor_id: str = "system.scheduler") -> dict:
    db = SessionLocal()
    try:
        return run_daily_cycle(db, actor_id=actor_id)
    finally:
        db.close()


def get_automation_status(db: Session) -> dict:
    running = db.execute(
        text(
            """
            SELECT run_id::text AS run_id, started_at, actor_id
            FROM automation_runs
            WHERE run_type = 'DAILY_CYCLE' AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
    ).mappings().first()

    last = db.execute(
        text(
            """
            SELECT run_id::text AS run_id, status, started_at, completed_at, summary, error_message
            FROM automation_runs
            WHERE run_type = 'DAILY_CYCLE'
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
    ).mappings().first()

    return {
        "daily_cycle_running": bool(running),
        "running_run": dict(running) if running else None,
        "last_run": dict(last) if last else None,
    }
