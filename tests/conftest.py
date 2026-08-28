from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from es_futures_ingest.config import Config
from es_futures_ingest.contract_roll import resolve_front_month
from es_futures_ingest.polygon_client import PolygonAPIError, PolygonDataUnavailableError

TEST_BUCKET = "test-raw-bucket"


@pytest.fixture
def aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def s3_client(aws_credentials):
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=TEST_BUCKET)
        yield client


@pytest.fixture
def test_config() -> Config:
    return Config(
        raw_bucket_name=TEST_BUCKET,
        polygon_api_key="test-key",
        retry_max_attempts=3,
        retry_backoff_base_seconds=0.01,
        code_version="test-sha",
        config_version="test-config-v1",
    )


class FakePolygonClient:
    """Test double satisfying PolygonClient's public interface.

    By default, `get_active_futures_contracts` auto-agrees with whatever
    ticker `resolve_front_month` would compute locally, so tests unrelated to
    ambiguity detection don't need to configure it. Pass `active_contracts`
    explicitly to simulate a cross-validation mismatch.
    """

    def __init__(self, bars=None, active_contracts=None, unavailable_for=None, api_error_for=None):
        self.bars = bars or {}
        self.active_contracts = active_contracts
        self.unavailable_for = unavailable_for or set()
        self.api_error_for = api_error_for or set()
        self.calls: list[tuple[str, object]] = []

    def fetch_daily_bar(self, ticker, trade_date):
        self.calls.append((ticker, trade_date))
        key = (ticker, trade_date)
        if key in self.unavailable_for:
            raise PolygonDataUnavailableError(f"no data for {ticker} {trade_date}")
        if key in self.api_error_for:
            raise PolygonAPIError(f"api error for {ticker} {trade_date}")
        if key not in self.bars:
            raise PolygonDataUnavailableError(f"no data for {ticker} {trade_date}")
        return self.bars[key]

    def get_active_futures_contracts(self, underlying, as_of):
        if self.active_contracts is not None:
            return self.active_contracts
        return [resolve_front_month(as_of).ticker]


@pytest.fixture
def fake_polygon_client():
    return FakePolygonClient()
