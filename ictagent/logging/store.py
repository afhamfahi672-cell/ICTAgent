"""
Persistent, queryable log of every decision cycle — SQLite-backed.

Every decision is logged, including NO_TRADE, together with the full
structure/context snapshot that produced it — the point of this module
is to make the agent's reasoning auditable, not just its trades. This is
what Phase 2 (manual reasoning-quality review) reads from.

SQLite to start: no external service to run for a single-operator setup
reviewing decisions by hand. `DecisionLog`'s public interface doesn't
leak SQLite specifics, so swapping the backend later is contained to
this file. `connection` is injectable (e.g. `sqlite3.connect(":memory:")`)
so tests don't touch the filesystem — see tests/test_logging.py.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from ictagent.agent.types import Decision
from ictagent.structure.types import StructureState

DEFAULT_DB_PATH = "ictagent_decisions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    instrument TEXT NOT NULL,
    action TEXT NOT NULL,
    direction TEXT,
    entry REAL,
    stop REAL,
    target REAL,
    confidence REAL,
    rationale TEXT NOT NULL,
    structure_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    playbook_version TEXT,
    logged_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_instrument ON decisions(instrument);
CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp);
CREATE INDEX IF NOT EXISTS idx_decisions_action ON decisions(action);
"""


class DecisionLog:
    """`connection` can be injected (any `sqlite3.Connection`, e.g. an
    in-memory database) — used by tests to avoid touching the filesystem.
    Defaults to a real file at `db_path`."""

    def __init__(
        self,
        db_path: Union[str, Path] = DEFAULT_DB_PATH,
        connection: Optional[sqlite3.Connection] = None,
    ):
        self._conn = connection if connection is not None else sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(
        self,
        decision: Decision,
        structure_state: Optional[StructureState] = None,
        context_snapshot: Optional[dict] = None,
        playbook_version: Optional[str] = None,
    ) -> int:
        """Persist one decision cycle. Returns the new row's id."""
        structure_json = json.dumps(
            structure_state.to_dict() if structure_state is not None else {}, sort_keys=True
        )
        context_json = json.dumps(context_snapshot or {}, sort_keys=True)

        cursor = self._conn.execute(
            """
            INSERT INTO decisions (
                timestamp, instrument, action, direction, entry, stop, target,
                confidence, rationale, structure_json, context_json,
                playbook_version, logged_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.timestamp.isoformat(),
                decision.instrument,
                decision.action.value,
                decision.direction.value if decision.direction else None,
                decision.entry,
                decision.stop,
                decision.target,
                decision.confidence,
                decision.rationale,
                structure_json,
                context_json,
                playbook_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()
