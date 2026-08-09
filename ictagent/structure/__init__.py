"""
Deterministic market structure computation.

Pure Python, no broker/LLM dependency, fully unit-testable against
synthetic or historical OHLCV data. The agent/ module reasons *over* the
output of this package (StructureState) — it never computes structure
itself.
"""

from .types import (
    Candle,
    Direction,
    SwingKind,
    BreakKind,
    SwingPoint,
    StructureEvent,
    LiquidityPool,
    FairValueGap,
    OrderBlock,
    OTEZone,
    StructureState,
)
from .swings import find_swing_points
from .structure_breaks import detect_structure_breaks
from .liquidity import find_equal_highs_lows
from .fvg import find_fair_value_gaps
from .order_blocks import find_order_blocks
from .ote import fibonacci_retracement, ote_zone, find_ote_zones
from .pipeline import compute_structure, StructureConfig

__all__ = [
    "Candle",
    "Direction",
    "SwingKind",
    "BreakKind",
    "SwingPoint",
    "StructureEvent",
    "LiquidityPool",
    "FairValueGap",
    "OrderBlock",
    "OTEZone",
    "StructureState",
    "find_swing_points",
    "detect_structure_breaks",
    "find_equal_highs_lows",
    "find_fair_value_gaps",
    "find_order_blocks",
    "fibonacci_retracement",
    "ote_zone",
    "find_ote_zones",
    "compute_structure",
    "StructureConfig",
]
