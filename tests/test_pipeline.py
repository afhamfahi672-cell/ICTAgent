import json

from ictagent.structure.pipeline import compute_structure, StructureConfig
from ictagent.structure.types import Direction

from .fixtures import trend_reversal_candles


def test_pipeline_wires_all_stages_together():
    candles = trend_reversal_candles()
    state = compute_structure(candles, StructureConfig(swing_lookback=1))

    assert len(state.swing_points) == 5
    assert len(state.structure_events) == 3
    assert len(state.fair_value_gaps) >= 0  # none guaranteed in this fixture, just shouldn't error
    assert len(state.order_blocks) == 3
    assert len(state.ote_zones) == 3

    # trend reflects the most recent structure event (final BOS bearish)
    assert state.trend == Direction.BEARISH


def test_default_config_runs_without_error():
    candles = trend_reversal_candles()
    state = compute_structure(candles)  # default lookback=2
    assert state is not None


def test_state_is_json_serializable():
    candles = trend_reversal_candles()
    state = compute_structure(candles, StructureConfig(swing_lookback=1))
    payload = json.dumps(state.to_dict())
    assert isinstance(payload, str)
    assert "structure_events" in payload
