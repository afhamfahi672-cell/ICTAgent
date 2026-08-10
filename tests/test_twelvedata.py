from datetime import datetime, timezone

import pytest

from ictagent.config.settings import Settings, Phase
from ictagent.data.twelvedata import (
    TwelveDataAPIError,
    TwelveDataAuthError,
    TwelveDataClient,
    _parse_candle,
    _parse_candle_time,
    _parse_candles,
)


# ---------------------------------------------------------------------------
# Fake transport — no network, no real Twelve Data key.
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, response=None):
        self.response = response
        self.calls = []

    def get(self, url, params=None):
        self.calls.append({"url": url, "params": params})
        return self.response


def _settings(**overrides) -> Settings:
    base = dict(
        phase=Phase.PAPER,
        live_trading_confirm="",
        kite_api_key=None,
        kite_api_secret=None,
        kite_access_token=None,
        oanda_api_token=None,
        oanda_account_id=None,
        oanda_environment="practice",
        twelvedata_api_key="test-td-key",
        anthropic_api_key=None,
        news_api_key=None,
    )
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# Pure parsing helpers
# ---------------------------------------------------------------------------


def test_parse_candle_time_intraday():
    assert _parse_candle_time("2023-06-01 12:30:00") == datetime(2023, 6, 1, 12, 30, tzinfo=timezone.utc)


def test_parse_candle_time_daily():
    assert _parse_candle_time("2023-06-01") == datetime(2023, 6, 1, tzinfo=timezone.utc)


def test_parse_candle_defaults_missing_volume_to_zero():
    raw = {"datetime": "2023-06-01 12:30:00", "open": "1.08", "high": "1.09", "low": "1.07", "close": "1.085"}
    c = _parse_candle(raw)
    assert c.volume == 0.0


def test_parse_candle_uses_volume_when_present():
    raw = {
        "datetime": "2023-06-01 12:30:00", "open": "1.08", "high": "1.09", "low": "1.07",
        "close": "1.085", "volume": "12345",
    }
    assert _parse_candle(raw).volume == 12345.0


def test_parse_candles_sorts_chronologically_regardless_of_input_order():
    payload = {
        "values": [
            {"datetime": "2023-06-01 12:45:00", "open": "1", "high": "1", "low": "1", "close": "1"},
            {"datetime": "2023-06-01 12:15:00", "open": "1", "high": "1", "low": "1", "close": "1"},
            {"datetime": "2023-06-01 12:30:00", "open": "1", "high": "1", "low": "1", "close": "1"},
        ]
    }
    candles = _parse_candles(payload)
    assert [c.timestamp.minute for c in candles] == [15, 30, 45]


def test_parse_candles_missing_values_key_returns_empty():
    assert _parse_candles({"status": "ok"}) == []


def test_parse_candles_raises_on_soft_error_payload():
    payload = {"status": "error", "code": 401, "message": "invalid api key"}
    with pytest.raises(TwelveDataAPIError) as exc_info:
        _parse_candles(payload)
    assert exc_info.value.code == 401
    assert "invalid api key" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TwelveDataClient construction / auth
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_auth_error():
    with pytest.raises(TwelveDataAuthError):
        TwelveDataClient(settings=_settings(twelvedata_api_key=None), session=FakeSession())


# ---------------------------------------------------------------------------
# fetch_candles
# ---------------------------------------------------------------------------


def test_fetch_candles_builds_request_and_parses_response():
    payload = {
        "values": [
            {"datetime": "2023-06-01 12:00:00", "open": "1.0", "high": "1.1", "low": "0.9", "close": "1.05"},
        ]
    }
    session = FakeSession(response=FakeResponse(json_data=payload))
    client = TwelveDataClient(settings=_settings(), session=session)

    candles = client.fetch_candles("EUR/USD", interval="15min", count=300)

    assert len(candles) == 1
    assert candles[0].close == 1.05

    call = session.calls[0]
    assert call["url"] == "https://api.twelvedata.com/time_series"
    assert call["params"] == {
        "symbol": "EUR/USD",
        "interval": "15min",
        "outputsize": 300,
        "apikey": "test-td-key",
    }


def test_fetch_candles_raises_on_non_200_http_status():
    session = FakeSession(response=FakeResponse(status_code=429, text="rate limited"))
    client = TwelveDataClient(settings=_settings(), session=session)

    with pytest.raises(TwelveDataAPIError) as exc_info:
        client.fetch_candles("EUR/USD")
    assert exc_info.value.code == 429


def test_fetch_candles_raises_on_soft_error_response_body():
    session = FakeSession(
        response=FakeResponse(json_data={"status": "error", "code": 400, "message": "bad symbol"})
    )
    client = TwelveDataClient(settings=_settings(), session=session)

    with pytest.raises(TwelveDataAPIError):
        client.fetch_candles("NOT_A_SYMBOL")
