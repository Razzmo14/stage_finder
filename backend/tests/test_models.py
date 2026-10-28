"""Model round-trip tests for feature db-002: create, read, update, delete."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db.models import (
    Application,
    Document,
    Education,
    EventLog,
    Experience,
    LLMUsage,
    MatchResult,
    ModelConfig,
    Offer,
    Profile,
    Project,
    SearchCriteria,
)


@pytest.fixture
def session(engine) -> Session:
    with Session(engine, expire_on_commit=False) as session:
        yield session


def make_profile(session: Session) -> Profile:
    profile = Profile(
        full_name="Ada Lovelace",
        email="ada@example.com",
        headline="Software engineering student",
        skills=["python", "react"],
        languages=["en", "fr"],
        base_letter="Dear hiring manager,",
    )
    session.add(profile)
    session.commit()
    return profile


def make_offer(session: Session, source: str = "france_travail", source_id: str = "123") -> Offer:
    offer = Offer(
        source=source,
        source_id=source_id,
        title="Stage Python",
        company="Acme",
        dedup_hash="hash-123",
        raw_payload={"id": source_id},
    )
    session.add(offer)
    session.commit()
    return offer


def test_profile_round_trip_with_children(session: Session) -> None:
    profile = make_profile(session)
    profile_id = profile.id

    read = session.get(Profile, profile_id)
    assert read is not None
    assert read.full_name == "Ada Lovelace"
    assert read.skills == ["python", "react"]

    read.headline = "Updated headline"
    session.add(read)
    session.commit()
    assert session.get(Profile, profile_id).headline == "Updated headline"

    for child in (Experience(company="Acme", position="Intern"), Education(school="ENSIMAG")):
        child.profile_id = profile_id
        session.add(child)
    session.add(Project(name="Stage Finder", profile_id=profile_id, skills=["tauri"]))
    session.add(Document(profile_id=profile_id, kind="cv", filename="cv.pdf"))
    session.commit()

    experiences = session.exec(
        select(Experience).where(Experience.profile_id == profile_id)
    ).all()
    assert len(experiences) == 1 and experiences[0].company == "Acme"
    assert len(session.exec(select(Education).where(Education.profile_id == profile_id)).all()) == 1
    assert len(session.exec(select(Project).where(Project.profile_id == profile_id)).all()) == 1
    assert len(session.exec(select(Document).where(Document.profile_id == profile_id)).all()) == 1

    # Foreign keys protect children from orphaning
    with pytest.raises(IntegrityError):
        session.delete(read)
        session.commit()
    session.rollback()

    for table in (Experience, Education, Project, Document):
        for row in session.exec(select(table).where(table.profile_id == profile_id)).all():
            session.delete(row)
    session.flush()
    session.delete(read)
    session.commit()
    assert session.get(Profile, profile_id) is None


def test_search_criteria_round_trip(session: Session) -> None:
    criteria = SearchCriteria(name="Python internships", keywords=["python", "stage"], remote=True)
    session.add(criteria)
    session.commit()

    read = session.exec(
        select(SearchCriteria).where(SearchCriteria.name == "Python internships")
    ).one()
    assert read.keywords == ["python", "stage"]
    assert read.remote is True
    assert read.enabled is True

    read.enabled = False
    session.add(read)
    session.commit()
    assert session.exec(select(SearchCriteria)).one().enabled is False

    session.delete(read)
    session.commit()
    assert list(session.exec(select(SearchCriteria)).all()) == []


def test_offer_match_result_and_application_round_trip(session: Session) -> None:
    profile = make_profile(session)
    offer = make_offer(session)

    match = MatchResult(
        offer_id=offer.id,
        profile_id=profile.id,
        score=87,
        rationale="Strong Python overlap",
        matched_skills=["python"],
        missing_skills=["rust"],
        red_flags=["unpaid"],
        model="openrouter/default",
    )
    session.add(match)
    application = Application(
        offer_id=offer.id,
        profile_id=profile.id,
        status="pending_review",
        recipient="jobs@acme.com",
        email_subject="Candidature stage Python",
    )
    session.add(application)
    session.commit()

    read_match = session.get(MatchResult, match.id)
    assert read_match.score == 87
    assert read_match.model == "openrouter/default"

    read_app = session.get(Application, application.id)
    assert read_app.status == "pending_review"

    read_app.status = "draft_saved"
    session.add(read_app)
    session.commit()
    assert session.get(Application, application.id).status == "draft_saved"

    session.add(
        EventLog(event_type="status_changed", application_id=read_app.id, detail="draft_saved")
    )
    session.add(
        LLMUsage(
            task="letter_generation", model="m", prompt_tokens=10, completion_tokens=5, cost=0.001
        )
    )
    session.commit()

    events = session.exec(select(EventLog).where(EventLog.application_id == read_app.id)).all()
    assert len(events) == 1
    usage = session.exec(select(LLMUsage)).one()
    assert usage.cost == pytest.approx(0.001)

    session.delete(read_app)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    # EventLog rows must be removed before their application
    for row in session.exec(select(EventLog).where(EventLog.application_id == read_app.id)).all():
        session.delete(row)
    session.flush()
    session.delete(read_app)
    session.commit()
    assert session.get(Application, application.id) is None
    assert session.exec(select(EventLog).where(EventLog.application_id == read_app.id)).all() == []


def test_offer_dedup_constraint(session: Session) -> None:
    make_offer(session, source="france_travail", source_id="123")
    session.add(Offer(source="france_travail", source_id="123", dedup_hash="hash-123"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    # Same source_id on another source is allowed
    session.add(Offer(source="adzuna", source_id="123", dedup_hash="hash-456"))
    session.commit()


def test_model_config_unique_task(session: Session) -> None:
    session.add(ModelConfig(task="matching", provider="openrouter", model="m1"))
    session.commit()
    session.add(ModelConfig(task="matching", provider="openrouter", model="m2"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(ModelConfig(task="letter_generation", provider="openrouter", model="m2"))
    session.commit()
    assert len(session.exec(select(ModelConfig)).all()) == 2
