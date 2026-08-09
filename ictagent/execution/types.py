"""Types shared by the paper broker and the execution gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union

from ictagent.agent.types import Decision
from ictagent.structure.types import Direction


@dataclass(frozen=True)
class Position:
    """An open simulated position."""

    instrument: str
    direction: Direction
    entry: float
    stop: Optional[float]
    target: Optional[float]
    size: float
    opened_at: datetime

    def unrealized_pnl(self, current_price: float) -> float:
        move = current_price - self.entry
        if self.direction == Direction.BEARISH:
            move = -move
        return move * self.size

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "direction": self.direction.value,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "size": self.size,
            "opened_at": self.opened_at.isoformat(),
        }


@dataclass(frozen=True)
class ClosedPosition:
    """A simulated position that has been exited."""

    position: Position
    exit_price: float
    closed_at: datetime
    realized_pnl: float

    def to_dict(self) -> dict:
        return {
            "position": self.position.to_dict(),
            "exit_price": self.exit_price,
            "closed_at": self.closed_at.isoformat(),
            "realized_pnl": self.realized_pnl,
        }


@dataclass(frozen=True)
class ExecutionResult:
    """What happened when a Decision was handed to execution/."""

    status: str  # "simulated_fill" | "simulated_close" | "pending_confirmation" | "rejected" | "no_action"
    decision: Decision
    fill: Optional[Union[Position, ClosedPosition]]
    message: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "decision": self.decision.to_dict(),
            "fill": self.fill.to_dict() if self.fill is not None else None,
            "message": self.message,
        }
