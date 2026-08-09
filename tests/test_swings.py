import pytest

from ictagent.structure.swings import find_swing_points
from ictagent.structure.types import SwingKind

from .fixtures import zigzag_candles


def test_finds_single_swing_high_and_low():
    candles = zigzag_candles()
    points = find_swing_points(candles, lookback=2)

    highs = [p for p in points if p.kind == SwingKind.HIGH]
    lows = [p for p in points if p.kind == SwingKind.LOW]

    assert len(highs) == 1
    assert highs[0].index == 4
    assert highs[0].price == pytest.approx(14)

    assert len(lows) == 1
    assert lows[0].index == 9
    assert lows[0].price == pytest.approx(8)


def test_points_are_chronologically_ordered():
    candles = zigzag_candles()
    points = find_swing_points(candles, lookback=2)
    indices = [p.index for p in points]
    assert indices == sorted(indices)


def test_no_pivots_possible_when_series_shorter_than_window():
    candles = zigzag_candles()[:3]
    assert find_swing_points(candles, lookback=2) == []


def test_rejects_invalid_lookback():
    with pytest.raises(ValueError):
        find_swing_points(zigzag_candles(), lookback=0)
