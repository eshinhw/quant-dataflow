import json
from datetime import UTC, date, datetime
from uuid import uuid4

from es_futures_ingest import backfill_cli
from es_futures_ingest.schema import IngestionRunRecord


def _record(
    dates: list[date], outcomes: list[str], errors: dict | None = None
) -> IngestionRunRecord:
    return IngestionRunRecord(
        run_id=uuid4(),
        trigger="manual_backfill",
        requested_dates=dates,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        code_version="v1",
        config_version="c1",
        outcome_by_date=dict(zip(dates, outcomes)),
        error_detail=errors,
    )


def test_backfill_single_date_defaults_end_date(monkeypatch, capsys):
    captured = {}

    def fake_run(dates, trigger):
        captured["dates"] = dates
        captured["trigger"] = trigger
        return _record(dates, ["success"])

    monkeypatch.setattr(backfill_cli, "run", fake_run)

    exit_code = backfill_cli.cli_main(["backfill", "--start-date", "2025-12-10"])

    assert exit_code == 0
    assert captured["dates"] == [date(2025, 12, 10)]
    assert captured["trigger"] == "manual_backfill"
    output = json.loads(capsys.readouterr().out)
    assert output["outcome_by_date"]["2025-12-10"] == "success"


def test_backfill_date_range_expands_all_calendar_dates(monkeypatch):
    captured = {}

    def fake_run(dates, trigger):
        captured["dates"] = dates
        return _record(dates, ["success"] * len(dates))

    monkeypatch.setattr(backfill_cli, "run", fake_run)

    backfill_cli.cli_main(
        ["backfill", "--start-date", "2025-12-10", "--end-date", "2025-12-12"]
    )

    assert captured["dates"] == [date(2025, 12, 10), date(2025, 12, 11), date(2025, 12, 12)]


def test_backfill_exit_code_1_when_any_date_fails(monkeypatch):
    def fake_run(dates_arg, trigger):
        return _record(dates_arg, ["success", "failed"], errors={dates_arg[1]: "boom"})

    monkeypatch.setattr(backfill_cli, "run", fake_run)

    exit_code = backfill_cli.cli_main(
        ["backfill", "--start-date", "2025-12-10", "--end-date", "2025-12-11"]
    )

    assert exit_code == 1


def test_backfill_exit_code_0_when_all_succeed_or_skipped(monkeypatch):
    def fake_run(dates_arg, trigger):
        return _record(dates_arg, ["success", "skipped_non_trading_day"])

    monkeypatch.setattr(backfill_cli, "run", fake_run)

    exit_code = backfill_cli.cli_main(
        ["backfill", "--start-date", "2025-12-10", "--end-date", "2025-12-11"]
    )

    assert exit_code == 0
