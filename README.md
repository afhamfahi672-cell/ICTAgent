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
equities/F&O (Zerodha Kite Connect). `context/` is implemented —
kill-zone/session timing (no external API) and news + economic calendar
via Finnhub. `agent/` is implemented — `Reasoner.decide()` calls the
Claude API with structure + context + playbook rules and returns a
`Decision`. `logging/` is implemented — every decision is persisted with
its full structure/context snapshot, queryable by instrument/action/date/
confidence. `execution/` has a full paper-trading simulator wired up to
the phase gate — nothing beyond simulated fills exists yet, and the
`autonomous` phase is hard-blocked (see below). Real broker order
placement (`execution/kite.py`, `execution/oanda.py`) isn't built.
`ictagent/cycle.py` is the orchestrator that actually runs a watchlist
of instruments through all of the above on a schedule — this is what
turns the pieces into a process that can sit and watch a market.

148/148 tests passing, all offline (no live credentials or network
access needed for the suite).

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
  context/     Implemented. sessions.py (kill-zone/session timing, no
               external API) + finnhub.py (news + economic calendar).
  playbook/    ICT rules/knowledge base (base_rules.md), loaded into
               the agent's reasoning context
  agent/       Implemented. Reasoner.decide() calls the Claude API each
               cycle with structure + context + playbook rules, forces
               a Decision via strict tool use.
  execution/   Implemented (paper simulation only). ExecutionGate routes
               a Decision to PaperBroker (paper phase), a
               pending-confirmation result (semi_auto), or a hard-gated
               NotImplementedError (autonomous) — no live order code
               exists yet, in any phase.
  logging/     Implemented. DecisionLog persists every decision + full
               structure/context snapshot to SQLite; query.py filters
               by instrument/action/date/confidence for Phase 2 review.
  config/      Settings, credentials (env-var only), phase gate
  cycle.py     Implemented. DecisionCycleRunner — the orchestrator that
               runs a watchlist of instruments through all of the above
               on a schedule. Knows nothing about brokers itself; each
               watched instrument's candle fetch is injected.
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

## Context layer

`ictagent.context.sessions.get_session_context(moment)` — kill-zone and
trading-session timing, no external API, correct across DST via
`zoneinfo` (not a fixed UTC offset table, which would silently drift out
of sync for half the year):

```python
from ictagent.context.sessions import get_session_context

ctx = get_session_context()  # defaults to now (UTC)
ctx.open_sessions        # e.g. ["london", "new_york"]
ctx.active_kill_zones    # e.g. ["ny_am_kz"]
ctx.in_kill_zone         # bool
```

`ictagent.context.finnhub.FinnhubClient` — news headlines + economic
calendar via Finnhub, chosen as a starting provider (see the module
docstring for the free-tier caveat on the calendar endpoint and how to
swap providers later). Requires `NEWS_API_KEY`:

```python
from ictagent.context.finnhub import FinnhubClient

client = FinnhubClient()
headlines = client.get_news(category="forex")
events = client.get_economic_calendar("2026-01-01", "2026-01-07")
```

Both are unit-tested offline (`tests/test_sessions.py`,
`tests/test_finnhub.py`) — `FinnhubClient` accepts an injectable
`session`, same pattern as the OANDA/Kite adapters.

## Agent (reasoning layer)

`ictagent.agent.reasoner.Reasoner.decide()` calls the Claude API once
per decision cycle and returns a `Decision` — the structure comes from
`structure/`, the model reasons over it plus context and playbook rules,
and never computes structure itself (it's explicitly instructed not to
report structural elements absent from the supplied data). Output is
forced into shape via **strict tool use**: a single `record_trade_decision`
tool with `strict: true`, `tool_choice` pinned to it — not "ask for JSON
and hope."

```python
from ictagent.agent.reasoner import Reasoner
from ictagent.structure.pipeline import compute_structure
from ictagent.context.sessions import get_session_context

reasoner = Reasoner()  # reads ANTHROPIC_API_KEY from env via config.settings
structure_state = compute_structure(candles)
decision = reasoner.decide(
    "EUR_USD",
    structure_state,
    context_snapshot={"session": get_session_context().to_dict()},
)
print(decision.action, decision.rationale)
```

**Model**: defaults to `claude-opus-5` — current best-practice guidance
is to default to Opus-tier for real reasoning work and treat cost as an
explicit choice, not something to quietly optimize away. For a live
agent running many decision cycles a day that cost is real; if it
becomes a problem at your cycle frequency, pass
`Reasoner(config=AgentConfig(model="claude-sonnet-5"))` — nothing else
changes. The static half of the prompt (playbook rules + instructions)
is marked cacheable (`cache_control`), since it's identical on every
cycle and only the structure/context JSON changes.

Safety-classifier refusals (`stop_reason == "refusal"`, an Opus 5
behavior) raise `AgentRefusalError` rather than crashing on an
unexpected response shape. All prompt construction and request/response
wiring is unit-tested offline (`tests/test_prompts.py`,
`tests/test_reasoner.py`) against an injected fake Claude client — no
API key needed to run the suite.

## Decision log

`ictagent.logging.DecisionLog` persists every decision — including
NO_TRADE — with the full `StructureState` and context snapshot that
produced it, to a local SQLite file:

```python
from ictagent.logging import DecisionLog, list_decisions

log = DecisionLog()  # ictagent_decisions.db by default
log.record(decision, structure_state=structure_state, context_snapshot=context, playbook_version="v0.1")

recent = list_decisions(log, instrument="EUR_USD", action="enter", min_confidence=0.6)
```

This is the audit trail Phase 2 (manual reasoning-quality review) reads
from — the point is to make the agent's reasoning reviewable, not just
its trades. `DecisionLog` accepts an injectable `connection` (e.g.
`sqlite3.connect(":memory:")`), so `tests/test_logging.py` runs with no
filesystem writes.

## Execution (paper simulation only)

`ictagent.execution.ExecutionGate` routes a `Decision` by the current
phase — it never places a real order in any phase yet:

```python
from ictagent.execution import ExecutionGate

gate = ExecutionGate()  # reads ICTAGENT_PHASE from env; defaults to paper
result = gate.handle(decision)
print(result.status)  # "simulated_fill" in paper phase
```

- **paper** (default): `PaperBroker` simulates the fill in memory — opens/
  closes positions, tracks P&L — with no network call at all.
- **semi_auto**: returns `"pending_confirmation"` and stops; no broker
  call is made. Actual human-confirms-then-places-order wiring isn't
  built yet.
- **autonomous**: requires `Settings.require_live_trading_enabled()` to
  pass first (both `ICTAGENT_PHASE` and `ICTAGENT_LIVE_TRADING_CONFIRM`
  correctly set — see [Phase gate](#phase-gate)), and even then raises
  `NotImplementedError` — `execution/kite.py`/`execution/oanda.py` order
  placement don't exist. There is no code path anywhere in this repo
  that can place a live order.

`HOLD`/`NO_TRADE` decisions short-circuit before any phase check —
nothing to execute regardless of phase. Fully unit-tested
(`tests/test_execution.py`), including both autonomous-phase failure
modes (`PermissionError` without the confirm string, `NotImplementedError`
with it).

## Running the loop

`ictagent.cycle.DecisionCycleRunner` is what actually watches a market —
it runs a configured watchlist through fetch → structure → context →
agent → log → execute, once (`run_once()`) or on a schedule
(`run_forever()`). It doesn't know about brokers itself: each
`WatchedInstrument`'s candle fetch is injected, so the same runner works
against OANDA, Kite, or canned data for a backtest.

```python
from ictagent.cycle import DecisionCycleRunner, WatchedInstrument
from ictagent.data.oanda import OandaClient
from ictagent.structure.pipeline import StructureConfig

oanda = OandaClient()  # reads OANDA_* from env

watchlist = [
    WatchedInstrument(
        instrument="EUR_USD",
        fetch_candles=lambda: oanda.fetch_candles("EUR_USD", granularity="M15", count=300),
        structure_config=StructureConfig(swing_lookback=2),
    ),
    WatchedInstrument(
        instrument="GBP_USD",
        fetch_candles=lambda: oanda.fetch_candles("GBP_USD", granularity="M15", count=300),
    ),
]

runner = DecisionCycleRunner(
    watchlist,
    on_cycle=lambda results: print(f"cycle: {len(results)} instrument(s) processed"),
)

runner.run_once()                                    # one pass, for testing/inspection
# runner.run_forever(interval_seconds=15 * 60)        # every 15 minutes, indefinitely
```

Each pass: fetches candles, computes structure, attaches session/kill-zone
context (plus anything from `extra_context`, e.g. news), asks the agent
for a `Decision`, persists it to the `DecisionLog` — including
`no_trade`, always — then hands it to the `ExecutionGate` (a simulated
fill by default; nothing live). A failure on one instrument (bad data, a
Claude API error, a refusal) becomes a `CycleError` in the results list
rather than aborting the rest of the watchlist — one bad symbol shouldn't
take a scheduled process down. Fully unit-tested against a fake Claude
client and an in-memory decision log (`tests/test_cycle.py`), including
the failure-isolation and scheduling behavior.

This is still just Phase 1 (paper simulation) — `run_forever()` will
happily sit and generate simulated trades and a full decision log for
you to review, which is exactly what Phase 2 needs.
