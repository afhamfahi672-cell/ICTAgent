import json

from ictagent.agent.prompts import build_prompt, build_system_blocks, build_user_content
from ictagent.structure.pipeline import compute_structure, StructureConfig

from .fixtures import trend_reversal_candles


def _state():
    candles = trend_reversal_candles()
    return compute_structure(candles, StructureConfig(swing_lookback=1))


def test_system_blocks_are_cacheable_and_include_playbook():
    blocks = build_system_blocks()
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "text"
    assert block["cache_control"] == {"type": "ephemeral"}
    assert "Fair Value Gaps" in block["text"]  # from base_rules.md
    assert "record_trade_decision" in block["text"]  # from AGENT_INSTRUCTIONS


def test_system_blocks_accept_custom_playbook():
    blocks = build_system_blocks(playbook_rules="Custom rule set.")
    assert "Custom rule set." in blocks[0]["text"]
    assert "record_trade_decision" in blocks[0]["text"]  # instructions still appended


def test_user_content_is_valid_json_with_expected_shape():
    state = _state()
    content = build_user_content("EUR_USD", state, context_snapshot={"session": "london"})
    payload = json.loads(content)
    assert payload["instrument"] == "EUR_USD"
    assert payload["context"] == {"session": "london"}
    assert "structure_events" in payload["structure"]
    assert len(payload["structure"]["structure_events"]) == 3


def test_user_content_defaults_empty_context():
    state = _state()
    content = build_user_content("NIFTY", state)
    payload = json.loads(content)
    assert payload["context"] == {}


def test_build_prompt_combines_both_halves():
    state = _state()
    system_blocks, user_content = build_prompt("EUR_USD", state)
    assert isinstance(system_blocks, list)
    payload = json.loads(user_content)
    assert payload["instrument"] == "EUR_USD"
