"""
Zerodha Kite Connect adapter — historical candles + live quote snapshots
for Indian equities and index F&O.

Auth/session handling is entirely self-contained here and deliberately
does not share anything with data/oanda.py. Kite's auth model is
fundamentally different from OANDA's static long-lived token:

  1. KITE_API_KEY identifies the app (set once, doesn't expire).
  2. Every trading day, a human logs into Kite in a browser via the URL
     from `login_url()`, gets redirected back with a one-time
     `request_token`, and that token is exchanged for a fresh
     `access_token` via `generate_session()` (needs KITE_API_SECRET).
     The access_token is only valid until the next Kite session reset
     (effectively, one trading day).
  3. If `KITE_ACCESS_TOKEN` is already set in the environment (e.g. a
     separate daily login script already ran and exported it), this
     client picks it up at construction and skips step 2.

There is no code here that performs the interactive browser login for
you — that step inherently needs a human in the loop once a day. This
module just exposes `login_url()`/`generate_session()` so whatever
daily "log in to Kite" script gets built later can call them.

Live tick streaming (KiteTicker, WebSocket-based) is not implemented
yet — it's a meaningfully different, callback/event-driven design from
this REST-style client, and isn't needed for Phase 1 (paper trading on
a decision-cycle cadence, not tick-by-tick). `get_quote()` gives a
REST snapshot, which is sufficient for a polling decision loop.

All response parsing (`_parse_candle`, `_parse_candles`, `_parse_quote`,
`_coerce_datetime`) is pure and unit-tested with no network dependency.
`KiteClient` accepts an injectable `kite` object (anything exposing the
official `kiteconnect.KiteConnect` client's method names used below),
so its wiring is fully unit-tested against a fake — see
tests/test_kite.py. Real usage requires `pip install kiteconnect`
(`pip install -e ".[data]"` pulls it in), imported lazily so this
module and its tests don't require it to be installed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from ictagent.config.settings import Settings, load_settings
from ictagent.structure.types import Candle

from .types import Quote

# NSE/BSE/NFO/etc. all run on India Standard Time; Kite's REST responses
# report local exchange time with no explicit offset in some fields, so
# we attach this fixed offset ourselves (India has no DST).
IST = timezone(timedelta(hours=5, minutes=30))

# Kite Connect's supported historical_data intervals.
KITE_INTERVALS = frozenset(
    {"minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"}
)


class KiteAuthError(RuntimeError):
    """Raised when required Kite credentials/session state are missing
    for the operation being attempted (no API key, no API secret when
    generating a session, or no active session yet)."""


class KiteAPIError(RuntimeError):
    """Raised when the underlying kiteconnect call raises — normalizes
    kiteconnect's own exception hierarchy into one type for callers here."""


# ---------------------------------------------------------------------------
# Pure parsing helpers — no network dependency, exercised directly in tests.
# ---------------------------------------------------------------------------


def _coerce_datetime(value) -> datetime:
    """Kite gives us timestamps in a few different shapes depending on
    endpoint and kiteconnect SDK version: already-parsed tz-aware
    datetimes (historical_data), ISO strings with a +0530-style offset,
    or plain "YYYY-MM-DD HH:MM:SS" strings with no offset at all (assumed
    IST, since that's the only timezone Kite ever reports in)."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        s = value
        if len(s) >= 5 and s[-5] in "+-" and s[-4:].isdigit() and s[-3] != ":":
            s = f"{s[:-2]}:{s[-2:]}"  # "+0530" -> "+05:30"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        # fromisoformat happily parses "YYYY-MM-DD HH:MM:SS" (space
        # separator) as *naive* when there's no offset in the string —
        # that's Kite reporting local exchange time with the offset
        # omitted, not UTC, so attach IST rather than leaving it naive.
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=IST)
    raise TypeError(f"Cannot coerce {value!r} to a datetime")


def _parse_candle(raw: dict) -> Candle:
    return Candle(
        timestamp=_coerce_datetime(raw["date"]),
        open=float(raw["open"]),
        high=float(raw["high"]),
        low=float(raw["low"]),
        close=float(raw["close"]),
        volume=float(raw.get("volume", 0)),
    )


def _parse_candles(raw_records: list[dict]) -> list[Candle]:
    """`raw_records` is whatever `kiteconnect`'s own `historical_data()`
    returns — Kite's REST endpoint only ever returns completed bars, so
    unlike the OANDA adapter there's no in-progress-candle filtering to
    do here."""
    return [_parse_candle(r) for r in raw_records]


def _parse_quote(instrument_key: str, raw: dict) -> Quote:
    """`instrument_key` is the "EXCHANGE:TRADINGSYMBOL" string used to
    look this entry up in `kite.quote()`'s response dict. Bid/ask come
    from the best market-depth level; if depth is empty (illiquid
    instrument, or a snapshot taken outside market hours) both fall back
    to last traded price rather than raising."""
    timestamp = raw.get("timestamp") or raw.get("last_trade_time")
    if timestamp is None:
        raise ValueError(f"Kite quote for {instrument_key!r} has no timestamp: {raw!r}")

    depth = raw.get("depth") or {}
    buys = depth.get("buy") or []
    sells = depth.get("sell") or []
    last_price = float(raw.get("last_price", 0))

    bid = float(buys[0]["price"]) if buys and buys[0].get("price") else last_price
    ask = float(sells[0]["price"]) if sells and sells[0].get("price") else last_price

    return Quote(instrument=instrument_key, time=_coerce_datetime(timestamp), bid=bid, ask=ask)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class KiteClient:
    """Zerodha Kite Connect client for historical candles and live quote
    snapshots.

    `kite` can be injected (any object exposing the subset of
    `kiteconnect.KiteConnect`'s interface used below: `login_url`,
    `generate_session`, `set_access_token`, `historical_data`, `quote`,
    `instruments`) — used by tests to avoid any real network call or a
    real Kite login. Defaults to a real `kiteconnect.KiteConnect`.
    """

    def __init__(self, settings: Optional[Settings] = None, kite=None):
        self._settings = settings or load_settings()

        if not self._settings.kite_api_key:
            raise KiteAuthError(
                "KITE_API_KEY is not set. See .env.example for the required "
                "KITE_* environment variables."
            )

        if kite is not None:
            self._kite = kite
        else:
            from kiteconnect import KiteConnect  # lazy: only needed for real usage

            self._kite = KiteConnect(api_key=self._settings.kite_api_key)

        self._session_ready = False
        self._instrument_cache: dict[str, dict[str, int]] = {}

        if self._settings.kite_access_token:
            self._kite.set_access_token(self._settings.kite_access_token)
            self._session_ready = True

    def login_url(self) -> str:
        """URL for the human login step. Send the user here; Kite
        redirects back to the app's configured redirect URL with a
        `request_token` query param, which goes to `generate_session()`."""
        return self._kite.login_url()

    def generate_session(self, request_token: str) -> str:
        """Exchange a one-time request_token (from the login redirect)
        for a fresh access_token, and activate it on this client. Must be
        called once per trading day unless KITE_ACCESS_TOKEN was already
        set to a still-valid token."""
        if not self._settings.kite_api_secret:
            raise KiteAuthError(
                "KITE_API_SECRET is not set; required to generate a Kite session."
            )
        data = self._call(
            self._kite.generate_session,
            request_token,
            api_secret=self._settings.kite_api_secret,
        )
        access_token = data["access_token"]
        self._kite.set_access_token(access_token)
        self._session_ready = True
        return access_token

    def fetch_candles(
        self,
        exchange: str,
        tradingsymbol: str,
        interval: str,
        from_date: Union[str, datetime],
        to_date: Union[str, datetime],
        continuous: bool = False,
    ) -> list[Candle]:
        """Historical candles for one instrument. `exchange` is Kite's
        exchange code ("NSE", "NFO", "BSE", ...); `tradingsymbol` is
        e.g. "INFY" or a F&O contract symbol. Resolves and caches the
        numeric instrument_token Kite's historical_data endpoint actually
        requires."""
        if interval not in KITE_INTERVALS:
            raise ValueError(
                f"Unknown interval {interval!r}; expected one of {sorted(KITE_INTERVALS)}"
            )
        self._require_session()
        token = self._resolve_instrument_token(exchange, tradingsymbol)
        raw = self._call(
            self._kite.historical_data, token, from_date, to_date, interval, continuous
        )
        return _parse_candles(raw)

    def get_quote(self, instruments: list[str]) -> dict[str, Quote]:
        """`instruments`: "EXCHANGE:TRADINGSYMBOL" strings, e.g.
        ["NSE:INFY", "NSE:NIFTY 50"] — Kite's own convention, used
        directly, no instrument_token lookup needed for this endpoint."""
        self._require_session()
        raw = self._call(self._kite.quote, instruments)
        return {key: _parse_quote(key, data) for key, data in raw.items()}

    def _resolve_instrument_token(self, exchange: str, tradingsymbol: str) -> int:
        if exchange not in self._instrument_cache:
            raw = self._call(self._kite.instruments, exchange)
            self._instrument_cache[exchange] = {
                row["tradingsymbol"]: row["instrument_token"] for row in raw
            }
        token = self._instrument_cache[exchange].get(tradingsymbol)
        if token is None:
            raise KiteAPIError(f"Unknown instrument {exchange}:{tradingsymbol}")
        return token

    def _require_session(self) -> None:
        if not self._session_ready:
            raise KiteAuthError(
                "No active Kite session. Complete the login flow (login_url() -> "
                "generate_session(request_token)), or set KITE_ACCESS_TOKEN to an "
                "already-valid token for today."
            )

    @staticmethod
    def _call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # normalize kiteconnect's own exception hierarchy
            raise KiteAPIError(str(e)) from e
