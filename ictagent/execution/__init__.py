"""
Order placement, gated by the current phase.

Not implemented yet. Planned responsibilities:

  execution/kite.py     Kite Connect order placement.
  execution/oanda.py    OANDA v20 order placement.
  execution/gate.py     Phase-aware dispatcher: routes a `Decision`
                         (agent/types.py) to either a log-only simulated
                         fill, a propose-and-confirm flow, or a real
                         broker call — never the broker call directly.

Hard rule: nothing in this package is ever allowed to call a live broker
order endpoint without first calling
`ictagent.config.settings.Settings.require_live_trading_enabled()`,
which only returns without raising when BOTH `ICTAGENT_PHASE` is not
"paper" AND `ICTAGENT_LIVE_TRADING_CONFIRM` matches the exact confirm
string. See ictagent/config/settings.py for the full gate design.

Until this module is built out, there is no code path anywhere in this
repo that can place a live order.
"""
