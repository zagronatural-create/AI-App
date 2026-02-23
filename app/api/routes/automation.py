from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_roles
from app.db.session import get_db
from app.services.automation import (
    get_automation_status,
    list_automation_runs,
    mark_stuck_runs_failed,
    run_daily_cycle,
    run_daily_cycle_detached,
)

router = APIRouter()


@router.post("/run-daily")
def run_daily(
    actor_id: str = "api.user",
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("ops_scheduler", "admin")),
) -> dict:
    chosen_actor = actor_id if actor_id != "api.user" else current_user.user_id
    return run_daily_cycle(db, actor_id=chosen_actor)


@router.post("/run-daily-async")
def run_daily_async(
    background_tasks: BackgroundTasks,
    actor_id: str = "api.user",
    current_user: AuthUser = Depends(require_roles("ops_scheduler", "admin")),
) -> dict:
    chosen_actor = actor_id if actor_id != "api.user" else current_user.user_id
    background_tasks.add_task(run_daily_cycle_detached, chosen_actor)
    return {
        "status": "queued",
        "message": "Daily cycle accepted for background execution.",
        "actor_id": chosen_actor,
    }


@router.get("/runs")
def runs(limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)) -> dict:
    return {"rows": list_automation_runs(db, limit=limit)}


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    return get_automation_status(db)


@router.post("/watchdog/mark-stuck-failed")
def watchdog_mark_stuck_failed(
    timeout_minutes: int = Query(default=120, ge=30, le=1440),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("ops_scheduler", "admin")),
) -> dict:
    count = mark_stuck_runs_failed(db, timeout_minutes=timeout_minutes)
    return {
        "marked_failed_runs": count,
        "timeout_minutes": timeout_minutes,
        "actor_id": current_user.user_id,
    }
