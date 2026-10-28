"""Migration tests for feature db-002.

Verify the Alembic chain: empty -> head, head -> base, base -> head.
"""

from tests.conftest import downgrade_base, table_names, upgrade_head

ALL_TABLES = {
    "profile",
    "experience",
    "education",
    "project",
    "document",
    "searchcriteria",
    "offer",
    "matchresult",
    "application",
    "llmusage",
    "eventlog",
    "modelconfig",
}


def test_upgrade_from_empty_creates_all_tables(db_url, engine) -> None:
    assert table_names(engine) == ALL_TABLES


def test_downgrade_to_base_removes_all_tables(db_url, engine) -> None:
    downgrade_base(db_url)
    assert table_names(engine) == set()
    # engine is closed implicitly when the next connection is made


def test_reupgrade_after_downgrade_succeeds(db_url, tmp_path) -> None:
    upgrade_head(db_url)
    downgrade_base(db_url)
    upgrade_head(db_url)
    from app.db.engine import make_engine

    engine = make_engine(tmp_path / "test.db")
    assert table_names(engine) == ALL_TABLES
