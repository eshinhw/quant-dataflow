import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest

from es_futures_ingest.schema import RawDailyBar

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs/001-ingest-es-futures/contracts/raw-daily-bar.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _valid_bar() -> RawDailyBar:
    return RawDailyBar(
        contract_ticker="ESZ5",
        trade_date=date(2025, 12, 10),
        open=5000.0,
        high=5050.0,
        low=4990.0,
        close=5025.0,
        volume=1_200_000,
        source="polygon.io",
        ingested_at=datetime(2025, 12, 10, 21, 30, tzinfo=UTC),
        code_version="abc123",
        config_version="cfg-v1",
        run_id=uuid4(),
    )


def test_raw_daily_bar_conforms_to_schema(schema):
    bar = _valid_bar()
    jsonschema.validate(instance=json.loads(bar.model_dump_json()), schema=schema)


def test_raw_daily_bar_rejects_invalid_ticker():
    with pytest.raises(ValueError):
        _valid_bar_with(contract_ticker="INVALID")


def test_raw_daily_bar_rejects_ohlc_inconsistency():
    with pytest.raises(ValueError):
        _valid_bar_with(low=6000.0)


def _valid_bar_with(**overrides):
    fields = dict(
        contract_ticker="ESZ5",
        trade_date=date(2025, 12, 10),
        open=5000.0,
        high=5050.0,
        low=4990.0,
        close=5025.0,
        volume=1_200_000,
        source="polygon.io",
        ingested_at=datetime(2025, 12, 10, 21, 30, tzinfo=UTC),
        code_version="abc123",
        config_version="cfg-v1",
        run_id=uuid4(),
    )
    fields.update(overrides)
    return RawDailyBar(**fields)
