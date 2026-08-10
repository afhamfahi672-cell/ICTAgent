"""
Runtime phase override — lets the dashboard change ICTAGENT_PHASE
without a redeploy.

The scheduler re-reads this on every cycle and applies it on top of the
env-var-derived Settings. Critically, `ICTAGENT_LIVE_TRADING_CONFIRM` is
never settable from here — it stays a real environment variable only
settable on the hosting provider's own settings page, so the dashboard's
phase buttons can move you between paper/semi_auto/autonomous freely,
but "autonomous" clicked here still can't unlock live trading on its
own. See config/settings.py for the two-independent-switches design
this preserves, and execution/gate.py for where it's enforced.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union

from ictagent.config.settings import Phase

DEFAULT_DB_PATH = "ictagent_web.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS phase_override (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    phase TEXT NOT NULL
);
"""


class PhaseStore:
    """`connection` can be injected (e.g. an in-memory sqlite database)
    for tests. Defaults to a real file at `db_path`."""

    def __init__(
        self,
        db_path: Union[str, Path] = DEFAULT_DB_PATH,
        connection: Optional[sqlite3.Connection] = None,
    ):
        self._conn = (
            connection if connection is not None else sqlite3.connect(db_path, check_same_thread=False)
        )
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get_phase(self, default: Phase) -> Phase:
        row = self._conn.execute("SELECT phase FROM phase_override WHERE id = 1").fetchone()
        if row is None:
            return default
        try:
            return Phase(row[0])
        except ValueError:
            return default

    def set_phase(self, phase: Phase) -> None:
        self._conn.execute(
            "INSERT INTO phase_override (id, phase) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET phase = excluded.phase",
            (phase.value,),
        )
        self._conn.commit()
