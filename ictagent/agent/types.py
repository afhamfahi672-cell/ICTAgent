"""
The decision object every reasoning cycle produces — the one piece of
agent/'s eventual interface worth fixing early, since logging/ and
execution/ both need to agree on its shape before either is built.

The actual Claude API call (agent/reasoner.py or similar, calling the
Claude API with StructureState + context + playbook rules and parsing
the model's response into a Decision) is not implemented yet — that's
the next module after data/.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Optional

from ictagent.structure.types import Direction


class Action(str, Enum):
    ENTER = "enter"
    EXIT = "exit"
    HOLD = "hold"
    NO_TRADE = "no_trade"


@dataclass(frozen=True)
class Decision:
    """One decision-cycle output. `rationale` is required and must be
    non-empty for every action, including NO_TRADE — see playbook rule
    "Decision discipline"."""

    timestamp: datetime
    action: Action
    instrument: str
    rationale: str
    direction: Optional[Direction] = None
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    confidence: Optional[float] = None  # 0.0-1.0

    def __post_init__(self):
        if not self.rationale or not self.rationale.strip():
            raise ValueError("Decision.rationale must be non-empty (see playbook rule 7)")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Decision.confidence must be between 0.0 and 1.0")
        if self.action == Action.ENTER and self.direction is None:
            raise ValueError("Decision.direction is required when action is ENTER")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["action"] = self.action.value
        d["direction"] = self.direction.value if self.direction else None
        return d
