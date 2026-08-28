from datetime import date

from es_futures_ingest import contract_roll, ingest
from tests.conftest import FakePolygonClient

TRADE_DATE = date(2025, 12, 10)  # a Wednesday CME trading day


def _bar_keys(s3_client, bucket: str) -> list[str]:
    objects = s3_client.list_objects_v2(Bucket=bucket, Prefix="raw/")
    return [o["Key"] for o in objects.get("Contents", []) if o["Key"].endswith("bar.json")]


def test_single_day_ingestion_writes_one_bar_with_lineage(s3_client, test_config):
    ticker = contract_roll.resolve_front_month(TRADE_DATE).ticker
    bar_data = {"open": 5000.0, "high": 5050.0, "low": 4990.0, "close": 5025.0, "volume": 1_000_000}
    client = FakePolygonClient(bars={(ticker, TRADE_DATE): bar_data})

    record = ingest.run(
        [TRADE_DATE],
        "manual_backfill",
        config=test_config,
        polygon_client=client,
        s3_client=s3_client,
    )

    assert record.outcome_by_date[TRADE_DATE] == "success"
    assert _bar_keys(s3_client, test_config.raw_bucket_name) != []
    assert len(_bar_keys(s3_client, test_config.raw_bucket_name)) == 1

    run_prefix = f"lineage/es_futures_ingest_runs/run_id={record.run_id}/"
    run_objects = s3_client.list_objects_v2(Bucket=test_config.raw_bucket_name, Prefix=run_prefix)
    assert run_objects.get("KeyCount", 0) == 1


def test_rerun_for_same_date_is_idempotent(s3_client, test_config):
    ticker = contract_roll.resolve_front_month(TRADE_DATE).ticker
    bar_data = {"open": 5000.0, "high": 5050.0, "low": 4990.0, "close": 5025.0, "volume": 1_000_000}
    client = FakePolygonClient(bars={(ticker, TRADE_DATE): bar_data})

    run_kwargs = dict(config=test_config, polygon_client=client, s3_client=s3_client)
    ingest.run([TRADE_DATE], "manual_backfill", **run_kwargs)
    ingest.run([TRADE_DATE], "manual_backfill", **run_kwargs)

    bar_keys = _bar_keys(s3_client, test_config.raw_bucket_name)
    assert len(bar_keys) == 1
    assert client.calls.count((ticker, TRADE_DATE)) == 2
