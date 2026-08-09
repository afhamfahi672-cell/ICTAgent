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
`data/oanda.py` and `data/kite.py` are both implemented — historical
candles and live pricing for forex (OANDA v20 REST) and Indian
equities/F&O (Zerodha Kite Connect). `context/`, `agent/` (beyond the
`Decision` type), `execution/`, and `logging/` are scaffolded with
docstrings describing what's planned but not yet implemented — see the
phasing below.

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
  data/        Market data ingestion. oanda.py and kite.py both
               implemented (candles + live pricing).
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

## OANDA adapter

`ictagent.data.oanda.OandaClient` talks to OANDA's v20 REST API
directly over `requests` (not the unmaintained `oandapyV20` SDK, whose
sdist fails to build against current setuptools). Requires `OANDA_API_TOKEN`
and, for pricing endpoints, `OANDA_ACCOUNT_ID`; `OANDA_ENVIRONMENT` picks
`practice` (default) or `live`.

```python
from ictagent.data.oanda import OandaClient

client = OandaClient()  # reads credentials from env via config.settings
candles = client.fetch_candles("EUR_USD", granularity="M15", count=500)
quotes = client.get_current_price(["EUR_USD", "GBP_USD"])
for quote in client.stream_prices(["EUR_USD"]):
    ...  # long-lived generator; run it in its own thread/task
```

`fetch_candles` drops incomplete (still-forming) candles by default —
structure/ must never compute over a candle whose OHLC can still change.
All response parsing is pure and unit-tested without live credentials or
network access (`tests/test_oanda.py`); `OandaClient` itself accepts an
injectable `session` for the same reason.

## Kite Connect adapter

`ictagent.data.kite.KiteClient` wraps the official `kiteconnect` SDK
(`pip install -e ".[data]"` pulls it in; imported lazily so the module
and its tests don't require it). Requires `KITE_API_KEY` always, plus
either a fresh `KITE_ACCESS_TOKEN` already in the environment, or a
one-time-per-day login:

```python
from ictagent.data.kite import KiteClient

client = KiteClient()
print(client.login_url())          # send the user here to log into Kite
# ...user logs in, gets redirected back with a request_token...
client.generate_session(request_token)  # exchanges it for today's access_token

candles = client.fetch_candles("NSE", "INFY", interval="day",
                                from_date="2024-01-01", to_date="2024-06-01")
quotes = client.get_quote(["NSE:INFY", "NSE:NIFTY 50"])
```

Unlike OANDA's long-lived token, Kite's `access_token` is only valid for
roughly one trading day — this client doesn't automate the browser login
step (that inherently needs a human once a day), it just exposes
`login_url()`/`generate_session()` for whatever daily login step gets
built later. Live tick-by-tick streaming (`KiteTicker`, WebSocket-based)
isn't implemented yet — `get_quote()` gives a REST snapshot, which is
enough for a periodic decision-cycle loop. All parsing is unit-tested
offline (`tests/test_kite.py`) against an injected fake client.
