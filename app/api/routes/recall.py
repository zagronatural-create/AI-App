from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.recall import RecallSimulationRequest
from app.services.recall import simulate_recall

router = APIRouter()


@router.post("/simulate")
def run_simulation(payload: RecallSimulationRequest, db: Session = Depends(get_db)) -> dict:
    simulation = simulate_recall(db, payload.batch_code)
    return {
        "simulation": simulation,
        "note": "Simulation output assists operations planning and does not replace regulatory recall procedures.",
    }
