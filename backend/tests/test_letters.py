"""Tests for letter-007: letter generation + grounding check."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import config, secrets
from app.db.models import Application, Experience, LLMUsage, Offer, Profile
from app.llm.provider import Completion, CompletionRequest
from app.main import create_app
from app.services.langdetect import detect_language
from app.services.letter_generation.grounding import (
    HeuristicGroundingChecker,
    LLMGroundingChecker,
)
from app.services.letter_generation.service import LetterOutput, generate_letter

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

LETTER_JSON = {
    "letter": "Madame, Monsieur, votre stage Python chez Acme m'intéresse...",
    "email_subject": "Candidature - Stage Python",
    "email_body": "Bonjour, veuillez trouver ma candidature.",
    "claims": [
        "I developed Python tools at Acme.",
        "I have extensive Kubernetes experience.",
    ],
}


class FakeLetterProvider:
    name = "fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.calls.append(request)
        return Completion(
            content=self.reply, model=request.model, prompt_tokens=200, completion_tokens=80
        )


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    application = create_app(session_token=TOKEN)
    application.state.fake_provider = FakeLetterProvider(json.dumps(LETTER_JSON))
    application.state.llm_provider = lambda: application.state.fake_provider
    yield application
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.KeyringBackend())


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def seed(session: Session) -> tuple[Profile, Offer]:
    profile = Profile(
        full_name="Ada Lovelace",
        headline="Python developer",
        summary="I build Python tools.",
        skills=["python", "react", "sql"],
        base_letter="Dear hiring manager, I am a developer.",
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    session.add(
        Experience(
            profile_id=profile.id,
            company="Acme",
            position="Python intern",
            description="Built internal Python tooling.",
            skills=["python"],
        )
    )
    offer = Offer(
        source="ft",
        source_id="1",
        title="Stage Python - developpement web",
        company="Acme",
        location="Paris",
        description="Nous cherchons un stagiaire Python et React pour 6 mois.",
        dedup_hash="h1",
    )
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return profile, offer


# --- Language detection ------------------------------------------------------


def test_detect_language_french_and_english() -> None:
    french = "Nous recherchons un stagiaire pour une mission de 6 mois dans l'entreprise."
    english = "We are looking for an intern for a 6-month role in the company."
    assert detect_language(french) == "fr"
    assert detect_language(english) == "en"


# --- Grounding ---------------------------------------------------------------


def test_heuristic_grounding_flags_fabricated_skill(engine) -> None:
    with Session(engine) as session:
        profile, _ = seed(session)
        experiences = session.exec(select(Experience)).all()
        checker = HeuristicGroundingChecker()
        verdicts = checker.check(LETTER_JSON["claims"], profile, experiences)

        by_claim = {v.claim: v for v in verdicts}
        assert by_claim["I developed Python tools at Acme."].supported is True
        assert by_claim["I have extensive Kubernetes experience."].supported is False
        assert "Kubernetes" in by_claim["I have extensive Kubernetes experience."].reason


def test_llm_grounding_checker_with_mocked_verifier(engine) -> None:
    with Session(engine) as session:
        profile, _ = seed(session)
        experiences = session.exec(select(Experience)).all()

        reply = json.dumps(
            {
                "claims": [
                    {"claim": "I developed Python tools at Acme.", "supported": True, "reason": ""},
                    {
                        "claim": "I have extensive Kubernetes experience.",
                        "supported": False,
                        "reason": "Kubernetes is not in the profile",
                    },
                ]
            }
        )
        checker = LLMGroundingChecker(FakeLetterProvider(reply), "vendor/capable", True)
        verdicts = checker.check(LETTER_JSON["claims"], profile, experiences)
        assert verdicts[0].supported is True
        assert verdicts[1].supported is False
        assert verdicts[1].reason


# --- Letter generation -------------------------------------------------------


def test_generate_letter_language_follows_offer(engine) -> None:
    with Session(engine) as session:
        profile, offer = seed(session)
        experiences = session.exec(select(Experience)).all()
        provider = FakeLetterProvider(json.dumps(LETTER_JSON))
        letter, _ = generate_letter(
            provider,
            model="vendor/capable",
            supports_structured=True,
            profile=profile,
            offer=offer,
            experiences=experiences,
        )
        # The French offer triggers a French instruction in the prompt
        user_prompt = provider.calls[0].messages[-1].content
        assert "French" in user_prompt
        # Structured output validates against the schema
        assert isinstance(letter, LetterOutput)
        assert letter.claims == LETTER_JSON["claims"]


def test_generate_letter_english_offer(engine) -> None:
    with Session(engine) as session:
        profile, _ = seed(session)
        offer = Offer(
            source="ft",
            source_id="2",
            title="Python internship",
            company="Acme",
            description="We are looking for a Python intern for our team.",
            dedup_hash="h2",
        )
        session.add(offer)
        session.commit()
        session.refresh(offer)
        provider = FakeLetterProvider(json.dumps(LETTER_JSON))
        generate_letter(
            provider,
            model="vendor/capable",
            supports_structured=True,
            profile=profile,
            offer=offer,
            experiences=[],
        )
        assert "English" in provider.calls[0].messages[-1].content


# --- API end to end -----------------------------------------------------------


def test_letters_generate_creates_pending_review_application(client, app) -> None:
    with Session(app.state.db_engine) as session:
        profile, offer = seed(session)
        profile_id, offer_id = profile.id, offer.id

    response = client.post(
        "/api/v1/letters/generate", json={"offer_id": offer_id}, headers=HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_review"
    assert body["email_subject"] == "Candidature - Stage Python"
    assert len(body["claims"]) == 2
    assert len(body["flagged_claims"]) == 1
    assert body["flagged_claims"][0]["supported"] is False

    with Session(app.state.db_engine) as session:
        application = session.exec(select(Application)).one()
        assert application.status == "pending_review"
        assert application.profile_id == profile_id
        usage = session.exec(select(LLMUsage)).all()
        assert len(usage) == 1
        assert usage[0].task == "letter_generation"

    # Regeneration updates the same application row
    response = client.post(
        "/api/v1/letters/generate",
        json={"offer_id": offer_id, "regenerate": True},
        headers=HEADERS,
    )
    assert response.status_code == 200
    with Session(app.state.db_engine) as session:
        assert len(session.exec(select(Application)).all()) == 1


def test_letters_generate_requires_auth(client) -> None:
    assert client.post("/api/v1/letters/generate", json={"offer_id": 1}).status_code == 401


def test_letters_generate_unknown_offer(client) -> None:
    with Session(client.app.state.db_engine) as session:
        profile = Profile(full_name="Ada")
        session.add(profile)
        session.commit()
    response = client.post(
        "/api/v1/letters/generate", json={"offer_id": 999}, headers=HEADERS
    )
    assert response.status_code == 404
