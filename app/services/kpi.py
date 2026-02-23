from sqlalchemy import text
from sqlalchemy.orm import Session


def get_daily_kpi(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT kpi_date, avg_recall_trace_time_ms, supplier_risk_coverage_pct,
                   batch_compliance_auto_validation_pct, avg_audit_report_gen_time_sec,
                   quality_deviation_rate
            FROM kpi_daily
            ORDER BY kpi_date DESC
            LIMIT 30;
            """
        )
    ).mappings()
    return [dict(r) for r in rows]
