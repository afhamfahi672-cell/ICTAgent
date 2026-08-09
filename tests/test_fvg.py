import pytest

from ictagent.structure.fvg import find_fair_value_gaps
from ictagent.structure.types import Direction

from .fixtures import make_candles


def _fvg_candles():
    # idx: (open, high, low, close)
    return make_candles(
        [
            (10, 11, 9, 10),      # 0  c1 of bullish gap (high=11)
            (12, 16, 12, 15),     # 1  impulse candle
            (14, 15, 13, 14.5),   # 2  c3 of bullish gap (low=13) -> gap [11,13]
            (14, 14.5, 12, 13),   # 3  later candle: dips back into [11,13] -> mitigates gap
            (13, 13.5, 12.5, 13), # 4  c1 of bearish gap (low=12.5)
            (12, 12, 8, 8.5),     # 5  impulse candle down
            (10.8, 11, 10.5, 10.6),  # 6  c3 of bearish gap (high=11) -> gap [11,12.5], never mitigated
        ]
    )


def test_finds_bullish_and_bearish_gaps():
    candles = _fvg_candles()
    gaps = find_fair_value_gaps(candles)

    assert len(gaps) == 2
    bullish, bearish = gaps

    assert bullish.index == 1
    assert bullish.direction == Direction.BULLISH
    assert bullish.top == pytest.approx(13)
    assert bullish.bottom == pytest.approx(11)
    assert bullish.mitigated_index == 3
    assert bullish.is_mitigated

    assert bearish.index == 5
    assert bearish.direction == Direction.BEARISH
    assert bearish.top == pytest.approx(12.5)
    assert bearish.bottom == pytest.approx(11)
    assert bearish.mitigated_index is None
    assert not bearish.is_mitigated


def test_no_gaps_on_overlapping_candles():
    candles = make_candles([(10, 11, 9, 10)] * 6)
    assert find_fair_value_gaps(candles) == []
