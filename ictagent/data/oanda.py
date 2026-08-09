"""
OANDA v20 REST API adapter — candles (historical) + pricing (live).

Talks to the v20 REST API directly over `requests` rather than via the
`oandapyV20` SDK: that SDK is unmaintained and its sdist fails to build
against current setuptools (legacy `distutils` command class), so
depending on it is a maintenance trap. The v20 REST surface used here
(instrument candles, account pricing, pricing stream) is small and
stable enough that wrapping it directly is the more reliable choice.

Auth/session handling is entirely self-contained in `OandaClient` — it
knows nothing about Kite Connect, and nothing here is imported by a
Kite adapter. Credentials come from `ictagent.config.settings`, which
reads them from environment variables only.

All parsing (`_parse_candle`, `_parse_candles`, `_parse_quote`,
`_parse_oanda_time`, `_to_rfc3339`) is pure and has no network
dependency, so it's fully unit-testable without touching OANDA's API —
see tests/test_oanda.py. `OandaClient` itself accepts an injectable
`session` (anything exposing `requests.Session`'s `.get()` / `.headers`
surface), so its request-building/response-parsing wiring is unit
tested against a fake session, no live credentials required.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterator, Optional, Union

from ictagent.config.settings import Settings, load_settings
from ictagent.structure.types import Candle

from .types import Quote

# Standard OANDA v20 candlestick granularities.
OANDA_GRANULARITIES = frozenset(
    {
        "S5", "S10", "S15", "S30",
        "M1", "M2", "M4", "M5", "M10", "M15", "M30",
        "H1", "H2", "H3", "H4", "H6", "H8", "H12",
        "D", "W", "M",
    }
)

_ENVIRONMENT_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


class OandaAuthError(RuntimeError):
    """Raised when required OANDA credentials are missing for the
    operation being attempted (e.g. no API token, or no account ID for
    an account-scoped endpoint)."""


class OandaAPIError(RuntimeError):
    """Raised when OANDA's API returns a non-2xx response."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"OANDA API error {status_code}: {body}")


# ---------------------------------------------------------------------------
# Pure parsing helpers — no network dependency, exercised directly in tests.
# ---------------------------------------------------------------------------


def _parse_oanda_time(raw: str) -> datetime:
    """Parse OANDA's RFC3339 nanosecond timestamps
    (e.g. "2023-01-01T00:00:00.123456789Z") into a UTC datetime,
    truncated to microsecond precision (Python's datetime has no
    nanosecond resolution)."""
    s = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    if "." in s:
        head, rest = s.split(".", 1)
        frac, sep, tz = rest.partition("+")
        if not sep:
            frac, sep, tz = rest.partition("-")
            sep = "-" if sep else ""
        frac = frac[:6].ljust(6, "0")
        s = f"{head}.{frac}{sep}{tz}" if sep else head
    return datetime.fromisoformat(s)


def _to_rfc3339(value: Union[str, datetime]) -> str:
    """Accepts a datetime (naive datetimes are assumed UTC) or an
    already-formatted RFC3339 string, returns an RFC3339 string suitable
    for OANDA's `from`/`to` query params."""
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    raise TypeError(f"start/end must be a datetime or RFC3339 string, got {type(value)!r}")


def _parse_candle(raw: dict) -> Candle:
    ohlc = raw.get("mid") or raw.get("bid") or raw.get("ask")
    if ohlc is None:
        raise ValueError(f"OANDA candle has no mid/bid/ask price data: {raw!r}")
    return Candle(
        timestamp=_parse_oanda_time(raw["time"]),
        open=float(ohlc["o"]),
        high=float(ohlc["h"]),
        low=float(ohlc["l"]),
        close=float(ohlc["c"]),
        volume=float(raw.get("volume", 0)),
    )


def _parse_candles(payload: dict, include_incomplete: bool = False) -> list[Candle]:
    """`payload` is the raw decoded JSON body of a GET
    /v3/instruments/{instrument}/candles response. Incomplete (still
    forming) candles are dropped by default — their OHLC can still
    change, and structure/ must never compute over a moving target."""
    out = []
    for raw in payload.get("candles", []):
        if not include_incomplete and not raw.get("complete", True):
            continue
        out.append(_parse_candle(raw))
    return out


def _parse_quote(raw: dict) -> Quote:
    """`raw` is one entry from a pricing response's `prices` list, or one
    decoded line from a pricing stream with `"type": "PRICE"`."""
    return Quote(
        instrument=raw["instrument"],
        time=_parse_oanda_time(raw["time"]),
        bid=float(raw["bids"][0]["price"]),
        ask=float(raw["asks"][0]["price"]),
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OandaClient:
    """OANDA v20 REST client for historical candles and live pricing.

    `session` can be injected (any object exposing `requests.Session`'s
    `.headers` mapping and `.get(url, params=..., stream=...)` returning
    a `requests.Response`-like object) — used by tests to avoid any real
    network call. Defaults to a real `requests.Session()`.
    """

    def __init__(self, settings: Optional[Settings] = None, session=None):
        self._settings = settings or load_settings()

        if not self._settings.oanda_api_token:
            raise OandaAuthError(
                "OANDA_API_TOKEN is not set. See .env.example for the "
                "required OANDA_* environment variables."
            )

        environment = self._settings.oanda_environment
        if environment not in _ENVIRONMENT_URLS:
            raise ValueError(
                f"Unknown OANDA_ENVIRONMENT {environment!r}; expected one of "
                f"{sorted(_ENVIRONMENT_URLS)}"
            )
        self._base_url = _ENVIRONMENT_URLS[environment]
        self._account_id = self._settings.oanda_account_id

        if session is not None:
            self._session = session
        else:
            import requests  # lazy: only needed for real (non-test) usage

            self._session = requests.Session()

        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._settings.oanda_api_token}",
                "Accept-Datetime-Format": "RFC3339",
            }
        )

    def fetch_candles(
        self,
        instrument: str,
        granularity: str,
        count: int = 500,
        start: Optional[Union[str, datetime]] = None,
        end: Optional[Union[str, datetime]] = None,
        price: str = "M",
        include_incomplete: bool = False,
    ) -> list[Candle]:
        """Historical/recent candles for one instrument.

        `price`: "M" (mid, default), "B" (bid), or "A" (ask).
        If `start`/`end` are given, `count` is ignored (OANDA's own
        from/to + count interaction rules apply); otherwise the most
        recent `count` candles are returned.
        """
        if granularity not in OANDA_GRANULARITIES:
            raise ValueError(
                f"Unknown granularity {granularity!r}; expected one of "
                f"{sorted(OANDA_GRANULARITIES)}"
            )

        params: dict = {"granularity": granularity, "price": price}
        if start is not None:
            params["from"] = _to_rfc3339(start)
        if end is not None:
            params["to"] = _to_rfc3339(end)
        if start is None and end is None:
            params["count"] = count

        payload = self._get(f"/v3/instruments/{instrument}/candles", params)
        return _parse_candles(payload, include_incomplete=include_incomplete)

    def get_current_price(self, instruments: list[str]) -> dict[str, Quote]:
        """One-shot pricing snapshot, keyed by instrument."""
        account_id = self._require_account_id()
        payload = self._get(
            f"/v3/accounts/{account_id}/pricing",
            {"instruments": ",".join(instruments)},
        )
        quotes = (_parse_quote(p) for p in payload.get("prices", []))
        return {q.instrument: q for q in quotes}

    def stream_prices(self, instruments: list[str]) -> Iterator[Quote]:
        """Long-lived streaming price generator. Blocks between yields —
        callers run this in its own thread/task, not on a request path.
        Heartbeat messages are silently skipped."""
        account_id = self._require_account_id()
        url = f"{self._base_url}/v3/accounts/{account_id}/pricing/stream"
        response = self._session.get(
            url, params={"instruments": ",".join(instruments)}, stream=True
        )
        if getattr(response, "status_code", 200) != 200:
            raise OandaAPIError(response.status_code, getattr(response, "text", ""))

        for line in response.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            data = json.loads(line)
            if data.get("type") == "PRICE":
                yield _parse_quote(data)

    def _require_account_id(self) -> str:
        if not self._account_id:
            raise OandaAuthError(
                "OANDA_ACCOUNT_ID is not set; required for pricing endpoints."
            )
        return self._account_id

    def _get(self, path: str, params: dict) -> dict:
        response = self._session.get(self._base_url + path, params=params)
        status = getattr(response, "status_code", 200)
        if status != 200:
            raise OandaAPIError(status, getattr(response, "text", ""))
        return response.json()
