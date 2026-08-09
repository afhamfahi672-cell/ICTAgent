"""
Persistent, queryable log of every decision cycle.

Not implemented yet. Planned responsibilities:

  logging/store.py   Append-only persistence (SQLite to start — no
                      external service needed for Phase 1/2 manual
                      review) of every `Decision` (agent/types.py)
                      together with the full `StructureState` and
                      market context snapshot that produced it, and the
                      playbook rule set version in effect at the time.
  logging/query.py    Read-side helpers for the manual reasoning-quality
                      review pass (Phase 2) — filter by instrument, date
                      range, action, confidence, etc.

Every decision is logged, including NO_TRADE — the point of this module
is to make the agent's reasoning auditable, not just its trades.
"""
