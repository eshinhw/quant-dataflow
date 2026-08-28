from datetime import date

from es_futures_ingest import contract_roll, ingest
from tests.conftest import FakePolygonClient

TRADE_DATE = date(2025, 12, 10)  # a Wednesday CME trading day


def test_unpublished_data_fails_loud_with_no_partial_write(s3_client, test_config):
    ticker = contract_roll.resolve_front_month(TRADE_DATE).ticker
    client = FakePolygonClient(unavailable_for={(ticker, TRADE_DATE)})

    record = ingest.run(
        [TRADE_DATE], "scheduled", config=test_config, polygon_client=client, s3_client=s3_client
    )

    assert record.outcome_by_date[TRADE_DATE] == "failed"
    assert record.error_detail is not None
    assert TRADE_DATE in record.error_detail

    raw_objects = s3_client.list_objects_v2(Bucket=test_config.raw_bucket_name, Prefix="raw/")
    assert raw_objects.get("KeyCount", 0) == 0
