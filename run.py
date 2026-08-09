#!/usr/bin/env python3
"""
Entry point for running the paper-trading decision loop.

Usage:
    cp .env.example .env      # fill in your API keys first — see README
    python run.py             # runs ONE decision cycle and exits
    python run.py --forever   # runs continuously (Ctrl+C to stop)

Reads the instrument list from ICTAGENT_WATCHLIST in your .env — a
comma-separated list of OANDA instrument names, e.g. "EUR_USD,GBP_USD".
Defaults to "EUR_USD" alone if not set.

Only wires up the OANDA (forex) leg for now, since it's the one that
needs nothing beyond a free practice account to try. See README.md's
"Running the loop" section for how to add a Kite Connect (Indian
equities) watchlist entry once you have that subscription.

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
    parser.add_argument("--granularity", default="M15", help="OANDA candle granularity (default M15).")
    args = parser.parse_args()

    # Imports deliberately happen after load_dotenv() so config.settings
    # picks up whatever .env just set, and after argparse so --help works
    # even with nothing configured yet.
    from ictagent.agent.reasoner import AgentAuthError
    from ictagent.config.settings import load_settings
    from ictagent.cycle import DecisionCycleRunner, WatchedInstrument
    from ictagent.data.oanda import OandaAuthError, OandaClient

    settings = load_settings()
    print(f"Phase: {settings.phase.value} (live trading enabled: {settings.live_trading_enabled})")

    watchlist_env = os.environ.get("ICTAGENT_WATCHLIST", "EUR_USD")
    instruments = [s.strip() for s in watchlist_env.split(",") if s.strip()]
    print(f"Watchlist: {', '.join(instruments)}")

    try:
        oanda = OandaClient(settings=settings)
    except OandaAuthError as e:
        _fail(f"OANDA isn't set up yet: {e}")

    def make_fetcher(instrument: str):
        return lambda: oanda.fetch_candles(instrument, granularity=args.granularity, count=300)

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
