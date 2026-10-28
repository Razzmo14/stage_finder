"""FastAPI application factory for the Stage Finder sidecar."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import Session

from app.api.router import api_router
from app.core.config import get_settings
from app.core.security import SessionTokenMiddleware
from app.db.engine import make_engine
from app.db.migrate import run_migrations
from app.llm.catalog import ModelCatalog

# Per-task model defaults; user assignment (ModelConfig) arrives with the
# full model-settings feature.
DEFAULT_TASK_MODELS = {
    "profile_extraction": "openai/gpt-4o-mini",
    "matching": "openai/gpt-4o-mini",
    "letter_generation": "openai/gpt-4o-mini",
    "claim_check": "openai/gpt-4o-mini",
}


def _run_searches(app: FastAPI):
    from sqlmodel import Session

    from app.services.scheduler import run_all_criteria

    def run() -> dict:
        with Session(app.state.db_engine) as session:
            return run_all_criteria(session, app.state.job_sources)

    return run


def _check_follow_ups(app: FastAPI):
    from sqlmodel import Session

    from app.services.scheduler import record_follow_up_notifications

    def run() -> list[dict]:
        with Session(app.state.db_engine) as session:
            return record_follow_up_notifications(session)

    return run


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

        # Scheduler: periodic searches + follow-up checks. May never send.
        from app.services.scheduler import make_scheduler, register_jobs
        from app.services.settings import get_setting, set_setting

        with Session(app.state.db_engine) as session:
            scheduler_settings = get_setting(session, "scheduler") or {
                "enabled": False,
                "search_interval_minutes": 240,
                "follow_up_check_minutes": 15,
            }
            if not scheduler_settings:
                set_setting(session, "scheduler", dict(scheduler_settings))
        app.state.scheduler = make_scheduler()
        register_jobs(
            app.state.scheduler,
            run_searches=_run_searches(app),
            check_follow_ups=_check_follow_ups(app),
            settings=dict(scheduler_settings),
        )
        yield
        if app.state.scheduler.running:
            app.state.scheduler.shutdown(wait=False)
        app.state.db_engine.dispose()

    app = FastAPI(title="Stage Finder backend", version="0.1.0", lifespan=lifespan)
    app.state.session_token = session_token or get_settings().session_token
    app.state.catalog = ModelCatalog()
    def _llm_provider():
        from app.llm.registry import get_active_provider
        from app.services.settings import get_setting

        with Session(app.state.db_engine, expire_on_commit=False) as session:
            llm_settings = get_setting(session, "llm")
        return get_active_provider(app.state, llm_settings, catalog=app.state.catalog)

    app.state.llm_provider = _llm_provider
    app.state.get_task_model = lambda task: DEFAULT_TASK_MODELS[task]
    from app.services.job_sources.adzuna import AdzunaJobSource
    from app.services.job_sources.france_travail import FranceTravailJobSource
    from app.services.job_sources.jooble import JoobleJobSource
    from app.services.matching.embeddings import HashingEmbedder

    app.state.job_sources = {
        "france_travail": FranceTravailJobSource(),
        "adzuna": AdzunaJobSource(),
        "jooble": JoobleJobSource(),
    }
    app.state.embedder = HashingEmbedder()
    from app.services.letter_generation.grounding import HeuristicGroundingChecker

    app.state.grounding_checker = HeuristicGroundingChecker()
    from app.services.mailer.gmail import GmailClient
    from app.services.mailer.graph import GraphClient
    from app.services.mailer.smtp_imap import SmtpImapClient

    app.state.gmail_client = GmailClient()
    app.state.mail_clients = {
        "gmail": app.state.gmail_client,
        "graph": GraphClient(),
        "smtp": SmtpImapClient(),
    }

    app.include_router(api_router)
    app.add_middleware(SessionTokenMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
