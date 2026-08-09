"""Synthetic OHLCV fixtures shared across structure/ unit tests.

Everything here is a hand-traced synthetic series — no live/historical
data dependency — so expected outputs can be worked out by hand and
asserted exactly.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ictagent.structure.types import Candle

_START = datetime(2024, 1, 1, 9, 15)


def make_candles(rows: list[tuple[float, float, float, float]]) -> list[Candle]:
    """rows: list of (open, high, low, close), one per minute starting
    at an arbitrary fixed timestamp."""
    return [
        Candle(
            timestamp=_START + timedelta(minutes=i),
            open=o,
            high=h,
            low=l,
            close=c,
            volume=1000,
        )
        for i, (o, h, l, c) in enumerate(rows)
    ]


def zigzag_candles() -> list[Candle]:
    """15 bars: a clean up-down-up cycle with exactly one swing high
    (index 4, price 14) and one swing low (index 9, price 8) at
    lookback=2. Open/close are irrelevant here (not bullish/bearish
    balanced on purpose) — only high/low matter for swing detection."""
    highs_lows = [
        (10, 9), (11, 10), (12, 11), (13, 12), (14, 13),
        (13, 12), (12, 11), (11, 10), (10, 9), (9, 8),
        (10, 9), (11, 10), (12, 11), (13, 12), (14, 13),
    ]
    rows = [(l + 0.3, h, l, l + 0.6) for h, l in highs_lows]
    return make_candles(rows)


def trend_reversal_candles() -> list[Candle]:
    """11 bars (lookback=1), hand-traced to produce, in order:
      - index 6: BOS bullish, breaking the index-3 swing high (13)
      - index 8: CHoCH bearish, breaking the index-4 swing low (8)
      - index 10: BOS bearish, breaking the index-8 swing low (7.5)

    Swing points at lookback=1: highs at idx3 (13) and idx6 (14);
    lows at idx1 (7), idx4 (8), idx8 (7.5).

    Opens are chosen deliberately (not just interpolated) so
    is_bullish()/is_bearish() give a specific, hand-verified order-block
    walk-back result — see tests/test_order_blocks.py and
    tests/test_ote.py, which reuse this exact fixture.
    """
    # (open, high, low, close)
    rows = [
        (9.6, 10, 9, 9.5),      # 0
        (7.3, 8, 7, 7.5),       # 1  swing low (7)
        (9.7, 11, 9, 9.5),      # 2
        (10.3, 13, 10, 12.5),   # 3  swing high (13)
        (8.9, 9, 8, 8.5),       # 4  swing low (8), bearish candle
        (8.7, 10, 8.5, 9.7),    # 5
        (9.8, 14, 9.5, 13.8),   # 6  swing high (14); breakout candle -> BOS bullish
        (13.3, 13.5, 12, 12.5), # 7
        (11.8, 12, 7.5, 7.8),   # 8  swing low (7.5); breaks idx4 low -> CHoCH bearish
        (9.1, 10, 9, 9.3),      # 9
        (8.8, 9, 6, 6.5),       # 10 breaks idx8 low -> BOS bearish
    ]
    return make_candles(rows)
