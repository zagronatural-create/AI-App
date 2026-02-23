from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_roles
from app.db.session import get_db
from app.schemas.audit import AuditPackGenerateIn
from app.services.audit_pack import generate_audit_pack, list_audit_packs, resolve_pack_file, verify_audit_pack
from app.services.audit import audit_events_to_csv, get_audit_event, list_audit_events

router = APIRouter()


@router.get('/events')
def events(
    limit: int = Query(default=200, ge=1, le=1000),
    actor_id: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    from_ts: str | None = Query(default=None, description='ISO timestamp'),
    to_ts: str | None = Query(default=None, description='ISO timestamp'),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles('viewer', 'qa_manager', 'compliance_manager', 'admin')),
) -> dict:
    rows = list_audit_events(
        db,
        limit=limit,
        actor_id=actor_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return {
        'rows': rows,
        'requested_by': current_user.user_id,
        'disclaimer': 'Audit event views support investigation and documentation; they are not legal certifications.',
    }


@router.get('/events/export.csv')
def events_export_csv(
    limit: int = Query(default=1000, ge=1, le=10000),
    actor_id: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    from_ts: str | None = Query(default=None, description='ISO timestamp'),
    to_ts: str | None = Query(default=None, description='ISO timestamp'),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles('viewer', 'qa_manager', 'compliance_manager', 'admin')),
) -> StreamingResponse:
    rows = list_audit_events(
        db,
        limit=limit,
        actor_id=actor_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    csv_data = audit_events_to_csv(rows)
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    filename = f'audit_events_{ts}.csv'
    headers = {'Content-Disposition': f'attachment; filename=\"{filename}\"'}
    return StreamingResponse(iter([csv_data]), media_type='text/csv', headers=headers)


@router.get('/events/{audit_id}')
def event_detail(
    audit_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles('viewer', 'qa_manager', 'compliance_manager', 'admin')),
) -> dict:
    row = get_audit_event(db, audit_id)
    if not row:
        raise HTTPException(status_code=404, detail='Audit event not found')
    return {'event': row, 'requested_by': current_user.user_id}


@router.post('/packs/generate')
def generate_pack(
    payload: AuditPackGenerateIn,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles('qa_manager', 'compliance_manager', 'admin')),
) -> dict:
    return generate_audit_pack(
        db,
        created_by=current_user.user_id,
        limit=payload.limit,
        actor_id=payload.actor_id,
        action_type=payload.action_type,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        from_ts=payload.from_ts,
        to_ts=payload.to_ts,
        notes=payload.notes,
    )


@router.post('/packs/{pack_id}/verify')
def verify_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles('viewer', 'qa_manager', 'compliance_manager', 'admin')),
) -> dict:
    result = verify_audit_pack(db, pack_id=pack_id, verified_by=current_user.user_id)
    if not result:
        raise HTTPException(status_code=404, detail='Audit pack not found')
    return result


@router.get('/packs')
def packs(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles('viewer', 'qa_manager', 'compliance_manager', 'admin')),
) -> dict:
    return {'rows': list_audit_packs(db, limit=limit), 'requested_by': current_user.user_id}


@router.get('/packs/{pack_id}/download/{file_name}')
def pack_download(
    pack_id: str,
    file_name: str,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(require_roles('viewer', 'qa_manager', 'compliance_manager', 'admin')),
) -> FileResponse:
    _ = current_user
    file_path = resolve_pack_file(db, pack_id=pack_id, file_name=file_name)
    if not file_path:
        raise HTTPException(status_code=404, detail='Pack file not found')
    return FileResponse(path=file_path, filename=file_name, media_type='application/octet-stream')
