from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.dashboard import get_overview

router = APIRouter()


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    return get_overview(db)
