"""Scheduled daily ingestion Lambda handler (contracts/daily-job.md).

Triggered once per day by an EventBridge Scheduler rule (research.md item 8).
Targets "the most recently completed trading day" and raises on failure so
the Lambda invocation itself is reported as an error — never silently
absorbing a failed day into a "successful" invocation (Observability &
Auditability principle).
"""

from __future__ import annotations

from typing import Any

from . import trading_calendar
from .ingest import run
from .logging_setup import get_logger

logger = get_logger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    target_date = trading_calendar.most_recent_completed_trading_day()
    record = run([target_date], trigger="scheduled")

    outcome = record.outcome_by_date[target_date]
    if outcome == "failed":
        detail = (record.error_detail or {}).get(target_date, "unknown error")
        logger.error(
            "Daily ingestion job failed",
            extra={
                "trade_date": str(target_date),
                "run_id": str(record.run_id),
            },
        )
        raise RuntimeError(f"Ingestion failed for {target_date}: {detail}")

    return record.model_dump(mode="json")
