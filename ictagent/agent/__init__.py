"""
LLM reasoning layer.

Not implemented yet. Planned responsibilities:

  agent/reasoner.py   Calls the Claude API each decision cycle with:
                       current StructureState (structure/), market
                       context (context/), and relevant playbook rules
                       (playbook/base_rules.md); parses the response
                       into a `Decision` (agent/types.py).
  agent/prompts.py    Prompt templates / formatting of StructureState
                       and context into the Claude API request.

The LLM never computes market structure itself — it only reasons over
what structure/ has already deterministically computed. Every decision,
including "no trade", carries a required human-readable rationale
(enforced by `Decision.__post_init__`).
"""

from .types import Action, Decision

__all__ = ["Action", "Decision"]
