"""
Equal highs / equal lows -> resting liquidity pools.

ICT premise: clusters of swing highs sitting at roughly the same price
represent sell-side stops resting above the market (a magnet for price to
run before reversing); clusters of swing lows at roughly the same price
represent buy-side stops resting below the market.

We cluster swing points of the same kind by price proximity: sort by
price, then greedily group consecutive points whose price is within
`tolerance_pct` of the running cluster reference price. Any cluster with
2+ points is reported as a liquidity pool. Points are *not* required to
be adjacent in time — a high from 40 candles ago and one from 3 candles
ago at the same price still form a valid liquidity pool.
"""

from __future__ import annotations

from .types import SwingPoint, SwingKind, LiquidityPool


def find_equal_highs_lows(
    swing_points: list[SwingPoint],
    tolerance_pct: float = 0.05,
) -> list[LiquidityPool]:
    """
    Args:
        swing_points: output of find_swing_points().
        tolerance_pct: max allowed deviation from the cluster's reference
            price, as a percentage (0.05 = 0.05%). Widen for noisier /
            lower-timeframe data, tighten for cleaner higher-timeframe data.
    """
    if tolerance_pct < 0:
        raise ValueError("tolerance_pct must be >= 0")

    pools: list[LiquidityPool] = []
    for kind in (SwingKind.HIGH, SwingKind.LOW):
        pts = sorted((p for p in swing_points if p.kind == kind), key=lambda p: p.price)
        pools.extend(_cluster(pts, kind, tolerance_pct))

    # Report in chronological order of the cluster's most recent point,
    # which is the natural reading order for "what liquidity is nearby".
    pools.sort(key=lambda pool: max(p.index for p in pool.points))
    return pools


def _cluster(
    sorted_points: list[SwingPoint], kind: SwingKind, tolerance_pct: float
) -> list[LiquidityPool]:
    pools: list[LiquidityPool] = []
    cluster: list[SwingPoint] = []

    for pt in sorted_points:
        if not cluster:
            cluster = [pt]
            continue

        ref_price = sum(p.price for p in cluster) / len(cluster)
        allowed = ref_price * (tolerance_pct / 100.0)
        if abs(pt.price - ref_price) <= allowed:
            cluster.append(pt)
        else:
            if len(cluster) >= 2:
                pools.append(_make_pool(cluster, kind))
            cluster = [pt]

    if len(cluster) >= 2:
        pools.append(_make_pool(cluster, kind))

    return pools


def _make_pool(cluster: list[SwingPoint], kind: SwingKind) -> LiquidityPool:
    ref_price = sum(p.price for p in cluster) / len(cluster)
    ordered = tuple(sorted(cluster, key=lambda p: p.index))
    return LiquidityPool(kind=kind, price=ref_price, points=ordered)
