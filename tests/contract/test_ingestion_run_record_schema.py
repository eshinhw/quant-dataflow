import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest

from es_futures_ingest.schema import IngestionRunRecord

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs/001-ingest-es-futures/contracts/ingestion-run-record.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def test_ingestion_run_record_conforms_to_schema(schema):
    record = IngestionRunRecord(
        run_id=uuid4(),
        trigger="manual_backfill",
        requested_dates=[date(2025, 12, 10), date(2025, 12, 11)],
        started_at=datetime(2025, 12, 12, 1, 0, tzinfo=UTC),
        completed_at=datetime(2025, 12, 12, 1, 5, tzinfo=UTC),
        code_version="abc123",
        config_version="cfg-v1",
        outcome_by_date={
            date(2025, 12, 10): "success",
            date(2025, 12, 11): "failed",
        },
        error_detail={date(2025, 12, 11): "Polygon.io request failed"},
    )
    payload = json.loads(record.model_dump_json())
    jsonschema.validate(instance=payload, schema=schema)


def test_ingestion_run_record_requires_at_least_one_date():
    with pytest.raises(ValueError):
        IngestionRunRecord(
            run_id=uuid4(),
            trigger="scheduled",
            requested_dates=[],
            started_at=datetime(2025, 12, 12, 1, 0, tzinfo=UTC),
            code_version="abc123",
            config_version="cfg-v1",
            outcome_by_date={},
        )
