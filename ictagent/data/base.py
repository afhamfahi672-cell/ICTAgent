"""Broker-agnostic contract that data adapters conform to.

This is intentionally a `Protocol` (structural typing), not an ABC to
subclass — Kite and OANDA have different native concepts (Kite instrument
tokens + intervals vs. OANDA instrument names + granularities) and each
adapter's constructor/auth handling is necessarily broker-specific.
What must line up is the shape of the *output*: `list[Candle]` from
`ictagent.structure.types`, so `structure/` and `agent/` never need a
broker-specific code path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

from ictagent.structure.types import Candle


@runtime_checkable
class MarketDataProvider(Protocol):
    def fetch_candles(
        self,
        instrument: str,
        granularity: str,
        count: int = 500,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[Candle]:
        """Return chronologically ordered, completed candles only."""
        ...
