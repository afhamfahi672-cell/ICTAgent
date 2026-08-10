import time

import pytest

from ictagent.web.auth import (
    AuthConfigError,
    check_password,
    create_session_token,
    verify_session_token,
)


def test_check_password_missing_env_raises_auth_config_error(monkeypatch):
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    with pytest.raises(AuthConfigError):
        check_password("anything")


def test_check_password_correct_and_incorrect(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "correct-horse")
    assert check_password("correct-horse") is True
    assert check_password("wrong") is False
    assert check_password("") is False


def test_create_session_token_missing_secret_key_raises(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "pw")
    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    with pytest.raises(AuthConfigError):
        create_session_token()


def test_token_round_trip(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-signing-key")
    token = create_session_token()
    assert verify_session_token(token) is True


def test_verify_rejects_none_and_empty(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-signing-key")
    assert verify_session_token(None) is False
    assert verify_session_token("") is False


def test_verify_rejects_tampered_token(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-signing-key")
    token = create_session_token()
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert verify_session_token(tampered) is False


def test_verify_rejects_token_signed_with_a_different_key(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET_KEY", "key-one")
    token = create_session_token()
    monkeypatch.setenv("SESSION_SECRET_KEY", "key-two")
    assert verify_session_token(token) is False


def test_verify_rejects_expired_token(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-signing-key")

    with monkeypatch.context() as m:
        long_ago = time.time() - 10_000_000
        m.setattr(time, "time", lambda: long_ago)
        token = create_session_token()

    assert verify_session_token(token) is False
