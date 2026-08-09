"""
Pivot-based swing high/low detection.

A candle at index i is a swing high if its high is strictly greater than
the highs of `lookback` candles on both sides. Swing low is the mirror
image on lows. This is the standard fractal/pivot definition used
throughout ICT structure mapping — everything downstream (BOS/CHoCH,
liquidity pools, OTE legs) is built on top of these points.

Note the pivot requires `lookback` candles *after* it to confirm, so a
swing at index i is only "known" once candle i + lookback has closed.
Callers that need this (structure_breaks.py) account for that lag
explicitly rather than assuming a swing is knowable at its own index.
"""

from __future__ import annotations

from .types import Candle, SwingPoint, SwingKind


def find_swing_points(candles: list[Candle], lookback: int = 2) -> list[SwingPoint]:
    """Return swing highs and lows, in chronological (index) order.

    Args:
        candles: chronologically ordered OHLCV bars.
        lookback: number of candles required on each side to confirm a
            pivot. Higher = fewer, more significant swings.
    """
    if lookback < 1:
        raise ValueError("lookback must be >= 1")

    n = len(candles)
    points: list[SwingPoint] = []

    for i in range(lookback, n - lookback):
        window = candles[i - lookback : i + lookback + 1]
        pivot = candles[i]

        if all(pivot.high > c.high for c in window if c is not pivot):
            points.append(
                SwingPoint(
                    index=i,
                    timestamp=pivot.timestamp,
                    price=pivot.high,
                    kind=SwingKind.HIGH,
                )
            )
        elif all(pivot.low < c.low for c in window if c is not pivot):
            points.append(
                SwingPoint(
                    index=i,
                    timestamp=pivot.timestamp,
                    price=pivot.low,
                    kind=SwingKind.LOW,
                )
            )

    return points
