"""ContractRollSchedule: front-month ES futures contract resolution.

Encodes the standard CME ES quarterly expiration cycle (research.md item 3)
locally rather than depending on Polygon.io for it, avoiding a circular trust
dependency on the very source being ingested.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

# ES quarterly contract months in chronological order within a year:
# H=March, M=June, U=September, Z=December.
_QUARTER_MONTHS: list[tuple[int, str]] = [
    (3, "H"),
    (6, "M"),
    (9, "U"),
    (12, "Z"),
]
_MAX_YEAR_LOOKAHEAD = 2


class AmbiguousContractError(RuntimeError):
    """Raised when the front-month contract cannot be unambiguously determined."""


@dataclass(frozen=True)
class ContractRoll:
    ticker: str
    expiration_date: date


def _third_friday(year: int, month: int) -> date:
    cal = calendar.Calendar()
    fridays = [
        d
        for d in cal.itermonthdates(year, month)
        if d.month == month and d.weekday() == calendar.FRIDAY
    ]
    return fridays[2]


def resolve_front_month(as_of: date) -> ContractRoll:
    """The front-month ES contract active on `as_of`.

    The front month is the nearest quarterly contract whose expiration date
    has not yet passed as of `as_of` (inclusive: on its expiration day, a
    contract is still considered active for that day).
    """
    for year_offset in range(_MAX_YEAR_LOOKAHEAD + 1):
        candidate_year = as_of.year + year_offset
        for month, code in _QUARTER_MONTHS:
            expiration = _third_friday(candidate_year, month)
            if expiration >= as_of:
                # Single-digit year (e.g. ESZ5 for Dec 2025), per the ticker
                # convention confirmed against the live futures API.
                ticker = f"ES{code}{candidate_year % 10}"
                return ContractRoll(ticker=ticker, expiration_date=expiration)
    raise RuntimeError(
        f"Unable to resolve a front-month ES contract for {as_of}"
    )


def validate_against_reference(
    roll: ContractRoll, as_of: date, polygon_client
) -> None:
    """Secondary cross-check (research.md item 3) of a locally resolved
    front-month contract against the futures API's own reference data.

    Never used as the primary source of truth — only to catch a case where
    the local quarterly-roll calculation has drifted from what the exchange
    actually considers active, so an ambiguous/disagreeing date fails loudly
    (FR-010) instead of silently ingesting under a possibly-wrong ticker.
    """
    active_tickers = polygon_client.get_active_futures_contracts("ES", as_of)
    if roll.ticker not in active_tickers:
        raise AmbiguousContractError(
            f"Locally resolved front-month contract {roll.ticker!r} for {as_of} is not "
            f"among the reference API's active ES contracts {active_tickers!r}"
        )
