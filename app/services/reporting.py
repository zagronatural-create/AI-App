from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.compliance import batch_comparison


def export_readiness_summary(db: Session, batch_code: str) -> dict:
    batch = db.execute(
        text(
            """
            SELECT batch_id::text AS batch_id, batch_code, product_sku,
                   produced_at, status
            FROM production_batches
            WHERE batch_code = :batch_code;
            """
        ),
        {"batch_code": batch_code},
    ).mappings().first()

    if not batch:
        return {"error": "Batch not found"}

    comparison = batch_comparison(db, batch_code)
    fail_count = sum(1 for row in comparison if row["status"] == "FAIL")
    warning_count = sum(1 for row in comparison if row["status"] == "WARNING")

    readiness = "REVIEW_REQUIRED" if fail_count > 0 else "CONDITIONAL_PASS" if warning_count > 0 else "PASS"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch": dict(batch),
        "compliance_summary": {
            "total_parameters": len(comparison),
            "fail_count": fail_count,
            "warning_count": warning_count,
            "readiness_status": readiness,
        },
        "comparison": comparison,
        "disclaimer": "AI-assisted readiness report; not a legal compliance certificate.",
    }
