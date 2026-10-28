"""Tests for track-010: list/kanban data, timeline, timestamps, follow-up."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import config, secrets
from app.db.models import Application, EventLog, Offer, Profile
from app.main import create_app

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    application = create_app(session_token=TOKEN)
    with TestClient(application) as client:
        yield client, application
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.KeyringBackend())


def seed(session: Session, n: int = 3) -> list[int]:
    profile = Profile(full_name="Ada")
    session.add(profile)
    session.commit()
    session.refresh(profile)
    ids = []
    for i in range(n):
        offer = Offer(
            source="ft", source_id=str(i), title=f"Offer {i}", company="C", dedup_hash=f"h{i}"
        )
        session.add(offer)
        session.commit()
        session.refresh(offer)
        statuses = ["pending_review", "approved", "rejected"]
        application = Application(
            offer_id=offer.id,
            profile_id=profile.id,
            status=statuses[i % len(statuses)],
            recipient="jobs@example.com",
            email_subject=f"Subject {i}",
            follow_up_date="2026-11-05",
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        ids.append(application.id)
    return ids


def test_list_view_returns_all_statuses_with_follow_ups(tmp_path, monkeypatch) -> None:
    for client, app in make_client(tmp_path, monkeypatch):
        with Session(app.state.db_engine) as session:
            seed(session)
        rows = client.get("/api/v1/applications", headers=HEADERS).json()
        statuses = {r["status"] for r in rows}
        assert statuses == {"pending_review", "approved", "rejected"}
        assert all(r["follow_up_date"] == "2026-11-05" for r in rows)
        # Kanban source data: one entry per status column
        assert len(rows) == 3


def test_status_transition_updates_timestamp_and_timeline(tmp_path, monkeypatch) -> None:
    for client, app in make_client(tmp_path, monkeypatch):
        with Session(app.state.db_engine) as session:
            ids = seed(session, n=1)
            application_id = ids[0]
            before = session.get(Application, application_id)
            old_updated = before.updated_at
            before.created_at = datetime.now(UTC) - timedelta(days=1)
            session.add(before)
            session.commit()

        response = client.post(
            f"/api/v1/applications/{application_id}/approve", headers=HEADERS
        )
        assert response.status_code == 200

        with Session(app.state.db_engine) as session:
            row = session.get(Application, application_id)
            assert row.status == "approved"
            assert row.updated_at > old_updated

        detail = client.get(f"/api/v1/applications/{application_id}", headers=HEADERS).json()
        events = detail["events"]
        assert events[-1]["event_type"] == "approved"
        assert len(events) == 1


def test_timeline_orders_events_chronologically(tmp_path, monkeypatch) -> None:
    for client, app in make_client(tmp_path, monkeypatch):
        with Session(app.state.db_engine) as session:
            ids = seed(session, n=1)
            application_id = ids[0]
            session.add(
                EventLog(event_type="edited", application_id=application_id, detail="letter")
            )
            session.add(
                EventLog(event_type="approved", application_id=application_id, detail="")
            )
            session.commit()

        response = client.post(
            f"/api/v1/applications/{application_id}/reject", headers=HEADERS
        )
        assert response.status_code == 200
        detail = client.get(f"/api/v1/applications/{application_id}", headers=HEADERS).json()
        assert [e["event_type"] for e in detail["events"]] == ["edited", "approved", "rejected"]


def test_filter_by_status(tmp_path, monkeypatch) -> None:
    for client, app in make_client(tmp_path, monkeypatch):
        with Session(app.state.db_engine) as session:
            seed(session)
        rows = client.get(
            "/api/v1/applications?status=approved", headers=HEADERS
        ).json()
        assert len(rows) == 1
        assert rows[0]["status"] == "approved"
