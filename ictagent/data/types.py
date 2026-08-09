"""Shared data-layer types, broker-agnostic — both the OANDA and (later)
Kite adapters convert their native responses into these."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Quote:
    """A live bid/ask snapshot for one instrument."""

    instrument: str
    time: datetime
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "time": self.time.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
        }
