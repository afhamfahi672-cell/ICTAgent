"""
Fibonacci retracement and Optimal Trade Entry (OTE) zone calculation.

OTE, in ICT terms, is the discount (for longs) or premium (for shorts)
zone of a recently broken impulse leg where price is favoured to react
from on its retracement — conventionally the 0.62-0.79 retracement band
(0.705/0.79 "deep OTE" variants exist; 0.62-0.79 is used as the default
here and is fully configurable).

`fibonacci_retracement` is a generic, direction-agnostic interpolator so
it can be reused for any leg, not just OTE. `ote_zone` wraps it for the
specific bullish/bearish OTE case. `find_ote_zones` derives legs
automatically from swing points + structure events, for the common case
of "give me the current OTE zone(s) implied by recent structure".
"""

from __future__ import annotations

from typing import Iterable

from .types import (
    Candle,
    SwingPoint,
    SwingKind,
    StructureEvent,
    OTEZone,
    Direction,
)

DEFAULT_OTE_MIN = 0.62
DEFAULT_OTE_MAX = 0.79


def fibonacci_retracement(
    leg_start: float, leg_end: float, ratios: Iterable[float]
) -> dict[float, float]:
    """Price at each retracement ratio for a leg from leg_start -> leg_end.

    ratio=0.0 -> leg_end, ratio=1.0 -> leg_start (standard convention:
    0% retracement is the most recent extreme, 100% is a full round trip
    back to where the leg began).
    """
    return {r: leg_end + (leg_start - leg_end) * r for r in ratios}


def ote_zone(
    leg_start: SwingPoint,
    leg_end: SwingPoint,
    direction: Direction,
    ote_min: float = DEFAULT_OTE_MIN,
    ote_max: float = DEFAULT_OTE_MAX,
) -> OTEZone:
    """OTE zone for one impulse leg (leg_start -> leg_end price-wise).

    Bullish: leg_start is the swing low the leg began at, leg_end is the
    swing high it reached; the zone sits below leg_end (a discount to buy
    into). Bearish is the mirror image.
    """
    levels = fibonacci_retracement(leg_start.price, leg_end.price, (ote_min, ote_max))
    prices = list(levels.values())
    return OTEZone(
        direction=direction,
        leg_start=leg_start,
        leg_end=leg_end,
        zone_high=max(prices),
        zone_low=min(prices),
        ote_min=ote_min,
        ote_max=ote_max,
    )


def find_ote_zones(
    candles: list[Candle],
    swing_points: list[SwingPoint],
    structure_events: list[StructureEvent],
    ote_min: float = DEFAULT_OTE_MIN,
    ote_max: float = DEFAULT_OTE_MAX,
) -> list[OTEZone]:
    """Derive one OTE zone per structure event, using the swing point of
    the opposite kind immediately preceding the break as the leg's origin
    and the extreme price reached by the impulse (up to and including the
    breaking candle) as the leg's terminus.

    Events with no prior opposite-kind swing in history are skipped (not
    enough context to define a leg).
    """
    zones: list[OTEZone] = []
    lows = sorted((p for p in swing_points if p.kind == SwingKind.LOW), key=lambda p: p.index)
    highs = sorted((p for p in swing_points if p.kind == SwingKind.HIGH), key=lambda p: p.index)

    for event in structure_events:
        if event.direction == Direction.BULLISH:
            origin = _last_before(lows, event.index)
            if origin is None:
                continue
            extreme_idx, extreme_price = _extreme(candles, origin.index, event.index, high=True)
            leg_end = SwingPoint(
                index=extreme_idx,
                timestamp=candles[extreme_idx].timestamp,
                price=extreme_price,
                kind=SwingKind.HIGH,
            )
            zones.append(ote_zone(origin, leg_end, Direction.BULLISH, ote_min, ote_max))
        else:
            origin = _last_before(highs, event.index)
            if origin is None:
                continue
            extreme_idx, extreme_price = _extreme(candles, origin.index, event.index, high=False)
            leg_end = SwingPoint(
                index=extreme_idx,
                timestamp=candles[extreme_idx].timestamp,
                price=extreme_price,
                kind=SwingKind.LOW,
            )
            zones.append(ote_zone(origin, leg_end, Direction.BEARISH, ote_min, ote_max))

    return zones


def _last_before(points: list[SwingPoint], index: int) -> SwingPoint | None:
    candidate = None
    for p in points:
        if p.index >= index:
            break
        candidate = p
    return candidate


def _extreme(candles: list[Candle], start_index: int, end_index: int, high: bool) -> tuple[int, float]:
    segment = candles[start_index : end_index + 1]
    if high:
        c = max(segment, key=lambda c: c.high)
        return start_index + segment.index(c), c.high
    c = min(segment, key=lambda c: c.low)
    return start_index + segment.index(c), c.low
