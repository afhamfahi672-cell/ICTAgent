"""
Prompt construction for the reasoning cycle — pure functions, no network
dependency, fully unit-testable.

The system prompt is split into two pieces:
  1. The playbook rules (playbook/base_rules.md by default) + fixed
     decision-discipline instructions below — identical on every cycle,
     so it's marked cacheable (`cache_control`). A live agent calls this
     many times a day; without caching, the same ~1-2k token playbook
     gets re-priced as fresh input on every single cycle.
  2. The user turn: the current instrument + StructureState + market
     context, serialized as JSON — this changes every cycle, so it is
     never cached.
"""

from __future__ import annotations

import json
from typing import Optional

from ictagent.structure.types import StructureState
from ictagent.playbook import load_base_rules

AGENT_INSTRUCTIONS = """\
# Task

Each message that follows this system prompt is one decision cycle for one \
instrument. You will be given, as JSON:
  - "instrument": the instrument this cycle concerns
  - "structure": the full output of the deterministic structure/ pipeline \
(swing points, BOS/CHoCH events, liquidity pools, fair value gaps, order \
blocks, OTE zones) for that instrument, computed independently of you
  - "context": market context (session/kill-zone timing, economic \
calendar, news headlines) available for this cycle, when supplied

You must call the `record_trade_decision` tool exactly once per message, \
applying the playbook rules above to the supplied structure and context. \
You do not compute market structure yourself and must not report BOS/ \
CHoCH, liquidity pools, FVGs, order blocks, or OTE zones that are not \
present in the supplied "structure" JSON — if the structure looks wrong \
or incomplete, say so in the rationale rather than inventing your own.

A "no_trade" action is a complete, valid decision when the setup is \
insufficient — it is not a fallback to avoid. Every call, including \
no_trade, requires a non-empty rationale stating which playbook elements \
were present or absent and why that was or was not sufficient.
"""


def build_system_blocks(playbook_rules: Optional[str] = None) -> list[dict]:
    """The static (cacheable) half of the prompt."""
    rules = playbook_rules if playbook_rules is not None else load_base_rules()
    text = rules.rstrip() + "\n\n" + AGENT_INSTRUCTIONS
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def build_user_content(
    instrument: str,
    structure_state: StructureState,
    context_snapshot: Optional[dict] = None,
) -> str:
    """The per-cycle (never cached) half of the prompt."""
    payload = {
        "instrument": instrument,
        "structure": structure_state.to_dict(),
        "context": context_snapshot or {},
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def build_prompt(
    instrument: str,
    structure_state: StructureState,
    context_snapshot: Optional[dict] = None,
    playbook_rules: Optional[str] = None,
) -> tuple[list[dict], str]:
    """Returns (system_blocks, user_content) ready to hand to the Claude API."""
    return (
        build_system_blocks(playbook_rules),
        build_user_content(instrument, structure_state, context_snapshot),
    )
