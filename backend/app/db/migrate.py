"""Run Alembic migrations programmatically (sidecar startup, tests)."""

import sys
from pathlib import Path

from alembic.config import Config

from alembic import command


def alembic_ini_path() -> Path:
    """backend/alembic.ini, resolved from this module's location.

    In a PyInstaller-frozen build the alembic files are bundled next to
    the executable (sys._MEIPASS / the exe directory).
    """
    frozen = getattr(sys, "frozen", False)
    if frozen:
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "alembic.ini"
    return Path(__file__).resolve().parents[2] / "alembic.ini"


def run_migrations(db_url: str | None = None) -> None:
    """Apply all pending migrations (alembic upgrade head).

    script_location is forced to an absolute path: a relative value would
    be resolved against the current working directory, which breaks the
    frozen sidecar when the app is launched from anywhere but backend/.
    """
    ini = alembic_ini_path()
    config = Config(str(ini))
    config.set_main_option("script_location", str(ini.parent / "alembic"))
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(config, "head")
