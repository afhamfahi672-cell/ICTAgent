"""
Hosted dashboard — a private, login-protected website for watching the
agent's decisions and controlling its phase, deployable to a host like
Render (see render.yaml at the repo root).

  web/auth.py         Session-cookie auth against DASHBOARD_PASSWORD /
                       SESSION_SECRET_KEY (env vars only — set on the
                       hosting provider's own settings page, never in
                       this app).
  web/phase_store.py   Runtime phase override so the dashboard's phase
                       control takes effect without a redeploy.
                       ICTAGENT_LIVE_TRADING_CONFIRM stays env-var only —
                       not settable from here.
  web/scheduler.py     Background thread running the decision cycle on
                       an interval, in-process (no separate worker).
  web/app.py           The FastAPI app itself: login, dashboard, phase
                       control, "run a cycle now".

Nothing in this package accepts or stores API keys — see the module
docstrings above for where those actually go.
"""
