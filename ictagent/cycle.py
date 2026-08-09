"""
Decision-cycle orchestration — the piece that actually runs structure/,
context/, agent/, logging/, and execution/ together, on a schedule, for
a configured watchlist of instruments. Nothing before this module ran
itself; this is what turns the independently-tested pieces into a
process that can sit and watch a market.

This module deliberately knows nothing about brokers. Each
`WatchedInstrument` carries an injected `fetch_candles` callable — wire
in `OandaClient.fetch_candles`, `KiteClient.fetch_candles`, a canned
list for a backtest, or a fake for tests. `compute_structure()` doesn't
care where candles came from, and neither does this module.

One decision cycle, per instrument:
  1. fetch candles (injected)
  2. compute_structure() -> StructureState
  3. gather context (session/kill-zone timing always; `extra_context`
     if supplied — e.g. news for that instrument)
  4. Reasoner.decide() -> Decision
  5. DecisionLog.record() -> persisted, always, including no_trade
  6. ExecutionGate.handle() -> simulated fill in paper phase (the
     default; see execution/gate.py for what every other phase does)

A failure on one instrument (bad data, a Claude API error, a refusal)
is caught and reported as a CycleError rather than aborting the whole
pass — a scheduled process watching ten instruments shouldn't go dark
because one of them hit a transient problem.

Still Phase 1: nothing here places a live order — that guarantee lives
in execution/gate.py and holds regardless of what this loop does.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Union

from ictagent.agent.reasoner import Reasoner
from ictagent.agent.types import Decision
from ictagent.config.settings import Settings, load_settings
from ictagent.context.sessions import get_session_context
from ictagent.execution.gate import ExecutionGate
from ictagent.execution.types import ExecutionResult
from ictagent.logging.store import DecisionLog
from ictagent.structure.pipeline import StructureConfig, compute_structure
from ictagent.structure.types import Candle, StructureState

FetchCandles = Callable[[], list[Candle]]
ContextProvider = Callable[[], dict]


@dataclass
class WatchedInstrument:
    """One instrument the runner processes each cycle.

    `fetch_candles` is injected rather than this module knowing about
    brokers — e.g. `lambda: oanda_client.fetch_candles("EUR_USD", "M15")`
    or `lambda: kite_client.fetch_candles("NSE", "INFY", "day", ...)`.
    `extra_context`, if given, is merged into the context snapshot handed
    to the agent (e.g. `lambda: {"news": [a.to_dict() for a in ...]}`).
    """

    instrument: str
    fetch_candles: FetchCandles
    structure_config: StructureConfig = field(default_factory=StructureConfig)
    extra_context: Optional[ContextProvider] = None


@dataclass
class CycleResult:
    instrument: str
    decision: Decision
    structure_state: StructureState
    execution_result: ExecutionResult
    decision_log_id: int

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "decision": self.decision.to_dict(),
            "structure": self.structure_state.to_dict(),
            "execution": self.execution_result.to_dict(),
            "decision_log_id": self.decision_log_id,
        }


@dataclass
class CycleError:
    """One instrument failed this cycle; the rest of the watchlist still ran."""

    instrument: str
    error: str

    def to_dict(self) -> dict:
        return {"instrument": self.instrument, "error": self.error}


class DecisionCycleRunner:
    def __init__(
        self,
        watchlist: list[WatchedInstrument],
        settings: Optional[Settings] = None,
        reasoner: Optional[Reasoner] = None,
        decision_log: Optional[DecisionLog] = None,
        execution_gate: Optional[ExecutionGate] = None,
        playbook_rules: Optional[str] = None,
        playbook_version: Optional[str] = None,
        on_cycle: Optional[Callable[[list[Union[CycleResult, CycleError]]], None]] = None,
    ):
        self._watchlist = watchlist
        self._settings = settings or load_settings()
        self._reasoner = reasoner or Reasoner(settings=self._settings)
        self._decision_log = decision_log or DecisionLog()
        self._execution_gate = execution_gate or ExecutionGate(settings=self._settings)
        self._playbook_rules = playbook_rules  # None -> Reasoner/build_prompt's own default
        self._playbook_version = playbook_version
        self._on_cycle = on_cycle

    def run_once(self) -> list[Union[CycleResult, CycleError]]:
        results: list[Union[CycleResult, CycleError]] = []
        for item in self._watchlist:
            try:
                results.append(self._run_one_instrument(item))
            except Exception as e:
                results.append(CycleError(instrument=item.instrument, error=str(e)))

        if self._on_cycle is not None:
            self._on_cycle(results)

        return results

    def run_forever(
        self,
        interval_seconds: float,
        max_cycles: Optional[int] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Blocking loop: run_once(), sleep, repeat. `max_cycles` bounds
        the loop (used by tests/backtests); omit it for a real,
        indefinitely running process. `sleep` is injectable for tests."""
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            self.run_once()
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                sleep(interval_seconds)

    def _run_one_instrument(self, item: WatchedInstrument) -> CycleResult:
        candles = item.fetch_candles()
        structure_state = compute_structure(candles, item.structure_config)

        context_snapshot: dict = {"session": get_session_context().to_dict()}
        if item.extra_context is not None:
            context_snapshot.update(item.extra_context())

        decision = self._reasoner.decide(
            item.instrument,
            structure_state,
            context_snapshot=context_snapshot,
            playbook_rules=self._playbook_rules,
        )

        log_id = self._decision_log.record(
            decision,
            structure_state=structure_state,
            context_snapshot=context_snapshot,
            playbook_version=self._playbook_version,
        )

        execution_result = self._execution_gate.handle(decision)

        return CycleResult(
            instrument=item.instrument,
            decision=decision,
            structure_state=structure_state,
            execution_result=execution_result,
            decision_log_id=log_id,
        )
