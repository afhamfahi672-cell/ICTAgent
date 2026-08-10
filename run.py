#!/usr/bin/env python3
"""
Entry point for running the paper-trading decision loop.

Usage:
    cp .env.example .env      # fill in your API keys first — see README
    python run.py             # runs ONE decision cycle and exits
    python run.py --forever   # runs continuously (Ctrl+C to stop)

Reads the instrument list from ICTAGENT_WATCHLIST in your .env — a
comma-separated list of Twelve Data symbols, e.g. "EUR/USD,GBP/USD".
Defaults to "EUR/USD" alone if not set.

Wires up the forex leg via Twelve Data (data/twelvedata.py) — a plain
market-data API with no brokerage account or country restriction,
unlike OANDA, which doesn't serve Indian residents. Pass
`--provider oanda` if you're not in that situation and would rather use
OANDA (needs OANDA_API_TOKEN/OANDA_ACCOUNT_ID instead of
TWELVEDATA_API_KEY). See README.md's "Running the loop" section for how
to add a Kite Connect (Indian equities) watchlist entry once you have
that subscription.

This script is paper-trading only. See config/settings.py and README's
"Phase gate" section for how live trading stays locked out regardless
of what this script does.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def _fail(message: str) -> None:
    """Print a plain, non-scary error and exit — no Python traceback for
    the everyday case of a missing/misconfigured API key."""
    raise SystemExit(f"\n{message}\n\nSee .env.example and README.md for setup steps.")


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader — no extra dependency for something this
    small. A real environment variable already set always wins over the
    file, so `FOO=bar python run.py` still overrides .env."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run the ICTAgent paper-trading decision loop.")
    parser.add_argument("--forever", action="store_true", help="Run continuously instead of one cycle.")
    parser.add_argument(
        "--interval", type=int, default=15 * 60,
        help="Seconds between cycles in --forever mode (default 900 = 15 minutes).",
    )
    parser.add_argument(
        "--provider", choices=["twelvedata", "oanda"], default="twelvedata",
        help="Forex data source (default twelvedata — see module docstring for why).",
    )
    parser.add_argument(
        "--candle-interval", default=None,
        help='Candle size. Twelve Data: e.g. "15min" (default). OANDA: e.g. "M15".',
    )
    args = parser.parse_args()

    # Imports deliberately happen after load_dotenv() so config.settings
    # picks up whatever .env just set, and after argparse so --help works
    # even with nothing configured yet.
    from ictagent.agent.reasoner import AgentAuthError
    from ictagent.config.settings import load_settings
    from ictagent.cycle import DecisionCycleRunner, WatchedInstrument

    settings = load_settings()
    print(f"Phase: {settings.phase.value} (live trading enabled: {settings.live_trading_enabled})")

    default_watchlist = "EUR/USD" if args.provider == "twelvedata" else "EUR_USD"
    watchlist_env = os.environ.get("ICTAGENT_WATCHLIST", default_watchlist)
    instruments = [s.strip() for s in watchlist_env.split(",") if s.strip()]
    print(f"Data source: {args.provider}")
    print(f"Watchlist: {', '.join(instruments)}")

    if args.provider == "oanda":
        from ictagent.data.oanda import OandaAuthError, OandaClient

        candle_interval = args.candle_interval or "M15"
        try:
            client = OandaClient(settings=settings)
        except OandaAuthError as e:
            _fail(f"OANDA isn't set up yet: {e}")

        def make_fetcher(instrument: str):
            return lambda: client.fetch_candles(instrument, granularity=candle_interval, count=300)
    else:
        from ictagent.data.twelvedata import TwelveDataAuthError, TwelveDataClient

        candle_interval = args.candle_interval or "15min"
        try:
            client = TwelveDataClient(settings=settings)
        except TwelveDataAuthError as e:
            _fail(f"Twelve Data isn't set up yet: {e}")

        def make_fetcher(instrument: str):
            return lambda: client.fetch_candles(instrument, interval=candle_interval, count=300)

    watchlist = [
        WatchedInstrument(instrument=instrument, fetch_candles=make_fetcher(instrument))
        for instrument in instruments
    ]

    def on_cycle(results) -> None:
        for r in results:
            if hasattr(r, "decision"):
                d = r.decision
                print(
                    f"[{d.timestamp}] {r.instrument}: {d.action.value.upper()} "
                    f"(confidence={d.confidence}) — {d.rationale}"
                )
                print(f"    execution: {r.execution_result.status}")
            else:
                print(f"[ERROR] {r.instrument}: {r.error}")

    try:
        runner = DecisionCycleRunner(watchlist, settings=settings, on_cycle=on_cycle)
    except AgentAuthError as e:
        _fail(f"Claude isn't set up yet: {e}")

    if args.forever:
        print(f"Running every {args.interval} seconds. Press Ctrl+C to stop.")
        try:
            runner.run_forever(interval_seconds=args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        runner.run_once()


if __name__ == "__main__":
    main()
