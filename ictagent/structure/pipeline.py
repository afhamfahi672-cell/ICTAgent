"""
Orchestrates the deterministic structure computation: swings -> BOS/CHoCH
-> liquidity pools -> FVGs -> order blocks -> OTE zones.

This is the single entry point the rest of the app (context/, agent/)
should call. Everything below it is independently unit-testable and has
zero broker or LLM dependency; `compute_structure` just wires it up.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import Candle, StructureState
from .swings import find_swing_points
from .structure_breaks import detect_structure_breaks
from .liquidity import find_equal_highs_lows
from .fvg import find_fair_value_gaps
from .order_blocks import find_order_blocks
from .ote import find_ote_zones, DEFAULT_OTE_MIN, DEFAULT_OTE_MAX


@dataclass
class StructureConfig:
    swing_lookback: int = 2
    liquidity_tolerance_pct: float = 0.05
    ote_min: float = DEFAULT_OTE_MIN
    ote_max: float = DEFAULT_OTE_MAX


def compute_structure(
    candles: list[Candle], config: StructureConfig | None = None
) -> StructureState:
    cfg = config or StructureConfig()

    swing_points = find_swing_points(candles, lookback=cfg.swing_lookback)
    structure_events = detect_structure_breaks(
        candles, swing_points, lookback=cfg.swing_lookback
    )
    liquidity_pools = find_equal_highs_lows(
        swing_points, tolerance_pct=cfg.liquidity_tolerance_pct
    )
    fair_value_gaps = find_fair_value_gaps(candles)
    order_blocks = find_order_blocks(candles, structure_events)
    ote_zones = find_ote_zones(
        candles, swing_points, structure_events, ote_min=cfg.ote_min, ote_max=cfg.ote_max
    )

    return StructureState(
        swing_points=swing_points,
        structure_events=structure_events,
        liquidity_pools=liquidity_pools,
        fair_value_gaps=fair_value_gaps,
        order_blocks=order_blocks,
        ote_zones=ote_zones,
    )
