from __future__ import annotations

from pydantic import BaseModel


class SupplierFeatureInput(BaseModel):
    delay_rate_90d: float = 0
    quality_fail_rate_180d: float = 0
    rejection_rate: float = 0
    volume_cv: float = 0
    critical_nonconformities_12m: float = 0


class AnomalyScanIn(BaseModel):
    lookback_hours: int = 72
    z_threshold: float = 2.5
    actor_id: str | None = None
