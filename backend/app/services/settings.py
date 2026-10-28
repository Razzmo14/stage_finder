"""Application settings: key/value storage in the appsetting table.

Never secrets: secrets go to the OS keychain only.
"""

from datetime import UTC, datetime

from sqlmodel import Session, select

from app.db.models import AppSetting

DEFAULT_SETTINGS: dict[str, dict] = {
    "mail": {
        "allow_direct_send": False,
        "daily_send_limit": 20,
        "sender_email": "",
        "account": "gmail",
    },
    "gmail_redirect_uri": {"uri": "http://localhost:1420/oauth/gmail/callback"},
    "scheduler": {"enabled": False, "search_interval_minutes": 240, "follow_up_check_minutes": 15},
}


def get_setting(session: Session, key: str) -> dict:
    row = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    if row is not None:
        return dict(row.value or {})
    return dict(DEFAULT_SETTINGS.get(key, {}))


def set_setting(session: Session, key: str, value: dict) -> None:
    row = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    if row is None:
        row = AppSetting(key=key)
    row.value = value
    row.updated_at = datetime.now(UTC)
    session.add(row)
    session.commit()
