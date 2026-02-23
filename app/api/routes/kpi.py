from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.kpi import get_daily_kpi

router = APIRouter()


@router.get("/daily")
def kpi_daily(db: Session = Depends(get_db)) -> dict:
    return {"rows": get_daily_kpi(db)}
