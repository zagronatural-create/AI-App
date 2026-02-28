from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_roles
from app.db.session import get_db
from app.schemas.risk import AnomalyScanIn, SupplierFeatureInput
from app.services.anomaly import list_anomalies, run_anomaly_scan
from app.services.risk import (
    list_batch_risk_matrix,
    list_supplier_risk_heatmap,
    load_supplier_features,
    score_batch_and_store,
    supplier_risk_score,
)

router = APIRouter()


@router.post("/supplier/score")
def score_supplier_from_features(payload: SupplierFeatureInput) -> dict:
    return supplier_risk_score(payload.model_dump())


@router.get("/supplier/{supplier_id}/score")
def score_supplier_from_db(supplier_id: str, db: Session = Depends(get_db)) -> dict:
    features = load_supplier_features(db, supplier_id)
    score = supplier_risk_score(features)
    return {"supplier_id": supplier_id, "features": features, **score}


@router.post("/batch/{batch_code}/score")
def score_batch(
    batch_code: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("qa_analyst", "qa_manager", "compliance_manager", "admin")),
) -> dict:
    return score_batch_and_store(db, batch_code=batch_code, actor_id=current_user.user_id)


@router.post("/anomalies/run")
def run_anomalies(
    payload: AnomalyScanIn,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("qa_analyst", "qa_manager", "compliance_manager", "admin")),
) -> dict:
    actor_id = payload.actor_id or current_user.user_id
    return run_anomaly_scan(
        db,
        lookback_hours=payload.lookback_hours,
        z_threshold=payload.z_threshold,
        actor_id=actor_id,
    )


@router.get("/anomalies")
def get_anomalies(limit: int = 200, db: Session = Depends(get_db)) -> dict:
    return {"rows": list_anomalies(db, limit=limit)}


@router.get("/supplier/heatmap")
def supplier_heatmap(
    limit: int = 25,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(
        require_roles("viewer", "qa_analyst", "qa_manager", "compliance_manager", "ops_scheduler", "admin")
    ),
) -> dict:
    _ = current_user
    safe_limit = min(max(int(limit), 1), 200)
    data = list_supplier_risk_heatmap(db, limit=safe_limit)
    data["note"] = "Supplier heatmap is AI-assisted risk intelligence, not legal certification."
    return data


@router.get("/batch/risk-matrix")
def batch_risk_matrix(
    limit: int = 40,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(
        require_roles("viewer", "qa_analyst", "qa_manager", "compliance_manager", "ops_scheduler", "admin")
    ),
) -> dict:
    _ = current_user
    safe_limit = min(max(int(limit), 1), 300)
    data = list_batch_risk_matrix(db, limit=safe_limit)
    data["note"] = "Batch matrix supports prioritization; final release/recall decisions remain with authorized teams."
    return data
