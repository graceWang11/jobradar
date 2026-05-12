"""Single-user cookie session auth.

If API_PASSWORD is not set, the API runs in open mode (suitable for localhost
dev). When it is set, /api/auth/login establishes the session and every other
endpoint requires the cookie.
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request, status

SESSION_KEY = "jr_user"


def password_required() -> bool:
    return bool(os.environ.get("API_PASSWORD", "").strip())


def session_secret() -> str:
    secret = os.environ.get("API_SESSION_SECRET", "").strip()
    if secret:
        return secret
    # Dev fallback: ephemeral secret. Cookies invalidate on every server restart.
    # Set API_SESSION_SECRET in .env for persistent sessions.
    return secrets.token_urlsafe(32)


def verify_password(supplied: str) -> bool:
    expected = os.environ.get("API_PASSWORD", "")
    if not expected:
        return False
    return secrets.compare_digest(supplied.encode(), expected.encode())


def require_auth(request: Request) -> None:
    """FastAPI dependency. No-op when password auth is disabled."""
    if not password_required():
        return
    if request.session.get(SESSION_KEY):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
