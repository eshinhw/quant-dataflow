"""CME trading-day recognition (research.md item 4).

Uses pandas-market-calendars' CME_Equity calendar as the source of truth for
which calendar dates are valid ES futures trading sessions, so holiday
handling never has to be hand-maintained.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import pandas_market_calendars as mcal

_CALENDAR_NAME = "CME_Equity"
_LOOKBACK_DAYS_FOR_MOST_RECENT = 14


@lru_cache(maxsize=1)
def _calendar():
    return mcal.get_calendar(_CALENDAR_NAME)


def is_trading_day(day: date) -> bool:
    schedule = _calendar().schedule(start_date=day, end_date=day)
    return not schedule.empty


def trading_days_between(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    schedule = _calendar().schedule(start_date=start, end_date=end)
    return [ts.date() for ts in schedule.index]


def most_recent_completed_trading_day(as_of: date | None = None) -> date:
    """The most recent trading day on or before `as_of` (default: today).

    The daily job is scheduled after market close/finalization, so "as_of"
    itself is the completed trading day when it is a trading day; otherwise
    this walks backward to the last valid session.
    """
    reference = as_of if as_of is not None else date.today()
    window_start = reference - timedelta(days=_LOOKBACK_DAYS_FOR_MOST_RECENT)
    days = trading_days_between(window_start, reference)
    if not days:
        raise RuntimeError(
            f"No trading day found in the {_LOOKBACK_DAYS_FOR_MOST_RECENT}-day "
            f"window ending {reference}"
        )
    return days[-1]
