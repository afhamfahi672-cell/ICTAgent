from datetime import datetime

import pytest

from ictagent.agent.types import Action, Decision
from ictagent.config.settings import Phase, Settings, LIVE_TRADING_CONFIRM_STRING
from ictagent.structure.types import Direction
from ictagent.execution.simulator import PaperBroker
from ictagent.execution.gate import ExecutionGate
from ictagent.execution.types import ClosedPosition, Position


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
        anthropic_api_key=None,
        news_api_key=None,
    )
    base.update(overrides)
    return Settings(**base)


def _enter_decision(**overrides) -> Decision:
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


def _exit_decision(**overrides) -> Decision:
    base = dict(
        timestamp=datetime(2026, 1, 2, 9, 20),
        action=Action.EXIT,
        instrument="EUR_USD",
        direction=None,
        entry=1.0900,
        stop=None,
        target=None,
        confidence=0.6,
        rationale="Target zone reached, structure weakening.",
    )
    base.update(overrides)
    return Decision(**base)


def _no_trade_decision(**overrides) -> Decision:
    base = dict(
        timestamp=datetime(2026, 1, 1, 9, 20),
        action=Action.NO_TRADE,
        instrument="EUR_USD",
        direction=None,
        entry=None,
        stop=None,
        target=None,
        confidence=None,
        rationale="No setup present.",
    )
    base.update(overrides)
    return Decision(**base)


# ---------------------------------------------------------------------------
# Position P&L
# ---------------------------------------------------------------------------


def test_position_unrealized_pnl_bullish_profit():
    pos = Position(
        instrument="EUR_USD", direction=Direction.BULLISH, entry=100, stop=95, target=110,
        size=2, opened_at=datetime(2026, 1, 1),
    )
    assert pos.unrealized_pnl(110) == 20  # (110-100)*2


def test_position_unrealized_pnl_bearish_profit_on_price_drop():
    pos = Position(
        instrument="EUR_USD", direction=Direction.BEARISH, entry=100, stop=105, target=90,
        size=2, opened_at=datetime(2026, 1, 1),
    )
    assert pos.unrealized_pnl(90) == 20  # price dropped 10, short profits 10*2


def test_position_unrealized_pnl_bearish_loss_on_price_rise():
    pos = Position(
        instrument="EUR_USD", direction=Direction.BEARISH, entry=100, stop=105, target=90,
        size=1, opened_at=datetime(2026, 1, 1),
    )
    assert pos.unrealized_pnl(105) == -5


# ---------------------------------------------------------------------------
# PaperBroker
# ---------------------------------------------------------------------------


def test_broker_enter_opens_position():
    broker = PaperBroker()
    result = broker.handle_decision(_enter_decision(), size=3)

    assert result.status == "simulated_fill"
    assert isinstance(result.fill, Position)
    assert result.fill.size == 3
    assert "EUR_USD" in broker.positions


def test_broker_rejects_duplicate_enter():
    broker = PaperBroker()
    broker.handle_decision(_enter_decision())
    result = broker.handle_decision(_enter_decision())

    assert result.status == "rejected"
    assert len(broker.positions) == 1


def test_broker_enter_requires_entry_price():
    broker = PaperBroker()
    decision = Decision(
        timestamp=datetime(2026, 1, 1),
        action=Action.ENTER,
        instrument="EUR_USD",
        direction=Direction.BULLISH,
        rationale="edge case",
    )
    with pytest.raises(ValueError):
        broker.handle_decision(decision)


def test_broker_exit_closes_position_and_computes_pnl():
    broker = PaperBroker()
    broker.handle_decision(_enter_decision(entry=1.0850), size=10)

    result = broker.handle_decision(_exit_decision(entry=1.0900))

    assert result.status == "simulated_close"
    assert isinstance(result.fill, ClosedPosition)
    assert result.fill.exit_price == 1.0900
    assert result.fill.realized_pnl == pytest.approx((1.0900 - 1.0850) * 10)
    assert "EUR_USD" not in broker.positions


def test_broker_exit_prefers_explicit_price_over_decision_entry():
    broker = PaperBroker()
    broker.handle_decision(_enter_decision(entry=1.0850), size=1)

    result = broker.handle_decision(_exit_decision(entry=1.0900), price=1.0950)

    assert result.fill.exit_price == 1.0950


def test_broker_exit_with_no_open_position_is_rejected():
    broker = PaperBroker()
    result = broker.handle_decision(_exit_decision())
    assert result.status == "rejected"


def test_broker_hold_and_no_trade_are_no_ops():
    broker = PaperBroker()
    result = broker.handle_decision(_no_trade_decision())
    assert result.status == "no_action"
    assert broker.positions == {}


# ---------------------------------------------------------------------------
# ExecutionGate
# ---------------------------------------------------------------------------


def test_gate_no_trade_short_circuits_regardless_of_phase():
    gate = ExecutionGate(settings=_settings(phase=Phase.AUTONOMOUS))
    result = gate.handle(_no_trade_decision())
    assert result.status == "no_action"


def test_gate_paper_phase_delegates_to_broker():
    gate = ExecutionGate(settings=_settings(phase=Phase.PAPER))
    result = gate.handle(_enter_decision())
    assert result.status == "simulated_fill"
    assert "EUR_USD" in gate.broker.positions


def test_gate_semi_auto_returns_pending_confirmation_without_touching_broker():
    gate = ExecutionGate(settings=_settings(phase=Phase.SEMI_AUTO))
    result = gate.handle(_enter_decision())
    assert result.status == "pending_confirmation"
    assert gate.broker.positions == {}  # never touched


def test_gate_autonomous_without_live_trading_enabled_raises_permission_error():
    gate = ExecutionGate(settings=_settings(phase=Phase.AUTONOMOUS, live_trading_confirm=""))
    with pytest.raises(PermissionError):
        gate.handle(_enter_decision())


def test_gate_autonomous_with_live_trading_enabled_raises_not_implemented():
    gate = ExecutionGate(
        settings=_settings(phase=Phase.AUTONOMOUS, live_trading_confirm=LIVE_TRADING_CONFIRM_STRING)
    )
    with pytest.raises(NotImplementedError):
        gate.handle(_enter_decision())
