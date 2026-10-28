"""FastAPI application factory for the Stage Finder sidecar."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.security import SessionTokenMiddleware
from app.db.migrate import run_migrations


def create_app(session_token: str | None = None) -> FastAPI:
    """Build the sidecar app.

    The token is taken from the argument when provided (used by tests and
    by programmatic launches), otherwise from the STAGE_FINDER_SESSION_TOKEN
    environment variable set by the Tauri core.
    """
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        run_migrations(f"sqlite:///{settings.db_path}")
        yield

    app = FastAPI(title="Stage Finder backend", version="0.1.0", lifespan=lifespan)
    app.state.session_token = session_token or get_settings().session_token
    app.add_middleware(SessionTokenMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
