"""
Fundamentals/news + session-timing context layer.

  context/sessions.py    Implemented. Kill-zone / trading-session timing
                          — fully deterministic, no external API. See
                          module docstring for the London/New York/Tokyo/
                          NSE windows and the ICT kill-zone defaults.
  context/finnhub.py     Implemented. News headlines + economic calendar
                          via the Finnhub API (a starting provider choice
                          — see the module docstring for the free-tier
                          caveat on the calendar endpoint and how to swap
                          providers later).

Output of this module is handed to agent/ alongside structure/'s
StructureState — it is descriptive context, not a decision by itself.
"""

from .sessions import (
    Window,
    SessionContext,
    TRADING_SESSIONS,
    KILL_ZONES,
    get_session_context,
)
from .finnhub import (
    NewsArticle,
    EconomicEvent,
    FinnhubClient,
    NewsAuthError,
    NewsAPIError,
)

__all__ = [
    "Window",
    "SessionContext",
    "TRADING_SESSIONS",
    "KILL_ZONES",
    "get_session_context",
    "NewsArticle",
    "EconomicEvent",
    "FinnhubClient",
    "NewsAuthError",
    "NewsAPIError",
]
