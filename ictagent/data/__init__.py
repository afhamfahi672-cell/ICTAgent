"""
Market data ingestion — candles and live quotes.

  data/oanda.py   Implemented. OANDA v20 REST adapter (candles + live
                   pricing), talking to the REST API directly over
                   `requests` — see the module docstring for why.
  data/kite.py    Not implemented yet. Zerodha Kite Connect adapter:
                   auth/session handling, historical candle fetch, live
                   quote/tick subscription.
  data/base.py    `MarketDataProvider` — the shared structural contract
                   both adapters converge on (`fetch_candles(...) ->
                   list[Candle]`), so structure/ and agent/ never need
                   to know which broker produced the data.
  data/types.py   Broker-agnostic types shared across adapters (`Quote`).

Kite and OANDA are fully separate adapters with separate auth/session
handling — each is developable/testable without the other. Both convert
broker-native responses into `ictagent.structure.types.Candle`, the same
type structure/ already consumes.

Credentials are read via ictagent.config.settings.load_settings() —
never hardcoded here.
"""

from .types import Quote
from .base import MarketDataProvider
from .oanda import OandaClient, OandaAuthError, OandaAPIError, OANDA_GRANULARITIES

__all__ = [
    "Quote",
    "MarketDataProvider",
    "OandaClient",
    "OandaAuthError",
    "OandaAPIError",
    "OANDA_GRANULARITIES",
]
