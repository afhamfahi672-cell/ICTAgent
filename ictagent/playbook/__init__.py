"""
ICT rules/knowledge base, loaded into the agent's reasoning context.

`base_rules.md` is the current ruleset (plain markdown for now — a
structured JSON/YAML form can be added later if agent/ needs to
selectively pull individual rules by tag rather than loading the whole
document each cycle).
"""

from pathlib import Path

BASE_RULES_PATH = Path(__file__).parent / "base_rules.md"


def load_base_rules() -> str:
    return BASE_RULES_PATH.read_text()
