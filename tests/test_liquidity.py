from datetime import datetime, timedelta

import pytest

from ictagent.structure.liquidity import find_equal_highs_lows
from ictagent.structure.types import SwingPoint, SwingKind

_T0 = datetime(2024, 1, 1)


def _pt(index, price, kind):
    return SwingPoint(index=index, timestamp=_T0 + timedelta(minutes=index), price=price, kind=kind)


def test_clusters_equal_highs_and_lows_within_tolerance():
    points = [
        _pt(0, 100.0, SwingKind.HIGH),
        _pt(5, 100.03, SwingKind.HIGH),   # within 0.05% of 100 -> clusters
        _pt(10, 105.0, SwingKind.HIGH),   # far away -> lone point, no pool
        _pt(3, 50.0, SwingKind.LOW),
        _pt(8, 50.02, SwingKind.LOW),     # within 0.05% of 50 -> clusters
        _pt(12, 60.0, SwingKind.LOW),     # lone point, no pool
    ]

    pools = find_equal_highs_lows(points, tolerance_pct=0.05)

    assert len(pools) == 2

    high_pool = next(p for p in pools if p.kind == SwingKind.HIGH)
    assert len(high_pool.points) == 2
    assert {pt.index for pt in high_pool.points} == {0, 5}
    assert high_pool.price == pytest.approx(100.015)

    low_pool = next(p for p in pools if p.kind == SwingKind.LOW)
    assert len(low_pool.points) == 2
    assert {pt.index for pt in low_pool.points} == {3, 8}
    assert low_pool.price == pytest.approx(50.01)


def test_lone_swing_points_do_not_form_a_pool():
    points = [_pt(0, 100.0, SwingKind.HIGH), _pt(5, 200.0, SwingKind.HIGH)]
    assert find_equal_highs_lows(points, tolerance_pct=0.05) == []


def test_pool_can_span_more_than_two_points():
    points = [
        _pt(0, 100.0, SwingKind.HIGH),
        _pt(4, 100.02, SwingKind.HIGH),
        _pt(8, 99.98, SwingKind.HIGH),
    ]
    pools = find_equal_highs_lows(points, tolerance_pct=0.05)
    assert len(pools) == 1
    assert len(pools[0].points) == 3


def test_rejects_negative_tolerance():
    with pytest.raises(ValueError):
        find_equal_highs_lows([], tolerance_pct=-1)
