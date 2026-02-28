from __future__ import annotations

from datetime import date
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_roles
from app.db.session import get_db
from app.schemas.regulatory import ThresholdReleaseApproveIn, ThresholdReleasePublishIn
from app.services.regulatory import (
    active_coverage_report,
    approve_threshold_release,
    get_threshold_release,
    import_threshold_release,
    list_parameter_requirements,
    list_threshold_releases,
    publish_threshold_release,
    release_coverage_report,
    release_summary_for_ui,
)

router = APIRouter()


@router.post("/releases/import-csv")
async def import_release_csv(
    standard_name: str = Form(...),
    release_code: str = Form(...),
    document_title: str = Form(...),
    effective_from: str = Form(...),
    imported_by: str | None = Form(None),
    jurisdiction: str | None = Form(None),
    source_authority: str | None = Form(None),
    document_url: str | None = Form(None),
    publication_date: str | None = Form(None),
    effective_to: str | None = Form(None),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("qa_manager", "compliance_manager", "admin")),
) -> dict:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV uploads are supported")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    actor = imported_by or current_user.user_id
    try:
        return import_threshold_release(
            db,
            standard_name=standard_name,
            release_code=release_code,
            document_title=document_title,
            effective_from=effective_from,
            imported_by=actor,
            csv_bytes=content,
            jurisdiction=jurisdiction,
            source_authority=source_authority,
            document_url=document_url,
            publication_date=publication_date,
            effective_to=effective_to,
            notes=notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/releases")
def get_releases(
    limit: int = Query(default=100, ge=1, le=500),
    standard_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(
        require_roles("viewer", "qa_analyst", "qa_manager", "compliance_manager", "admin")
    ),
) -> dict:
    _ = current_user
    return {"rows": list_threshold_releases(db, limit=limit, standard_name=standard_name)}


@router.get("/releases/summary")
def get_release_summary(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(
        require_roles("viewer", "qa_analyst", "qa_manager", "compliance_manager", "admin")
    ),
) -> dict:
    _ = current_user
    return release_summary_for_ui(db, limit=limit)


@router.get("/releases/{release_id}")
def release_detail(
    release_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(
        require_roles("viewer", "qa_analyst", "qa_manager", "compliance_manager", "admin")
    ),
) -> dict:
    _ = current_user
    row = get_threshold_release(db, str(release_id))
    if not row:
        raise HTTPException(status_code=404, detail="Release not found")
    return row


@router.get("/releases/{release_id}/coverage")
def release_coverage(
    release_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(
        require_roles("viewer", "qa_analyst", "qa_manager", "compliance_manager", "admin")
    ),
) -> dict:
    _ = current_user
    try:
        return release_coverage_report(db, release_id=str(release_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/coverage/active")
def active_coverage(
    as_of: str | None = Query(default=None, description="YYYY-MM-DD"),
    product_category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(
        require_roles("viewer", "qa_analyst", "qa_manager", "compliance_manager", "admin")
    ),
) -> dict:
    _ = current_user
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid as_of date format. Use YYYY-MM-DD.") from exc
    return active_coverage_report(db, as_of=as_of_date, product_category=product_category)


@router.get("/coverage/requirements")
def coverage_requirements(
    as_of: str | None = Query(default=None, description="YYYY-MM-DD"),
    product_category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(
        require_roles("viewer", "qa_analyst", "qa_manager", "compliance_manager", "admin")
    ),
) -> dict:
    _ = current_user
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid as_of date format. Use YYYY-MM-DD.") from exc
    return list_parameter_requirements(db, as_of=as_of_date, product_category=product_category)


@router.post("/releases/{release_id}/approve")
def approve_release(
    release_id: uuid.UUID,
    payload: ThresholdReleaseApproveIn,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("qa_manager", "compliance_manager", "admin")),
) -> dict:
    actor = payload.approved_by or current_user.user_id
    try:
        return approve_threshold_release(
            db,
            release_id=str(release_id),
            approved_by=actor,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/releases/{release_id}/publish")
def publish_release(
    release_id: uuid.UUID,
    payload: ThresholdReleasePublishIn,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("qa_manager", "compliance_manager", "admin")),
) -> dict:
    actor = payload.published_by or current_user.user_id
    try:
        return publish_threshold_release(db, release_id=str(release_id), published_by=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
