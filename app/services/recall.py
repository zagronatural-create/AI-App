from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.trace import trace_backward, trace_forward


def simulate_recall(db: Session, batch_code: str) -> dict:
    backward = trace_backward(db, batch_code)
    forward = trace_forward(db, batch_code)

    qty_query = text(
        """
        SELECT COALESCE(SUM(dr.dispatch_qty), 0) AS impacted_qty
        FROM production_batches b
        JOIN finished_products fp ON fp.batch_id = b.batch_id
        LEFT JOIN dispatch_records dr ON dr.finished_id = fp.finished_id
        WHERE b.batch_code = :batch_code;
        """
    )
    impacted_qty = float(db.execute(qty_query, {"batch_code": batch_code}).scalar_one())

    return {
        "batch_code": batch_code,
        "impacted_customers_count": len({c["customer_id"] for c in forward["customers"]}),
        "impacted_qty": impacted_qty,
        "suppliers_count": len({s["supplier_id"] for s in backward["suppliers"]}),
        "finished_lots_count": len({f["finished_id"] for f in forward["finished_lots"]}),
        "customers": forward["customers"],
    }
