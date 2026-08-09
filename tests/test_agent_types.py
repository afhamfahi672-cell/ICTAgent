from datetime import datetime

import pytest

from ictagent.agent.types import Action, Decision
from ictagent.structure.types import Direction


def test_no_trade_requires_rationale():
    with pytest.raises(ValueError):
        Decision(
            timestamp=datetime.now(),
            action=Action.NO_TRADE,
            instrument="NIFTY",
            rationale="   ",
        )


def test_enter_requires_direction():
    with pytest.raises(ValueError):
        Decision(
            timestamp=datetime.now(),
            action=Action.ENTER,
            instrument="EUR_USD",
            rationale="Clean BOS + OTE + FVG confluence",
        )


def test_confidence_must_be_in_unit_range():
    with pytest.raises(ValueError):
        Decision(
            timestamp=datetime.now(),
            action=Action.NO_TRADE,
            instrument="NIFTY",
            rationale="no setup",
            confidence=1.5,
        )


def test_valid_decision_round_trips_to_dict():
    d = Decision(
        timestamp=datetime(2026, 1, 1, 9, 20),
        action=Action.ENTER,
        instrument="EUR_USD",
        direction=Direction.BULLISH,
        entry=1.0850,
        stop=1.0820,
        target=1.0910,
        confidence=0.7,
        rationale="BOS + bullish OB + OTE confluence in NY kill zone",
    )
    payload = d.to_dict()
    assert payload["action"] == "enter"
    assert payload["direction"] == "bullish"
    assert payload["timestamp"] == "2026-01-01T09:20:00"
