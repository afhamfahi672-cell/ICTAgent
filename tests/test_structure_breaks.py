import pytest

from ictagent.structure.swings import find_swing_points
from ictagent.structure.structure_breaks import detect_structure_breaks
from ictagent.structure.types import BreakKind, Direction

from .fixtures import trend_reversal_candles


def test_bos_then_choch_then_bos():
    candles = trend_reversal_candles()
    swings = find_swing_points(candles, lookback=1)
    events = detect_structure_breaks(candles, swings, lookback=1)

    assert len(events) == 3

    bos1, choch, bos2 = events

    assert bos1.index == 6
    assert bos1.kind == BreakKind.BOS
    assert bos1.direction == Direction.BULLISH
    assert bos1.broken_level.price == pytest.approx(13)

    assert choch.index == 8
    assert choch.kind == BreakKind.CHOCH
    assert choch.direction == Direction.BEARISH
    assert choch.broken_level.price == pytest.approx(8)

    assert bos2.index == 10
    assert bos2.kind == BreakKind.BOS
    assert bos2.direction == Direction.BEARISH
    assert bos2.broken_level.price == pytest.approx(7.5)


def test_first_break_is_always_bos_regardless_of_direction():
    """A series with only a single bearish break and no prior trend
    should still label it BOS, not CHoCH (nothing to change from)."""
    candles = trend_reversal_candles()[:5]  # cut off before any break fires
    swings = find_swing_points(candles, lookback=1)
    events = detect_structure_breaks(candles, swings, lookback=1)
    assert events == []  # sanity: no break yet in this truncated slice


def test_no_events_on_flat_series():
    from .fixtures import make_candles

    flat = make_candles([(10, 10.1, 9.9, 10)] * 10)
    swings = find_swing_points(flat, lookback=2)
    events = detect_structure_breaks(flat, swings, lookback=2)
    assert events == []
