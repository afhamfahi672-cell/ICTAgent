import sqlite3

import pytest

from ictagent.config.settings import Settings, Phase
from ictagent.agent.reasoner import Reasoner
from ictagent.execution.gate import ExecutionGate
from ictagent.logging.store import DecisionLog
from ictagent.logging.query import list_decisions
from ictagent.structure.pipeline import StructureConfig
from ictagent.cycle import CycleError, CycleResult, DecisionCycleRunner, WatchedInstrument

from .fixtures import trend_reversal_candles


# ---------------------------------------------------------------------------
# Fake anthropic client — no network, no real API key. Mirrors
# tests/test_reasoner.py's doubles (kept local rather than shared, matching
# how each test file owns its own fakes throughout this suite).
# ---------------------------------------------------------------------------


class FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, input_: dict):
        self.input = input_


class FakeResponse:
    def __init__(self, content, stop_reason="tool_use", stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class FakeMessages:
    def __init__(self, response_fn):
        self.response_fn = response_fn
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response_fn(kwargs)


class FakeAnthropicClient:
    def __init__(self, response_fn):
        self.messages = FakeMessages(response_fn)


def _settings(**overrides) -> Settings:
    base = dict(
        phase=Phase.PAPER,
        live_trading_confirm="",
        kite_api_key=None,
        kite_api_secret=None,
        kite_access_token=None,
        oanda_api_token=None,
        oanda_account_id=None,
        oanda_environment="practice",
        anthropic_api_key="test-key",
        news_api_key=None,
    )
    base.update(overrides)
    return Settings(**base)


_NO_TRADE_INPUT = {
    "action": "no_trade",
    "instrument": "PLACEHOLDER",
    "direction": None,
    "entry": None,
    "stop": None,
    "target": None,
    "confidence": None,
    "rationale": "No confluence this cycle.",
}

_ENTER_INPUT = {
    "action": "enter",
    "instrument": "PLACEHOLDER",
    "direction": "bullish",
    "entry": 1.0850,
    "stop": 1.0820,
    "target": 1.0910,
    "confidence": 0.7,
    "rationale": "BOS + bullish OB + OTE confluence.",
}


def _decision_input_for(instrument: str, template: dict) -> dict:
    return {**template, "instrument": instrument}


def _make_runner(
    watchlist,
    response_fn,
    settings=None,
    decision_log=None,
    execution_gate=None,
    on_cycle=None,
):
    settings = settings or _settings()
    reasoner = Reasoner(settings=settings, client=FakeAnthropicClient(response_fn))
    decision_log = decision_log or DecisionLog(connection=sqlite3.connect(":memory:"))
    execution_gate = execution_gate or ExecutionGate(settings=settings)
    return DecisionCycleRunner(
        watchlist=watchlist,
        settings=settings,
        reasoner=reasoner,
        decision_log=decision_log,
        execution_gate=execution_gate,
        playbook_version="test-v0",
        on_cycle=on_cycle,
    ), decision_log


def _watched(instrument: str) -> WatchedInstrument:
    return WatchedInstrument(
        instrument=instrument,
        fetch_candles=trend_reversal_candles,
        structure_config=StructureConfig(swing_lookback=1),
    )


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------


def test_run_once_processes_all_watchlist_items_and_logs_each():
    def respond(kwargs):
        instrument = kwargs["messages"][0]["content"]
        # crude but sufficient: route by which instrument's name appears
        if "EUR_USD" in instrument:
            return FakeResponse([FakeToolUseBlock(_decision_input_for("EUR_USD", _ENTER_INPUT))])
        return FakeResponse([FakeToolUseBlock(_decision_input_for("NIFTY", _NO_TRADE_INPUT))])

    watchlist = [_watched("EUR_USD"), _watched("NIFTY")]
    runner, log = _make_runner(watchlist, respond)

    results = runner.run_once()

    assert len(results) == 2
    assert all(isinstance(r, CycleResult) for r in results)
    assert {r.instrument for r in results} == {"EUR_USD", "NIFTY"}

    logged = list_decisions(log, limit=10)
    assert len(logged) == 2
    assert {d.playbook_version for d in logged} == {"test-v0"}


def test_run_once_enter_decision_produces_simulated_fill():
    def respond(_kwargs):
        return FakeResponse([FakeToolUseBlock(_decision_input_for("EUR_USD", _ENTER_INPUT))])

    runner, _log = _make_runner([_watched("EUR_USD")], respond)
    [result] = runner.run_once()

    assert result.execution_result.status == "simulated_fill"
    assert result.decision.action.value == "enter"


def test_run_once_no_trade_decision_produces_no_action():
    def respond(_kwargs):
        return FakeResponse([FakeToolUseBlock(_decision_input_for("NIFTY", _NO_TRADE_INPUT))])

    runner, _log = _make_runner([_watched("NIFTY")], respond)
    [result] = runner.run_once()

    assert result.execution_result.status == "no_action"


def test_run_once_includes_session_context_in_agent_call():
    captured = {}

    def respond(kwargs):
        captured["messages"] = kwargs["messages"]
        return FakeResponse([FakeToolUseBlock(_decision_input_for("EUR_USD", _NO_TRADE_INPUT))])

    runner, _log = _make_runner([_watched("EUR_USD")], respond)
    runner.run_once()

    user_content = captured["messages"][0]["content"]
    assert '"session"' in user_content
    assert "open_sessions" in user_content


def test_run_once_isolates_failures_per_instrument():
    def broken_fetch():
        raise RuntimeError("data feed unavailable")

    def respond(_kwargs):
        return FakeResponse([FakeToolUseBlock(_decision_input_for("NIFTY", _NO_TRADE_INPUT))])

    watchlist = [
        WatchedInstrument(instrument="EUR_USD", fetch_candles=broken_fetch),
        _watched("NIFTY"),
    ]
    runner, log = _make_runner(watchlist, respond)

    results = runner.run_once()

    assert len(results) == 2
    failed = next(r for r in results if r.instrument == "EUR_USD")
    succeeded = next(r for r in results if r.instrument == "NIFTY")

    assert isinstance(failed, CycleError)
    assert "data feed unavailable" in failed.error
    assert isinstance(succeeded, CycleResult)

    # only the instrument that succeeded got logged
    assert len(list_decisions(log, limit=10)) == 1


def test_run_once_invokes_on_cycle_callback():
    captured = []

    def respond(_kwargs):
        return FakeResponse([FakeToolUseBlock(_decision_input_for("EUR_USD", _NO_TRADE_INPUT))])

    runner, _log = _make_runner([_watched("EUR_USD")], respond, on_cycle=lambda results: captured.append(results))
    runner.run_once()

    assert len(captured) == 1
    assert len(captured[0]) == 1


def test_extra_context_is_merged_into_context_snapshot():
    captured = {}

    def respond(kwargs):
        captured["messages"] = kwargs["messages"]
        return FakeResponse([FakeToolUseBlock(_decision_input_for("EUR_USD", _NO_TRADE_INPUT))])

    watched = WatchedInstrument(
        instrument="EUR_USD",
        fetch_candles=trend_reversal_candles,
        structure_config=StructureConfig(swing_lookback=1),
        extra_context=lambda: {"news": ["Fed holds rates steady"]},
    )
    runner, _log = _make_runner([watched], respond)
    runner.run_once()

    assert "Fed holds rates steady" in captured["messages"][0]["content"]


# ---------------------------------------------------------------------------
# run_forever
# ---------------------------------------------------------------------------


def test_run_forever_respects_max_cycles_and_sleeps_between_not_after():
    def respond(_kwargs):
        return FakeResponse([FakeToolUseBlock(_decision_input_for("EUR_USD", _NO_TRADE_INPUT))])

    runner, log = _make_runner([_watched("EUR_USD")], respond)

    sleep_calls = []
    runner.run_forever(interval_seconds=5, max_cycles=3, sleep=sleep_calls.append)

    assert len(list_decisions(log, limit=10)) == 3
    assert sleep_calls == [5, 5]  # slept between cycles, not after the last one


def test_run_forever_invokes_on_cycle_each_pass():
    def respond(_kwargs):
        return FakeResponse([FakeToolUseBlock(_decision_input_for("EUR_USD", _NO_TRADE_INPUT))])

    seen = []
    runner, _log = _make_runner([_watched("EUR_USD")], respond, on_cycle=lambda r: seen.append(r))
    runner.run_forever(interval_seconds=0, max_cycles=2, sleep=lambda _s: None)

    assert len(seen) == 2
