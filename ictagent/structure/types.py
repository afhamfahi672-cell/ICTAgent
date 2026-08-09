"""
Shared data types for the structure/ module.

Everything here is a plain, JSON-serializable dataclass. There is no
broker or LLM dependency in this file — the rest of ictagent (data/,
context/, agent/) consumes these types, this module doesn't know they
exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class SwingKind(str, Enum):
    HIGH = "high"
    LOW = "low"


class BreakKind(str, Enum):
    BOS = "BOS"      # break of structure: continuation of current trend
    CHOCH = "CHoCH"  # change of character: reversal of current trend


@dataclass(frozen=True)
class Candle:
    """One OHLCV bar. `timestamp` is left as `Any` so callers can pass
    whatever they already have (pandas Timestamp, datetime, epoch int,
    plain string) without this module forcing a conversion."""

    timestamp: Any
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def is_bullish(self) -> bool:
        return self.close > self.open

    def is_bearish(self) -> bool:
        return self.close < self.open

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = str(self.timestamp)
        return d


@dataclass(frozen=True)
class SwingPoint:
    index: int
    timestamp: Any
    price: float
    kind: SwingKind

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": str(self.timestamp),
            "price": self.price,
            "kind": self.kind.value,
        }


@dataclass(frozen=True)
class StructureEvent:
    """A BOS or CHoCH: candle `index` closed beyond `broken_level`."""

    index: int
    timestamp: Any
    kind: BreakKind
    direction: Direction
    broken_level: SwingPoint
    close_price: float

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": str(self.timestamp),
            "kind": self.kind.value,
            "direction": self.direction.value,
            "broken_level": self.broken_level.to_dict(),
            "close_price": self.close_price,
        }


@dataclass(frozen=True)
class LiquidityPool:
    """A cluster of ~equal swing highs (sell-side liquidity resting above
    price) or ~equal swing lows (buy-side liquidity resting below price)."""

    kind: SwingKind
    price: float  # reference level (mean of the cluster)
    points: tuple[SwingPoint, ...]

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "price": self.price,
            "points": [p.to_dict() for p in self.points],
        }


@dataclass(frozen=True)
class FairValueGap:
    """A 3-candle imbalance. `top`/`bottom` bound the unfilled gap zone.
    `mitigated_index` is the first later candle index whose range traded
    back into the zone, or None if still open as of the last candle."""

    index: int  # index of the middle (impulse) candle
    timestamp: Any
    direction: Direction
    top: float
    bottom: float
    mitigated_index: Optional[int] = None

    @property
    def is_mitigated(self) -> bool:
        return self.mitigated_index is not None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": str(self.timestamp),
            "direction": self.direction.value,
            "top": self.top,
            "bottom": self.bottom,
            "mitigated_index": self.mitigated_index,
            "is_mitigated": self.is_mitigated,
        }


@dataclass(frozen=True)
class OrderBlock:
    """The last opposing candle before the impulsive leg that produced a
    structural break. `breaks_structure_at` points at the StructureEvent
    index this order block is attributed to."""

    index: int
    timestamp: Any
    direction: Direction
    high: float
    low: float
    breaks_structure_at: int
    mitigated_index: Optional[int] = None

    @property
    def is_mitigated(self) -> bool:
        return self.mitigated_index is not None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": str(self.timestamp),
            "direction": self.direction.value,
            "high": self.high,
            "low": self.low,
            "breaks_structure_at": self.breaks_structure_at,
            "mitigated_index": self.mitigated_index,
            "is_mitigated": self.is_mitigated,
        }


@dataclass(frozen=True)
class OTEZone:
    """Optimal Trade Entry: the discount/premium retracement zone of an
    impulse leg, bounded by ote_max..ote_min fib ratios (default 0.62-0.79)
    measured from `leg_end` back towards `leg_start`."""

    direction: Direction
    leg_start: SwingPoint
    leg_end: SwingPoint
    zone_high: float
    zone_low: float
    ote_min: float
    ote_max: float

    def contains(self, price: float) -> bool:
        return self.zone_low <= price <= self.zone_high

    def to_dict(self) -> dict:
        return {
            "direction": self.direction.value,
            "leg_start": self.leg_start.to_dict(),
            "leg_end": self.leg_end.to_dict(),
            "zone_high": self.zone_high,
            "zone_low": self.zone_low,
            "ote_min": self.ote_min,
            "ote_max": self.ote_max,
        }


@dataclass
class StructureState:
    """Aggregate output of the full structure/ pipeline for one instrument
    + timeframe, as of the last candle supplied. This is what gets handed
    to context/ and agent/ downstream."""

    swing_points: list[SwingPoint] = field(default_factory=list)
    structure_events: list[StructureEvent] = field(default_factory=list)
    liquidity_pools: list[LiquidityPool] = field(default_factory=list)
    fair_value_gaps: list[FairValueGap] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)
    ote_zones: list[OTEZone] = field(default_factory=list)

    @property
    def trend(self) -> Optional[Direction]:
        """Current trend implied by the most recent structure event, if any."""
        if not self.structure_events:
            return None
        return self.structure_events[-1].direction

    def to_dict(self) -> dict:
        return {
            "trend": self.trend.value if self.trend else None,
            "swing_points": [p.to_dict() for p in self.swing_points],
            "structure_events": [e.to_dict() for e in self.structure_events],
            "liquidity_pools": [p.to_dict() for p in self.liquidity_pools],
            "fair_value_gaps": [g.to_dict() for g in self.fair_value_gaps],
            "order_blocks": [b.to_dict() for b in self.order_blocks],
            "ote_zones": [z.to_dict() for z in self.ote_zones],
        }
