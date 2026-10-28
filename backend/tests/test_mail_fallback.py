"""Tests for mail-012: Microsoft Graph (PKCE) and SMTP/IMAP fallback."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlmodel import Session

from app.core import config, secrets
from app.main import create_app
from app.services.mailer.gmail import build_mime
from app.services.mailer.graph import GraphClient, build_graph_message
from app.services.mailer.smtp_imap import SmtpImapClient

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def graph_mock_transport(calls: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(
                200, json={"access_token": "g-at", "refresh_token": "g-rt", "expires_in": 3600}
            )
        if request.url.path.endswith("/messages"):
            return httpx.Response(201, json={"id": "graph-draft-1"})
        if request.url.path.endswith("/sendMail"):
            return httpx.Response(202, json={})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def memory_secrets():
    secrets.use_backend(secrets.MemoryBackend())
    yield
    secrets.use_backend(secrets.KeyringBackend())


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    secrets.set_secret("graph_client_id", "graph-client-id")
    application = create_app(session_token=TOKEN)
    application.state.graph_calls: list = []
    application.state.mail_clients["graph"] = GraphClient(
        transport=graph_mock_transport(application.state.graph_calls)
    )
    yield application
    config.get_settings.cache_clear()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


# --- Graph ---------------------------------------------------------------------


def test_graph_connect_flow_pkce(client, app) -> None:
    start = client.post("/api/v1/mail/graph/connect/start", json={}, headers=HEADERS).json()
    query = parse_qs(urlparse(start["authorize_url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in start["authorize_url"]
    assert "login.microsoftonline.com" in start["authorize_url"]

    complete = client.post(
        "/api/v1/mail/graph/connect/complete",
        json={"code": "auth-code", "state": start["state"]},
        headers=HEADERS,
    )
    assert complete.status_code == 200

    token_requests = [c for c in app.state.graph_calls if c.url.path.endswith("/token")]
    body = parse_qs(token_requests[-1].content.decode())
    assert body["code_verifier"][0]
    assert secrets.get_secret("graph_access_token") == "g-at"

    status = client.get("/api/v1/mail/status", headers=HEADERS).json()
    assert status["graph_connected"] is True


def test_graph_connect_rejects_forged_state(client) -> None:
    response = client.post(
        "/api/v1/mail/graph/connect/complete",
        json={"code": "x", "state": "forged"},
        headers=HEADERS,
    )
    assert response.status_code == 422


def test_graph_draft_and_send_shape(app) -> None:
    client = app.state.mail_clients["graph"]
    start_flow = client.start_connect("http://localhost:1420/oauth/gmail/callback")[0]
    client.complete_connect(start_flow, "code")
    mime = build_mime(sender="a@x.com", to="b@y.com", subject="S", body="Hello")

    draft = client.create_draft(mime)
    assert draft["id"] == "graph-draft-1"
    sent = client.send(mime)
    assert sent["id"] == "graph-send"
    # Authorization header carried the token
    messages_requests = [c for c in app.state.graph_calls if c.url.path.endswith("/messages")]
    assert messages_requests[0].headers["Authorization"] == "Bearer g-at"


def test_build_graph_message_shape() -> None:
    message = build_graph_message(sender="a@x.com", to="b@y.com", subject="S", body="Hello")
    assert message["message"]["subject"] == "S"
    assert message["message"]["toRecipients"][0]["emailAddress"]["address"] == "b@y.com"
    assert message["saveToSentItems"] is True


# --- SMTP/IMAP ---------------------------------------------------------------


class FakeSmtp:
    instances: list["FakeSmtp"] = []

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sent: list = []
        self.failures = 0
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, message):
        if self.failures > 0:
            self.failures -= 1
            raise OSError("transient SMTP failure")
        self.sent.append(message)


class FakeImap:
    def __init__(self, host: str, port: int) -> None:
        self.appended: list = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, user, password):
        self.login_args = (user, password)

    def append(self, mailbox, flags, date, content):
        self.appended.append((mailbox, content))


def smtp_client(smtp=None, imap=None) -> SmtpImapClient:
    return SmtpImapClient(smtp_factory=lambda h, p: smtp, imap_factory=lambda h, p: imap)


def configure_smtp_secrets() -> None:
    secrets.set_secret("smtp_host", "smtp.example.com")
    secrets.set_secret("smtp_port", "587")
    secrets.set_secret("smtp_user", "user@example.com")
    secrets.set_secret("smtp_password", "app-password")
    secrets.set_secret("imap_host", "imap.example.com")
    secrets.set_secret("imap_port", "993")


def test_smtp_send_with_retry(monkeypatch) -> None:
    monkeypatch.setattr("app.services.mailer.smtp_imap.time.sleep", lambda s: None)
    configure_smtp_secrets()
    fake = FakeSmtp("smtp.example.com", 587)
    fake.failures = 2  # two transient failures, third attempt succeeds
    smtp = smtp_client(smtp=fake)

    result = smtp.send(build_mime(sender="a@x.com", to="b@y.com", subject="S", body="B"))
    assert result["id"].startswith("smtp-")
    assert len(fake.sent) == 1
    assert fake.login_args == ("user@example.com", "app-password")


def test_smtp_send_fails_after_max_retries(monkeypatch) -> None:
    monkeypatch.setattr("app.services.mailer.smtp_imap.time.sleep", lambda s: None)
    configure_smtp_secrets()
    fake = FakeSmtp("smtp.example.com", 587)
    fake.failures = 99
    smtp = smtp_client(smtp=fake)
    with pytest.raises(Exception, match="after 3 attempts"):
        smtp.send(build_mime(sender="a@x.com", to="b@y.com", subject="S", body="B"))


def test_imap_draft_append() -> None:
    configure_smtp_secrets()
    imap = FakeImap("imap.example.com", 993)
    smtp = smtp_client(imap=imap)
    assert smtp.connected() is True

    result = smtp.create_draft(build_mime(sender="a@x.com", to="b@y.com", subject="S", body="B"))
    assert result["id"] == "imap-draft"
    assert imap.appended[0][0] == "Drafts"
    assert b"Subject: S" in imap.appended[0][1]


def test_smtp_not_configured() -> None:
    smtp = smtp_client()
    assert smtp.connected() is False
    with pytest.raises(Exception, match="SMTP is not configured"):
        smtp.send(b"x")


def test_deliver_uses_selected_account(client, app) -> None:
    """The active account setting routes deliver() to the right client."""
    from app.db.models import Application, Offer, Profile

    configure_smtp_secrets()
    client.put(
        "/api/v1/mail/settings",
        json={"allow_direct_send": True, "daily_send_limit": 5,
              "sender_email": "me@example.com", "account": "smtp"},
        headers=HEADERS,
    )
    fake_imap = FakeImap("imap.example.com", 993)
    app.state.mail_clients["smtp"] = smtp_client(imap=fake_imap)

    with Session(app.state.db_engine) as session:
        profile = Profile(full_name="Ada")
        session.add(profile)
        session.commit()
        session.refresh(profile)
        offer = Offer(source="ft", source_id="1", title="T", company="C", dedup_hash="h")
        session.add(offer)
        session.commit()
        session.refresh(offer)
        application = Application(
            offer_id=offer.id, profile_id=profile.id, status="approved",
            recipient="jobs@example.com", email_subject="S", email_body="B",
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        application_id = application.id

    response = client.post(
        f"/api/v1/applications/{application_id}/deliver",
        json={"mode": "draft", "confirm": True},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "draft_saved"
    assert fake_imap.appended, "draft went through the SMTP/IMAP account"
