from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_roles
from app.db.session import get_db
from app.schemas.compliance import ParseTextRequest
from app.services.compliance import batch_comparison, parse_lab_text
from app.services.lab_ingestion import (
    create_ingestion_job,
    get_ingestion_job,
    ingest_lab_report,
    list_batch_reports,
    process_ingestion_job,
)
from app.services.reporting import export_readiness_summary

router = APIRouter()


@router.post("/labs/reports/parse-text")
def parse_report_text(payload: ParseTextRequest) -> dict:
    extracted = parse_lab_text(payload.raw_text)
    return {
        "message": "Extracted parameter candidates from report text",
        "extracted": extracted,
        "note": "This parser is AI-assistive extraction, not legal certification.",
    }


@router.post("/labs/reports/upload")
async def upload_lab_report(
    batch_code: str = Form(...),
    uploaded_by: str | None = Form(None),
    lab_name: str = Form(...),
    fssai_approved: bool = Form(False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("qa_analyst", "compliance_manager", "admin")),
) -> dict:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    result = ingest_lab_report(
        db,
        batch_code=batch_code,
        uploaded_by=uploaded_by or current_user.user_id,
        lab_name=lab_name,
        fssai_approved=fssai_approved,
        filename=file.filename,
        file_content=content,
    )
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/labs/reports/upload-async")
async def upload_lab_report_async(
    background_tasks: BackgroundTasks,
    batch_code: str = Form(...),
    uploaded_by: str | None = Form(None),
    lab_name: str = Form(...),
    fssai_approved: bool = Form(False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("qa_analyst", "compliance_manager", "admin")),
) -> dict:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    created = create_ingestion_job(
        db,
        batch_code=batch_code,
        uploaded_by=uploaded_by or current_user.user_id,
        lab_name=lab_name,
        fssai_approved=fssai_approved,
        filename=file.filename,
        file_content=content,
    )
    background_tasks.add_task(process_ingestion_job, created["job_id"])
    return created


@router.get("/labs/reports/jobs/{job_id}")
def get_ingestion_job_status(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = get_ingestion_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/labs/reports/{batch_code}/versions")
def get_report_versions(batch_code: str, db: Session = Depends(get_db)) -> dict:
    return {"batch_code": batch_code, "reports": list_batch_reports(db, batch_code)}


@router.get("/batch/{batch_code}/comparison")
def get_batch_comparison(batch_code: str, db: Session = Depends(get_db)) -> dict:
    rows = batch_comparison(db, batch_code)
    return {
        "batch_code": batch_code,
        "comparison": rows,
        "summary": {
            "total_parameters": len(rows),
            "fail_count": sum(1 for row in rows if row["status"] == "FAIL"),
            "warning_count": sum(1 for row in rows if row["status"] == "WARNING"),
        },
        "disclaimer": "AI-assisted compliance intelligence only; final regulatory decisions remain with authorized teams.",
    }


@router.get("/batch/{batch_code}/comparison/export.csv")
def export_batch_comparison_csv(
    batch_code: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles("viewer", "qa_analyst", "qa_manager", "compliance_manager", "admin")),
) -> StreamingResponse:
    _ = current_user
    rows = batch_comparison(db, batch_code)
    if not rows:
        raise HTTPException(status_code=404, detail="No comparison data found for batch")

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "parameter_code",
            "batch_value",
            "fssai_limit",
            "eu_limit",
            "codex_limit",
            "haccp_limit",
            "status",
            "risk_flag",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.get("parameter_code"),
                row.get("batch_value"),
                row.get("fssai_limit"),
                row.get("eu_limit"),
                row.get("codex_limit"),
                row.get("haccp_limit"),
                row.get("status"),
                row.get("risk_flag"),
            ]
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"batch_comparison_{batch_code}_{ts}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)


@router.get("/batch/{batch_code}/export-readiness")
def get_export_readiness(batch_code: str, db: Session = Depends(get_db)) -> dict:
    return export_readiness_summary(db, batch_code)
