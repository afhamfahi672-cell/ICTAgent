"""
Order placement, gated by the current phase.

  execution/simulator.py   Implemented. PaperBroker — simulates ENTER/
                            EXIT fills in memory, tracks open positions
                            and P&L. No broker API is ever touched.
  execution/gate.py        Implemented. ExecutionGate — routes a
                            Decision to PaperBroker (paper phase),
                            a pending-confirmation result (semi_auto,
                            no broker call), or a hard-gated
                            NotImplementedError (autonomous — see below).
  execution/kite.py        Not implemented yet. Real Kite Connect order
                            placement.
  execution/oanda.py       Not implemented yet. Real OANDA order
                            placement.

Hard rule, still true: nothing in this package can call a live broker
order endpoint. Reaching the autonomous branch of ExecutionGate requires
`ictagent.config.settings.Settings.require_live_trading_enabled()` to
pass (both `ICTAGENT_PHASE` and `ICTAGENT_LIVE_TRADING_CONFIRM` correctly
set), and even then it raises `NotImplementedError` — the real
order-placement modules (execution/kite.py, execution/oanda.py) don't
exist yet. There is no code path anywhere in this repo that can place a
live order.
"""

from .types import Position, ClosedPosition, ExecutionResult
from .simulator import PaperBroker
from .gate import ExecutionGate

__all__ = [
    "Position",
    "ClosedPosition",
    "ExecutionResult",
    "PaperBroker",
    "ExecutionGate",
]
