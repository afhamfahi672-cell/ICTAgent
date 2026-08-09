"""
The Claude API call: one decision cycle in, one Decision out.

Model: claude-opus-5 by default. This is deliberate, not a placeholder —
current guidance is to default to Opus-tier for any serious reasoning
task and let cost be an explicit choice, not an accident. For a live
agent running many decision cycles a day, that cost is real; if latency/
cost at your cycle frequency becomes a problem, override
`AgentConfig.model` (e.g. to "claude-sonnet-5") — nothing else in this
module changes. See README for the tradeoff.

Structured output is forced via **strict tool use**: a single tool,
`record_trade_decision`, with `strict: true` and `tool_choice` pinned to
it. This is the recommended pattern for a schema Claude's response must
validate against exactly, rather than asking for JSON in prose and
parsing it. One call, one forced tool_use block, no agentic loop needed
here — a decision cycle is inherently single-turn.

Safety-classifier refusals (`stop_reason == "refusal"`) are handled
explicitly rather than left to crash on an unexpected response shape —
see AgentRefusalError.

Auth/session handling mirrors data/oanda.py and data/kite.py: credentials
come from config.settings, the `anthropic` SDK is imported lazily (only
needed for real, non-test usage), and `client` is injectable so the
request-building/response-parsing wiring here is fully unit-tested
without any real API key — see tests/test_reasoner.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ictagent.config.settings import Settings, load_settings
from ictagent.structure.types import StructureState, Direction

from .prompts import build_prompt
from .types import Action, Decision

DECISION_TOOL_NAME = "record_trade_decision"

DECISION_TOOL = {
    "name": DECISION_TOOL_NAME,
    "description": (
        "Record the trading decision for this cycle, based solely on the "
        "supplied market structure, context, and playbook rules. Call this "
        "exactly once per message, including when the decision is to take "
        "no action — a 'no_trade' action with a populated rationale is a "
        "complete, valid decision, not a fallback to avoid."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [a.value for a in Action],
                "description": "What to do this cycle.",
            },
            "instrument": {
                "type": "string",
                "description": "The instrument this decision concerns.",
            },
            "direction": {
                "anyOf": [
                    {"type": "string", "enum": [d.value for d in Direction]},
                    {"type": "null"},
                ],
                "description": "Required (non-null) when action is 'enter'.",
            },
            "entry": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "stop": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "target": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "confidence": {
                "anyOf": [{"type": "number"}, {"type": "null"}],
                "description": (
                    "0.0-1.0. Higher confidence should reflect more "
                    "independent structural elements agreeing (BOS/CHoCH + "
                    "liquidity sweep + FVG + order block + OTE), per the "
                    "playbook's decision-discipline rule."
                ),
            },
            "rationale": {
                "type": "string",
                "description": (
                    "Required, non-empty. State which structural elements "
                    "(BOS/CHoCH, liquidity, FVG, order block, OTE, session "
                    "timing) were present or absent and why that was or "
                    "was not sufficient for this decision."
                ),
            },
        },
        "required": [
            "action",
            "instrument",
            "direction",
            "entry",
            "stop",
            "target",
            "confidence",
            "rationale",
        ],
        "additionalProperties": False,
    },
}


class AgentError(RuntimeError):
    """Raised when the reasoning call fails or returns something the
    caller can't turn into a Decision."""


class AgentAuthError(AgentError):
    """Raised when ANTHROPIC_API_KEY is not set."""


class AgentRefusalError(AgentError):
    """Raised when Claude's safety classifiers decline the request
    (`stop_reason == "refusal"`). `category` is one of Anthropic's
    refusal categories (e.g. "cyber") or None; `explanation`, if given,
    is a short human-readable reason."""

    def __init__(self, category: Optional[str], explanation: Optional[str]):
        self.category = category
        self.explanation = explanation
        super().__init__(
            f"Claude declined the request (category={category!r}): "
            f"{explanation or 'no explanation given'}"
        )


class AgentConfig:
    def __init__(self, model: str = "claude-opus-5", max_tokens: int = 8192):
        self.model = model
        self.max_tokens = max_tokens


class Reasoner:
    """Calls the Claude API once per `decide()` call and returns a Decision."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client=None,
        config: Optional[AgentConfig] = None,
    ):
        self._settings = settings or load_settings()

        if not self._settings.anthropic_api_key:
            raise AgentAuthError(
                "ANTHROPIC_API_KEY is not set. See .env.example for the "
                "required environment variable."
            )

        self._config = config or AgentConfig()

        if client is not None:
            self._client = client
        else:
            import anthropic  # lazy: only needed for real (non-test) usage

            self._client = anthropic.Anthropic(api_key=self._settings.anthropic_api_key)

    def decide(
        self,
        instrument: str,
        structure_state: StructureState,
        context_snapshot: Optional[dict] = None,
        playbook_rules: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> Decision:
        system_blocks, user_content = build_prompt(
            instrument, structure_state, context_snapshot, playbook_rules
        )

        try:
            response = self._client.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=system_blocks,
                tools=[DECISION_TOOL],
                tool_choice={"type": "tool", "name": DECISION_TOOL_NAME},
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as e:  # normalize the Anthropic SDK's own exception hierarchy
            raise AgentError(f"Claude API call failed: {e}") from e

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            explanation = getattr(details, "explanation", None) if details else None
            raise AgentRefusalError(category, explanation)

        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_use is None:
            raise AgentError(
                f"Expected a {DECISION_TOOL_NAME!r} tool_use block, got "
                f"stop_reason={response.stop_reason!r} with no tool_use content"
            )

        return _decision_from_tool_input(
            tool_use.input, instrument, timestamp or datetime.now(timezone.utc)
        )


def _decision_from_tool_input(raw: dict, instrument: str, timestamp: datetime) -> Decision:
    try:
        action = Action(raw["action"])
    except ValueError as e:
        raise AgentError(f"Model returned an unknown action {raw.get('action')!r}") from e

    direction_raw = raw.get("direction")
    try:
        direction = Direction(direction_raw) if direction_raw else None
    except ValueError as e:
        raise AgentError(f"Model returned an unknown direction {direction_raw!r}") from e

    try:
        return Decision(
            timestamp=timestamp,
            action=action,
            instrument=raw.get("instrument") or instrument,
            direction=direction,
            entry=raw.get("entry"),
            stop=raw.get("stop"),
            target=raw.get("target"),
            confidence=raw.get("confidence"),
            rationale=raw["rationale"],
        )
    except ValueError as e:
        # Decision.__post_init__ enforces the same discipline rules
        # (non-empty rationale, direction required on entry, confidence in
        # range) as a defense-in-depth check against a malformed or
        # hallucinated tool call slipping past the schema.
        raise AgentError(f"Model returned an invalid decision: {e}") from e
