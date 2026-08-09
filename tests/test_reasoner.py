import pytest

from ictagent.config.settings import Settings, Phase
from ictagent.agent.reasoner import (
    Reasoner,
    AgentConfig,
    AgentError,
    AgentAuthError,
    AgentRefusalError,
    DECISION_TOOL_NAME,
)
from ictagent.agent.types import Action, Decision
from ictagent.structure.pipeline import compute_structure, StructureConfig
from ictagent.structure.types import Direction

from .fixtures import trend_reversal_candles


# ---------------------------------------------------------------------------
# Fake anthropic client — no network, no real API key.
# ---------------------------------------------------------------------------


class FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, input_: dict):
        self.input = input_


class FakeTextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class FakeStopDetails:
    def __init__(self, category=None, explanation=None):
        self.category = category
        self.explanation = explanation


class FakeResponse:
    def __init__(self, content, stop_reason="tool_use", stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class FakeMessages:
    def __init__(self, response=None, exception=None):
        self.response = response
        self.exception = exception
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exception is not None:
            raise self.exception
        return self.response


class FakeAnthropicClient:
    def __init__(self, response=None, exception=None):
        self.messages = FakeMessages(response=response, exception=exception)


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


def _state():
    candles = trend_reversal_candles()
    return compute_structure(candles, StructureConfig(swing_lookback=1))


_VALID_DECISION_INPUT = {
    "action": "enter",
    "instrument": "EUR_USD",
    "direction": "bullish",
    "entry": 1.0850,
    "stop": 1.0820,
    "target": 1.0910,
    "confidence": 0.7,
    "rationale": "BOS + bullish OB + OTE confluence in the NY kill zone.",
}


# ---------------------------------------------------------------------------
# Construction / auth
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_auth_error():
    with pytest.raises(AgentAuthError):
        Reasoner(settings=_settings(anthropic_api_key=None))


def test_client_can_be_injected_without_real_key_check():
    # settings() already has a fake key; injected client means no real
    # network/SDK is ever touched.
    fake = FakeAnthropicClient(response=FakeResponse([FakeToolUseBlock(_VALID_DECISION_INPUT)]))
    reasoner = Reasoner(settings=_settings(), client=fake)
    assert reasoner is not None


# ---------------------------------------------------------------------------
# decide()
# ---------------------------------------------------------------------------


def test_decide_returns_parsed_decision():
    fake = FakeAnthropicClient(response=FakeResponse([FakeToolUseBlock(_VALID_DECISION_INPUT)]))
    reasoner = Reasoner(settings=_settings(), client=fake, config=AgentConfig(model="claude-opus-5"))

    decision = reasoner.decide("EUR_USD", _state())

    assert isinstance(decision, Decision)
    assert decision.action == Action.ENTER
    assert decision.direction == Direction.BULLISH
    assert decision.entry == 1.0850
    assert decision.confidence == 0.7
    assert "BOS" in decision.rationale

    # verify request shape
    call = fake.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["tool_choice"] == {"type": "tool", "name": DECISION_TOOL_NAME}
    assert call["tools"][0]["name"] == DECISION_TOOL_NAME
    assert call["tools"][0]["strict"] is True
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["messages"][0]["role"] == "user"


def test_decide_handles_no_trade_action():
    raw = {
        "action": "no_trade",
        "instrument": "NIFTY",
        "direction": None,
        "entry": None,
        "stop": None,
        "target": None,
        "confidence": None,
        "rationale": "No BOS, no liquidity sweep, price mid-range. No setup.",
    }
    fake = FakeAnthropicClient(response=FakeResponse([FakeToolUseBlock(raw)]))
    reasoner = Reasoner(settings=_settings(), client=fake)

    decision = reasoner.decide("NIFTY", _state())
    assert decision.action == Action.NO_TRADE
    assert decision.direction is None


def test_decide_raises_on_refusal():
    fake = FakeAnthropicClient(
        response=FakeResponse(
            [], stop_reason="refusal", stop_details=FakeStopDetails(category="cyber", explanation="declined")
        )
    )
    reasoner = Reasoner(settings=_settings(), client=fake)

    with pytest.raises(AgentRefusalError) as exc_info:
        reasoner.decide("EUR_USD", _state())
    assert exc_info.value.category == "cyber"


def test_decide_raises_when_no_tool_use_block_present():
    fake = FakeAnthropicClient(response=FakeResponse([FakeTextBlock("I decided not to call the tool.")]))
    reasoner = Reasoner(settings=_settings(), client=fake)

    with pytest.raises(AgentError):
        reasoner.decide("EUR_USD", _state())


def test_decide_wraps_underlying_client_exceptions():
    fake = FakeAnthropicClient(exception=RuntimeError("connection reset"))
    reasoner = Reasoner(settings=_settings(), client=fake)

    with pytest.raises(AgentError, match="connection reset"):
        reasoner.decide("EUR_USD", _state())


def test_decide_wraps_invalid_decision_from_model():
    raw = {**_VALID_DECISION_INPUT, "rationale": ""}  # violates Decision's own validation
    fake = FakeAnthropicClient(response=FakeResponse([FakeToolUseBlock(raw)]))
    reasoner = Reasoner(settings=_settings(), client=fake)

    with pytest.raises(AgentError):
        reasoner.decide("EUR_USD", _state())


def test_decide_rejects_unknown_action_string():
    raw = {**_VALID_DECISION_INPUT, "action": "yolo"}
    fake = FakeAnthropicClient(response=FakeResponse([FakeToolUseBlock(raw)]))
    reasoner = Reasoner(settings=_settings(), client=fake)

    with pytest.raises(AgentError):
        reasoner.decide("EUR_USD", _state())
