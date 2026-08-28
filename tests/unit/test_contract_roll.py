import calendar as calendar_module
from datetime import timedelta

import pytest

from es_futures_ingest.contract_roll import resolve_front_month


def _third_friday(year: int, month: int):
    cal = calendar_module.Calendar()
    fridays = [
        d for d in cal.itermonthdates(year, month)
        if d.month == month and d.weekday() == calendar_module.FRIDAY
    ]
    return fridays[2]


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_resolve_front_month_before_march_expiration(year):
    march_expiration = _third_friday(year, 3)
    roll = resolve_front_month(march_expiration - timedelta(days=1))
    assert roll.ticker == f"ESH{year % 10}"
    assert roll.expiration_date == march_expiration


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_resolve_front_month_on_expiration_day_is_still_current(year):
    march_expiration = _third_friday(year, 3)
    roll = resolve_front_month(march_expiration)
    assert roll.ticker == f"ESH{year % 10}"


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_resolve_front_month_day_after_expiration_rolls_to_next_quarter(year):
    march_expiration = _third_friday(year, 3)
    roll = resolve_front_month(march_expiration + timedelta(days=1))
    assert roll.ticker == f"ESM{year % 10}"
    assert roll.expiration_date == _third_friday(year, 6)


def test_resolve_front_month_rolls_across_year_boundary():
    december_expiration = _third_friday(2025, 12)
    roll = resolve_front_month(december_expiration + timedelta(days=1))
    assert roll.ticker == "ESH6"
    assert roll.expiration_date == _third_friday(2026, 3)
