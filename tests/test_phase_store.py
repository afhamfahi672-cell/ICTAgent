import sqlite3

from ictagent.config.settings import Phase
from ictagent.web.phase_store import PhaseStore


def _store() -> PhaseStore:
    return PhaseStore(connection=sqlite3.connect(":memory:", check_same_thread=False))


def test_returns_default_when_nothing_stored():
    store = _store()
    assert store.get_phase(default=Phase.PAPER) == Phase.PAPER
    assert store.get_phase(default=Phase.SEMI_AUTO) == Phase.SEMI_AUTO


def test_set_then_get_returns_override_regardless_of_default():
    store = _store()
    store.set_phase(Phase.SEMI_AUTO)
    assert store.get_phase(default=Phase.PAPER) == Phase.SEMI_AUTO


def test_set_phase_overwrites_previous_value():
    store = _store()
    store.set_phase(Phase.SEMI_AUTO)
    store.set_phase(Phase.AUTONOMOUS)
    assert store.get_phase(default=Phase.PAPER) == Phase.AUTONOMOUS


def test_corrupt_stored_value_falls_back_to_default():
    store = _store()
    # bypass set_phase to simulate bad data landing in the table
    store._conn.execute(
        "INSERT INTO phase_override (id, phase) VALUES (1, 'not_a_real_phase')"
    )
    store._conn.commit()
    assert store.get_phase(default=Phase.PAPER) == Phase.PAPER
