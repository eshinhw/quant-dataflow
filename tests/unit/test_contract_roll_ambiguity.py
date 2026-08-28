from datetime import date

import pytest

from es_futures_ingest.contract_roll import (
    AmbiguousContractError,
    resolve_front_month,
    validate_against_reference,
)
from tests.conftest import FakePolygonClient


def test_validate_against_reference_passes_when_tickers_agree():
    as_of = date(2025, 12, 10)
    roll = resolve_front_month(as_of)
    client = FakePolygonClient(active_contracts=[roll.ticker])

    validate_against_reference(roll, as_of, client)  # should not raise


def test_validate_against_reference_raises_when_tickers_disagree():
    as_of = date(2025, 12, 10)
    roll = resolve_front_month(as_of)
    client = FakePolygonClient(active_contracts=["ESM6"])  # deliberately wrong reference

    with pytest.raises(AmbiguousContractError):
        validate_against_reference(roll, as_of, client)
