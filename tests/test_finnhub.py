from datetime import date, datetime, timezone

import pytest

from ictagent.config.settings import Settings, Phase
from ictagent.context.finnhub import (
    FinnhubClient,
    NewsAPIError,
    NewsAuthError,
    _parse_article,
    _parse_articles,
    _parse_event,
    _parse_events,
    _to_date_str,
)


# ---------------------------------------------------------------------------
# Fake transport — no network, no real Finnhub key.
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
        anthropic_api_key=None,
        news_api_key="test-finnhub-key",
    )
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# Pure parsing helpers
# ---------------------------------------------------------------------------


def test_parse_article():
    raw = {
        "headline": "EUR/USD rallies on ECB comments",
        "summary": "Summary text.",
        "source": "Reuters",
        "url": "https://example.com/a",
        "datetime": 1700000000,
        "category": "forex",
        "related": "EURUSD",
    }
    a = _parse_article(raw)
    assert a.headline == "EUR/USD rallies on ECB comments"
    assert a.published_at == datetime.fromtimestamp(1700000000, tz=timezone.utc)
    assert a.related == "EURUSD"


def test_parse_articles_list():
    raw = [
        {"headline": "A", "summary": "", "source": "S", "url": "u", "datetime": 1700000000},
        {"headline": "B", "summary": "", "source": "S", "url": "u", "datetime": 1700000100},
    ]
    articles = _parse_articles(raw)
    assert [a.headline for a in articles] == ["A", "B"]


def test_parse_event():
    raw = {
        "event": "Nonfarm Payrolls",
        "country": "US",
        "impact": "high",
        "time": "2023-06-02 12:30:00",
        "actual": "339",
        "estimate": "190",
        "prev": "294",
        "unit": "K",
    }
    e = _parse_event(raw)
    assert e.event == "Nonfarm Payrolls"
    assert e.impact == "high"
    assert e.event_time == datetime(2023, 6, 2, 12, 30, tzinfo=timezone.utc)
    assert e.actual == 339.0
    assert e.estimate == 190.0
    assert e.previous == 294.0


def test_parse_event_handles_missing_values():
    raw = {"event": "TBD Event", "country": "IN", "impact": "", "time": None, "actual": "", "prev": None}
    e = _parse_event(raw)
    assert e.impact is None
    assert e.event_time is None
    assert e.actual is None
    assert e.previous is None


def test_parse_events_from_payload():
    payload = {
        "economicCalendar": [
            {"event": "CPI", "country": "US", "impact": "high", "time": "2023-06-01 12:30:00"},
        ]
    }
    events = _parse_events(payload)
    assert len(events) == 1
    assert events[0].event == "CPI"


def test_parse_events_missing_key_returns_empty():
    assert _parse_events({}) == []


def test_to_date_str_variants():
    assert _to_date_str("2023-06-01") == "2023-06-01"
    assert _to_date_str(date(2023, 6, 1)) == "2023-06-01"
    assert _to_date_str(datetime(2023, 6, 1, 9, 30)) == "2023-06-01"
    with pytest.raises(TypeError):
        _to_date_str(12345)


# ---------------------------------------------------------------------------
# FinnhubClient construction / auth
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_auth_error():
    with pytest.raises(NewsAuthError):
        FinnhubClient(settings=_settings(news_api_key=None), session=FakeSession())


# ---------------------------------------------------------------------------
# get_news / get_company_news / get_economic_calendar
# ---------------------------------------------------------------------------


def test_get_news_builds_request_and_parses_response():
    payload = [
        {"headline": "Fed holds rates", "summary": "s", "source": "AP", "url": "u", "datetime": 1700000000},
    ]
    session = FakeSession(response=FakeResponse(json_data=payload))
    client = FinnhubClient(settings=_settings(), session=session)

    articles = client.get_news(category="forex")

    assert len(articles) == 1
    assert articles[0].headline == "Fed holds rates"

    call = session.calls[0]
    assert call["url"] == "https://finnhub.io/api/v1/news"
    assert call["params"] == {"category": "forex", "token": "test-finnhub-key"}


def test_get_company_news_scopes_by_symbol_and_dates():
    session = FakeSession(response=FakeResponse(json_data=[]))
    client = FinnhubClient(settings=_settings(), session=session)

    client.get_company_news("INFY", date(2023, 6, 1), date(2023, 6, 7))

    params = session.calls[0]["params"]
    assert params["symbol"] == "INFY"
    assert params["from"] == "2023-06-01"
    assert params["to"] == "2023-06-07"


def test_get_economic_calendar_parses_events():
    payload = {
        "economicCalendar": [
            {"event": "CPI", "country": "US", "impact": "high", "time": "2023-06-01 12:30:00"},
        ]
    }
    session = FakeSession(response=FakeResponse(json_data=payload))
    client = FinnhubClient(settings=_settings(), session=session)

    events = client.get_economic_calendar("2023-06-01", "2023-06-07")

    assert len(events) == 1
    assert events[0].event == "CPI"
    assert session.calls[0]["url"] == "https://finnhub.io/api/v1/calendar/economic"


def test_raises_news_api_error_on_non_200():
    session = FakeSession(response=FakeResponse(status_code=403, text="plan does not include this endpoint"))
    client = FinnhubClient(settings=_settings(), session=session)

    with pytest.raises(NewsAPIError) as exc_info:
        client.get_economic_calendar("2023-06-01", "2023-06-07")
    assert exc_info.value.status_code == 403
