"""SMTP/IMAP fallback: send via SMTP, drafts via IMAP APPEND.

Credentials live in the keychain (smtp_host, smtp_port, smtp_user,
smtp_password, imap_host, imap_port). Sends retry with exponential
backoff; the daily send limit is enforced by the mailer service.
"""

import imaplib
import smtplib
import ssl
import time
from email.message import EmailMessage

from app.core import secrets

SMTP_HOST = "smtp_host"
SMTP_PORT = "smtp_port"
SMTP_USER = "smtp_user"
SMTP_PASSWORD = "smtp_password"
IMAP_HOST = "imap_host"
IMAP_PORT = "imap_port"

MAX_RETRIES = 3
BACKOFF_SECONDS = 1.0


class SmtpImapError(Exception):
    pass


class SmtpImapClient:
    name = "smtp"

    def __init__(self, smtp_factory=None, imap_factory=None) -> None:
        # Factories are injectable for tests.
        self._smtp_factory = smtp_factory or self._default_smtp
        self._imap_factory = imap_factory or self._default_imap

    def _default_smtp(self, host: str, port: int):
        return smtplib.SMTP(host, port, timeout=30)

    def _default_imap(self, host: str, port: int):
        return imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())

    def connected(self) -> bool:
        return bool(
            secrets.get_secret(SMTP_HOST)
            and secrets.get_secret(SMTP_USER)
            and secrets.get_secret(SMTP_PASSWORD)
        )

    def send(self, mime: bytes) -> dict:
        host = secrets.get_secret(SMTP_HOST)
        port = int(secrets.get_secret(SMTP_PORT) or 587)
        user = secrets.get_secret(SMTP_USER)
        password = secrets.get_secret(SMTP_PASSWORD)
        if not host or not user or not password:
            raise SmtpImapError("SMTP is not configured (keychain)")

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                with self._smtp_factory(host, port) as smtp:
                    smtp.starttls()
                    smtp.login(user, password)
                    smtp.send_message(_to_email_message(mime))
                return {"id": f"smtp-{attempt}"}
            except Exception as error:  # noqa: BLE001 - retry transient SMTP failures
                last_error = error
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_SECONDS * (2**attempt))
        raise SmtpImapError(f"SMTP send failed after {MAX_RETRIES} attempts: {last_error}")

    def create_draft(self, mime: bytes) -> dict:
        host = secrets.get_secret(IMAP_HOST)
        port = int(secrets.get_secret(IMAP_PORT) or 993)
        user = secrets.get_secret(SMTP_USER)
        password = secrets.get_secret(SMTP_PASSWORD)
        if not host or not user or not password:
            raise SmtpImapError("IMAP is not configured (keychain)")
        with self._imap_factory(host, port) as imap:
            imap.login(user, password)
            imap.append("Drafts", None, imaplib.Time2Internaldate(time.time()), mime)
        return {"id": "imap-draft"}


def _to_email_message(mime: bytes) -> EmailMessage:
    import email
    from email import policy

    parsed = email.message_from_bytes(mime, policy=policy.default)
    message = EmailMessage()
    message["From"] = parsed["From"]
    message["To"] = parsed["To"]
    message["Subject"] = parsed["Subject"]
    message.set_content(parsed.get_body(preferencelist=("plain",)).get_content())
    return message
