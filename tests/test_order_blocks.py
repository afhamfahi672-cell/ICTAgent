import pytest

from ictagent.structure.swings import find_swing_points
from ictagent.structure.structure_breaks import detect_structure_breaks
from ictagent.structure.order_blocks import find_order_blocks
from ictagent.structure.types import Direction

from .fixtures import trend_reversal_candles


def test_order_blocks_for_each_structure_event():
    candles = trend_reversal_candles()
    swings = find_swing_points(candles, lookback=1)
    events = detect_structure_breaks(candles, swings, lookback=1)
    obs = find_order_blocks(candles, events)

    assert len(obs) == 3
    ob_bull, ob_bear1, ob_bear2 = obs

    # BOS bullish @ idx6 -> last bearish candle walking back is idx4
    assert ob_bull.index == 4
    assert ob_bull.direction == Direction.BULLISH
    assert ob_bull.high == pytest.approx(9)
    assert ob_bull.low == pytest.approx(8)
    assert ob_bull.breaks_structure_at == 6

    # CHoCH bearish @ idx8 -> last bullish candle walking back is idx6
    assert ob_bear1.index == 6
    assert ob_bear1.direction == Direction.BEARISH
    assert ob_bear1.high == pytest.approx(14)
    assert ob_bear1.low == pytest.approx(9.5)
    assert ob_bear1.breaks_structure_at == 8

    # BOS bearish @ idx10 -> last bullish candle walking back is idx9
    assert ob_bear2.index == 9
    assert ob_bear2.direction == Direction.BEARISH
    assert ob_bear2.high == pytest.approx(10)
    assert ob_bear2.low == pytest.approx(9)
    assert ob_bear2.breaks_structure_at == 10


def test_order_block_mitigation_tracked():
    candles = trend_reversal_candles()
    swings = find_swing_points(candles, lookback=1)
    events = detect_structure_breaks(candles, swings, lookback=1)
    obs = find_order_blocks(candles, events)

    # The bullish OB (idx4, range [8,9]) breaks structure at idx6; idx8's
    # range [7.5,12] trades back through it -> mitigated at idx8.
    ob_bull = obs[0]
    assert ob_bull.mitigated_index == 8
    assert ob_bull.is_mitigated

    # The final bearish OB (idx9) breaks structure at idx10, the last
    # candle in the fixture -> no future data to mitigate it against.
    ob_bear2 = obs[2]
    assert ob_bear2.mitigated_index is None
    assert not ob_bear2.is_mitigated


def test_no_order_block_when_no_opposing_candle_in_history():
    from .fixtures import make_candles
    from ictagent.structure.types import StructureEvent, SwingPoint, SwingKind, BreakKind

    candles = make_candles([(11, 11, 9, 9.5)] * 3)  # all bearish (close<open)
    fake_level = SwingPoint(index=0, timestamp=candles[0].timestamp, price=9, kind=SwingKind.LOW)
    fake_event = StructureEvent(
        index=2,
        timestamp=candles[2].timestamp,
        kind=BreakKind.BOS,
        direction=Direction.BEARISH,  # needs a bullish (up-close) candle in history; none exists
        broken_level=fake_level,
        close_price=10.5,
    )
    assert find_order_blocks(candles, [fake_event]) == []
