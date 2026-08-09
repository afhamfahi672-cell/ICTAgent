"""
Fair Value Gap (FVG) detection — classic 3-candle imbalance.

For three consecutive candles (c1, c2, c3):
  - Bullish FVG: c3.low > c1.high. The impulse candle c2 left a gap
    between c1's high and c3's low that price never traded through.
    Zone = [c1.high, c3.low].
  - Bearish FVG: c3.high < c1.low. Zone = [c3.high, c1.low].

c2 (the middle, impulsive candle) is the index a gap is anchored to.

Mitigation: once formed, we scan forward for the first later candle
whose range trades back into the zone (a touch, not necessarily a full
fill) and record that as `mitigated_index`. Still-open gaps have
`mitigated_index=None`.
"""

from __future__ import annotations

from .types import Candle, FairValueGap, Direction


def find_fair_value_gaps(candles: list[Candle]) -> list[FairValueGap]:
    gaps: list[FairValueGap] = []

    for i in range(1, len(candles) - 1):
        c1, c2, c3 = candles[i - 1], candles[i], candles[i + 1]

        if c3.low > c1.high:
            gap = FairValueGap(
                index=i,
                timestamp=c2.timestamp,
                direction=Direction.BULLISH,
                top=c3.low,
                bottom=c1.high,
            )
            gaps.append(_with_mitigation(gap, candles, i + 2))
        elif c3.high < c1.low:
            gap = FairValueGap(
                index=i,
                timestamp=c2.timestamp,
                direction=Direction.BEARISH,
                top=c1.low,
                bottom=c3.high,
            )
            gaps.append(_with_mitigation(gap, candles, i + 2))

    return gaps


def _with_mitigation(
    gap: FairValueGap, candles: list[Candle], start_index: int
) -> FairValueGap:
    for k in range(start_index, len(candles)):
        c = candles[k]
        # Any overlap between the candle's range and the gap zone counts
        # as a touch/mitigation.
        if c.low <= gap.top and c.high >= gap.bottom:
            return FairValueGap(
                index=gap.index,
                timestamp=gap.timestamp,
                direction=gap.direction,
                top=gap.top,
                bottom=gap.bottom,
                mitigated_index=k,
            )
    return gap
