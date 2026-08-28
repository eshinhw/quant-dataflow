"""Futures data client wrapper (research.md items 2, 7, 9).

Makes direct HTTP calls to the futures data API rather than using the
`polygon-api-client` SDK. The SDK's hardcoded `/futures/vX/...` paths against
`api.polygon.io` turned out to be dead for this account — confirmed via raw
HTTP: a plain-text 404 from the API gateway itself, on every futures
endpoint, while non-futures endpoints on the same key worked fine. The real,
working futures API was confirmed during integration testing (2026-08-28) to
live at a different host and version path: `https://api.massive.com/futures/v1/...`.

Two behaviors specific to this API, discovered during that same integration
testing:
- A session's `window_start` filter value and its reported `session_end_date`
  can differ by a day (CME futures sessions run ~24h overnight/Globex), so a
  single-date fetch queries a 2-day window and matches `session_end_date`
  client-side rather than trusting the filter to align exactly.
- "No data yet" is reported as `{"results": [], "status": "OK"}` — a normal
  200 response, not an HTTP error — so PolygonDataUnavailableError is raised
  on an empty match, not on any particular status code.
"""

from __future__ import annotations

from datetime import date, timedelta

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_BASE_URL = "https://api.massive.com/futures/v1"
_REQUEST_TIMEOUT_SECONDS = 10
_MAX_CONTRACT_PAGES = 3


class PolygonDataUnavailableError(RuntimeError):
    """Raised when there is no data for the requested contract/date yet."""


class PolygonAPIError(RuntimeError):
    """Raised when a transient API failure survives all retries."""


class PolygonClient:
    def __init__(
        self,
        api_key: str,
        retry_max_attempts: int,
        retry_backoff_base_seconds: float,
    ):
        self._api_key = api_key
        self._retry_max_attempts = retry_max_attempts
        self._retry_backoff_base_seconds = retry_backoff_base_seconds

    def _retrying(self):
        return retry(
            reraise=True,
            stop=stop_after_attempt(self._retry_max_attempts),
            wait=wait_exponential(multiplier=self._retry_backoff_base_seconds),
            retry=retry_if_exception_type(PolygonAPIError),
        )

    def _get(self, url: str, params: dict | None = None) -> dict:
        query = {**(params or {}), "apiKey": self._api_key}
        try:
            response = requests.get(
                url, params=query, timeout=_REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            raise PolygonAPIError(f"Request to {url} failed: {exc}") from exc

        if response.status_code != 200:
            raise PolygonAPIError(
                f"Request to {url} failed with status {response.status_code}: {response.text}"
            )

        payload = response.json()
        if payload.get("status") not in ("OK", None):
            raise PolygonAPIError(
                f"Request to {url} returned an error payload: {payload}"
            )
        return payload

    def fetch_daily_bar(self, ticker: str, trade_date: date) -> dict:
        """Fetch the daily OHLCV bar for `ticker` on `trade_date`.

        Raises PolygonDataUnavailableError if there is no bar for that
        contract/date yet, or PolygonAPIError if retries are exhausted.
        """
        fetch_with_retry = self._retrying()(self._fetch_aggregate)
        return fetch_with_retry(ticker, trade_date)

    def _fetch_aggregate(self, ticker: str, trade_date: date) -> dict:
        window_start_from = trade_date - timedelta(days=1)
        payload = self._get(
            f"{_BASE_URL}/aggs/{ticker}",
            {
                "resolution": "1day",
                "window_start.gte": window_start_from.isoformat(),
                "window_start.lte": trade_date.isoformat(),
            },
        )
        results = payload.get("results", [])
        match = next(
            (
                r
                for r in results
                if r.get("session_end_date") == trade_date.isoformat()
            ),
            None,
        )
        if match is None:
            raise PolygonDataUnavailableError(
                f"No daily bar for {ticker} on {trade_date} yet"
            )

        return {
            "open": match["open"],
            "high": match["high"],
            "low": match["low"],
            "close": match["close"],
            "volume": int(match["volume"]),
        }

    def get_active_futures_contracts(
        self, underlying: str, as_of: date
    ) -> list[str]:
        """Reference tickers considered active for `underlying` on `as_of`.

        Used only as a secondary cross-check (contract_roll.py) on the
        locally computed front-month contract — never as the primary source
        of truth.
        """
        fetch_with_retry = self._retrying()(self._fetch_reference_contracts)
        return fetch_with_retry(underlying, as_of)

    def _fetch_reference_contracts(
        self, underlying: str, as_of: date
    ) -> list[str]:
        tickers: list[str] = []
        url = f"{_BASE_URL}/contracts"
        params = {
            "product_code": underlying,
            "as_of": as_of.isoformat(),
            "active": "true",
            "limit": 250,
            # Only date/product_code/ticker are valid sort fields for this
            # endpoint; near-term contracts aren't guaranteed to sort first,
            # so pagination (_MAX_CONTRACT_PAGES) covers the rest of the list.
            "sort": "ticker.asc",
        }

        for _ in range(_MAX_CONTRACT_PAGES):
            payload = (
                self._get(url, params)
                if params is not None
                else self._get(url)
            )
            tickers.extend(
                result["ticker"] for result in payload.get("results", [])
            )
            next_url = payload.get("next_url")
            if not next_url:
                break
            url, params = next_url, None

        return tickers
