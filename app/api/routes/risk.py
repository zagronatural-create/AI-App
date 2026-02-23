from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_roles
from app.db.session import get_db
from app.schemas.risk import AnomalyScanIn, SupplierFeatureInput
from app.services.anomaly import list_anomalies, run_anomaly_scan
from app.services.risk import load_supplier_features, score_batch_and_store, supplier_risk_score

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
