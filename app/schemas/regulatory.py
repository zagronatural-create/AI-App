from __future__ import annotations

from pydantic import BaseModel


class ThresholdReleaseApproveIn(BaseModel):
    approved_by: str | None = None
    notes: str | None = None


class ThresholdReleasePublishIn(BaseModel):
    published_by: str | None = None
