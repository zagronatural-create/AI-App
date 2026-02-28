from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_overview(db: Session) -> dict:
    alerts = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (WHERE status = 'open') AS open_alerts,
              COUNT(*) FILTER (WHERE status = 'acknowledged') AS acknowledged_alerts,
              COUNT(*) FILTER (WHERE severity = 'critical' AND status = 'open') AS critical_open_alerts
            FROM alerts
            """
        )
    ).mappings().first()

    compliance = db.execute(
        text(
            """
            WITH latest_q AS (
              SELECT q.batch_id, q.parameter_code, q.observed_value, q.tested_at, q.created_at, q.test_id,
                     ROW_NUMBER() OVER (
                       PARTITION BY q.batch_id, q.parameter_code
                       ORDER BY COALESCE(q.tested_at, q.created_at) DESC, q.created_at DESC, q.test_id DESC
                     ) AS rn
              FROM quality_test_records q
            ), cmp AS (
              SELECT q.batch_id,
                     CASE
                       WHEN MAX(CASE WHEN q.observed_value > COALESCE(t.limit_max, q.observed_value) THEN 1 ELSE 0 END) = 1 THEN 'FAIL'
                       WHEN MAX(CASE WHEN q.observed_value >= COALESCE(t.limit_max, q.observed_value) * 0.9 THEN 1 ELSE 0 END) = 1 THEN 'WARNING'
                       ELSE 'PASS'
                     END AS status
              FROM latest_q q
              LEFT JOIN production_batches b ON b.batch_id = q.batch_id
              LEFT JOIN compliance_thresholds t
                ON t.parameter_code = q.parameter_code
               AND t.product_category = b.product_sku
               AND t.effective_from <= COALESCE(q.tested_at::date, current_date)
               AND (t.effective_to IS NULL OR t.effective_to >= COALESCE(q.tested_at::date, current_date))
              WHERE q.rn = 1
              GROUP BY q.batch_id
            )
            SELECT
              COUNT(*) FILTER (WHERE status = 'PASS') AS pass_batches,
              COUNT(*) FILTER (WHERE status = 'WARNING') AS warning_batches,
              COUNT(*) FILTER (WHERE status = 'FAIL') AS fail_batches
            FROM cmp
            """
        )
    ).mappings().first()

    supplier_risk = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (WHERE risk_band = 'LOW') AS low_risk,
              COUNT(*) FILTER (WHERE risk_band = 'MEDIUM') AS medium_risk,
              COUNT(*) FILTER (WHERE risk_band = 'HIGH') AS high_risk
            FROM ai_risk_scores
            WHERE entity_type = 'supplier'
              AND scored_at >= now() - interval '30 days'
            """
        )
    ).mappings().first()

    recalls = db.execute(
        text(
            """
            SELECT
              COUNT(*) AS total_recall_cases,
              COALESCE(SUM(impacted_qty), 0) AS total_impacted_qty
            FROM recall_cases
            """
        )
    ).mappings().first()

    anomalies = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (WHERE severity = 'critical') AS critical_anomalies,
              COUNT(*) FILTER (WHERE severity = 'warning') AS warning_anomalies
            FROM anomaly_events
            WHERE detected_at >= now() - interval '7 day'
            """
        )
    ).mappings().first()

    latest_kpi = db.execute(
        text(
            """
            SELECT kpi_date, avg_recall_trace_time_ms, supplier_risk_coverage_pct,
                   batch_compliance_auto_validation_pct, avg_audit_report_gen_time_sec,
                   quality_deviation_rate
            FROM kpi_daily
            ORDER BY kpi_date DESC
            LIMIT 1
            """
        )
    ).mappings().first()

    return {
        "alerts": dict(alerts) if alerts else {},
        "compliance": dict(compliance) if compliance else {},
        "supplier_risk": dict(supplier_risk) if supplier_risk else {},
        "recalls": dict(recalls) if recalls else {},
        "anomalies_7d": dict(anomalies) if anomalies else {},
        "latest_kpi": dict(latest_kpi) if latest_kpi else {},
        "disclaimer": "Dashboard metrics support operational intelligence and documentation; not legal certification outcomes.",
    }
