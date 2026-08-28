from datetime import timedelta

from es_futures_ingest import contract_roll, ingest, trading_calendar
from es_futures_ingest.contract_roll import _third_friday
from tests.conftest import FakePolygonClient


def test_contract_roll_transition_across_date_range(s3_client, test_config):
    december_expiration = _third_friday(2025, 12)
    pre_roll_day = december_expiration  # still the expiring (current) contract

    post_roll_day = december_expiration + timedelta(days=1)
    while not trading_calendar.is_trading_day(post_roll_day):
        post_roll_day += timedelta(days=1)

    pre_ticker = contract_roll.resolve_front_month(pre_roll_day).ticker
    post_ticker = contract_roll.resolve_front_month(post_roll_day).ticker
    assert pre_ticker == "ESZ5"
    assert post_ticker == "ESH6"

    bar_data = {"open": 5000.0, "high": 5050.0, "low": 4990.0, "close": 5025.0, "volume": 1_000_000}
    client = FakePolygonClient(
        bars={
            (pre_ticker, pre_roll_day): bar_data,
            (post_ticker, post_roll_day): bar_data,
        }
    )

    record = ingest.run(
        [pre_roll_day, post_roll_day],
        "manual_backfill",
        config=test_config,
        polygon_client=client,
        s3_client=s3_client,
    )

    assert record.outcome_by_date[pre_roll_day] == "success"
    assert record.outcome_by_date[post_roll_day] == "success"

    objects = s3_client.list_objects_v2(Bucket=test_config.raw_bucket_name, Prefix="raw/")
    keys = [o["Key"] for o in objects.get("Contents", []) if o["Key"].endswith("bar.json")]
    assert any(f"contract={pre_ticker}/" in k for k in keys)
    assert any(f"contract={post_ticker}/" in k for k in keys)
