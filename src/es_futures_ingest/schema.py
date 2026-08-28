"""Pydantic models for RawDailyBar and IngestionRunRecord.

Field constraints mirror data-model.md and the JSON Schemas published in
specs/001-ingest-es-futures/contracts/.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

_CONTRACT_TICKER_RE = re.compile(r"^ES[HMUZ][0-9]$")

OutcomeLiteral = Literal["success", "failed", "skipped_non_trading_day"]
TriggerLiteral = Literal["scheduled", "manual_backfill"]


class RawDailyBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_ticker: str
    trade_date: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)
    source: Literal["polygon.io"] = "polygon.io"
    ingested_at: datetime
    code_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    run_id: UUID

    @field_validator("contract_ticker")
    @classmethod
    def _validate_ticker(cls, value: str) -> str:
        if not _CONTRACT_TICKER_RE.match(value):
            raise ValueError(
                f"contract_ticker {value!r} does not match ES futures ticker "
                "format (e.g. ESZ5)"
            )
        return value

    @model_validator(mode="after")
    def _validate_ohlc_consistency(self) -> RawDailyBar:
        if not (self.low <= self.open <= self.high):
            raise ValueError(
                f"open {self.open} out of [low={self.low}, high={self.high}] range"
            )
        if not (self.low <= self.close <= self.high):
            raise ValueError(
                f"close {self.close} out of [low={self.low}, high={self.high}] range"
            )
        if self.low > self.high:
            raise ValueError(f"low {self.low} exceeds high {self.high}")
        return self


class IngestionRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    trigger: TriggerLiteral
    requested_dates: list[date] = Field(min_length=1)
    started_at: datetime
    completed_at: datetime | None = None
    code_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    outcome_by_date: dict[date, OutcomeLiteral]
    error_detail: dict[date, str] | None = None
