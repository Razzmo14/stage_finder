"""Tests for review-008: review actions, edits, streaming, hard rule."""


import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.applications import REVIEW_STATUSES
from app.core import config, secrets
from app.db.models import Application, Offer, Profile
from app.llm.provider import Completion, CompletionRequest
from app.main import create_app

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

STREAMED_LETTER = ["Madame, ", "voici la lettre ", "revue et raccourcie."]


class FakeReviewProvider:
    name = "fake"

    def __init__(self) -> None:
        self.stream_requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        return Completion(content="ok", model=request.model)

    def stream(self, request: CompletionRequest):
        self.stream_requests.append(request)
        yield from STREAMED_LETTER


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    application = create_app(session_token=TOKEN)
    application.state.review_provider = FakeReviewProvider()
    application.state.llm_provider = lambda: application.state.review_provider
    yield application
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.KeyringBackend())


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def seed_application(session: Session) -> tuple[int, int]:
    profile = Profile(full_name="Ada", base_letter="Base letter text.")
    session.add(profile)
    session.commit()
    session.refresh(profile)
    offer = Offer(source="ft", source_id="1", title="Stage Python", company="Acme",
                  location="Paris", description="Python internship", dedup_hash="h")
    session.add(offer)
    session.commit()
    session.refresh(offer)
    application = Application(
        offer_id=offer.id,
        profile_id=profile.id,
        status="pending_review",
        letter_text="Original generated letter.",
        email_subject="Subject",
        email_body="Body",
        claims=[{"claim": "I know Python.", "supported": True, "reason": ""}],
        flagged_claims=[{"claim": "I know Kubernetes.", "supported": False, "reason": "Unknown"}],
    )
    session.add(application)
    session.commit()
    session.refresh(application)
    return application.id, offer.id


def test_review_statuses_never_include_sent() -> None:
    assert "sent" not in REVIEW_STATUSES
    assert "draft_sent" not in REVIEW_STATUSES


def test_queue_lists_pending_review_with_offer(client, app) -> None:
    with Session(app.state.db_engine) as session:
        application_id, _ = seed_application(session)

    queue = client.get("/api/v1/applications?status=pending_review", headers=HEADERS).json()
    assert len(queue) == 1
    item = queue[0]
    assert item["id"] == application_id
    assert item["offer"]["title"] == "Stage Python"
    assert len(item["flagged_claims"]) == 1


def test_inline_edit_persists_and_logs(client, app) -> None:
    with Session(app.state.db_engine) as session:
        application_id, _ = seed_application(session)

    response = client.patch(
        f"/api/v1/applications/{application_id}",
        json={"letter_text": "Edited by hand.", "email_subject": "New subject"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["letter_text"] == "Edited by hand."
    assert response.json()["status"] == "pending_review"  # edits never change status

    detail = client.get(f"/api/v1/applications/{application_id}", headers=HEADERS).json()
    events = [e["event_type"] for e in detail["events"]]
    assert "edited" in events


def test_approve_and_reject_transitions(client, app) -> None:
    with Session(app.state.db_engine) as session:
        application_id, _ = seed_application(session)

    approved = client.post(
        f"/api/v1/applications/{application_id}/approve", headers=HEADERS
    ).json()
    assert approved["status"] == "approved"  # intent only, nothing was sent

    rejected = client.post(
        f"/api/v1/applications/{application_id}/reject", headers=HEADERS
    ).json()
    assert rejected["status"] == "rejected"

    detail = client.get(f"/api/v1/applications/{application_id}", headers=HEADERS).json()
    events = [e["event_type"] for e in detail["events"]]
    assert events == ["approved", "rejected"]


def test_no_review_endpoint_can_send() -> None:
    """HARD RULE: the review module exposes no send path at all."""
    import app.api.applications as applications_module

    for route in applications_module.router.routes:
        path = getattr(route, "path", "")
        assert "send" not in path.lower(), f"Send path exposed: {path}"
    assert "sent" not in REVIEW_STATUSES
    assert "draft_sent" not in REVIEW_STATUSES


def test_streamed_regeneration_updates_letter(client, app) -> None:
    with Session(app.state.db_engine) as session:
        application_id, _ = seed_application(session)

    with client.stream(
        "POST",
        "/api/v1/letters/regenerate",
        json={"application_id": application_id, "instructions": "make it shorter"},
        headers=HEADERS,
    ) as response:
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        received = "".join(
            chunk.decode() for chunk in response.iter_bytes()
        )
    assert received == "".join(STREAMED_LETTER)

    # The user's instructions reached the provider
    request_obj = app.state.review_provider.stream_requests[0]
    assert "make it shorter" in request_obj.messages[-1].content
    assert "Original generated letter." in request_obj.messages[-1].content

    detail = client.get(f"/api/v1/applications/{application_id}", headers=HEADERS).json()
    assert detail["letter_text"] == received
    events = [e["event_type"] for e in detail["events"]]
    assert "letter_regenerated" in events


def test_regeneration_with_custom_model(client, app) -> None:
    with Session(app.state.db_engine) as session:
        application_id, _ = seed_application(session)
    with client.stream(
        "POST",
        "/api/v1/letters/regenerate",
        json={"application_id": application_id, "model": "vendor/other"},
        headers=HEADERS,
    ) as response:
        assert response.status_code == 200
    assert app.state.review_provider.stream_requests[0].model == "vendor/other"


def test_unknown_application_404(client) -> None:
    assert client.get("/api/v1/applications/999", headers=HEADERS).status_code == 404
    response = client.post(
        "/api/v1/letters/regenerate",
        json={"application_id": 999, "instructions": "shorter"},
        headers=HEADERS,
    )
    assert response.status_code == 404
