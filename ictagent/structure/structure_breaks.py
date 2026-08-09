"""
Break of Structure (BOS) and Change of Character (CHoCH) detection.

Definitions used here (standard ICT usage):
  - BOS   (Break of Structure): a close beyond the most recent relevant
    swing point *in the direction of the current trend* -> continuation.
  - CHoCH (Change of Character): a close beyond the most recent relevant
    swing point *against* the current trend -> the trend flips.

The very first break in either direction (no trend established yet) is
labelled BOS, since there is no prior trend to change.

Detection walks candles in order, tracking the latest *confirmed* swing
high/low that hasn't yet been broken. A swing at index i is only
eligible to be used once `i + lookback <= current index`, matching the
confirmation lag from swings.py (a pivot needs `lookback` future candles
before we could have known about it in real time).

We test with candle *close* crossing the swing level, not the wick, to
avoid firing on every intra-range wick poke — this is the common,
conservative convention for structure-break confirmation.
"""

from __future__ import annotations

from .types import Candle, SwingPoint, SwingKind, StructureEvent, BreakKind, Direction


def detect_structure_breaks(
    candles: list[Candle],
    swing_points: list[SwingPoint],
    lookback: int = 2,
) -> list[StructureEvent]:
    swing_highs = sorted(
        (p for p in swing_points if p.kind == SwingKind.HIGH), key=lambda p: p.index
    )
    swing_lows = sorted(
        (p for p in swing_points if p.kind == SwingKind.LOW), key=lambda p: p.index
    )

    events: list[StructureEvent] = []
    trend: Direction | None = None

    pending_high: SwingPoint | None = None
    pending_low: SwingPoint | None = None
    hi_ptr = 0
    lo_ptr = 0

    for j, candle in enumerate(candles):
        # Bring in any swings that are confirmed as of this candle.
        while hi_ptr < len(swing_highs) and swing_highs[hi_ptr].index + lookback <= j:
            pending_high = swing_highs[hi_ptr]
            hi_ptr += 1
        while lo_ptr < len(swing_lows) and swing_lows[lo_ptr].index + lookback <= j:
            pending_low = swing_lows[lo_ptr]
            lo_ptr += 1

        if pending_high is not None and candle.close > pending_high.price:
            kind = BreakKind.BOS if trend in (None, Direction.BULLISH) else BreakKind.CHOCH
            events.append(
                StructureEvent(
                    index=j,
                    timestamp=candle.timestamp,
                    kind=kind,
                    direction=Direction.BULLISH,
                    broken_level=pending_high,
                    close_price=candle.close,
                )
            )
            trend = Direction.BULLISH
            pending_high = None  # consumed; need a new confirmed high to break next

        if pending_low is not None and candle.close < pending_low.price:
            kind = BreakKind.BOS if trend in (None, Direction.BEARISH) else BreakKind.CHOCH
            events.append(
                StructureEvent(
                    index=j,
                    timestamp=candle.timestamp,
                    kind=kind,
                    direction=Direction.BEARISH,
                    broken_level=pending_low,
                    close_price=candle.close,
                )
            )
            trend = Direction.BEARISH
            pending_low = None

    return events
