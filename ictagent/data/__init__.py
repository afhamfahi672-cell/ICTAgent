"""
Market data ingestion — candles and live quotes.

  data/oanda.py       Implemented. OANDA v20 REST adapter (candles +
                       live pricing) for users who can hold an OANDA
                       account. Not available to Indian residents (RBI/
                       FEMA rules) — see data/twelvedata.py for the
                       no-account-needed alternative used by default.
  data/twelvedata.py  Implemented. Twelve Data adapter — forex/equity
                       candles from a plain market-data API, no
                       brokerage account or KYC required. The default
                       forex data source wired into web/scheduler.py
                       and run.py.
  data/kite.py        Implemented. Zerodha Kite Connect adapter: daily
                       login/session handling, historical candle fetch,
                       and live quote snapshots. Live tick streaming
                       (KiteTicker, WebSocket-based) is not implemented
                       yet — see the module docstring.
  data/base.py        `MarketDataProvider` — the shared structural
                       contract adapters converge on for
                       `fetch_candles(...) -> list[Candle]`, so
                       structure/ and agent/ never need to know which
                       provider produced the data. Signatures differ
                       slightly per provider (Kite needs exchange/
                       tradingsymbol/interval; Twelve Data uses
                       "EUR/USD"-style symbols vs. OANDA's "EUR_USD") —
                       see each adapter's module docstring.
  data/types.py       Provider-agnostic types shared across adapters
                       (`Quote`).

Every adapter here is fully separate with its own auth/session handling
— each is developable/testable without the others. All convert
provider-native responses into `ictagent.structure.types.Candle`, the
same type structure/ already consumes.

Credentials are read via ictagent.config.settings.load_settings() —
never hardcoded here.
"""

from .types import Quote
from .base import MarketDataProvider
from .oanda import OandaClient, OandaAuthError, OandaAPIError, OANDA_GRANULARITIES
from .twelvedata import TwelveDataClient, TwelveDataAuthError, TwelveDataAPIError
from .kite import KiteClient, KiteAuthError, KiteAPIError, KITE_INTERVALS

__all__ = [
    "Quote",
    "MarketDataProvider",
    "OandaClient",
    "OandaAuthError",
    "OandaAPIError",
    "OANDA_GRANULARITIES",
    "TwelveDataClient",
    "TwelveDataAuthError",
    "TwelveDataAPIError",
    "KiteClient",
    "KiteAuthError",
    "KiteAPIError",
    "KITE_INTERVALS",
]
