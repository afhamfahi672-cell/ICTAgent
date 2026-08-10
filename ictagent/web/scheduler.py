"""
Runs the decision cycle on a background thread inside the same process
as the web app — no separate worker process/dyno needed, which keeps
this deployable on a single free-tier web service.

Design choices that matter for correctness, not just convenience:

  - `OandaClient` and `Reasoner` are built once, in `__init__` — their
    credentials don't change when the phase does, so there's no reason
    to reconnect every cycle.
  - `PaperBroker` is likewise built once and reused across cycles —
    it's where open simulated positions live. Rebuilding it per cycle
    would silently forget every open position each time the phase
    changed, which defeats the point of paper trading.
  - Only the *phase* is re-resolved every cycle, from `PhaseStore` —
    that's the one thing the dashboard is meant to change live.

Only wires up the OANDA (forex) leg for now, matching run.py.
"""

from __future__ import annotations

import dataclasses
import threading
from typing import Optional

from ictagent.agent.reasoner import Reasoner
from ictagent.config.settings import Settings, load_settings
from ictagent.cycle import CycleError, DecisionCycleRunner, WatchedInstrument
from ictagent.data.oanda import OandaClient
from ictagent.execution.gate import ExecutionGate
from ictagent.execution.simulator import PaperBroker
from ictagent.logging.store import DecisionLog

from .phase_store import PhaseStore


class CycleScheduler:
    def __init__(
        self,
        instruments: list[str],
        decision_log: DecisionLog,
        phase_store: PhaseStore,
        interval_seconds: int,
        granularity: str = "M15",
        settings: Optional[Settings] = None,
        oanda: Optional[OandaClient] = None,
        reasoner: Optional[Reasoner] = None,
        broker: Optional[PaperBroker] = None,
    ):
        self._instruments = instruments
        self._decision_log = decision_log
        self._phase_store = phase_store
        self._interval_seconds = interval_seconds
        self._granularity = granularity
        self._base_settings = settings or load_settings()
        self._oanda = oanda or OandaClient(settings=self._base_settings)
        self._reasoner = reasoner or Reasoner(settings=self._base_settings)
        self._broker = broker or PaperBroker()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.last_error: Optional[str] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def broker(self) -> PaperBroker:
        return self._broker

    def run_once(self) -> list:
        """One cycle, synchronously — used by the background loop and by
        the dashboard's "run now" button alike."""
        effective_phase = self._phase_store.get_phase(default=self._base_settings.phase)
        cycle_settings = dataclasses.replace(self._base_settings, phase=effective_phase)

        watchlist = [
            WatchedInstrument(
                instrument=instrument,
                fetch_candles=self._make_fetcher(instrument),
            )
            for instrument in self._instruments
        ]

        execution_gate = ExecutionGate(settings=cycle_settings, broker=self._broker)
        runner = DecisionCycleRunner(
            watchlist,
            settings=cycle_settings,
            reasoner=self._reasoner,
            decision_log=self._decision_log,
            execution_gate=execution_gate,
        )
        results = runner.run_once()
        self.last_error = next((r.error for r in results if isinstance(r, CycleError)), None)
        return results

    def _make_fetcher(self, instrument: str):
        return lambda: self._oanda.fetch_candles(instrument, granularity=self._granularity, count=300)

    def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:  # a whole-cycle failure shouldn't kill the background thread
                self.last_error = str(e)
            self._stop_event.wait(self._interval_seconds)
