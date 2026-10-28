"""Shared fixtures: a migrated temporary database per test."""

import pytest
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from alembic import command
from app.db.engine import make_engine

ALEMBIC_INI = "alembic.ini"


def table_names(engine: Engine) -> set[str]:
    """Application table names in the database (alembic_version excluded)."""
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def make_alembic_config(db_url: str) -> Config:
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def upgrade_head(db_url: str) -> None:
    command.upgrade(make_alembic_config(db_url), "head")


def downgrade_base(db_url: str) -> None:
    command.downgrade(make_alembic_config(db_url), "base")


@pytest.fixture
def db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path}/test.db"


@pytest.fixture
def engine(db_url, tmp_path) -> Engine:
    """Fresh engine over a migrated empty database."""
    upgrade_head(db_url)
    return make_engine(tmp_path / "test.db")
