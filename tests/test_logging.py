import sqlite3
from datetime import datetime, timedelta

import pytest

from ictagent.agent.types import Action, Decision
from ictagent.logging.store import DecisionLog
from ictagent.logging.query import get_decision, list_decisions
from ictagent.structure.pipeline import compute_structure, StructureConfig
from ictagent.structure.types import Direction

from .fixtures import trend_reversal_candles


def _log() -> DecisionLog:
    return DecisionLog(connection=sqlite3.connect(":memory:"))


def _state():
    candles = trend_reversal_candles()
    return compute_structure(candles, StructureConfig(swing_lookback=1))


def _decision(**overrides) -> Decision:
    base = dict(
        timestamp=datetime(2026, 1, 1, 9, 20),
        action=Action.ENTER,
        instrument="EUR_USD",
        direction=Direction.BULLISH,
        entry=1.0850,
        stop=1.0820,
        target=1.0910,
        confidence=0.7,
        rationale="BOS + bullish OB + OTE confluence.",
    )
    base.update(overrides)
    return Decision(**base)


def test_record_and_get_round_trip():
    log = _log()
    decision = _decision()
    state = _state()

    row_id = log.record(decision, structure_state=state, context_snapshot={"session": "london"}, playbook_version="v0.1")

    logged = get_decision(log, row_id)
    assert logged is not None
    assert logged.instrument == "EUR_USD"
    assert logged.action == "enter"
    assert logged.direction == "bullish"
    assert logged.entry == 1.0850
    assert logged.rationale == decision.rationale
    assert logged.playbook_version == "v0.1"
    assert logged.context == {"session": "london"}
    assert "structure_events" in logged.structure
    assert logged.timestamp == decision.timestamp


def test_get_decision_missing_id_returns_none():
    log = _log()
    assert get_decision(log, 999) is None


def test_record_no_trade_decision_with_null_fields():
    log = _log()
    decision = _decision(
        action=Action.NO_TRADE,
        direction=None,
        entry=None,
        stop=None,
        target=None,
        confidence=None,
        rationale="No BOS, no confluence. No setup.",
    )
    row_id = log.record(decision)
    logged = get_decision(log, row_id)
    assert logged.action == "no_trade"
    assert logged.direction is None
    assert logged.entry is None
    assert logged.structure == {}
    assert logged.context == {}


def test_record_defaults_structure_and_context_to_empty_when_omitted():
    log = _log()
    row_id = log.record(_decision())
    logged = get_decision(log, row_id)
    assert logged.structure == {}
    assert logged.context == {}
    assert logged.playbook_version is None


def test_list_decisions_orders_most_recent_first():
    log = _log()
    log.record(_decision(timestamp=datetime(2026, 1, 1, 9, 0)))
    log.record(_decision(timestamp=datetime(2026, 1, 1, 10, 0)))
    log.record(_decision(timestamp=datetime(2026, 1, 1, 8, 0)))

    results = list_decisions(log)
    timestamps = [d.timestamp for d in results]
    assert timestamps == sorted(timestamps, reverse=True)


def test_list_decisions_filters_by_instrument():
    log = _log()
    log.record(_decision(instrument="EUR_USD"))
    log.record(_decision(instrument="NIFTY"))

    results = list_decisions(log, instrument="NIFTY")
    assert len(results) == 1
    assert results[0].instrument == "NIFTY"


def test_list_decisions_filters_by_action():
    log = _log()
    log.record(_decision(action=Action.ENTER))
    log.record(
        _decision(
            action=Action.NO_TRADE,
            direction=None,
            entry=None,
            stop=None,
            target=None,
            confidence=None,
            rationale="no setup",
        )
    )

    results = list_decisions(log, action="no_trade")
    assert len(results) == 1
    assert results[0].action == "no_trade"


def test_list_decisions_filters_by_confidence_and_date_range():
    log = _log()
    log.record(_decision(timestamp=datetime(2026, 1, 1), confidence=0.3))
    log.record(_decision(timestamp=datetime(2026, 1, 2), confidence=0.8))
    log.record(_decision(timestamp=datetime(2026, 1, 10), confidence=0.9))

    high_confidence = list_decisions(log, min_confidence=0.5)
    assert {d.confidence for d in high_confidence} == {0.8, 0.9}

    windowed = list_decisions(
        log, since=datetime(2026, 1, 1, 12, 0), until=datetime(2026, 1, 5)
    )
    assert len(windowed) == 1
    assert windowed[0].timestamp == datetime(2026, 1, 2)


def test_list_decisions_respects_limit():
    log = _log()
    for i in range(5):
        log.record(_decision(timestamp=datetime(2026, 1, 1) + timedelta(hours=i)))

    assert len(list_decisions(log, limit=2)) == 2
    assert len(list_decisions(log, limit=100)) == 5


def test_record_returns_new_row_id_each_time():
    log = _log()
    first = log.record(_decision())
    second = log.record(_decision())
    assert second == first + 1
