"""
Persistent, queryable log of every decision cycle.

  logging/store.py   Implemented. DecisionLog — SQLite-backed append log
                      of every Decision (agent/types.py) together with
                      the full StructureState and market context
                      snapshot that produced it, and the playbook rule
                      set version in effect at the time.
  logging/query.py   Implemented. Read-side filters for the manual
                      reasoning-quality review pass (Phase 2) — by
                      instrument, action, date range, minimum confidence.

Every decision is logged, including NO_TRADE — the point of this module
is to make the agent's reasoning auditable, not just its trades.
"""

from .store import DecisionLog, DEFAULT_DB_PATH
from .query import LoggedDecision, get_decision, list_decisions

__all__ = [
    "DecisionLog",
    "DEFAULT_DB_PATH",
    "LoggedDecision",
    "get_decision",
    "list_decisions",
]
