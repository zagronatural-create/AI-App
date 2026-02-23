from __future__ import annotations

from pydantic import BaseModel, Field


class AuditPackGenerateIn(BaseModel):
    limit: int = Field(default=5000, ge=1, le=50000)
    actor_id: str | None = None
    action_type: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    from_ts: str | None = None
    to_ts: str | None = None
    notes: str | None = None
