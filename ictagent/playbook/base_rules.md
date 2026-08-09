# ICTAgent Playbook — Base Rules (v0.1)

This is the starting knowledge base loaded into the agent's reasoning
context alongside each cycle's computed `StructureState` and market
context. It describes standard, widely-used Smart Money Concepts / ICT
terminology and heuristics — not sourced from any single creator's
proprietary course material. Expected to be refined and expanded over
time as reasoning quality is reviewed (Phase 2).

The agent reasons **over** these rules and the deterministic output of
`structure/`. It does not compute structure itself, and it must not
invent structure that isn't present in the supplied `StructureState`.

## 1. Market structure

- Structure is read from swing highs/lows, not indicators.
- **BOS (Break of Structure)**: a close beyond the most recent relevant
  swing point in the direction of the prevailing trend — continuation.
- **CHoCH (Change of Character)**: a close beyond the most recent
  relevant swing point *against* the prevailing trend — first sign of a
  potential reversal. Treat a single CHoCH as a warning to reassess
  bias, not on its own sufficient grounds for a counter-trend entry;
  prefer to see it followed by a subsequent BOS in the new direction
  before trading the reversal.
- Prefer trading in the direction of the higher-timeframe trend; use
  lower-timeframe structure only to refine entry timing within that
  bias, not to override it without a clear CHoCH first.

## 2. Liquidity

- Equal highs/equal lows mark resting liquidity (stop clusters) that
  price is statistically drawn to run before reversing.
- A liquidity sweep — price wicking through a liquidity pool and closing
  back inside the prior range — is treated as a stronger reversal signal
  than an unswept level.
- Do not chase price into a liquidity pool that hasn't been swept yet;
  wait for the sweep and the structural reaction that follows it.

## 3. Fair Value Gaps (FVG)

- A 3-candle imbalance where price is expected to eventually return to
  rebalance, at least partially, before continuing.
- An unmitigated FVG in the direction of the current bias is a candidate
  entry zone; a fully mitigated FVG is lower-priority context, not a
  live entry zone.
- FVGs against the prevailing trend are treated as potential resistance/
  support for the current move, not entry signals on their own.

## 4. Order blocks

- The last opposing candle before the impulsive move that produced a
  structural break. Bullish order block = last down-close candle before
  an up-move that breaks structure up; bearish = mirror image.
- An order block is a candidate entry zone only if it hasn't already
  been mitigated (price hasn't fully traded back through it since it
  formed) and only in the direction consistent with current structure.
- Confluence with an FVG or the OTE zone inside the same leg raises
  confidence; an order block with no such confluence is weaker evidence
  on its own.

## 5. Kill zones / session timing

- Highest-conviction setups are expected inside defined session windows
  (e.g. London open, New York AM) where volatility and directional
  follow-through are historically concentrated — see `context/sessions.py`
  once implemented.
- Outside kill zones, or immediately around high-impact scheduled news
  (see `context/calendar.py`), default toward "no trade" unless the
  setup is exceptionally clean; volatility around news events is not
  the same as a valid structural move.

## 6. Optimal Trade Entry (OTE)

- The 0.62–0.79 Fibonacci retracement zone of the most recent impulse
  leg (discount for longs, premium for shorts) — see
  `structure/ote.py` for the exact computation and configurable ratios.
- Strongest entries occur where OTE overlaps an order block and/or an
  unmitigated FVG in the same direction — three independent
  confirmations lining up in the same zone.
- A price at the OTE level with no supporting order block/FVG and no
  structural confirmation (no BOS/CHoCH in that direction yet) is weak
  evidence by itself.

## 7. Decision discipline

- Every decision — including "no trade" — must state which of the above
  elements were present, which were absent, and why they were or were
  not sufficient. A "no trade" with no rationale is treated as a bug in
  the agent, not an acceptable output.
- Confidence should reflect confluence: more independent structural
  elements agreeing (BOS/CHoCH + liquidity sweep + FVG + order block +
  OTE) → higher confidence. A single element in isolation should not
  produce a high-confidence trade decision.
- The agent must not override or "correct" the deterministic
  `StructureState` it is given. If the structure looks wrong, that's a
  bug to report, not something to reason around.
