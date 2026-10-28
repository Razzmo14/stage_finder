"""FastAPI application factory for the Stage Finder sidecar."""

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.security import SessionTokenMiddleware


def create_app(session_token: str | None = None) -> FastAPI:
    """Build the sidecar app.

    The token is taken from the argument when provided (used by tests and
    by programmatic launches), otherwise from the STAGE_FINDER_SESSION_TOKEN
    environment variable set by the Tauri core.
    """
    app = FastAPI(title="Stage Finder backend", version="0.1.0")
    app.state.session_token = session_token or get_settings().session_token
    app.add_middleware(SessionTokenMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
