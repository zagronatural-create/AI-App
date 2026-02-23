from __future__ import annotations

from pydantic import BaseModel


class ComplianceRow(BaseModel):
    parameter: str
    batch_value: float
    unit: str
    fssai_limit: str | None
    eu_limit: str | None
    codex_limit: str | None
    haccp_limit: str | None
    status: str
    risk_flag: str


class ParseTextRequest(BaseModel):
    raw_text: str
