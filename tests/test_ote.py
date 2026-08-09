import pytest

from ictagent.structure.swings import find_swing_points
from ictagent.structure.structure_breaks import detect_structure_breaks
from ictagent.structure.ote import fibonacci_retracement, ote_zone, find_ote_zones
from ictagent.structure.types import SwingPoint, SwingKind, Direction

from .fixtures import trend_reversal_candles


def test_fibonacci_retracement_basic_interpolation():
    levels = fibonacci_retracement(leg_start=100, leg_end=200, ratios=[0, 0.5, 1])
    assert levels[0] == pytest.approx(200)
    assert levels[0.5] == pytest.approx(150)
    assert levels[1] == pytest.approx(100)


def test_ote_zone_bullish_sits_below_leg_end():
    start = SwingPoint(index=0, timestamp=None, price=100, kind=SwingKind.LOW)
    end = SwingPoint(index=10, timestamp=None, price=200, kind=SwingKind.HIGH)

    zone = ote_zone(start, end, Direction.BULLISH, ote_min=0.62, ote_max=0.79)

    assert zone.zone_high == pytest.approx(138)  # 200 - 100*0.62
    assert zone.zone_low == pytest.approx(121)   # 200 - 100*0.79
    assert zone.contains(130)
    assert not zone.contains(150)


def test_find_ote_zones_derives_legs_from_structure():
    candles = trend_reversal_candles()
    swings = find_swing_points(candles, lookback=1)
    events = detect_structure_breaks(candles, swings, lookback=1)
    zones = find_ote_zones(candles, swings, events, ote_min=0.62, ote_max=0.79)

    assert len(zones) == 3
    z_bull, z_bear1, z_bear2 = zones

    assert z_bull.direction == Direction.BULLISH
    assert z_bull.leg_start.price == pytest.approx(8)
    assert z_bull.leg_end.price == pytest.approx(14)
    assert z_bull.zone_high == pytest.approx(10.28)
    assert z_bull.zone_low == pytest.approx(9.26)

    assert z_bear1.direction == Direction.BEARISH
    assert z_bear1.leg_start.price == pytest.approx(14)
    assert z_bear1.leg_end.price == pytest.approx(7.5)
    assert z_bear1.zone_low == pytest.approx(11.53)
    assert z_bear1.zone_high == pytest.approx(12.635)

    assert z_bear2.direction == Direction.BEARISH
    assert z_bear2.leg_start.price == pytest.approx(14)
    assert z_bear2.leg_end.price == pytest.approx(6)
    assert z_bear2.zone_low == pytest.approx(10.96)
    assert z_bear2.zone_high == pytest.approx(12.32)
