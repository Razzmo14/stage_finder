"""Mail delivery orchestration.

HARD RULE (ADR 0003): `deliver()` is the single code path to the mailbox.
- mode "draft" (default): creates a draft in the user's mailbox.
- mode "send": direct send, allowed only when the user enabled it in
  settings AND the request carries an explicit confirmation.
A per-day send limit applies to direct sends.
"""

from datetime import UTC, datetime

from sqlmodel import Session, select

from app.db.models import Application, AppSetting, EventLog
from app.services.mailer.gmail import GmailClient, build_mime


class DeliveryError(Exception):
    pass

DRAFT_STATUS = "draft_saved"
SENT_STATUS = "sent"

DEFAULT_SETTINGS: dict[str, dict] = {
    "mail": {"allow_direct_send": False, "daily_send_limit": 20, "sender_email": ""},
    "gmail_redirect_uri": {"uri": "http://localhost:1420/oauth/gmail/callback"},
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


def sends_today(session: Session) -> int:
    """Count direct sends performed today (UTC)."""
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = session.exec(
        select(EventLog).where(EventLog.event_type == "sent")
    ).all()
    return sum(1 for r in rows if r.created_at >= start)


def deliver(
    session: Session,
    application: Application,
    *,
    mode: str = "draft",
    confirm: bool = False,
    client: GmailClient | None = None,
) -> Application:
    """Create a draft or send the application email. Single gateway.

    Raises DeliveryError on any hard-rule violation or provider failure.
    """
    if mode not in ("draft", "send"):
        raise DeliveryError(f"Unknown mode: {mode}")
    if not confirm:
        raise DeliveryError("Explicit confirmation is required before any mailbox action")
    if mode == "send":
        mail_settings = get_setting(session, "mail")
        if not mail_settings.get("allow_direct_send", False):
            raise DeliveryError("Direct sending is disabled: enable it in Settings first")
        if sends_today(session) >= int(mail_settings.get("daily_send_limit", 20)):
            raise DeliveryError("Daily send limit reached")

    client = client or GmailClient()
    mail_settings = get_setting(session, "mail")
    sender = mail_settings.get("sender_email") or "me"
    recipient = application.recipient
    if not recipient:
        raise DeliveryError("The application has no recipient")

    mime = build_mime(
        sender=sender,
        to=recipient,
        subject=application.email_subject,
        body=application.email_body,
    )
    try:
        if mode == "draft":
            result = client.create_draft(mime)
            application.status = DRAFT_STATUS
            event = "draft_created"
        else:
            result = client.send(mime)
            application.status = SENT_STATUS
            application.sent_at = datetime.now(UTC)
            event = "sent"
    except Exception as error:  # noqa: BLE001 - normalize provider errors
        raise DeliveryError(str(error)) from error

    session.add(application)
    session.commit()
    session.refresh(application)
    session.add(
        EventLog(
            event_type=event,
            application_id=application.id,
            detail=f"id={result.get('id', '?')}",
        )
    )
    session.commit()
    return application
