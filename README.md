# ICTAgent

An LLM-reasoning trading agent built on ICT (Inner Circle Trader) / Smart
Money Concepts — market structure, liquidity, fair value gaps, order
blocks, kill zones, and Optimal Trade Entry (OTE). Deterministic Python
code computes market structure from OHLCV data; an LLM (Claude) reasons
over that structure plus market context each decision cycle and produces
a trade decision with explicit, logged rationale.

Two independent legs share the same agent architecture:

1. **Indian equities + index F&O** — via Zerodha Kite Connect
2. **Forex** — via OANDA v20 REST API

## Status

`structure/` is implemented and unit-tested against synthetic OHLCV
data — swing detection, BOS/CHoCH, equal highs/lows, fair value gaps,
order blocks, and OTE/Fibonacci zones. `config/` has the phase gate.
Everything else (`data/`, `context/`, `agent/`, `execution/`,
`logging/`) is scaffolded with docstrings describing what's planned but
not yet implemented — see the phasing below.

## Phasing (strict order)

1. **Paper trading / simulation only**, against historical + live data
2. Manual review of reasoning quality and trade logs
3. **Semi-auto** — agent proposes trades, a human confirms each one
4. **Fully autonomous** — only after 2 and 3 are validated over time

No trade execution logic runs against a live account until explicitly
enabled. See [Phase gate](#phase-gate) below.

## Architecture

```
ictagent/
  structure/   Deterministic market structure computation (pure Python,
               no broker/LLM dependency). Swing highs/lows, BOS/CHoCH,
               equal highs/lows (liquidity), fair value gaps, order
               blocks, OTE/Fibonacci zones. Testable standalone.
  data/        Market data ingestion — Kite Connect + OANDA (planned)
  context/     Fundamentals/news + kill-zone/session timing (planned)
  playbook/    ICT rules/knowledge base (base_rules.md), loaded into
               the agent's reasoning context
  agent/       Calls the Claude API each cycle with structure + context
               + playbook rules, returns a Decision (planned; the
               Decision type itself is already defined)
  execution/   Order placement, phase-gated (planned)
  logging/     Persistent, queryable decision + rationale log (planned)
  config/      Settings, credentials (env-var only), phase gate
```

Every agent decision — including "no trade" — carries a required
human-readable rationale, stored alongside the decision for later audit.
Kite Connect and OANDA are kept as fully decoupled integrations with
separate auth/session handling, so either can be developed and tested
independently.

## Phase gate

Two independent environment variables, not one, control whether the
agent can ever place a real order — see `ictagent/config/settings.py`:

```
ICTAGENT_PHASE=paper                          # paper | semi_auto | autonomous
ICTAGENT_LIVE_TRADING_CONFIRM=                 # must equal an exact literal string
```

`Settings.live_trading_enabled` is only `True` when phase is not `paper`
**and** the confirm string matches exactly. `execution/` must call
`Settings.require_live_trading_enabled()` before any live broker call —
this is enforced and unit-tested (`tests/test_settings.py`). A single
accidentally-flipped variable is never enough to unlock live trading.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in credentials; .env is gitignored
```

## Running tests

```bash
pytest
```

All `structure/` logic (swings, BOS/CHoCH, liquidity pools, FVGs, order
blocks, OTE zones, and the full pipeline) is covered against hand-traced
synthetic OHLCV fixtures in `tests/fixtures.py` — no broker connection
or network access required.

## Credentials

All API credentials (Kite Connect, OANDA, Claude API, news providers)
are read from environment variables only — see `.env.example`. Nothing
is ever hardcoded in this repo.
