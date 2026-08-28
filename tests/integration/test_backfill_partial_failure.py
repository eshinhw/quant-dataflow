from datetime import date

from es_futures_ingest import contract_roll, ingest
from tests.conftest import FakePolygonClient

DAY_1 = date(2025, 12, 10)
DAY_2 = date(2025, 12, 11)


def test_one_failing_date_does_not_block_the_others(s3_client, test_config):
    ticker_1 = contract_roll.resolve_front_month(DAY_1).ticker
    ticker_2 = contract_roll.resolve_front_month(DAY_2).ticker
    bar_data = {"open": 5000.0, "high": 5050.0, "low": 4990.0, "close": 5025.0, "volume": 1_000_000}
    client = FakePolygonClient(
        bars={(ticker_1, DAY_1): bar_data},
        unavailable_for={(ticker_2, DAY_2)},
    )

    record = ingest.run(
        [DAY_1, DAY_2],
        "manual_backfill",
        config=test_config,
        polygon_client=client,
        s3_client=s3_client,
    )

    assert record.outcome_by_date[DAY_1] == "success"
    assert record.outcome_by_date[DAY_2] == "failed"
    assert record.error_detail is not None and DAY_2 in record.error_detail

    raw_objects = s3_client.list_objects_v2(Bucket=test_config.raw_bucket_name, Prefix="raw/")
    bar_keys = [o["Key"] for o in raw_objects.get("Contents", []) if o["Key"].endswith("bar.json")]
    assert len(bar_keys) == 1
    assert f"contract={ticker_1}/" in bar_keys[0]
