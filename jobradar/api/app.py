"""FastAPI app factory."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from jobradar.api.auth import session_secret
from jobradar.api.db import init_db
from jobradar.api.events import bus
from jobradar.api.imap_poller import poller_manager
from jobradar.api.routes import account as account_routes
from jobradar.api.routes import auth as auth_routes
from jobradar.api.routes import email as email_routes
from jobradar.api.routes import jobs as jobs_routes


def _cors_origins() -> List[str]:
    # Both localhost and 127.0.0.1 variants so the page origin and the API
    # origin can be either flavour without breaking the cookie.
    raw = os.environ.get(
        "API_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,"
        "http://127.0.0.1:3000,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def _lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    bus.attach_loop(loop)
    poller_manager.attach_loop(loop)
    poller_manager.start_from_db()
    try:
        yield
    finally:
        await poller_manager.stop()


def create_app() -> FastAPI:
    init_db()

    app = FastAPI(title="JobRadar API", version="0.1.0", lifespan=_lifespan)

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
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(auth_routes.router)
    app.include_router(email_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(account_routes.router)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
