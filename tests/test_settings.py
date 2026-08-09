import pytest

from ictagent.config.settings import Phase, LIVE_TRADING_CONFIRM_STRING, load_settings


def test_defaults_to_paper_when_unset():
    s = load_settings(env={})
    assert s.phase == Phase.PAPER
    assert s.is_paper
    assert not s.live_trading_enabled


def test_unrecognized_phase_falls_back_to_paper():
    s = load_settings(env={"ICTAGENT_PHASE": "yolo_mode"})
    assert s.phase == Phase.PAPER


def test_phase_alone_does_not_enable_live_trading():
    s = load_settings(env={"ICTAGENT_PHASE": "autonomous"})
    assert s.phase == Phase.AUTONOMOUS
    assert not s.live_trading_enabled
    with pytest.raises(PermissionError):
        s.require_live_trading_enabled()


def test_confirm_string_alone_does_not_enable_live_trading():
    s = load_settings(env={"ICTAGENT_LIVE_TRADING_CONFIRM": LIVE_TRADING_CONFIRM_STRING})
    assert not s.live_trading_enabled


def test_both_flags_required_to_enable_live_trading():
    s = load_settings(
        env={
            "ICTAGENT_PHASE": "autonomous",
            "ICTAGENT_LIVE_TRADING_CONFIRM": LIVE_TRADING_CONFIRM_STRING,
        }
    )
    assert s.live_trading_enabled
    s.require_live_trading_enabled()  # should not raise


def test_wrong_confirm_string_does_not_enable_live_trading():
    s = load_settings(
        env={"ICTAGENT_PHASE": "autonomous", "ICTAGENT_LIVE_TRADING_CONFIRM": "yes please"}
    )
    assert not s.live_trading_enabled


def test_credentials_read_from_env():
    s = load_settings(env={"KITE_API_KEY": "abc", "ANTHROPIC_API_KEY": "xyz"})
    assert s.kite_api_key == "abc"
    assert s.anthropic_api_key == "xyz"
    assert s.oanda_api_token is None
