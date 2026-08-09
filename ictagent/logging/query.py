"""
Read-side helpers for the manual reasoning-quality review pass (Phase 2).

Pure query functions operating on a `DecisionLog`'s underlying
connection — a friendlier filtered read API than hand-writing SQL for
the common cases (by instrument, by action, by date range, by minimum
confidence), not a second storage concept.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .store import DecisionLog


@dataclass(frozen=True)
class LoggedDecision:
    id: int
    timestamp: datetime
    instrument: str
    action: str
    direction: Optional[str]
    entry: Optional[float]
    stop: Optional[float]
    target: Optional[float]
    confidence: Optional[float]
    rationale: str
    structure: dict
    context: dict
    playbook_version: Optional[str]
    logged_at: datetime

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "instrument": self.instrument,
            "action": self.action,
            "direction": self.direction,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "structure": self.structure,
            "context": self.context,
            "playbook_version": self.playbook_version,
            "logged_at": self.logged_at.isoformat(),
        }


def _row_to_logged_decision(row: sqlite3.Row) -> LoggedDecision:
    return LoggedDecision(
        id=row["id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        instrument=row["instrument"],
        action=row["action"],
        direction=row["direction"],
        entry=row["entry"],
        stop=row["stop"],
        target=row["target"],
        confidence=row["confidence"],
        rationale=row["rationale"],
        structure=json.loads(row["structure_json"]),
        context=json.loads(row["context_json"]),
        playbook_version=row["playbook_version"],
        logged_at=datetime.fromisoformat(row["logged_at"]),
    )


def get_decision(log: DecisionLog, decision_id: int) -> Optional[LoggedDecision]:
    row = log.connection.execute(
        "SELECT * FROM decisions WHERE id = ?", (decision_id,)
    ).fetchone()
    return _row_to_logged_decision(row) if row else None


def list_decisions(
    log: DecisionLog,
    instrument: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    min_confidence: Optional[float] = None,
    limit: int = 100,
) -> list[LoggedDecision]:
    """Most recent first. All filters are optional and combine with AND."""
    clauses: list[str] = []
    params: list = []

    if instrument is not None:
        clauses.append("instrument = ?")
        params.append(instrument)
    if action is not None:
        clauses.append("action = ?")
        params.append(action)
    if since is not None:
        clauses.append("timestamp >= ?")
        params.append(since.isoformat())
    if until is not None:
        clauses.append("timestamp <= ?")
        params.append(until.isoformat())
    if min_confidence is not None:
        clauses.append("confidence >= ?")
        params.append(min_confidence)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM decisions {where} ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = log.connection.execute(sql, params).fetchall()
    return [_row_to_logged_decision(r) for r in rows]
