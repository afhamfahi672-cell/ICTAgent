"""
Twelve Data adapter — forex (and equity) candle data via a plain
market-data API, not a brokerage.

Why this exists alongside data/oanda.py: OANDA — like most retail forex
brokers — requires a tradeable account to issue API access, and does
not offer accounts to Indian residents (RBI/FEMA rules restrict retail
forex trading through foreign brokers). Twelve Data has no such
restriction because it's just a data feed: sign up with an email
address, get a free API key, no KYC, no account funding, no country
gate. It's the default forex data source wired into web/scheduler.py
and run.py for exactly that reason; data/oanda.py is left fully intact
for anyone who can and wants to use it instead.

Free tier is generous enough for a periodic decision-cycle loop (not
tick-by-tick data): as of writing, 800 requests/day and 8 requests/
minute, comfortably covering a handful of instruments checked every 15
minutes. Confirm current limits on your own account before widening the
watchlist or shortening the interval — like Finnhub's calendar endpoint
(see context/finnhub.py), a provider's free-tier terms can change and
this isn't a guarantee of permanence.

Talks to the REST API directly over `requests`, matching every other
adapter in data/ — same rationale as data/oanda.py's module docstring.

All parsing (`_parse_candle`, `_parse_candles`, `_parse_candle_time`) is
pure and unit-tested with no network dependency. `TwelveDataClient`
accepts an injectable `session`, so its request-building/response-
parsing wiring is unit-tested against a fake session — see
tests/test_twelvedata.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ictagent.config.settings import Settings, load_settings
from ictagent.structure.types import Candle

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"


class TwelveDataAuthError(RuntimeError):
    """Raised when TWELVEDATA_API_KEY is not set."""


class TwelveDataAPIError(RuntimeError):
    """Raised on a non-2xx HTTP response, or a 200 response whose body
    itself carries `"status": "error"` — Twelve Data reports auth and
    rate-limit failures the second way, not just via HTTP status."""

    def __init__(self, message: str, code: Optional[int] = None):
        self.code = code
        super().__init__(f"Twelve Data API error{f' {code}' if code else ''}: {message}")


# ---------------------------------------------------------------------------
# Pure parsing helpers — no network dependency, exercised directly in tests.
# ---------------------------------------------------------------------------


def _parse_candle_time(raw: str) -> datetime:
    """Twelve Data intraday timestamps are "YYYY-MM-DD HH:MM:SS" with no
    timezone in the payload (treated as UTC); daily-and-longer intervals
    return a bare "YYYY-MM-DD"."""
    if len(raw) == 10:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _parse_candle(raw: dict) -> Candle:
    return Candle(
        timestamp=_parse_candle_time(raw["datetime"]),
        open=float(raw["open"]),
        high=float(raw["high"]),
        low=float(raw["low"]),
        close=float(raw["close"]),
        # Forex has no centralized volume; Twelve Data omits the field
        # entirely for FX symbols rather than sending 0.
        volume=float(raw["volume"]) if raw.get("volume") not in (None, "") else 0.0,
    )


def _parse_candles(payload: dict) -> list[Candle]:
    """`payload` is the decoded JSON body of a GET /time_series response.
    Raises TwelveDataAPIError if the body itself reports an error (see
    TwelveDataAPIError's docstring). Candles are sorted chronologically
    ascending regardless of the order Twelve Data returned them in — the
    API's ordering isn't documented as a stable guarantee, so this
    doesn't rely on it."""
    if payload.get("status") == "error":
        raise TwelveDataAPIError(payload.get("message", "unknown error"), code=payload.get("code"))

    candles = [_parse_candle(v) for v in payload.get("values") or []]
    candles.sort(key=lambda c: c.timestamp)
    return candles


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class TwelveDataClient:
    """`session` can be injected (anything exposing `requests.Session`'s
    `.get(url, params=...)` returning a `requests.Response`-like object) —
    used by tests to avoid any real network call. Defaults to a real
    `requests.Session()`."""

    def __init__(self, settings: Optional[Settings] = None, session=None):
        self._settings = settings or load_settings()

        if not self._settings.twelvedata_api_key:
            raise TwelveDataAuthError(
                "TWELVEDATA_API_KEY is not set. See .env.example for the "
                "required environment variable."
            )

        if session is not None:
            self._session = session
        else:
            import requests  # lazy: only needed for real (non-test) usage

            self._session = requests.Session()

    def fetch_candles(self, symbol: str, interval: str = "15min", count: int = 300) -> list[Candle]:
        """`symbol` uses Twelve Data's own format, e.g. "EUR/USD" (not
        OANDA's "EUR_USD"). `interval`: "1min", "5min", "15min", "30min",
        "45min", "1h", "2h", "4h", "1day", "1week", "1month"."""
        params = {"symbol": symbol, "interval": interval, "outputsize": count}
        payload = self._get("/time_series", params)
        return _parse_candles(payload)

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "apikey": self._settings.twelvedata_api_key}
        response = self._session.get(TWELVE_DATA_BASE_URL + path, params=params)
        status = getattr(response, "status_code", 200)
        if status != 200:
            raise TwelveDataAPIError(getattr(response, "text", ""), code=status)
        return response.json()
