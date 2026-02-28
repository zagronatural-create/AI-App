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
