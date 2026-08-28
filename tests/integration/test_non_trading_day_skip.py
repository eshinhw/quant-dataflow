from datetime import date

from es_futures_ingest import ingest
from tests.conftest import FakePolygonClient

SATURDAY = date(2025, 12, 13)


def test_non_trading_day_is_skipped_not_failed(s3_client, test_config):
    client = FakePolygonClient()

    record = ingest.run(
        [SATURDAY],
        "manual_backfill",
        config=test_config,
        polygon_client=client,
        s3_client=s3_client,
    )

    assert record.outcome_by_date[SATURDAY] == "skipped_non_trading_day"
    assert client.calls == []

    raw_objects = s3_client.list_objects_v2(Bucket=test_config.raw_bucket_name, Prefix="raw/")
    assert raw_objects.get("KeyCount", 0) == 0
