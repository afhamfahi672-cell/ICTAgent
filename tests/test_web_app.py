import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from ictagent.agent.types import Action, Decision
from ictagent.config.settings import Phase
from ictagent.logging.store import DecisionLog
from ictagent.web.app import create_app
from ictagent.web.phase_store import PhaseStore

# The login cookie is Secure, so it's only stored/sent by the (test) HTTP
# client over an https:// origin — matches how it'll actually behave
# once deployed behind Render's TLS-terminating edge.
BASE_URL = "https://testserver"


class FakeScheduler:
    def __init__(self):
        self.run_calls = 0
        self.last_error = None
        self.stopped = False

    def run_once(self):
        self.run_calls += 1
        return []

    def stop(self):
        self.stopped = True


def _memdb() -> sqlite3.Connection:
    return sqlite3.connect(":memory:", check_same_thread=False)


def _client(scheduler=None, decision_log=None, phase_store=None) -> TestClient:
    app = create_app(
        decision_log=decision_log or DecisionLog(connection=_memdb()),
        phase_store=phase_store or PhaseStore(connection=_memdb()),
        scheduler=scheduler,
        auto_start_scheduler=False,
    )
    return TestClient(app, base_url=BASE_URL)


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "test123")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-signing-key")


def _logged_in_client(**kwargs) -> TestClient:
    client = _client(**kwargs)
    client.post("/login", data={"password": "test123"})
    return client


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


def test_dashboard_redirects_to_login_when_unauthenticated():
    with _client() as client:
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"


def test_wrong_password_shows_error_and_no_cookie():
    with _client() as client:
        r = client.post("/login", data={"password": "wrong"}, follow_redirects=False)
        assert r.status_code == 401
        assert "Wrong password" in r.text
        assert "ictagent_session" not in r.cookies


def test_correct_password_sets_cookie_and_grants_access():
    with _client() as client:
        r = client.post("/login", data={"password": "test123"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        assert "ictagent_session" in client.cookies

        r = client.get("/")
        assert r.status_code == 200
        assert "ICTAgent" in r.text


def test_login_without_config_shows_friendly_error_not_a_crash(monkeypatch):
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    with _client() as client:
        r = client.post("/login", data={"password": "anything"})
        assert r.status_code == 500
        assert "fully configured yet" in r.text  # apostrophe is HTML-escaped by Jinja2


def test_logout_clears_session():
    with _logged_in_client() as client:
        assert client.get("/").status_code == 200
        client.get("/logout")
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 303


# ---------------------------------------------------------------------------
# Dashboard content
# ---------------------------------------------------------------------------


def test_dashboard_shows_decisions():
    log = DecisionLog(connection=_memdb())
    log.record(
        Decision(
            timestamp=datetime(2026, 1, 1, 9, 20),
            action=Action.NO_TRADE,
            instrument="EUR_USD",
            rationale="No confluence this cycle.",
        )
    )
    with _logged_in_client(decision_log=log) as client:
        r = client.get("/")
        assert "EUR_USD" in r.text
        assert "No confluence this cycle." in r.text
        assert "badge-no_trade" in r.text


def test_dashboard_shows_no_decisions_message_when_empty():
    with _logged_in_client() as client:
        r = client.get("/")
        assert "No decisions logged yet" in r.text


def test_dashboard_shows_scheduler_error_without_crashing():
    scheduler = FakeScheduler()
    scheduler.last_error = "OANDA_API_TOKEN is not set"
    with _logged_in_client(scheduler=scheduler) as client:
        r = client.get("/")
        assert "isn't running" in r.text
        assert "OANDA_API_TOKEN is not set" in r.text


def test_dashboard_shows_not_started_message_when_no_scheduler():
    with _logged_in_client() as client:
        r = client.get("/")
        assert "hasn't started yet" in r.text


# ---------------------------------------------------------------------------
# Phase control
# ---------------------------------------------------------------------------


def test_phase_change_requires_auth():
    with _client() as client:
        r = client.post("/phase", data={"phase": "semi_auto"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"


def test_phase_change_updates_dashboard():
    store = PhaseStore(connection=_memdb())
    with _logged_in_client(phase_store=store) as client:
        client.post("/phase", data={"phase": "semi_auto"})
        r = client.get("/")
        assert "badge-semi_auto" in r.text
    assert store.get_phase(default=Phase.PAPER) == Phase.SEMI_AUTO


def test_phase_change_ignores_invalid_value():
    store = PhaseStore(connection=_memdb())
    store.set_phase(Phase.PAPER)
    with _logged_in_client(phase_store=store) as client:
        r = client.post("/phase", data={"phase": "not_a_phase"}, follow_redirects=False)
        assert r.status_code == 303  # doesn't error out
    assert store.get_phase(default=Phase.AUTONOMOUS) == Phase.PAPER  # unchanged


# ---------------------------------------------------------------------------
# Run-now
# ---------------------------------------------------------------------------


def test_run_now_requires_auth():
    scheduler = FakeScheduler()
    with _client(scheduler=scheduler) as client:
        client.post("/run-now", follow_redirects=False)
        assert scheduler.run_calls == 0


def test_run_now_triggers_a_cycle():
    scheduler = FakeScheduler()
    with _logged_in_client(scheduler=scheduler) as client:
        r = client.post("/run-now", follow_redirects=False)
        assert r.status_code == 303
        assert scheduler.run_calls == 1


def test_run_now_with_no_scheduler_does_not_error():
    with _logged_in_client() as client:
        r = client.post("/run-now", follow_redirects=False)
        assert r.status_code == 303
