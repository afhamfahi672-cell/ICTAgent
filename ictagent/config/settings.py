"""
Central settings: broker/LLM credentials (env-var only, never hardcoded)
and the phase gate that governs what execution/ is allowed to do.

Phase gate design — deliberately two independent switches, not one:

  ICTAGENT_PHASE                 paper | semi_auto | autonomous
  ICTAGENT_LIVE_TRADING_CONFIRM  must equal the exact literal string
                                  LIVE_TRADING_CONFIRM_STRING

`Settings.live_trading_enabled` is True only when BOTH are set correctly.
A single accidentally-flipped env var (e.g. someone pastes ICTAGENT_PHASE
=autonomous into a shared .env) is not enough by itself to unlock a real
broker call — the confirm string has to be typed out deliberately too.
Every call site in execution/ that is about to touch a live Kite/OANDA
order endpoint must call `Settings.require_live_trading_enabled()` first.

This module only reads configuration; it never talks to a broker or the
Claude API itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class Phase(str, Enum):
    PAPER = "paper"
    SEMI_AUTO = "semi_auto"
    AUTONOMOUS = "autonomous"


LIVE_TRADING_CONFIRM_STRING = "I_UNDERSTAND_THIS_IS_LIVE_MONEY"


@dataclass(frozen=True)
class Settings:
    phase: Phase
    live_trading_confirm: str

    # Zerodha Kite Connect
    kite_api_key: str | None
    kite_api_secret: str | None
    kite_access_token: str | None

    # OANDA v20
    oanda_api_token: str | None
    oanda_account_id: str | None
    oanda_environment: str

    # Claude API
    anthropic_api_key: str | None

    # context/ providers
    news_api_key: str | None

    @property
    def is_paper(self) -> bool:
        return self.phase == Phase.PAPER

    @property
    def live_trading_enabled(self) -> bool:
        """True only when phase is not paper AND the exact confirm string
        has been set. This is the single source of truth execution/ must
        check before placing any order against a real account."""
        return (
            self.phase != Phase.PAPER
            and self.live_trading_confirm == LIVE_TRADING_CONFIRM_STRING
        )

    def require_live_trading_enabled(self) -> None:
        """Call this immediately before any broker call that would place
        a real order. Raises rather than silently downgrading to paper,
        so a misconfiguration fails loudly instead of trading live by
        accident in either direction."""
        if not self.live_trading_enabled:
            raise PermissionError(
                "Live trading is not enabled. Set ICTAGENT_PHASE to "
                "'semi_auto' or 'autonomous' AND ICTAGENT_LIVE_TRADING_CONFIRM "
                f"to the exact string {LIVE_TRADING_CONFIRM_STRING!r} "
                "before any order can be sent to a live broker endpoint."
            )


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build Settings from environment variables (or an injected mapping,
    for tests). Defaults to phase=paper and no live confirm, i.e. the
    safest possible state, whenever ICTAGENT_PHASE is unset or unrecognized."""
    e = env if env is not None else os.environ

    raw_phase = e.get("ICTAGENT_PHASE", Phase.PAPER.value).strip().lower()
    try:
        phase = Phase(raw_phase)
    except ValueError:
        phase = Phase.PAPER

    return Settings(
        phase=phase,
        live_trading_confirm=e.get("ICTAGENT_LIVE_TRADING_CONFIRM", ""),
        kite_api_key=e.get("KITE_API_KEY") or None,
        kite_api_secret=e.get("KITE_API_SECRET") or None,
        kite_access_token=e.get("KITE_ACCESS_TOKEN") or None,
        oanda_api_token=e.get("OANDA_API_TOKEN") or None,
        oanda_account_id=e.get("OANDA_ACCOUNT_ID") or None,
        oanda_environment=e.get("OANDA_ENVIRONMENT", "practice"),
        anthropic_api_key=e.get("ANTHROPIC_API_KEY") or None,
        news_api_key=e.get("NEWS_API_KEY") or None,
    )
