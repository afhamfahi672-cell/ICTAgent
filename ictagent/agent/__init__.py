"""
LLM reasoning layer.

  agent/types.py      Decision — the object every reasoning cycle
                       produces (action, instrument, direction, entry,
                       stop, target, confidence, rationale). Required
                       rationale enforced in __post_init__.
  agent/prompts.py     Pure prompt construction from StructureState +
                        market context + playbook rules — no network
                        dependency, unit-tested directly.
  agent/reasoner.py    Reasoner.decide(): the actual Claude API call,
                       using strict tool use to force the Decision
                       schema. Model defaults to claude-opus-5.

The LLM never computes market structure itself — it only reasons over
what structure/ has already deterministically computed, and is
instructed not to report structural elements that aren't in the data
it was given.
"""

from .types import Action, Decision
from .reasoner import (
    Reasoner,
    AgentConfig,
    AgentError,
    AgentAuthError,
    AgentRefusalError,
    DECISION_TOOL,
    DECISION_TOOL_NAME,
)

__all__ = [
    "Action",
    "Decision",
    "Reasoner",
    "AgentConfig",
    "AgentError",
    "AgentAuthError",
    "AgentRefusalError",
    "DECISION_TOOL",
    "DECISION_TOOL_NAME",
]
