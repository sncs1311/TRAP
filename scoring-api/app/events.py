"""Event contract: validated identically by the API and the stream worker."""
from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, ConfigDict, Field


def _now_ms() -> int:
    return int(time.time() * 1000)


class Transaction(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    txn_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    card_id: str
    ts_ms: int = Field(default_factory=_now_ms, ge=0)
    amount: float = Field(gt=0, allow_inf_nan=False)
    merchant_cat: int = Field(ge=0, le=9)
    is_online: int = Field(ge=0, le=1)
    distance_km: float = Field(ge=0, allow_inf_nan=False)
    is_foreign: int = Field(ge=0, le=1)
    account_age_days: float = Field(ge=0, allow_inf_nan=False)
    hour: int | None = Field(default=None, ge=0, le=23)   # optional; derived from ts_ms if absent

    # Simulator ground truth (never used for scoring; for demo dashboards only)
    label: int | None = None
    pattern: str | None = None

    def hour_value(self) -> int:
        return self.hour if self.hour is not None else (self.ts_ms // 3_600_000) % 24