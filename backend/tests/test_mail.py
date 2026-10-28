"""Tests for mail-009: Gmail OAuth2 (PKCE), drafts default, guarded send."""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import config, secrets
from app.db.models import Application, EventLog, Offer, Profile
from app.main import create_app
from app.services.mailer.gmail import (
    ACCESS_TOKEN_SECRET,
    CLIENT_ID_SECRET,
    REFRESH_TOKEN_SECRET,
    GmailClient,
    build_mime,
    encode_raw,
    new_oauth_state,
)
from app.services.mailer.mailer import get_setting, set_setting

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def gmail_mock_transport(calls: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path.endswith("/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "at-123",
                    "refresh_token": "rt-456",
                    "expires_in": 3600,
                    "email_address": "user@example.com",
                },
            )
        if path.endswith("/drafts"):
            return httpx.Response(200, json={"id": "draft-1"})
        if path.endswith("/messages/send"):
            return httpx.Response(200, json={"id": "msg-1"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    secrets.set_secret(CLIENT_ID_SECRET, "google-client-id")
    from app.services.mailer.graph import GraphClient
    from app.services.mailer.smtp_imap import SmtpImapClient

    application = create_app(session_token=TOKEN)
    application.state.gmail_calls: list = []
    application.state.gmail_client = GmailClient(
        transport=gmail_mock_transport(application.state.gmail_calls)
    )
    application.state.mail_clients = {
        "gmail": application.state.gmail_client,
        "graph": GraphClient(transport=gmail_mock_transport(application.state.gmail_calls)),
        "smtp": SmtpImapClient(),
    }
    yield application
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.KeyringBackend())


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


_seed_counter = {"n": 0}


def seed_application(session: Session) -> int:
    _seed_counter["n"] += 1
    n = _seed_counter["n"]
    profile = session.exec(select(Profile)).first()
    if profile is None:
        profile = Profile(full_name="Ada", email="from@example.com")
        session.add(profile)
        session.commit()
        session.refresh(profile)
    offer = Offer(source="ft", source_id=str(n), title="Stage", company="Acme", dedup_hash=f"h{n}")
    session.add(offer)
    session.commit()
    session.refresh(offer)
    application = Application(
        offer_id=offer.id,
        profile_id=profile.id,
        status="approved",
        recipient="jobs@acme.com",
        email_subject="Candidature",
        email_body="Bonjour,",
    )
    session.add(application)
    session.commit()
    session.refresh(application)
    return application.id


# --- OAuth2 PKCE --------------------------------------------------------------


def test_pkce_authorize_url_and_token_exchange() -> None:
    state = new_oauth_state("http://localhost:1420/oauth/gmail/callback")
    url = state.authorize_url("google-client-id")
    query = parse_qs(urlparse(url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["client_id"] == ["google-client-id"]
    # S256: challenge is the SHA256 of the verifier, base64url
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(state.code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    assert query["code_challenge"] == [expected]
    assert "code_verifier" not in url  # the verifier never leaves the backend


def test_connect_flow_with_mocked_endpoints(client, app) -> None:
    start = client.post(
        "/api/v1/mail/gmail/connect/start", json={}, headers=HEADERS
    ).json()
    assert "accounts.google.com" in start["authorize_url"]

    complete = client.post(
        "/api/v1/mail/gmail/connect/complete",
        json={"code": "auth-code", "state": start["state"]},
        headers=HEADERS,
    )
    assert complete.status_code == 200
    assert complete.json()["email_address"] == "user@example.com"

    # The token exchange carried the PKCE verifier
    token_requests = [c for c in app.state.gmail_calls if c.url.path.endswith("/token")]
    body = parse_qs(token_requests[-1].content.decode())
    assert body["code_verifier"][0]
    assert body["grant_type"] == ["authorization_code"]

    # Tokens are in the keychain, never in the DB
    assert secrets.get_secret(ACCESS_TOKEN_SECRET) == "at-123"
    assert secrets.get_secret(REFRESH_TOKEN_SECRET) == "rt-456"
    db_path = config.get_settings().db_path
    assert b"at-123" not in db_path.read_bytes()

    status = client.get("/api/v1/mail/status", headers=HEADERS).json()
    assert status["gmail_connected"] is True


def test_connect_complete_rejects_unknown_state(client) -> None:
    response = client.post(
        "/api/v1/mail/gmail/connect/complete",
        json={"code": "x", "state": "forged"},
        headers=HEADERS,
    )
    assert response.status_code == 422


# --- Drafts default, send gated -------------------------------------------------


def _connect(client) -> None:
    start = client.post("/api/v1/mail/gmail/connect/start", json={}, headers=HEADERS).json()
    client.post(
        "/api/v1/mail/gmail/connect/complete",
        json={"code": "auth-code", "state": start["state"]},
        headers=HEADERS,
    )


def test_deliver_requires_confirmation_even_for_drafts(client, app) -> None:
    _connect(client)
    with Session(app.state.db_engine) as session:
        application_id = seed_application(session)
    response = client.post(
        f"/api/v1/applications/{application_id}/deliver",
        json={"mode": "draft", "confirm": False},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "confirmation" in response.json()["detail"].lower()


def test_deliver_creates_draft_by_default(client, app) -> None:
    _connect(client)
    with Session(app.state.db_engine) as session:
        application_id = seed_application(session)
    response = client.post(
        f"/api/v1/applications/{application_id}/deliver",
        json={"mode": "draft", "confirm": True},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "draft_saved"

    draft_requests = [c for c in app.state.gmail_calls if c.url.path.endswith("/drafts")]
    assert len(draft_requests) == 1
    payload = json.loads(draft_requests[0].content)
    mime = base64.urlsafe_b64decode(payload["message"]["raw"])
    assert b"jobs@acme.com" in mime
    assert b"Candidature" in mime

    with Session(app.state.db_engine) as session:
        events = session.exec(select(EventLog)).all()
        assert events[-1].event_type == "draft_created"


def test_direct_send_blocked_without_setting(client, app) -> None:
    _connect(client)
    with Session(app.state.db_engine) as session:
        application_id = seed_application(session)
    response = client.post(
        f"/api/v1/applications/{application_id}/deliver",
        json={"mode": "send", "confirm": True},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "disabled" in response.json()["detail"]
    # Nothing was sent
    assert not [c for c in app.state.gmail_calls if c.url.path.endswith("/messages/send")]


def test_direct_send_works_when_enabled_and_confirmed(client, app) -> None:
    _connect(client)
    client.put(
        "/api/v1/mail/settings",
        json={"allow_direct_send": True, "daily_send_limit": 2, "sender_email": "me@example.com"},
        headers=HEADERS,
    )
    with Session(app.state.db_engine) as session:
        application_id = seed_application(session)

    response = client.post(
        f"/api/v1/applications/{application_id}/deliver",
        json={"mode": "send", "confirm": True},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    send_requests = [c for c in app.state.gmail_calls if c.url.path.endswith("/messages/send")]
    assert len(send_requests) == 1

    with Session(app.state.db_engine) as session:
        application = session.get(Application, application_id)
        assert application.sent_at is not None
        events = [e.event_type for e in session.exec(select(EventLog)).all()]
        assert "sent" in events


def test_daily_send_limit_enforced(client, app) -> None:
    _connect(client)
    client.put(
        "/api/v1/mail/settings",
        json={"allow_direct_send": True, "daily_send_limit": 1, "sender_email": "me@example.com"},
        headers=HEADERS,
    )
    with Session(app.state.db_engine) as session:
        first_id = seed_application(session)
        second_id = seed_application(session)

    assert (
        client.post(f"/api/v1/applications/{first_id}/deliver",
                    json={"mode": "send", "confirm": True}, headers=HEADERS).status_code
        == 200
    )
    blocked = client.post(
        f"/api/v1/applications/{second_id}/deliver",
        json={"mode": "send", "confirm": True},
        headers=HEADERS,
    )
    assert blocked.status_code == 422
    assert "limit" in blocked.json()["detail"].lower()


def test_unconnected_gmail_is_a_clear_error(client, app) -> None:
    with Session(app.state.db_engine) as session:
        application_id = seed_application(session)
    response = client.post(
        f"/api/v1/applications/{application_id}/deliver",
        json={"mode": "draft", "confirm": True},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "connected" in response.json()["detail"].lower()


def test_settings_persist(engine) -> None:
    with Session(engine) as session:
        set_setting(session, "mail", {"allow_direct_send": True, "daily_send_limit": 5})
        assert get_setting(session, "mail")["allow_direct_send"] is True
        # defaults
        assert get_setting(session, "mail")["daily_send_limit"] == 5


def test_build_mime_and_encode_raw() -> None:
    mime = build_mime(sender="a@x.com", to="b@y.com", subject="S", body="Hello")
    assert b"Hello" in mime
    assert base64.urlsafe_b64decode(encode_raw(mime)) == mime
