from datetime import datetime, timezone, timedelta

import pytest

from ictagent.config.settings import Settings, Phase
from ictagent.data.kite import (
    IST,
    KiteAPIError,
    KiteAuthError,
    KiteClient,
    _coerce_datetime,
    _parse_candle,
    _parse_candles,
    _parse_quote,
)


# ---------------------------------------------------------------------------
# Fake kiteconnect.KiteConnect double — no network, no real Kite app/login.
# ---------------------------------------------------------------------------


class FakeKite:
    def __init__(self):
        self.access_token = None
        self.calls = []
        self.login_url_value = "https://kite.zerodha.com/connect/login?api_key=x"
        self.generate_session_response = {"access_token": "fresh-token"}
        self.historical_data_response = []
        self.quote_response = {}
        self.instruments_response = []
        self.raise_on = None

    def _maybe_raise(self, name):
        if self.raise_on == name:
            raise Exception(f"simulated {name} failure")

    def login_url(self):
        self.calls.append(("login_url",))
        return self.login_url_value

    def generate_session(self, request_token, api_secret):
        self.calls.append(("generate_session", request_token, api_secret))
        self._maybe_raise("generate_session")
        return self.generate_session_response

    def set_access_token(self, token):
        self.calls.append(("set_access_token", token))
        self.access_token = token

    def historical_data(self, instrument_token, from_date, to_date, interval, continuous):
        self.calls.append(
            ("historical_data", instrument_token, from_date, to_date, interval, continuous)
        )
        self._maybe_raise("historical_data")
        return self.historical_data_response

    def quote(self, instruments):
        self.calls.append(("quote", instruments))
        self._maybe_raise("quote")
        return self.quote_response

    def instruments(self, exchange):
        self.calls.append(("instruments", exchange))
        self._maybe_raise("instruments")
        return self.instruments_response


def _settings(**overrides) -> Settings:
    base = dict(
        phase=Phase.PAPER,
        live_trading_confirm="",
        kite_api_key="test-api-key",
        kite_api_secret="test-api-secret",
        kite_access_token=None,
        oanda_api_token=None,
        oanda_account_id=None,
        oanda_environment="practice",
        twelvedata_api_key=None,
        anthropic_api_key=None,
        news_api_key=None,
    )
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# Pure parsing helpers
# ---------------------------------------------------------------------------


def test_coerce_datetime_passthrough():
    dt = datetime(2023, 1, 1, 9, 15, tzinfo=IST)
    assert _coerce_datetime(dt) is dt


def test_coerce_datetime_offset_without_colon():
    dt = _coerce_datetime("2023-01-01T09:15:00+0530")
    assert dt == datetime(2023, 1, 1, 9, 15, tzinfo=IST)


def test_coerce_datetime_offset_with_colon():
    dt = _coerce_datetime("2023-01-01T09:15:00+05:30")
    assert dt == datetime(2023, 1, 1, 9, 15, tzinfo=IST)


def test_coerce_datetime_plain_string_assumed_ist():
    dt = _coerce_datetime("2023-01-01 09:15:00")
    assert dt == datetime(2023, 1, 1, 9, 15, tzinfo=IST)


def test_coerce_datetime_rejects_other_types():
    with pytest.raises(TypeError):
        _coerce_datetime(12345)


def test_parse_candle():
    raw = {"date": "2023-01-01T09:15:00+0530", "open": 100, "high": 101, "low": 99,
           "close": 100.5, "volume": 12345}
    c = _parse_candle(raw)
    assert (c.open, c.high, c.low, c.close, c.volume) == (100.0, 101.0, 99.0, 100.5, 12345.0)
    assert c.timestamp == datetime(2023, 1, 1, 9, 15, tzinfo=IST)


def test_parse_candles():
    raw = [
        {"date": "2023-01-01T09:15:00+0530", "open": 100, "high": 101, "low": 99, "close": 100.5},
        {"date": "2023-01-01T09:16:00+0530", "open": 100.5, "high": 102, "low": 100, "close": 101.5},
    ]
    candles = _parse_candles(raw)
    assert len(candles) == 2
    assert candles[1].close == 101.5


def test_parse_quote_uses_best_depth():
    raw = {
        "timestamp": "2023-01-01 09:15:00",
        "last_price": 1500.0,
        "depth": {
            "buy": [{"price": 1499.5, "quantity": 10}],
            "sell": [{"price": 1500.5, "quantity": 20}],
        },
    }
    q = _parse_quote("NSE:INFY", raw)
    assert q.bid == 1499.5
    assert q.ask == 1500.5
    assert q.time == datetime(2023, 1, 1, 9, 15, tzinfo=IST)


def test_parse_quote_falls_back_to_last_price_without_depth():
    raw = {"timestamp": "2023-01-01 09:15:00", "last_price": 1500.0, "depth": {"buy": [], "sell": []}}
    q = _parse_quote("NSE:INFY", raw)
    assert q.bid == 1500.0
    assert q.ask == 1500.0


def test_parse_quote_requires_timestamp():
    with pytest.raises(ValueError):
        _parse_quote("NSE:INFY", {"last_price": 1500.0})


# ---------------------------------------------------------------------------
# KiteClient construction / auth
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_auth_error():
    with pytest.raises(KiteAuthError):
        KiteClient(settings=_settings(kite_api_key=None), kite=FakeKite())


def test_access_token_from_settings_activates_session():
    fake = FakeKite()
    client = KiteClient(settings=_settings(kite_access_token="today-token"), kite=fake)
    assert ("set_access_token", "today-token") in fake.calls
    # session is ready, so a call that requires it shouldn't raise KiteAuthError
    fake.quote_response = {}
    client.get_quote(["NSE:INFY"])


def test_no_session_blocks_data_calls():
    client = KiteClient(settings=_settings(), kite=FakeKite())
    with pytest.raises(KiteAuthError):
        client.get_quote(["NSE:INFY"])
    with pytest.raises(KiteAuthError):
        client.fetch_candles("NSE", "INFY", "day", "2023-01-01", "2023-01-02")


# ---------------------------------------------------------------------------
# login_url / generate_session
# ---------------------------------------------------------------------------


def test_generate_session_requires_api_secret():
    client = KiteClient(settings=_settings(kite_api_secret=None), kite=FakeKite())
    with pytest.raises(KiteAuthError):
        client.generate_session("req-token")


def test_generate_session_activates_client_and_returns_token():
    fake = FakeKite()
    client = KiteClient(settings=_settings(), kite=fake)
    token = client.generate_session("req-token")
    assert token == "fresh-token"
    assert ("generate_session", "req-token", "test-api-secret") in fake.calls
    assert ("set_access_token", "fresh-token") in fake.calls
    # session now ready
    fake.quote_response = {}
    client.get_quote(["NSE:INFY"])


def test_generate_session_wraps_kite_errors():
    fake = FakeKite()
    fake.raise_on = "generate_session"
    client = KiteClient(settings=_settings(), kite=fake)
    with pytest.raises(KiteAPIError):
        client.generate_session("bad-token")


def test_login_url_delegates_to_kite():
    fake = FakeKite()
    client = KiteClient(settings=_settings(), kite=fake)
    assert client.login_url() == fake.login_url_value


# ---------------------------------------------------------------------------
# fetch_candles
# ---------------------------------------------------------------------------


def test_fetch_candles_rejects_unknown_interval():
    client = KiteClient(settings=_settings(kite_access_token="tok"), kite=FakeKite())
    with pytest.raises(ValueError):
        client.fetch_candles("NSE", "INFY", "7minute", "2023-01-01", "2023-01-02")


def test_fetch_candles_resolves_token_and_caches_per_exchange():
    fake = FakeKite()
    fake.instruments_response = [
        {"tradingsymbol": "INFY", "instrument_token": 111},
        {"tradingsymbol": "TCS", "instrument_token": 222},
    ]
    fake.historical_data_response = [
        {"date": "2023-01-01T09:15:00+0530", "open": 100, "high": 101, "low": 99, "close": 100.5},
    ]
    client = KiteClient(settings=_settings(kite_access_token="tok"), kite=fake)

    candles1 = client.fetch_candles("NSE", "INFY", "day", "2023-01-01", "2023-01-02")
    candles2 = client.fetch_candles("NSE", "TCS", "day", "2023-01-01", "2023-01-02")

    assert len(candles1) == 1
    assert len(candles2) == 1

    instrument_calls = [c for c in fake.calls if c[0] == "instruments"]
    assert instrument_calls == [("instruments", "NSE")]  # only fetched once, cached

    historical_calls = [c for c in fake.calls if c[0] == "historical_data"]
    assert historical_calls[0][1] == 111  # INFY's token
    assert historical_calls[1][1] == 222  # TCS's token


def test_fetch_candles_unknown_tradingsymbol_raises():
    fake = FakeKite()
    fake.instruments_response = [{"tradingsymbol": "INFY", "instrument_token": 111}]
    client = KiteClient(settings=_settings(kite_access_token="tok"), kite=fake)
    with pytest.raises(KiteAPIError):
        client.fetch_candles("NSE", "DOES_NOT_EXIST", "day", "2023-01-01", "2023-01-02")


def test_fetch_candles_wraps_kite_errors():
    fake = FakeKite()
    fake.instruments_response = [{"tradingsymbol": "INFY", "instrument_token": 111}]
    fake.raise_on = "historical_data"
    client = KiteClient(settings=_settings(kite_access_token="tok"), kite=fake)
    with pytest.raises(KiteAPIError):
        client.fetch_candles("NSE", "INFY", "day", "2023-01-01", "2023-01-02")


# ---------------------------------------------------------------------------
# get_quote
# ---------------------------------------------------------------------------


def test_get_quote_parses_response_by_instrument_key():
    fake = FakeKite()
    fake.quote_response = {
        "NSE:INFY": {
            "timestamp": "2023-01-01 09:15:00",
            "last_price": 1500.0,
            "depth": {"buy": [{"price": 1499.5}], "sell": [{"price": 1500.5}]},
        }
    }
    client = KiteClient(settings=_settings(kite_access_token="tok"), kite=fake)
    quotes = client.get_quote(["NSE:INFY"])
    assert set(quotes) == {"NSE:INFY"}
    assert quotes["NSE:INFY"].bid == 1499.5
    assert quotes["NSE:INFY"].ask == 1500.5


def test_get_quote_wraps_kite_errors():
    fake = FakeKite()
    fake.raise_on = "quote"
    client = KiteClient(settings=_settings(kite_access_token="tok"), kite=fake)
    with pytest.raises(KiteAPIError):
        client.get_quote(["NSE:INFY"])
