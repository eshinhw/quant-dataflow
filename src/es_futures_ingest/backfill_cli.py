"""On-demand backfill CLI (contracts/backfill-cli.md).

Each date in the requested range is ingested independently via `ingest.run`,
which already isolates a failure on one date from the rest (FR-008) and skips
non-trading days without treating them as failures (FR-007) — both handled
once in `ingest.ingest_one_date` so the daily job and this CLI share the same
tested behavior.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from .ingest import run
from .logging_setup import get_logger

logger = get_logger(__name__)


def _date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError(f"--end-date {end} is before --start-date {start}")
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ingest-es-futures")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backfill = subparsers.add_parser(
        "backfill", help="Backfill ES futures daily bars"
    )
    backfill.add_argument(
        "--start-date", required=True, type=date.fromisoformat
    )
    backfill.add_argument(
        "--end-date", required=False, type=date.fromisoformat
    )

    return parser.parse_args(argv)


def cli_main(argv: list[str]) -> int:
    args = _parse_args(argv)
    end_date = args.end_date or args.start_date
    dates = _date_range(args.start_date, end_date)

    record = run(dates, trigger="manual_backfill")
    print(record.model_dump_json())

    failed_dates = [
        d
        for d, outcome in record.outcome_by_date.items()
        if outcome == "failed"
    ]
    if failed_dates:
        logger.error(
            "Backfill completed with failures",
            extra={"failed_dates": [str(d) for d in failed_dates]},
        )
        return 1
    return 0


def main() -> None:
    sys.exit(cli_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
