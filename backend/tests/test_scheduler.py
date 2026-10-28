"""Tests for sched-013: scheduled searches, reminders, hard rule."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import config, secrets
from app.db.models import Application, EventLog, Offer, Profile, SearchCriteria
from app.main import create_app
from app.services.job_sources.base import NormalizedOffer, SearchParams
from app.services.scheduler import (
    make_scheduler,
    register_jobs,
)

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


class FakeSource:
    name = "france_travail"

    def __init__(self) -> None:
        self.calls: list[SearchParams] = []

    def search(self, params: SearchParams) -> list[NormalizedOffer]:
        self.calls.append(params)
        offer = NormalizedOffer(
            source="france_travail", source_id="1", title="Stage", company="C", location="L"
        )
        offer.compute_hash()
        return [offer]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    application = create_app(session_token=TOKEN)
    application.state.fake_source = FakeSource()
    application.state.job_sources = {"france_travail": application.state.fake_source}
    yield application
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.KeyringBackend())


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def seed_criteria(session: Session, enabled: bool) -> int:
    criteria = SearchCriteria(
        name="Python", keywords=["python"], sources=["france_travail"], enabled=enabled
    )
    session.add(criteria)
    session.commit()
    session.refresh(criteria)
    return criteria.id


# --- Periodic searches ------------------------------------------------------


def test_run_all_criteria_only_enabled(client, app) -> None:
    with Session(app.state.db_engine) as session:
        seed_criteria(session, enabled=True)
        seed_criteria(session, enabled=False)

    stats = client.post("/api/v1/scheduler/run-searches", headers=HEADERS).json()
    assert stats["criteria"] == 1
    assert stats["new"] == 1
    assert len(app.state.fake_source.calls) == 1

    # Idempotent across runs: the same offers are deduplicated
    stats2 = client.post("/api/v1/scheduler/run-searches", headers=HEADERS).json()
    assert stats2["new"] == 0
    assert stats2["duplicates"] == 1


def test_scheduler_jobs_idempotent_across_restarts() -> None:
    scheduler = make_scheduler()
    register_jobs(
        scheduler,
        run_searches=lambda: None,
        check_follow_ups=lambda: None,
        settings={"enabled": True, "search_interval_minutes": 60, "follow_up_check_minutes": 10},
    )
    register_jobs(  # restart / re-register
        scheduler,
        run_searches=lambda: None,
        check_follow_ups=lambda: None,
        settings={"enabled": True, "search_interval_minutes": 30, "follow_up_check_minutes": 5},
    )
    job_ids = [job.id for job in scheduler.get_jobs()]
    assert sorted(job_ids) == [
        "stage_finder_follow_up_check",
        "stage_finder_periodic_search",
    ]
    # Interval updated in place (replace_existing), not duplicated
    search_job = scheduler.get_job("stage_finder_periodic_search")
    assert search_job.trigger.interval == timedelta(minutes=30)

    register_jobs(
        scheduler,
        run_searches=lambda: None,
        check_follow_ups=lambda: None,
        settings={"enabled": False},
    )
    assert scheduler.get_jobs() == []


def test_scheduler_settings_persist(client) -> None:
    updated = client.put(
        "/api/v1/settings/scheduler",
        json={"enabled": True, "search_interval_minutes": 120, "follow_up_check_minutes": 10},
        headers=HEADERS,
    ).json()
    assert updated["enabled"] is True
    read = client.get("/api/v1/settings/scheduler", headers=HEADERS).json()
    assert read["search_interval_minutes"] == 120


# --- Follow-up reminders ------------------------------------------------------


def seed_application(session: Session, follow_up_date: str, status: str = "approved") -> int:
    profile = session.exec(select(Profile)).first()
    if profile is None:
        profile = Profile(full_name="Ada")
        session.add(profile)
        session.commit()
        session.refresh(profile)
    offer = Offer(
        source="ft",
        source_id=f"s{follow_up_date}",
        title="T",
        company="C",
        dedup_hash=f"h{follow_up_date}",
    )
    session.add(offer)
    session.commit()
    session.refresh(offer)
    application = Application(
        offer_id=offer.id, profile_id=profile.id, status=status,
        follow_up_date=follow_up_date, recipient="x@y.z",
    )
    session.add(application)
    session.commit()
    session.refresh(application)
    return application.id


def test_due_follow_ups_and_notification_idempotence(client, app) -> None:
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    with Session(app.state.db_engine) as session:
        due_id = seed_application(session, yesterday)
        seed_application(session, tomorrow)

    follow_ups = client.get("/api/v1/follow-ups", headers=HEADERS).json()
    assert len(follow_ups) == 1
    assert follow_ups[0]["application_id"] == due_id

    # A due follow-up produces a notification (recorded once per day)
    first = client.post("/api/v1/follow-ups/notify", headers=HEADERS).json()
    assert len(first) == 1
    second = client.post("/api/v1/follow-ups/notify", headers=HEADERS).json()
    assert second == []

    with Session(app.state.db_engine) as session:
        events = session.exec(
            select(EventLog).where(EventLog.event_type == "follow_up_due")
        ).all()
        assert len(events) == 1


def test_due_follow_ups_ignore_rejected(client, app) -> None:
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    with Session(app.state.db_engine) as session:
        seed_application(session, yesterday, status="rejected")
    assert client.get("/api/v1/follow-ups", headers=HEADERS).json() == []


# --- HARD RULE: the scheduler may never send ---------------------------------


def test_scheduler_never_sends() -> None:
    """ADR 0003: no scheduler code path may reach the mailer."""
    import app.api.scheduler as scheduler_api
    import app.services.scheduler as scheduler_module

    for module in (scheduler_module, scheduler_api):
        source = open(module.__file__).read()
        assert "mailer" not in source, f"{module.__name__} references the mailer"
        assert "deliver" not in source, f"{module.__name__} references deliver()"
        assert "GmailClient" not in source
        assert "SmtpImapClient" not in source
        assert "GraphClient" not in source



def test_run_all_criteria_does_not_create_applications(client, app) -> None:
    """The periodic search ingests offers only; nothing else is touched."""
    with Session(app.state.db_engine) as session:
        seed_criteria(session, enabled=True)
    client.post("/api/v1/scheduler/run-searches", headers=HEADERS)
    with Session(app.state.db_engine) as session:
        assert len(session.exec(select(Offer)).all()) == 1
        assert session.exec(select(Application)).all() == []
        assert session.exec(select(EventLog)).all() == []
