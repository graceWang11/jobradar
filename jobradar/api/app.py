"""FastAPI app factory."""

from __future__ import annotations

import asyncio
import os
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from jobradar.api.auth import session_secret
from jobradar.api.db import init_db
from jobradar.api.events import bus
from jobradar.api.routes import auth as auth_routes
from jobradar.api.routes import email as email_routes


def _cors_origins() -> List[str]:
    raw = os.environ.get(
        "API_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    init_db()

    app = FastAPI(title="JobRadar API", version="0.1.0")

    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(),
        session_cookie="jr_session",
        same_site="lax",
        https_only=False,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(auth_routes.router)
    app.include_router(email_routes.router)

    @app.on_event("startup")
    async def _bind_event_loop() -> None:
        bus.attach_loop(asyncio.get_running_loop())

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
