"""
Phase-aware dispatcher: routes a Decision to a log-only simulated fill,
a propose-and-confirm flow, or (once it exists) a real broker call —
never straight to a broker.

  paper       -> PaperBroker simulates the fill in memory. No network call.
  semi_auto   -> returns "pending_confirmation" and stops. No broker call
                 is made here; a human confirming the trade and the actual
                 order placement are still to be built.
  autonomous  -> requires Settings.require_live_trading_enabled() to pass
                 (both ICTAGENT_PHASE and ICTAGENT_LIVE_TRADING_CONFIRM
                 correctly set — see config/settings.py), and even then
                 raises NotImplementedError: execution/kite.py and
                 execution/oanda.py order-placement code doesn't exist
                 yet. Reaching that line means the phase gate passed, but
                 there is still no code path anywhere in this repo that
                 can place a real order.

HOLD/NO_TRADE decisions short-circuit before any phase check — there is
nothing to execute regardless of phase.
"""

from __future__ import annotations

from typing import Optional

from ictagent.agent.types import Action, Decision
from ictagent.config.settings import Phase, Settings, load_settings

from .simulator import PaperBroker
from .types import ExecutionResult


class ExecutionGate:
    def __init__(self, settings: Optional[Settings] = None, broker: Optional[PaperBroker] = None):
        self._settings = settings or load_settings()
        self._broker = broker or PaperBroker()

    @property
    def broker(self) -> PaperBroker:
        return self._broker

    def handle(self, decision: Decision, size: float = 1.0, price: Optional[float] = None) -> ExecutionResult:
        if decision.action in (Action.HOLD, Action.NO_TRADE):
            return ExecutionResult(
                status="no_action", decision=decision, fill=None, message="No action decision; nothing to execute."
            )

        if self._settings.is_paper:
            return self._broker.handle_decision(decision, size=size, price=price)

        if self._settings.phase == Phase.SEMI_AUTO:
            return ExecutionResult(
                status="pending_confirmation",
                decision=decision,
                fill=None,
                message=(
                    "Semi-auto phase: awaiting human confirmation before any order "
                    "is placed. No broker call has been made."
                ),
            )

        # Phase.AUTONOMOUS
        self._settings.require_live_trading_enabled()  # raises PermissionError if not both flags set
        raise NotImplementedError(
            "Live order placement is not implemented yet (execution/kite.py and "
            "execution/oanda.py order-placement code doesn't exist). The phase gate "
            "passed, but there is still no code path that can place a real order."
        )
