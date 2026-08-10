import json
from datetime import datetime, timezone

import pytest

from ictagent.config.settings import Settings, Phase
from ictagent.data.oanda import (
    OandaAPIError,
    OandaAuthError,
    OandaClient,
    _parse_candle,
    _parse_candles,
    _parse_oanda_time,
    _parse_quote,
    _to_rfc3339,
)


# ---------------------------------------------------------------------------
# Fake transport — no network, no real OANDA credentials required.
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", lines=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self._lines = lines or []

    def json(self):
        return self._json

    def iter_lines(self):
        yield from self._lines


class FakeSession:
    def __init__(self, response=None):
        self.headers = {}
        self.response = response
        self.calls = []

    def get(self, url, params=None, stream=False):
        self.calls.append({"url": url, "params": params, "stream": stream})
        return self.response


def _settings(**overrides) -> Settings:
    base = dict(
        phase=Phase.PAPER,
        live_trading_confirm="",
        kite_api_key=None,
        kite_api_secret=None,
        kite_access_token=None,
        oanda_api_token="test-token",
        oanda_account_id="001-001-1234567-001",
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


def test_parse_oanda_time_with_nanoseconds_and_z():
    dt = _parse_oanda_time("2023-06-01T12:30:45.123456789Z")
    assert dt == datetime(2023, 6, 1, 12, 30, 45, 123456, tzinfo=timezone.utc)


def test_parse_oanda_time_without_fraction():
    dt = _parse_oanda_time("2023-06-01T12:30:45Z")
    assert dt == datetime(2023, 6, 1, 12, 30, 45, tzinfo=timezone.utc)


def test_to_rfc3339_passthrough_string():
    assert _to_rfc3339("2023-01-01T00:00:00Z") == "2023-01-01T00:00:00Z"


def test_to_rfc3339_naive_datetime_assumed_utc():
    result = _to_rfc3339(datetime(2023, 1, 1, 0, 0, 0))
    assert result == "2023-01-01T00:00:00Z"


def test_to_rfc3339_rejects_other_types():
    with pytest.raises(TypeError):
        _to_rfc3339(12345)


def test_parse_candle_prefers_mid():
    raw = {
        "time": "2023-01-01T00:00:00Z",
        "volume": 120,
        "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.15"},
    }
    c = _parse_candle(raw)
    assert (c.open, c.high, c.low, c.close, c.volume) == (1.1, 1.2, 1.0, 1.15, 120)


def test_parse_candle_falls_back_to_bid():
    raw = {
        "time": "2023-01-01T00:00:00Z",
        "bid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.15"},
    }
    c = _parse_candle(raw)
    assert c.close == 1.15


def test_parse_candle_raises_without_price_data():
    with pytest.raises(ValueError):
        _parse_candle({"time": "2023-01-01T00:00:00Z"})


def test_parse_candles_drops_incomplete_by_default():
    payload = {
        "candles": [
            {"complete": True, "time": "2023-01-01T00:00:00Z", "volume": 10,
             "mid": {"o": "1", "h": "2", "l": "0.5", "c": "1.5"}},
            {"complete": False, "time": "2023-01-01T00:01:00Z", "volume": 3,
             "mid": {"o": "1.5", "h": "1.6", "l": "1.4", "c": "1.55"}},
        ]
    }
    complete_only = _parse_candles(payload)
    assert len(complete_only) == 1

    with_incomplete = _parse_candles(payload, include_incomplete=True)
    assert len(with_incomplete) == 2


def test_parse_quote():
    raw = {
        "instrument": "EUR_USD",
        "time": "2023-01-01T00:00:00Z",
        "bids": [{"price": "1.0850", "liquidity": 1000000}],
        "asks": [{"price": "1.0852", "liquidity": 1000000}],
    }
    q = _parse_quote(raw)
    assert q.instrument == "EUR_USD"
    assert q.bid == 1.0850
    assert q.ask == 1.0852
    assert q.mid == pytest.approx(1.0851)


# ---------------------------------------------------------------------------
# OandaClient construction / auth
# ---------------------------------------------------------------------------


def test_missing_api_token_raises_auth_error():
    with pytest.raises(OandaAuthError):
        OandaClient(settings=_settings(oanda_api_token=None), session=FakeSession())


def test_unknown_environment_raises_value_error():
    with pytest.raises(ValueError):
        OandaClient(settings=_settings(oanda_environment="staging"), session=FakeSession())


def test_session_gets_auth_header():
    session = FakeSession()
    OandaClient(settings=_settings(), session=session)
    assert session.headers["Authorization"] == "Bearer test-token"


# ---------------------------------------------------------------------------
# fetch_candles
# ---------------------------------------------------------------------------


def test_fetch_candles_rejects_unknown_granularity():
    client = OandaClient(settings=_settings(), session=FakeSession())
    with pytest.raises(ValueError):
        client.fetch_candles("EUR_USD", granularity="M3")


def test_fetch_candles_builds_request_and_parses_response():
    payload = {
        "candles": [
            {"complete": True, "time": "2023-01-01T00:00:00Z", "volume": 100,
             "mid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.05"}},
            {"complete": True, "time": "2023-01-01T00:01:00Z", "volume": 80,
             "mid": {"o": "1.05", "h": "1.08", "l": "1.02", "c": "1.06"}},
        ]
    }
    session = FakeSession(response=FakeResponse(json_data=payload))
    client = OandaClient(settings=_settings(), session=session)

    candles = client.fetch_candles("EUR_USD", granularity="M1", count=2)

    assert len(candles) == 2
    assert candles[0].close == 1.05
    assert candles[1].close == 1.06

    call = session.calls[0]
    assert call["url"] == "https://api-fxpractice.oanda.com/v3/instruments/EUR_USD/candles"
    assert call["params"] == {"granularity": "M1", "price": "M", "count": 2}


def test_fetch_candles_uses_from_to_instead_of_count_when_given():
    session = FakeSession(response=FakeResponse(json_data={"candles": []}))
    client = OandaClient(settings=_settings(), session=session)

    client.fetch_candles(
        "EUR_USD",
        granularity="H1",
        start=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end=datetime(2023, 1, 2, tzinfo=timezone.utc),
    )

    params = session.calls[0]["params"]
    assert params["from"] == "2023-01-01T00:00:00Z"
    assert params["to"] == "2023-01-02T00:00:00Z"
    assert "count" not in params


def test_fetch_candles_raises_oanda_api_error_on_non_200():
    session = FakeSession(response=FakeResponse(status_code=401, text="invalid token"))
    client = OandaClient(settings=_settings(), session=session)

    with pytest.raises(OandaAPIError) as exc_info:
        client.fetch_candles("EUR_USD", granularity="M1")

    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# pricing
# ---------------------------------------------------------------------------


def test_get_current_price_requires_account_id():
    session = FakeSession()
    client = OandaClient(settings=_settings(oanda_account_id=None), session=session)
    with pytest.raises(OandaAuthError):
        client.get_current_price(["EUR_USD"])


def test_get_current_price_returns_quotes_by_instrument():
    payload = {
        "prices": [
            {
                "instrument": "EUR_USD",
                "time": "2023-01-01T00:00:00Z",
                "bids": [{"price": "1.0850"}],
                "asks": [{"price": "1.0852"}],
            }
        ]
    }
    session = FakeSession(response=FakeResponse(json_data=payload))
    client = OandaClient(settings=_settings(), session=session)

    quotes = client.get_current_price(["EUR_USD"])

    assert set(quotes) == {"EUR_USD"}
    assert quotes["EUR_USD"].bid == 1.0850
    assert session.calls[0]["url"].endswith(
        "/v3/accounts/001-001-1234567-001/pricing"
    )


def test_stream_prices_yields_quotes_and_skips_heartbeats():
    lines = [
        json.dumps({"type": "HEARTBEAT", "time": "2023-01-01T00:00:00Z"}).encode(),
        b"",  # blank keep-alive line, must be skipped
        json.dumps(
            {
                "type": "PRICE",
                "instrument": "EUR_USD",
                "time": "2023-01-01T00:00:01Z",
                "bids": [{"price": "1.0850"}],
                "asks": [{"price": "1.0852"}],
            }
        ).encode(),
    ]
    session = FakeSession(response=FakeResponse(status_code=200, lines=lines))
    client = OandaClient(settings=_settings(), session=session)

    quotes = list(client.stream_prices(["EUR_USD"]))

    assert len(quotes) == 1
    assert quotes[0].instrument == "EUR_USD"
    assert session.calls[0]["stream"] is True


def test_stream_prices_requires_account_id():
    client = OandaClient(settings=_settings(oanda_account_id=None), session=FakeSession())
    with pytest.raises(OandaAuthError):
        next(client.stream_prices(["EUR_USD"]))
