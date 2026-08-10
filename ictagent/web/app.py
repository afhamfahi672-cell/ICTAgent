"""
FastAPI dashboard: login-protected decision log viewer + phase control.

Routes:
  GET  /login     - password form
  POST /login     - check password, set signed session cookie
  GET  /logout    - clear session cookie
  GET  /          - dashboard (decisions, phase control) — requires auth
  POST /phase     - change the runtime phase override — requires auth
  POST /run-now   - trigger one decision cycle immediately — requires auth

Nowhere on this site accepts API keys — those stay in your hosting
provider's own environment-variable settings, never in this app's
database or forms. See README's "Hosting a private dashboard" section
and render.yaml.

`create_app()` takes everything as optional, injectable arguments
(decision_log, phase_store, scheduler) so the whole app is testable with
FastAPI's TestClient and no real credentials — see tests/test_web_app.py.
The module-level `app` at the bottom is what a real deployment's
`uvicorn ictagent.web.app:app` command points at.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ictagent.config.settings import Phase, load_settings
from ictagent.logging.query import list_decisions
from ictagent.logging.store import DecisionLog

from .auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    AuthConfigError,
    check_password,
    create_session_token,
    verify_session_token,
)
from .phase_store import PhaseStore
from .scheduler import CycleScheduler

TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app(
    decision_log: Optional[DecisionLog] = None,
    phase_store: Optional[PhaseStore] = None,
    scheduler: Optional[CycleScheduler] = None,
    auto_start_scheduler: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        if app.state.scheduler is None and auto_start_scheduler:
            try:
                watchlist_env = os.environ.get("ICTAGENT_WATCHLIST", "EUR_USD")
                interval = int(os.environ.get("ICTAGENT_CYCLE_INTERVAL_SECONDS", str(15 * 60)))
                sched = CycleScheduler(
                    instruments=[s.strip() for s in watchlist_env.split(",") if s.strip()],
                    decision_log=app.state.decision_log,
                    phase_store=app.state.phase_store,
                    interval_seconds=interval,
                )
                sched.start()
                app.state.scheduler = sched
            except Exception as e:
                # Missing OANDA/Claude keys, etc. — don't take the whole
                # site down; show the problem on the dashboard instead
                # (once logged in) so a first-time deploy fails
                # helpfully, not with a blank 502.
                app.state.scheduler_error = str(e)
        yield
        if app.state.scheduler is not None:
            app.state.scheduler.stop()

    app = FastAPI(title="ICTAgent Dashboard", lifespan=_lifespan)

    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.decision_log = decision_log or DecisionLog()
    app.state.phase_store = phase_store or PhaseStore()
    app.state.scheduler = scheduler
    app.state.scheduler_error: Optional[str] = None

    def _is_authenticated(request: Request) -> bool:
        try:
            return verify_session_token(request.cookies.get(SESSION_COOKIE_NAME))
        except AuthConfigError:
            # SESSION_SECRET_KEY got removed/changed out from under an
            # existing cookie — treat as logged out, not a server error.
            return False

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return app.state.templates.TemplateResponse(request, "login.html", {"error": None})

    @app.post("/login")
    def login_submit(request: Request, password: str = Form(...)):
        try:
            ok = check_password(password)
            token = create_session_token()
        except AuthConfigError as e:
            return app.state.templates.TemplateResponse(
                request,
                "login.html",
                {"error": f"This site isn't fully configured yet: {e}"},
                status_code=500,
            )
        if not ok:
            return app.state.templates.TemplateResponse(
                request, "login.html", {"error": "Wrong password."}, status_code=401
            )
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=SESSION_MAX_AGE_SECONDS,
        )
        return response

    @app.get("/logout")
    def logout():
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE_NAME)
        return response

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        if not _is_authenticated(request):
            return RedirectResponse(url="/login", status_code=303)

        settings = load_settings()
        current_phase = app.state.phase_store.get_phase(default=settings.phase)
        decisions = list_decisions(app.state.decision_log, limit=50)
        scheduler = app.state.scheduler

        return app.state.templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "current_phase": current_phase.value,
                "phases": [p.value for p in Phase],
                "live_trading_enabled": settings.live_trading_enabled,
                "decisions": decisions,
                "scheduler_running": scheduler is not None,
                "scheduler_error": app.state.scheduler_error or (scheduler.last_error if scheduler else None),
            },
        )

    @app.post("/phase")
    def change_phase(request: Request, phase: str = Form(...)):
        if not _is_authenticated(request):
            return RedirectResponse(url="/login", status_code=303)
        try:
            app.state.phase_store.set_phase(Phase(phase))
        except ValueError:
            pass  # unknown phase string from a tampered form — silently ignored, not applied
        return RedirectResponse(url="/", status_code=303)

    @app.post("/run-now")
    def run_now(request: Request):
        if not _is_authenticated(request):
            return RedirectResponse(url="/login", status_code=303)
        if app.state.scheduler is not None:
            try:
                app.state.scheduler.run_once()
            except Exception as e:
                app.state.scheduler_error = str(e)
        return RedirectResponse(url="/", status_code=303)

    return app


# What `uvicorn ictagent.web.app:app` (see render.yaml) actually serves.
app = create_app()
