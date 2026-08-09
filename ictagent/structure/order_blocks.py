"""
Order block identification.

Definition used here: for a given structural break (BOS or CHoCH), the
order block is the *last opposing candle* before the impulsive leg that
produced the break —

  - Bullish break -> walk backwards from the breaking candle to the most
    recent bearish (close < open) candle. That candle's high/low is the
    bullish order block.
  - Bearish break -> walk backwards to the most recent bullish
    (close > open) candle. That's the bearish order block.

This mirrors the standard ICT "last down-close candle before the up-move
that broke structure" definition. One order block is produced per
structure event; if no opposing candle is found scanning back to the
start of the series, that event is skipped (not enough history).

Mitigation tracking mirrors fvg.py: the first later candle whose range
trades back into the order block's [low, high] zone.
"""

from __future__ import annotations

from .types import Candle, StructureEvent, OrderBlock, Direction


def find_order_blocks(
    candles: list[Candle], structure_events: list[StructureEvent]
) -> list[OrderBlock]:
    blocks: list[OrderBlock] = []

    for event in structure_events:
        j = event.index
        k = j

        if event.direction == Direction.BULLISH:
            while k >= 0 and not candles[k].is_bearish():
                k -= 1
        else:
            while k >= 0 and not candles[k].is_bullish():
                k -= 1

        if k < 0:
            continue  # no opposing candle in available history

        ob_candle = candles[k]
        ob = OrderBlock(
            index=k,
            timestamp=ob_candle.timestamp,
            direction=event.direction,
            high=ob_candle.high,
            low=ob_candle.low,
            breaks_structure_at=j,
        )
        blocks.append(_with_mitigation(ob, candles, j + 1))

    return blocks


def _with_mitigation(ob: OrderBlock, candles: list[Candle], start_index: int) -> OrderBlock:
    for m in range(start_index, len(candles)):
        c = candles[m]
        if c.low <= ob.high and c.high >= ob.low:
            return OrderBlock(
                index=ob.index,
                timestamp=ob.timestamp,
                direction=ob.direction,
                high=ob.high,
                low=ob.low,
                breaks_structure_at=ob.breaks_structure_at,
                mitigated_index=m,
            )
    return ob
