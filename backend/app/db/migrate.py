"""Run Alembic migrations programmatically (sidecar startup, tests)."""

from pathlib import Path

from alembic.config import Config

from alembic import command


def alembic_ini_path() -> Path:
    """backend/alembic.ini, resolved from this module's location."""
    return Path(__file__).resolve().parents[2] / "alembic.ini"


def run_migrations(db_url: str | None = None) -> None:
    """Apply all pending migrations (alembic upgrade head)."""
    config = Config(str(alembic_ini_path()))
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(config, "head")
