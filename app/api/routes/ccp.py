from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_roles
from app.db.session import get_db
from app.schemas.ccp import AlertAckIn, CcpLogIn
from app.services.ccp import acknowledge_alert, batch_ccp_timeline, ingest_ccp_log, list_alerts

router = APIRouter()


@router.post("/logs")
def create_ccp_log(
    payload: CcpLogIn,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("qa_analyst", "qa_manager", "admin")),
) -> dict:
    operator_id = payload.operator_id or current_user.user_id
    result = ingest_ccp_log(
        db,
        batch_code=payload.batch_code,
        ccp_code=payload.ccp_code,
        metric_name=payload.metric_name,
        metric_value=payload.metric_value,
        unit=payload.unit,
        measured_at=payload.measured_at,
        operator_id=operator_id,
        source=payload.source,
    )
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/alerts")
def get_alerts(
    status: str = Query(default="open", pattern="^(open|acknowledged|all)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict:
    return {"status": status, "rows": list_alerts(db, status=status, limit=limit)}


@router.get("/batch/{batch_code}/timeline")
def get_batch_timeline(
    batch_code: str,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict:
    return batch_ccp_timeline(db, batch_code=batch_code, limit=limit)


@router.patch("/alerts/{alert_id}/ack")
def ack_alert(
    alert_id: str,
    payload: AlertAckIn,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("qa_manager", "compliance_manager", "admin")),
) -> dict:
    ack_by = payload.acknowledged_by or current_user.user_id
    updated = acknowledge_alert(db, alert_id=alert_id, acknowledged_by=ack_by)
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")
    return updated
