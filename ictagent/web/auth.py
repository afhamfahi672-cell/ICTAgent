"""
Minimal session-cookie auth for the single-user dashboard.

There is exactly one password (`DASHBOARD_PASSWORD`) and one signing key
(`SESSION_SECRET_KEY`) — both real environment variables set on the
hosting provider's own settings page, never in this repo, never typed
into the dashboard itself, never passed as a function argument from
outside this module. No usernames, no accounts: this is a private
control panel for one person, not a multi-tenant app.

The session token is a signed, timestamped blob (`itsdangerous`) stored
in a cookie — not a database-backed session — so logging in doesn't
depend on any extra storage. It carries no secret data itself; forging
one without the signing key is what the signature prevents.
"""

from __future__ import annotations

import hmac
import os
from typing import Optional

from itsdangerous import BadSignature, URLSafeTimedSerializer

SESSION_COOKIE_NAME = "ictagent_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60  # 12 hours


class AuthConfigError(RuntimeError):
    """Raised when DASHBOARD_PASSWORD / SESSION_SECRET_KEY aren't set —
    i.e. the site hasn't been configured yet, not that a login failed."""


def _get_secret_key() -> str:
    key = os.environ.get("SESSION_SECRET_KEY")
    if not key:
        raise AuthConfigError(
            "SESSION_SECRET_KEY is not set. Set it to any long random string "
            "in your hosting provider's environment variables."
        )
    return key


def _get_password() -> str:
    password = os.environ.get("DASHBOARD_PASSWORD")
    if not password:
        raise AuthConfigError(
            "DASHBOARD_PASSWORD is not set. Set it in your hosting provider's "
            "environment variables to whatever password you want to log in with."
        )
    return password


def check_password(candidate: str) -> bool:
    """Constant-time comparison — a plain `==` would leak how many
    leading characters matched via response timing."""
    return hmac.compare_digest(candidate, _get_password())


def create_session_token() -> str:
    serializer = URLSafeTimedSerializer(_get_secret_key())
    return serializer.dumps({"authenticated": True})


def verify_session_token(token: Optional[str]) -> bool:
    if not token:
        return False
    serializer = URLSafeTimedSerializer(_get_secret_key())
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return False
    except Exception:
        # Expired token, corrupt cookie, etc. — treat as "not logged in"
        # rather than a 500.
        return False
    return bool(data.get("authenticated"))
