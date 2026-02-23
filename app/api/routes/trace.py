from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.trace import trace_backward, trace_forward

router = APIRouter()


@router.get("/batch/{batch_code}/backward")
def get_backward(batch_code: str, db: Session = Depends(get_db)) -> dict:
    data = trace_backward(db, batch_code)
    if not data["suppliers"] and not data["raw_material_lots"]:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {"batch_code": batch_code, "backward": data}


@router.get("/batch/{batch_code}/forward")
def get_forward(batch_code: str, db: Session = Depends(get_db)) -> dict:
    data = trace_forward(db, batch_code)
    if not data["finished_lots"] and not data["customers"]:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {"batch_code": batch_code, "forward": data}


@router.get("/batch/{batch_code}/full")
def get_full_trace(batch_code: str, db: Session = Depends(get_db)) -> dict:
    backward = trace_backward(db, batch_code)
    forward = trace_forward(db, batch_code)
    if not backward["suppliers"] and not forward["finished_lots"]:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {"batch_code": batch_code, "backward": backward, "forward": forward}
