from __future__ import annotations

import json
import uuid
from math import exp

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit import append_audit_event


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + exp(-z))


def _risk_band(score: float) -> str:
    if score >= 66:
        return "HIGH"
    if score >= 33:
        return "MEDIUM"
    return "LOW"


def supplier_risk_score(features: dict) -> dict:
    weights = {
        "delay_rate_90d": 1.8,
        "quality_fail_rate_180d": 2.2,
        "rejection_rate": 1.5,
        "volume_cv": 1.1,
        "critical_nonconformities_12m": 0.35,
    }
    intercept = -2.0

    z = intercept + sum(weights[name] * float(features.get(name, 0)) for name in weights)
    probability = _sigmoid(z)
    score = round(probability * 100, 2)

    return {
        "risk_score": score,
        "risk_band": _risk_band(score),
        "risk_probability": round(probability, 4),
        "explanation": {
            "method": "logistic_baseline",
            "intercept": intercept,
            "feature_contributions": {
                name: round(weights[name] * float(features.get(name, 0)), 4) for name in weights
            },
        },
    }


def batch_risk_score(features: dict) -> dict:
    """Explainable batch-level risk baseline.

    Inputs are normalized to practical ranges and fed into a logistic model.
    """
    weights = {
        "supplier_risk_norm": 1.6,
        "storage_days_norm": 0.9,
        "open_alerts_norm": 1.4,
        "historical_deviation_rate": 1.3,
        "current_fail_count_norm": 2.0,
    }
    intercept = -2.2

    z = intercept + sum(weights[k] * float(features.get(k, 0)) for k in weights)
    probability = _sigmoid(z)
    score = round(probability * 100, 2)

    return {
        "risk_score": score,
        "risk_band": _risk_band(score),
        "risk_probability": round(probability, 4),
        "explanation": {
            "method": "logistic_batch_baseline",
            "intercept": intercept,
            "feature_contributions": {k: round(weights[k] * float(features.get(k, 0)), 4) for k in weights},
        },
    }


def load_supplier_features(db: Session, supplier_id: str) -> dict:
    query = text(
        """
        WITH base AS (
          SELECT sd.supplier_id,
                 SUM(CASE WHEN sd.received_at > now() - interval '90 day' THEN 1 ELSE 0 END) AS deliveries_90d,
                 SUM(CASE WHEN sd.received_at > now() - interval '90 day' AND sd.status != 'received' THEN 1 ELSE 0 END) AS delayed_90d
          FROM supplier_deliveries sd
          WHERE sd.supplier_id::text = :supplier_id
          GROUP BY sd.supplier_id
        )
        SELECT
          COALESCE(delayed_90d::float / NULLIF(deliveries_90d,0), 0) AS delay_rate_90d,
          0.08::float AS quality_fail_rate_180d,
          0.03::float AS rejection_rate,
          0.22::float AS volume_cv,
          1::float AS critical_nonconformities_12m
        FROM base;
        """
    )
    row = db.execute(query, {"supplier_id": supplier_id}).mappings().first()
    if not row:
        return {
            "delay_rate_90d": 0,
            "quality_fail_rate_180d": 0,
            "rejection_rate": 0,
            "volume_cv": 0,
            "critical_nonconformities_12m": 0,
        }
    return dict(row)


def load_batch_features(db: Session, batch_code: str) -> dict | None:
    batch = db.execute(
        text(
            """
            SELECT batch_id::text AS batch_id, product_sku,
                   GREATEST(EXTRACT(day FROM (now() - produced_at)), 0)::float AS storage_days
            FROM production_batches
            WHERE batch_code = :batch_code
            """
        ),
        {"batch_code": batch_code},
    ).mappings().first()
    if not batch:
        return None

    supplier_risk = db.execute(
        text(
            """
            WITH supplier_ids AS (
              SELECT DISTINCT sd.supplier_id
              FROM production_batches pb
              JOIN batch_material_map bmm ON bmm.batch_id = pb.batch_id
              JOIN raw_material_lots rml ON rml.rm_lot_id = bmm.rm_lot_id
              JOIN supplier_deliveries sd ON sd.delivery_id = rml.delivery_id
              WHERE pb.batch_code = :batch_code
            ), latest_scores AS (
              SELECT ars.entity_id, ars.score,
                     ROW_NUMBER() OVER (PARTITION BY ars.entity_id ORDER BY ars.scored_at DESC) AS rn
              FROM ai_risk_scores ars
              WHERE ars.entity_type = 'supplier'
            )
            SELECT COALESCE(AVG(ls.score)::float, 45.0) AS avg_supplier_score
            FROM supplier_ids s
            LEFT JOIN latest_scores ls ON ls.entity_id = s.supplier_id AND ls.rn = 1
            """
        ),
        {"batch_code": batch_code},
    ).scalar_one()

    open_alerts = db.execute(
        text(
            """
            SELECT COUNT(*)::float
            FROM alerts a
            JOIN production_batches pb ON pb.batch_id = a.batch_id
            WHERE pb.batch_code = :batch_code
              AND a.status = 'open'
            """
        ),
        {"batch_code": batch_code},
    ).scalar_one()

    fail_count = db.execute(
        text(
            """
            SELECT COUNT(*)::float
            FROM quality_test_records q
            JOIN production_batches b ON b.batch_id = q.batch_id
            JOIN compliance_thresholds t
              ON t.parameter_code = q.parameter_code
             AND t.product_category = b.product_sku
             AND t.effective_from <= COALESCE(q.tested_at::date, current_date)
             AND (t.effective_to IS NULL OR t.effective_to >= COALESCE(q.tested_at::date, current_date))
            WHERE b.batch_code = :batch_code
              AND ((t.limit_max IS NOT NULL AND q.observed_value > t.limit_max)
                OR (t.limit_min IS NOT NULL AND q.observed_value < t.limit_min))
            """
        ),
        {"batch_code": batch_code},
    ).scalar_one()

    hist_dev = db.execute(
        text(
            """
            WITH sku_batches AS (
              SELECT pb.batch_id, pb.batch_code
              FROM production_batches pb
              WHERE pb.product_sku = :product_sku
                AND pb.batch_code <> :batch_code
            ), has_fail AS (
              SELECT sb.batch_id,
                     MAX(CASE WHEN ((t.limit_max IS NOT NULL AND q.observed_value > t.limit_max)
                                 OR (t.limit_min IS NOT NULL AND q.observed_value < t.limit_min))
                              THEN 1 ELSE 0 END) AS fail_flag
              FROM sku_batches sb
              LEFT JOIN quality_test_records q ON q.batch_id = sb.batch_id
              LEFT JOIN production_batches b ON b.batch_id = q.batch_id
              LEFT JOIN compliance_thresholds t
                     ON t.parameter_code = q.parameter_code
                    AND t.product_category = b.product_sku
                    AND t.effective_from <= COALESCE(q.tested_at::date, current_date)
                    AND (t.effective_to IS NULL OR t.effective_to >= COALESCE(q.tested_at::date, current_date))
              GROUP BY sb.batch_id
            )
            SELECT COALESCE(AVG(fail_flag)::float, 0) FROM has_fail
            """
        ),
        {"product_sku": batch["product_sku"], "batch_code": batch_code},
    ).scalar_one()

    return {
        "batch_id": batch["batch_id"],
        "supplier_risk_norm": min(max(float(supplier_risk) / 100.0, 0), 1),
        "storage_days_norm": min(float(batch["storage_days"]) / 180.0, 1),
        "open_alerts_norm": min(float(open_alerts) / 10.0, 1),
        "historical_deviation_rate": min(max(float(hist_dev), 0), 1),
        "current_fail_count_norm": min(float(fail_count) / 5.0, 1),
    }


def score_batch_and_store(db: Session, batch_code: str, actor_id: str = "system") -> dict:
    features = load_batch_features(db, batch_code)
    if not features:
        return {"error": "Batch not found"}

    result = batch_risk_score(features)
    risk_id = uuid.uuid4()

    db.execute(
        text(
            """
            INSERT INTO ai_risk_scores (
              risk_id, entity_type, entity_id, model_name, model_version,
              score, risk_band, explanation, scored_at
            ) VALUES (
              :risk_id, 'batch', :entity_id, 'batch_risk_logistic_baseline', 'v1',
              :score, :risk_band, CAST(:explanation AS jsonb), now()
            )
            """
        ),
        {
            "risk_id": risk_id,
            "entity_id": features["batch_id"],
            "score": result["risk_score"],
            "risk_band": result["risk_band"],
            "explanation": json.dumps(result["explanation"] | {"features": features}),
        },
    )

    append_audit_event(
        db,
        actor_id=actor_id,
        action_type="BATCH_RISK_SCORED",
        entity_type="batch",
        entity_id=features["batch_id"],
        payload={"batch_code": batch_code, **result, "features": features},
    )
    db.commit()

    return {"batch_code": batch_code, "features": features, **result}


def _supplier_metric_band(metric: str, value: float) -> str:
    if metric in {"delay_rate_90d", "quality_deviation_rate", "rejection_rate"}:
        if value >= 0.15:
            return "HIGH"
        if value >= 0.05:
            return "MEDIUM"
        return "LOW"
    if metric == "volume_cv":
        if value >= 0.35:
            return "HIGH"
        if value >= 0.20:
            return "MEDIUM"
        return "LOW"
    return "LOW"


def _matrix_zone(probability: float, impact_score: float) -> str:
    if probability >= 0.66 and impact_score >= 66:
        return "CRITICAL"
    if probability >= 0.50 and impact_score >= 50:
        return "HIGH"
    if probability >= 0.33 or impact_score >= 33:
        return "MEDIUM"
    return "LOW"


def list_supplier_risk_heatmap(db: Session, limit: int = 25) -> dict:
    rows = db.execute(
        text(
            """
            WITH delivery_agg AS (
              SELECT
                sd.supplier_id,
                COUNT(*) FILTER (WHERE sd.received_at >= now() - interval '90 day') AS deliveries_90d,
                COUNT(*) FILTER (WHERE sd.received_at >= now() - interval '90 day' AND sd.status <> 'received') AS delayed_90d,
                AVG(sd.received_qty) FILTER (WHERE sd.received_at >= now() - interval '90 day') AS avg_qty_90d,
                COALESCE(STDDEV_POP(sd.received_qty) FILTER (WHERE sd.received_at >= now() - interval '90 day'), 0) AS std_qty_90d
              FROM supplier_deliveries sd
              GROUP BY sd.supplier_id
            ),
            lot_agg AS (
              SELECT
                sd.supplier_id,
                COUNT(*) FILTER (WHERE rml.created_at >= now() - interval '180 day') AS lots_180d,
                COUNT(*) FILTER (
                  WHERE rml.created_at >= now() - interval '180 day'
                    AND LOWER(COALESCE(rml.qc_status, '')) IN ('rejected', 'blocked')
                ) AS rejected_180d
              FROM supplier_deliveries sd
              JOIN raw_material_lots rml ON rml.delivery_id = sd.delivery_id
              GROUP BY sd.supplier_id
            ),
            quality_agg AS (
              SELECT
                sd.supplier_id,
                COUNT(q.test_id) FILTER (WHERE COALESCE(q.tested_at, q.created_at) >= now() - interval '180 day') AS tested_rows_180d,
                COUNT(q.test_id) FILTER (
                  WHERE COALESCE(q.tested_at, q.created_at) >= now() - interval '180 day'
                    AND (
                      (t.limit_max IS NOT NULL AND q.observed_value > t.limit_max)
                      OR (t.limit_min IS NOT NULL AND q.observed_value < t.limit_min)
                    )
                ) AS failed_rows_180d
              FROM supplier_deliveries sd
              JOIN raw_material_lots rml ON rml.delivery_id = sd.delivery_id
              JOIN batch_material_map bmm ON bmm.rm_lot_id = rml.rm_lot_id
              JOIN production_batches pb ON pb.batch_id = bmm.batch_id
              LEFT JOIN quality_test_records q ON q.batch_id = pb.batch_id
              LEFT JOIN compliance_thresholds t
                ON t.parameter_code = q.parameter_code
               AND t.standard_name = 'HACCP_INTERNAL'
               AND t.product_category = pb.product_sku
               AND t.effective_from <= COALESCE(q.tested_at::date, current_date)
               AND (t.effective_to IS NULL OR t.effective_to >= COALESCE(q.tested_at::date, current_date))
              GROUP BY sd.supplier_id
            ),
            latest_scores AS (
              SELECT
                ars.entity_id,
                ars.score,
                ars.risk_band,
                ROW_NUMBER() OVER (PARTITION BY ars.entity_id ORDER BY ars.scored_at DESC) AS rn
              FROM ai_risk_scores ars
              WHERE ars.entity_type = 'supplier'
            )
            SELECT
              s.supplier_id::text AS supplier_id,
              s.name AS supplier_name,
              COALESCE(da.deliveries_90d, 0) AS deliveries_90d,
              COALESCE(qa.tested_rows_180d, 0) AS tested_rows_180d,
              COALESCE(la.lots_180d, 0) AS lots_180d,
              COALESCE(da.delayed_90d::float / NULLIF(da.deliveries_90d, 0), 0) AS delay_rate_90d,
              COALESCE(qa.failed_rows_180d::float / NULLIF(qa.tested_rows_180d, 0), 0) AS quality_deviation_rate,
              COALESCE(la.rejected_180d::float / NULLIF(la.lots_180d, 0), 0) AS rejection_rate,
              CASE
                WHEN COALESCE(da.avg_qty_90d, 0) = 0 THEN 0
                ELSE COALESCE(da.std_qty_90d, 0) / NULLIF(da.avg_qty_90d, 0)
              END AS volume_cv,
              ls.score AS latest_score,
              ls.risk_band AS latest_risk_band
            FROM suppliers s
            LEFT JOIN delivery_agg da ON da.supplier_id = s.supplier_id
            LEFT JOIN lot_agg la ON la.supplier_id = s.supplier_id
            LEFT JOIN quality_agg qa ON qa.supplier_id = s.supplier_id
            LEFT JOIN latest_scores ls ON ls.entity_id = s.supplier_id AND ls.rn = 1
            WHERE LOWER(COALESCE(s.status, 'active')) = 'active'
            ORDER BY COALESCE(ls.score, 0) DESC, s.name
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()

    out_rows = []
    low = 0
    medium = 0
    high = 0

    for row in rows:
        features = {
            "delay_rate_90d": float(row["delay_rate_90d"] or 0),
            "quality_fail_rate_180d": float(row["quality_deviation_rate"] or 0),
            "rejection_rate": float(row["rejection_rate"] or 0),
            "volume_cv": float(row["volume_cv"] or 0),
            "critical_nonconformities_12m": 0.0,
        }
        inferred = supplier_risk_score(features)
        score = float(row["latest_score"]) if row["latest_score"] is not None else float(inferred["risk_score"])
        band = str(row["latest_risk_band"] or inferred["risk_band"]).upper()
        if band == "HIGH":
            high += 1
        elif band == "MEDIUM":
            medium += 1
        else:
            low += 1

        delay_rate = float(row["delay_rate_90d"] or 0)
        quality_dev = float(row["quality_deviation_rate"] or 0)
        rejection_rate = float(row["rejection_rate"] or 0)
        volume_cv = float(row["volume_cv"] or 0)

        out_rows.append(
            {
                "supplier_id": row["supplier_id"],
                "supplier_name": row["supplier_name"],
                "deliveries_90d": int(row["deliveries_90d"] or 0),
                "tested_rows_180d": int(row["tested_rows_180d"] or 0),
                "lots_180d": int(row["lots_180d"] or 0),
                "delay_rate_pct": round(delay_rate * 100, 2),
                "quality_deviation_rate_pct": round(quality_dev * 100, 2),
                "rejection_rate_pct": round(rejection_rate * 100, 2),
                "volume_cv": round(volume_cv, 3),
                "delay_band": _supplier_metric_band("delay_rate_90d", delay_rate),
                "quality_band": _supplier_metric_band("quality_deviation_rate", quality_dev),
                "rejection_band": _supplier_metric_band("rejection_rate", rejection_rate),
                "volume_band": _supplier_metric_band("volume_cv", volume_cv),
                "risk_score": round(score, 2),
                "risk_band": band,
                "score_source": "model" if row["latest_score"] is not None else "estimated",
            }
        )

    return {
        "rows": out_rows,
        "summary": {
            "total_suppliers": len(out_rows),
            "high_risk_suppliers": high,
            "medium_risk_suppliers": medium,
            "low_risk_suppliers": low,
        },
    }


def list_batch_risk_matrix(db: Session, limit: int = 40) -> dict:
    rows = db.execute(
        text(
            """
            WITH dispatch_agg AS (
              SELECT
                pb.batch_id,
                COALESCE(SUM(dr.dispatch_qty), 0)::float AS dispatch_qty_total,
                COALESCE(SUM(CASE WHEN c.customer_type = 'exporter' OR c.country_code <> 'IN' THEN dr.dispatch_qty ELSE 0 END), 0)::float AS export_dispatch_qty,
                COALESCE(SUM(CASE WHEN c.customer_type = 'distributor' THEN dr.dispatch_qty ELSE 0 END), 0)::float AS distributor_dispatch_qty,
                COUNT(DISTINCT dr.customer_id) AS customer_count
              FROM production_batches pb
              LEFT JOIN finished_products fp ON fp.batch_id = pb.batch_id
              LEFT JOIN dispatch_records dr ON dr.finished_id = fp.finished_id
              LEFT JOIN customers c ON c.customer_id = dr.customer_id
              GROUP BY pb.batch_id
            ),
            open_alert_agg AS (
              SELECT a.batch_id, COUNT(*)::int AS open_alert_count
              FROM alerts a
              WHERE a.status = 'open'
              GROUP BY a.batch_id
            ),
            latest_batch_scores AS (
              SELECT
                ars.entity_id,
                ars.score,
                ars.risk_band,
                ROW_NUMBER() OVER (PARTITION BY ars.entity_id ORDER BY ars.scored_at DESC) AS rn
              FROM ai_risk_scores ars
              WHERE ars.entity_type = 'batch'
            )
            SELECT
              pb.batch_id::text AS batch_id,
              pb.batch_code,
              pb.product_sku,
              pb.produced_at,
              COALESCE(da.dispatch_qty_total, 0) AS dispatch_qty_total,
              COALESCE(da.export_dispatch_qty, 0) AS export_dispatch_qty,
              COALESCE(da.distributor_dispatch_qty, 0) AS distributor_dispatch_qty,
              COALESCE(da.customer_count, 0) AS customer_count,
              COALESCE(oa.open_alert_count, 0) AS open_alert_count,
              lbs.score AS latest_score,
              lbs.risk_band AS latest_risk_band
            FROM production_batches pb
            LEFT JOIN dispatch_agg da ON da.batch_id = pb.batch_id
            LEFT JOIN open_alert_agg oa ON oa.batch_id = pb.batch_id
            LEFT JOIN latest_batch_scores lbs ON lbs.entity_id = pb.batch_id AND lbs.rn = 1
            WHERE pb.produced_at >= now() - interval '180 day'
            ORDER BY pb.produced_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()

    points = []
    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for row in rows:
        if row["latest_score"] is not None:
            score = float(row["latest_score"])
            source = "model"
            model_band = str(row["latest_risk_band"] or _risk_band(score)).upper()
        else:
            fallback = load_batch_features(db, str(row["batch_code"]))
            if fallback:
                estimated = batch_risk_score(fallback)
                score = float(estimated["risk_score"])
                model_band = str(estimated["risk_band"]).upper()
                source = "estimated"
            else:
                score = 0.0
                model_band = "LOW"
                source = "na"

        probability = round(max(min(score / 100.0, 1.0), 0.0), 4)

        dispatch_qty_total = float(row["dispatch_qty_total"] or 0)
        export_qty = float(row["export_dispatch_qty"] or 0)
        distributor_qty = float(row["distributor_dispatch_qty"] or 0)

        if export_qty > 0:
            market_factor = 1.0
        elif distributor_qty > 0:
            market_factor = 0.75
        else:
            market_factor = 0.55

        qty_norm = min(dispatch_qty_total / 1000.0, 1.0)
        impact_score = round(min(qty_norm * market_factor, 1.0) * 100.0, 2)
        zone = _matrix_zone(probability, impact_score)
        summary[zone] += 1

        points.append(
            {
                "batch_id": row["batch_id"],
                "batch_code": row["batch_code"],
                "product_sku": row["product_sku"],
                "produced_at": row["produced_at"],
                "predicted_deviation_probability": probability,
                "predicted_score": round(score, 2),
                "impact_score": impact_score,
                "impact_inputs": {
                    "dispatch_qty_total": round(dispatch_qty_total, 3),
                    "export_dispatch_qty": round(export_qty, 3),
                    "distributor_dispatch_qty": round(distributor_qty, 3),
                    "customer_count": int(row["customer_count"] or 0),
                    "market_factor": market_factor,
                    "open_alert_count": int(row["open_alert_count"] or 0),
                },
                "risk_zone": zone,
                "model_risk_band": model_band,
                "score_source": source,
            }
        )

    points.sort(key=lambda p: (p["predicted_deviation_probability"], p["impact_score"]), reverse=True)
    return {
        "rows": points,
        "summary": {
            "total_batches": len(points),
            "critical_zone": summary["CRITICAL"],
            "high_zone": summary["HIGH"],
            "medium_zone": summary["MEDIUM"],
            "low_zone": summary["LOW"],
        },
    }
