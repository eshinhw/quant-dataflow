from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from es_futures_ingest import daily_job, trading_calendar
from es_futures_ingest.schema import IngestionRunRecord


def _record(target_date: date, outcome: str, error: str | None = None) -> IngestionRunRecord:
    return IngestionRunRecord(
        run_id=uuid4(),
        trigger="scheduled",
        requested_dates=[target_date],
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        code_version="v1",
        config_version="c1",
        outcome_by_date={target_date: outcome},
        error_detail={target_date: error} if error else None,
    )


def test_handler_returns_record_on_success(monkeypatch):
    target_date = date(2025, 12, 10)
    monkeypatch.setattr(trading_calendar, "most_recent_completed_trading_day", lambda: target_date)
    record = _record(target_date, "success")
    monkeypatch.setattr(daily_job, "run", lambda dates, trigger: record)

    result = daily_job.handler({}, None)

    assert result["outcome_by_date"][target_date.isoformat()] == "success"


def test_handler_raises_on_failure_per_contract(monkeypatch):
    target_date = date(2025, 12, 10)
    monkeypatch.setattr(trading_calendar, "most_recent_completed_trading_day", lambda: target_date)
    record = _record(target_date, "failed", error="Polygon.io has no daily bar yet")
    monkeypatch.setattr(daily_job, "run", lambda dates, trigger: record)

    with pytest.raises(RuntimeError, match="Polygon.io has no daily bar yet"):
        daily_job.handler({}, None)
