"""Login / logout / session probe."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from jobradar.api.auth import SESSION_KEY, password_required, verify_password
from jobradar.api.schemas import LoginBody

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginBody, request: Request):
    if not password_required():
        # Open mode — no password configured. Still set a session marker so
        # frontend code that checks /auth/me can branch consistently.
        request.session[SESSION_KEY] = "anonymous"
        return {"ok": True, "mode": "open"}
    if not verify_password(body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad password")
    request.session[SESSION_KEY] = "user"
    return {"ok": True, "mode": "authenticated"}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    authed = bool(request.session.get(SESSION_KEY))
    return {
        "authenticated": authed or not password_required(),
        "passwordRequired": password_required(),
    }
