"""Core ingestion orchestration shared by the daily job and the backfill CLI.

Per contracts/daily-job.md and contracts/backfill-cli.md: each requested date
is ingested independently, and a failure on one date is recorded rather than
raised immediately, so a multi-date backfill isn't blocked by one bad date
(FR-008). Callers that need loud failure for a single date (the daily job)
inspect the resulting IngestionRunRecord and raise themselves.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import boto3

from . import contract_roll, s3_writer, trading_calendar
from .config import Config, get_config
from .logging_setup import get_logger
from .polygon_client import (
    PolygonAPIError,
    PolygonClient,
    PolygonDataUnavailableError,
)
from .schema import (
    IngestionRunRecord,
    OutcomeLiteral,
    RawDailyBar,
    TriggerLiteral,
)

logger = get_logger(__name__)

_RETRIABLE_FAILURE_TYPES: tuple[type[Exception], ...] = (
    PolygonDataUnavailableError,
    PolygonAPIError,
    contract_roll.AmbiguousContractError,
)


def build_polygon_client(config: Config) -> PolygonClient:
    return PolygonClient(
        api_key=config.polygon_api_key,
        retry_max_attempts=config.retry_max_attempts,
        retry_backoff_base_seconds=config.retry_backoff_base_seconds,
    )


def ingest_one_date(
    trade_date: date,
    *,
    run_id: UUID,
    config: Config,
    polygon_client: PolygonClient,
    s3_client,
) -> OutcomeLiteral:
    """Ingest a single trading date. Raises on any failure; callers of `run`
    catch and record it so other dates in the same run are unaffected."""
    if not trading_calendar.is_trading_day(trade_date):
        logger.info(
            "Skipping non-trading day", extra={"trade_date": str(trade_date)}
        )
        return "skipped_non_trading_day"

    roll = contract_roll.resolve_front_month(trade_date)
    # contract_roll.validate_against_reference(roll, trade_date, polygon_client)
    #
    # Disabled 2026-08-28: live testing found the /futures/v1/contracts
    # reference endpoint returns severely duplicate-heavy, effectively
    # unusable pagination (hundreds of identical rows for one ticker,
    # sorted by the only valid sort fields: date/product_code/ticker) —
    # walking it to confirm membership is rate-limit-prohibitive and not
    # reliable. contract_roll.py's own quarterly-cycle math is unaffected
    # and remains the correct primary logic; see research.md item 3 and
    # `validate_against_reference`'s docstring. Re-enable once there's a
    # documented, efficient way to query this endpoint for a single ticker.

    raw = polygon_client.fetch_daily_bar(roll.ticker, trade_date)

    bar = RawDailyBar(
        contract_ticker=roll.ticker,
        trade_date=trade_date,
        open=raw["open"],
        high=raw["high"],
        low=raw["low"],
        close=raw["close"],
        volume=raw["volume"],
        source="polygon.io",
        ingested_at=datetime.now(UTC),
        code_version=config.code_version,
        config_version=config.config_version,
        run_id=run_id,
    )

    key, written = s3_writer.write_raw_bar(
        s3_client, config.raw_bucket_name, bar
    )
    logger.info(
        "Ingested daily bar",
        extra={
            "trade_date": str(trade_date),
            "contract_ticker": roll.ticker,
            "s3_key": key,
            "written": written,
            "run_id": str(run_id),
        },
    )
    return "success"


def run(
    dates: list[date],
    trigger: TriggerLiteral,
    *,
    config: Config | None = None,
    polygon_client: PolygonClient | None = None,
    s3_client=None,
) -> IngestionRunRecord:
    """Ingest every date in `dates` independently and record the outcome of each.

    Never raises for a per-date failure — the caller (daily_job.py,
    backfill_cli.py) decides how to surface failures from the returned record.
    """
    cfg = config or get_config()
    client = polygon_client or build_polygon_client(cfg)
    s3 = s3_client or boto3.client("s3")

    run_id = uuid4()
    started_at = datetime.now(UTC)
    outcome_by_date: dict[date, OutcomeLiteral] = {}
    error_detail: dict[date, str] = {}

    for trade_date in dates:
        try:
            outcome_by_date[trade_date] = ingest_one_date(
                trade_date,
                run_id=run_id,
                config=cfg,
                polygon_client=client,
                s3_client=s3,
            )
        except _RETRIABLE_FAILURE_TYPES as exc:
            outcome_by_date[trade_date] = "failed"
            error_detail[trade_date] = str(exc)
            logger.error(
                "Ingestion failed for date",
                extra={"trade_date": str(trade_date), "error": str(exc)},
            )
        except (
            Exception
        ) as exc:  # noqa: BLE001 - fail loud, but isolate this date
            outcome_by_date[trade_date] = "failed"
            error_detail[trade_date] = str(exc)
            logger.error(
                "Unexpected ingestion failure",
                extra={"trade_date": str(trade_date), "error": str(exc)},
                exc_info=True,
            )

    completed_at = datetime.now(UTC)
    record = IngestionRunRecord(
        run_id=run_id,
        trigger=trigger,
        requested_dates=dates,
        started_at=started_at,
        completed_at=completed_at,
        code_version=cfg.code_version,
        config_version=cfg.config_version,
        outcome_by_date=outcome_by_date,
        error_detail=error_detail or None,
    )
    s3_writer.write_run_record(s3, cfg.raw_bucket_name, record)
    return record
