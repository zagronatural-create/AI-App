from sqlalchemy import text
from sqlalchemy.orm import Session


def trace_backward(db: Session, batch_code: str) -> dict:
    query = text(
        """
        SELECT DISTINCT s.supplier_id::text AS supplier_id, s.name,
               rml.rm_lot_id::text AS rm_lot_id, rml.internal_lot_code
        FROM production_batches b
        JOIN batch_material_map bmm ON bmm.batch_id = b.batch_id
        JOIN raw_material_lots rml ON rml.rm_lot_id = bmm.rm_lot_id
        JOIN supplier_deliveries sd ON sd.delivery_id = rml.delivery_id
        JOIN suppliers s ON s.supplier_id = sd.supplier_id
        WHERE b.batch_code = :batch_code;
        """
    )
    rows = db.execute(query, {"batch_code": batch_code}).mappings().all()
    return {
        "suppliers": [
            {"supplier_id": r["supplier_id"], "name": r["name"]} for r in rows
        ],
        "raw_material_lots": [
            {"rm_lot_id": r["rm_lot_id"], "internal_lot_code": r["internal_lot_code"]}
            for r in rows
        ],
    }


def trace_forward(db: Session, batch_code: str) -> dict:
    query = text(
        """
        SELECT DISTINCT fp.finished_id::text AS finished_id, fp.serial_lot_code,
               c.customer_id::text AS customer_id, c.name, c.customer_type
        FROM production_batches b
        JOIN finished_products fp ON fp.batch_id = b.batch_id
        LEFT JOIN dispatch_records dr ON dr.finished_id = fp.finished_id
        LEFT JOIN customers c ON c.customer_id = dr.customer_id
        WHERE b.batch_code = :batch_code;
        """
    )
    rows = db.execute(query, {"batch_code": batch_code}).mappings().all()
    return {
        "finished_lots": [
            {"finished_id": r["finished_id"], "serial_lot_code": r["serial_lot_code"]}
            for r in rows
        ],
        "customers": [
            {
                "customer_id": r["customer_id"],
                "name": r["name"],
                "customer_type": r["customer_type"],
            }
            for r in rows
            if r["customer_id"] is not None
        ],
    }
