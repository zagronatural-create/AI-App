from __future__ import annotations

from pydantic import BaseModel, Field


class CcpLogIn(BaseModel):
    batch_code: str
    ccp_code: str
    metric_name: str
    metric_value: float
    unit: str
    measured_at: str = Field(description="ISO datetime")
    operator_id: str | None = None
    source: str = "iot"


class AlertAckIn(BaseModel):
    acknowledged_by: str | None = None
