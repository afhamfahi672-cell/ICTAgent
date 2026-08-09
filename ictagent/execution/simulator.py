"""
Paper broker — simulates fills in memory. No broker API is ever touched
by this module; it exists so Phase 1 ("paper trading / simulation only")
has somewhere real to route ENTER/EXIT decisions to instead of a no-op.

Position sizing and execution-price sourcing are deliberately simple for
now (fixed unit size unless the caller passes one; the Decision's own
`entry` field is used as both the simulated entry and, for EXIT, the
simulated exit price unless a live/historical `price` is supplied) — this
is a starting point to refine once Phase 1 review is underway, not a
claim that it models real fills accurately.
"""

from __future__ import annotations

from typing import Optional

from ictagent.agent.types import Action, Decision

from .types import ClosedPosition, ExecutionResult, Position


class PaperBroker:
    def __init__(self):
        self._positions: dict[str, Position] = {}

    @property
    def positions(self) -> dict[str, Position]:
        return dict(self._positions)

    def handle_decision(
        self, decision: Decision, size: float = 1.0, price: Optional[float] = None
    ) -> ExecutionResult:
        if decision.action == Action.ENTER:
            return self._enter(decision, size)
        if decision.action == Action.EXIT:
            return self._exit(decision, price)
        # HOLD / NO_TRADE: nothing to simulate.
        return ExecutionResult(
            status="no_action", decision=decision, fill=None, message="No action decision; nothing to execute."
        )

    def _enter(self, decision: Decision, size: float) -> ExecutionResult:
        if decision.instrument in self._positions:
            return ExecutionResult(
                status="rejected",
                decision=decision,
                fill=None,
                message=(
                    f"Already have an open paper position in {decision.instrument!r}; "
                    "ignoring duplicate enter."
                ),
            )
        if decision.entry is None:
            raise ValueError("ENTER decision has no entry price to simulate a fill at.")

        position = Position(
            instrument=decision.instrument,
            direction=decision.direction,  # Decision.__post_init__ guarantees non-None on ENTER
            entry=decision.entry,
            stop=decision.stop,
            target=decision.target,
            size=size,
            opened_at=decision.timestamp,
        )
        self._positions[decision.instrument] = position
        return ExecutionResult(
            status="simulated_fill", decision=decision, fill=position, message="Paper position opened."
        )

    def _exit(self, decision: Decision, price: Optional[float]) -> ExecutionResult:
        position = self._positions.pop(decision.instrument, None)
        if position is None:
            return ExecutionResult(
                status="rejected",
                decision=decision,
                fill=None,
                message=f"No open paper position in {decision.instrument!r} to exit.",
            )

        exit_price = price if price is not None else (decision.entry if decision.entry is not None else position.entry)
        closed = ClosedPosition(
            position=position,
            exit_price=exit_price,
            closed_at=decision.timestamp,
            realized_pnl=position.unrealized_pnl(exit_price),
        )
        return ExecutionResult(
            status="simulated_close", decision=decision, fill=closed, message="Paper position closed."
        )
