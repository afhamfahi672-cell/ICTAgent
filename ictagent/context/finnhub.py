"""
Finnhub adapter — general market news + economic calendar.

Chosen as the default news/fundamentals provider so this layer needs
only one credential and one adapter to reason about, covering both
headlines and (see caveat below) a forward economic calendar. This is a
starting choice, not a locked-in one — nothing outside this file assumes
Finnhub, so swapping providers later means replacing this module alone.

Known caveat: Finnhub's free tier reliably covers general market news;
economic-calendar access has moved behind paid tiers at various points
in the past. Confirm current access on your own account before relying
on `get_economic_calendar()` in production — if it 403s, that's Finnhub's
plan gating, not a bug here.

Auth: a single API key (`NEWS_API_KEY` in `.env` — see `.env.example`),
sent as a `token` query parameter per Finnhub's convention (not a
header). Talks to the REST API directly over `requests`, the same
approach as data/oanda.py and for the same reason: keep the credential
surface and error handling in full view rather than behind an SDK.

All parsing (`_parse_article`, `_parse_articles`, `_parse_event`,
`_parse_events`, the timestamp helpers) is pure and unit-tested with no
network dependency. `FinnhubClient` accepts an injectable `session`, so
its request-building/response-parsing wiring is fully unit-tested
against a fake session too — see tests/test_finnhub.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional, Union

from ictagent.config.settings import Settings, load_settings

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


class NewsAuthError(RuntimeError):
    """Raised when NEWS_API_KEY (the Finnhub API key) is not set."""


class NewsAPIError(RuntimeError):
    """Raised when Finnhub's API returns a non-2xx response."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Finnhub API error {status_code}: {body}")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NewsArticle:
    headline: str
    summary: str
    source: str
    url: str
    published_at: datetime
    category: Optional[str] = None
    related: Optional[str] = None  # comma-separated tickers/symbols, per Finnhub

    def to_dict(self) -> dict:
        return {
            "headline": self.headline,
            "summary": self.summary,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "category": self.category,
            "related": self.related,
        }


@dataclass(frozen=True)
class EconomicEvent:
    event: str
    country: str
    impact: Optional[str]  # "low" | "medium" | "high", per Finnhub — passed through as-is
    event_time: Optional[datetime]
    actual: Optional[float]
    estimate: Optional[float]
    previous: Optional[float]
    unit: Optional[str]

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "country": self.country,
            "impact": self.impact,
            "event_time": self.event_time.isoformat() if self.event_time else None,
            "actual": self.actual,
            "estimate": self.estimate,
            "previous": self.previous,
            "unit": self.unit,
        }


# ---------------------------------------------------------------------------
# Pure parsing helpers — no network dependency, exercised directly in tests.
# ---------------------------------------------------------------------------


def _parse_news_time(raw) -> datetime:
    """Finnhub news timestamps are Unix seconds (UTC)."""
    return datetime.fromtimestamp(float(raw), tz=timezone.utc)


def _parse_article(raw: dict) -> NewsArticle:
    return NewsArticle(
        headline=raw.get("headline", ""),
        summary=raw.get("summary", ""),
        source=raw.get("source", ""),
        url=raw.get("url", ""),
        published_at=_parse_news_time(raw["datetime"]),
        category=raw.get("category"),
        related=raw.get("related") or None,
    )


def _parse_articles(raw_list: list[dict]) -> list[NewsArticle]:
    return [_parse_article(r) for r in raw_list]


def _parse_calendar_time(raw: Optional[str]) -> Optional[datetime]:
    """Finnhub economic calendar times are "YYYY-MM-DD HH:MM:SS", UTC."""
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _to_float_or_none(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_event(raw: dict) -> EconomicEvent:
    return EconomicEvent(
        event=raw.get("event", ""),
        country=raw.get("country", ""),
        impact=raw.get("impact") or None,
        event_time=_parse_calendar_time(raw.get("time")),
        actual=_to_float_or_none(raw.get("actual")),
        estimate=_to_float_or_none(raw.get("estimate")),
        previous=_to_float_or_none(raw.get("prev")),
        unit=raw.get("unit") or None,
    )


def _parse_events(payload: dict) -> list[EconomicEvent]:
    return [_parse_event(r) for r in payload.get("economicCalendar", [])]


def _to_date_str(value: Union[str, date, datetime]) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    raise TypeError(f"expected str/date/datetime, got {type(value)!r}")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FinnhubClient:
    """`session` can be injected (anything exposing `requests.Session`'s
    `.get(url, params=...)` returning a `requests.Response`-like object) —
    used by tests to avoid any real network call. Defaults to a real
    `requests.Session()`."""

    def __init__(self, settings: Optional[Settings] = None, session=None):
        self._settings = settings or load_settings()

        if not self._settings.news_api_key:
            raise NewsAuthError(
                "NEWS_API_KEY is not set. See .env.example for the required "
                "environment variable (a Finnhub API key)."
            )

        if session is not None:
            self._session = session
        else:
            import requests  # lazy: only needed for real (non-test) usage

            self._session = requests.Session()

    def get_news(self, category: str = "general") -> list[NewsArticle]:
        """General market headlines. `category`: "general", "forex",
        "crypto", or "merger" per Finnhub's own categories."""
        payload = self._get("/news", {"category": category})
        return _parse_articles(payload)

    def get_company_news(
        self,
        symbol: str,
        from_date: Union[str, date, datetime],
        to_date: Union[str, date, datetime],
    ) -> list[NewsArticle]:
        """Headlines for one equity symbol (not applicable to forex pairs
        or index futures — Finnhub's company-news endpoint is stock-only)."""
        payload = self._get(
            "/company-news",
            {"symbol": symbol, "from": _to_date_str(from_date), "to": _to_date_str(to_date)},
        )
        return _parse_articles(payload)

    def get_economic_calendar(
        self, from_date: Union[str, date, datetime], to_date: Union[str, date, datetime]
    ) -> list[EconomicEvent]:
        """Scheduled macro events in [from_date, to_date]. See the module
        docstring's caveat about free-tier access to this endpoint."""
        payload = self._get(
            "/calendar/economic",
            {"from": _to_date_str(from_date), "to": _to_date_str(to_date)},
        )
        return _parse_events(payload)

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "token": self._settings.news_api_key}
        response = self._session.get(FINNHUB_BASE_URL + path, params=params)
        status = getattr(response, "status_code", 200)
        if status != 200:
            raise NewsAPIError(status, getattr(response, "text", ""))
        return response.json()
