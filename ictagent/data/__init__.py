"""
Market data ingestion — candles and live quotes.

Not implemented yet. Planned layout, once we start on this module:

  data/kite.py    Zerodha Kite Connect client: auth/session handling,
                  historical candle fetch, live quote/tick subscription.
  data/oanda.py   OANDA v20 REST client: auth/session handling,
                  historical candle fetch, live pricing stream.
  data/base.py    Shared interface both adapters implement (e.g. a
                  `fetch_candles(instrument, timeframe, ...) -> list[Candle]`
                  contract) so structure/ and agent/ never need to know
                  which broker produced the data.

Kite and OANDA are kept as fully separate adapters with separate
auth/session handling — one must be developable/testable without the
other. Both adapters convert broker-native responses into
`ictagent.structure.types.Candle`, the same type structure/ already
consumes, so nothing downstream needs a broker-specific code path.

Credentials are read via ictagent.config.settings.load_settings() —
never hardcoded here.
"""
