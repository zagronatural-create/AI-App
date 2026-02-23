from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.compliance import normalize_parameter_code, parse_lab_text


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def ingest_lab_report(
    db: Session,
    *,
    batch_code: str,
    uploaded_by: str,
    lab_name: str,
    fssai_approved: bool,
    filename: str,
    file_content: bytes,
) -> dict:
    batch_row = db.execute(
        text("SELECT batch_id, product_sku FROM production_batches WHERE batch_code = :batch_code"),
        {"batch_code": batch_code},
    ).mappings().first()
    if not batch_row:
        return {"error": "Batch not found"}

    batch_id = batch_row["batch_id"]
    report_hash = _sha256_bytes(file_content)

    prev = db.execute(
        text(
            """
            SELECT report_id, version_no
            FROM lab_reports
            WHERE batch_id = :batch_id AND lab_name = :lab_name
            ORDER BY version_no DESC
            LIMIT 1
            """
        ),
        {"batch_id": batch_id, "lab_name": lab_name},
    ).mappings().first()

    version_no = (prev["version_no"] + 1) if prev else 1
    supersedes = prev["report_id"] if prev else None
    report_id = uuid.uuid4()

    batch_folder = Path(settings.storage_dir) / "lab_reports" / batch_code
    _ensure_dir(batch_folder)
    stamped_name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{filename}"
    output_path = batch_folder / stamped_name
    output_path.write_bytes(file_content)

    text_content = extract_pdf_text(file_content)
    extracted_rows = parse_lab_text(text_content)

    try:
        db.execute(
            text(
                """
                INSERT INTO lab_reports (
                  report_id, batch_id, file_url, report_hash, lab_name, fssai_approved,
                  version_no, uploaded_by, uploaded_at, supersedes_report_id
                ) VALUES (
                  :report_id, :batch_id, :file_url, :report_hash, :lab_name, :fssai_approved,
                  :version_no, :uploaded_by, now(), :supersedes
                )
                """
            ),
            {
                "report_id": report_id,
                "batch_id": batch_id,
                "file_url": str(output_path),
                "report_hash": report_hash,
                "lab_name": lab_name,
                "fssai_approved": fssai_approved,
                "version_no": version_no,
                "uploaded_by": uploaded_by,
                "supersedes": supersedes,
            },
        )

        inserted = 0
        for row in extracted_rows:
            db.execute(
                text(
                    """
                    INSERT INTO quality_test_records (
                      test_id, batch_id, report_id, parameter_code, parameter_name,
                      observed_value, unit, tested_at, created_at
                    ) VALUES (
                      :test_id, :batch_id, :report_id, :parameter_code, :parameter_name,
                      :observed_value, :unit, now(), now()
                    )
                    """
                ),
                {
                    "test_id": uuid.uuid4(),
                    "batch_id": batch_id,
                    "report_id": report_id,
                    "parameter_code": normalize_parameter_code(row["parameter_name"]),
                    "parameter_name": row["parameter_name"],
                    "observed_value": row["observed_value"],
                    "unit": row["unit"],
                },
            )
            inserted += 1

        db.commit()
    except Exception:
        db.rollback()
        raise

    warnings = []
    if not text_content:
        warnings.append("No extractable PDF text found; scanned-image OCR stage not configured yet.")
    if not extracted_rows:
        warnings.append("No structured parameter rows were extracted from PDF text.")

    return {
        "report_id": str(report_id),
        "batch_code": batch_code,
        "version_no": version_no,
        "supersedes_report_id": str(supersedes) if supersedes else None,
        "stored_file": str(output_path),
        "report_hash": report_hash,
        "extracted_rows": inserted,
        "warnings": warnings,
        "disclaimer": "AI-assisted extraction only; this workflow does not issue legal certifications.",
    }


def list_batch_reports(db: Session, batch_code: str) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT lr.report_id::text AS report_id,
                   pb.batch_code,
                   lr.lab_name,
                   lr.version_no,
                   lr.supersedes_report_id::text AS supersedes_report_id,
                   lr.report_hash,
                   lr.file_url,
                   lr.uploaded_by,
                   lr.uploaded_at
            FROM lab_reports lr
            JOIN production_batches pb ON pb.batch_id = lr.batch_id
            WHERE pb.batch_code = :batch_code
            ORDER BY lr.lab_name, lr.version_no DESC
            """
        ),
        {"batch_code": batch_code},
    ).mappings()
    return [dict(row) for row in rows]


def create_ingestion_job(
    db: Session,
    *,
    batch_code: str,
    uploaded_by: str,
    lab_name: str,
    fssai_approved: bool,
    filename: str,
    file_content: bytes,
) -> dict:
    job_id = uuid.uuid4()
    jobs_folder = Path(settings.storage_dir) / "jobs"
    _ensure_dir(jobs_folder)
    job_file = jobs_folder / f"{job_id}.pdf"
    job_file.write_bytes(file_content)

    payload = {
        "uploaded_by": uploaded_by,
        "lab_name": lab_name,
        "fssai_approved": fssai_approved,
        "filename": filename,
        "job_file": str(job_file),
    }

    db.execute(
        text(
            """
            INSERT INTO ingestion_jobs (job_id, status, batch_code, payload, created_at)
            VALUES (:job_id, 'queued', :batch_code, CAST(:payload AS jsonb), now())
            """
        ),
        {"job_id": job_id, "batch_code": batch_code, "payload": json.dumps(payload)},
    )
    db.commit()

    return {
        "job_id": str(job_id),
        "status": "queued",
        "batch_code": batch_code,
        "disclaimer": "Asynchronous AI-assisted processing started; not a legal certification workflow.",
    }


def process_ingestion_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT job_id::text AS job_id, batch_code, payload
                FROM ingestion_jobs
                WHERE job_id = :job_id
                """
            ),
            {"job_id": job_id},
        ).mappings().first()

        if not row:
            return

        db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'processing', started_at = now(), error_message = NULL
                WHERE job_id = :job_id
                """
            ),
            {"job_id": job_id},
        )
        db.commit()

        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        job_file = Path(payload["job_file"])
        content = job_file.read_bytes()

        result = ingest_lab_report(
            db,
            batch_code=row["batch_code"],
            uploaded_by=payload["uploaded_by"],
            lab_name=payload["lab_name"],
            fssai_approved=bool(payload["fssai_approved"]),
            filename=payload["filename"],
            file_content=content,
        )

        db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'completed', completed_at = now(), result = CAST(:result AS jsonb)
                WHERE job_id = :job_id
                """
            ),
            {"job_id": job_id, "result": json.dumps(result)},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        db.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'failed', completed_at = now(), error_message = :error_message
                WHERE job_id = :job_id
                """
            ),
            {"job_id": job_id, "error_message": str(exc)},
        )
        db.commit()
    finally:
        db.close()


def get_ingestion_job(db: Session, job_id: str) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT job_id::text AS job_id, job_type, status, batch_code, result, error_message,
                   created_at, started_at, completed_at
            FROM ingestion_jobs
            WHERE job_id = :job_id
            """
        ),
        {"job_id": job_id},
    ).mappings().first()
    if not row:
        return None
    out = dict(row)
    out["disclaimer"] = "Job status is operational intelligence only and not a legal certification decision."
    return out
