"""FastAPI application factory for the Stage Finder sidecar."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.security import SessionTokenMiddleware
from app.db.engine import make_engine
from app.db.migrate import run_migrations
from app.llm.catalog import ModelCatalog
from app.llm.openrouter import OpenRouterProvider

# Per-task model defaults; user assignment (ModelConfig) arrives with the
# full model-settings feature.
DEFAULT_TASK_MODELS = {
    "profile_extraction": "openai/gpt-4o-mini",
    "matching": "openai/gpt-4o-mini",
    "letter_generation": "openai/gpt-4o-mini",
    "claim_check": "openai/gpt-4o-mini",
}


def create_app(session_token: str | None = None) -> FastAPI:
    """Build the sidecar app.

    The token is taken from the argument when provided (used by tests and
    by programmatic launches), otherwise from the STAGE_FINDER_SESSION_TOKEN
    environment variable set by the Tauri core.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        run_migrations(f"sqlite:///{settings.db_path}")
        app.state.db_engine = make_engine(settings.db_path)
        yield
        app.state.db_engine.dispose()

    app = FastAPI(title="Stage Finder backend", version="0.1.0", lifespan=lifespan)
    app.state.session_token = session_token or get_settings().session_token
    app.state.catalog = ModelCatalog()
    app.state.llm_provider = lambda: OpenRouterProvider(catalog=app.state.catalog)
    app.state.get_task_model = lambda task: DEFAULT_TASK_MODELS[task]
    from app.services.job_sources.france_travail import FranceTravailJobSource

    app.state.job_sources = {"france_travail": FranceTravailJobSource()}

    app.include_router(api_router)
    app.add_middleware(SessionTokenMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
