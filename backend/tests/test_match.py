"""Tests for match-006: embedding similarity + LLM re-ranking."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import config, secrets
from app.db.models import LLMUsage, MatchResult, Offer, Profile
from app.llm.provider import Completion, CompletionRequest
from app.main import create_app
from app.services.matching.embeddings import HashingEmbedder, cosine, decode_vector, encode_vector
from app.services.matching.service import (
    MatchJudgement,
    run_matching,
    stage1_similarity,
)

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

JUDGEMENTS = {
    "Stage Python - developpement web": {
        "score": 82,
        "rationale": "Strong Python overlap",
        "matched_skills": ["python"],
        "missing_skills": ["docker"],
        "red_flags": [],
    },
    "Stage data engineer": {
        "score": 41,
        "rationale": "Weak overlap with the profile",
        "matched_skills": [],
        "missing_skills": ["spark", "sql"],
        "red_flags": ["requires relocation"],
    },
    "Developpeur React (stage)": {
        "score": 55,
        "rationale": "Partial front-end overlap",
        "matched_skills": ["react"],
        "missing_skills": ["typescript"],
        "red_flags": [],
    },
}


class FakeMatchProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.calls.append(request)
        user_text = request.messages[-1].content
        for title, judgement in JUDGEMENTS.items():
            if title in user_text:
                return Completion(
                    content=json.dumps(judgement),
                    model=request.model,
                    prompt_tokens=100,
                    completion_tokens=50,
                )
        return Completion(
            content=json.dumps({"score": 0, "rationale": "?"}),
            model=request.model,
            prompt_tokens=100,
            completion_tokens=50,
        )


def seed(session: Session) -> Profile:
    profile = Profile(
        full_name="Ada",
        headline="Python developer",
        summary="I build Python tools and React interfaces.",
        skills=["python", "react", "sql"],
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    offers = [
        Offer(source="ft", source_id="1", title="Stage Python - developpement web",
              company="Acme", description="Python, FastAPI, some React.",
              dedup_hash="h1"),
        Offer(source="ft", source_id="2", title="Stage data engineer",
              company="DataCorp", description="Spark pipelines and dbt.",
              dedup_hash="h2"),
        Offer(source="ft", source_id="3", title="Developpeur React (stage)",
              company="WebCo", description="React front-end internship.",
              dedup_hash="h3"),
    ]
    for offer in offers:
        session.add(offer)
    session.commit()
    return profile


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    application = create_app(session_token=TOKEN)
    application.state.fake_provider = FakeMatchProvider()
    application.state.llm_provider = lambda: application.state.fake_provider
    yield application
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.KeyringBackend())


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def test_hashing_embedder_deterministic_and_similarity() -> None:
    embedder = HashingEmbedder()
    a1 = embedder.embed(["python developer react"])[0]
    a2 = embedder.embed(["python developer react"])[0]
    b = embedder.embed(["spark dbt data pipelines"])[0]
    assert a1 == a2  # deterministic
    assert cosine(a1, a2) == pytest.approx(1.0)
    assert cosine(a1, b) < 0.6
    assert all(abs(v) <= 1.0 for v in a1)
    # round-trip serialization
    assert decode_vector(encode_vector(a1)) == pytest.approx(a1, abs=1e-6)


def test_stage1_ranks_relevant_offer_first(engine) -> None:
    with Session(engine) as session:
        profile = seed(session)
        offers = session.exec(select(Offer)).all()
        ranked = stage1_similarity(session, profile, offers, HashingEmbedder())
        titles = [offer.title for offer, _ in ranked]
        assert titles[0] == "Stage Python - developpement web"
        # Embeddings were stored with the model name
        offer = session.exec(select(Offer).where(Offer.title == titles[0])).one()
        assert offer.embedding is not None
        assert offer.embedding_model == "local-hashing-v1"


def test_stage1_reuses_stored_embedding(engine) -> None:
    with Session(engine) as session:
        profile = seed(session)
        offers = session.exec(select(Offer)).all()
        stage1_similarity(session, profile, offers, HashingEmbedder())
        calls = []

        class CountingEmbedder(HashingEmbedder):
            def embed(self, texts):
                calls.extend(texts)
                return super().embed(texts)

        stage1_similarity(session, profile, offers, CountingEmbedder())
        # only the profile text is re-embedded; offers come from the DB
        assert len(calls) == 1


def test_run_matching_stores_results_with_model(engine) -> None:
    with Session(engine) as session:
        profile = seed(session)
        offers = session.exec(select(Offer)).all()
        provider = FakeMatchProvider()

        def record_usage(completion) -> None:
            from app.llm.usage import record_completion

            record_completion(session, task="matching", completion=completion, cost=0.0)

        results = run_matching(
            session,
            provider,
            model="vendor/capable",
            supports_structured=True,
            profile=profile,
            offers=offers,
            top_n=2,
            record_usage=record_usage,
        )
        assert len(results) == 2
        assert {r.model for r in results} == {"vendor/capable"}
        # Stage 1 puts the Python offer first; the rest is ranked by similarity
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0].score == 82
        assert results[0].rationale == "Strong Python overlap"
        rows = session.exec(select(MatchResult)).all()
        assert len(rows) == 2
        usage = session.exec(select(LLMUsage)).all()
        assert len(usage) == 2
        assert all(u.task == "matching" for u in usage)


def test_stage2_structured_judgement_schema() -> None:
    judgement = MatchJudgement.model_validate(
        {"score": 72, "rationale": "ok", "matched_skills": ["python"],
         "missing_skills": [], "red_flags": []}
    )
    assert judgement.score == 72
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MatchJudgement.model_validate({"score": 150})


def test_match_run_endpoint_and_sorted_offers(client) -> None:
    client.put(
        "/api/v1/profile",
        json={"full_name": "Ada", "headline": "Python developer",
              "summary": "Python and React.", "skills": ["python", "react", "sql"]},
        headers=HEADERS,
    )
    with Session(client.app.state.db_engine) as session:
        session.add(Offer(source="ft", source_id="1", title="Stage Python - developpement web",
                          company="Acme", description="Python, FastAPI, React.", dedup_hash="h1"))
        session.add(Offer(source="ft", source_id="2", title="Stage data engineer",
                          company="DataCorp", description="Spark pipelines.", dedup_hash="h2"))
        session.add(Offer(source="ft", source_id="3", title="Comptable stagiaire",
                          company="PaperCo", description="Accounting internship.", dedup_hash="h3"))
        session.commit()

    response = client.post("/api/v1/match/run", json={"top_n": 2}, headers=HEADERS)
    assert response.status_code == 200
    matches = response.json()
    assert len(matches) == 2
    assert matches[0]["score"] == 82
    assert matches[0]["model"]

    # Offers list sorted by score, unmatched offers last
    offers = client.get("/api/v1/offers?sort=score", headers=HEADERS).json()
    scored = [o for o in offers if o["match"]]
    unscored = [o for o in offers if not o["match"]]
    assert len(scored) == 2
    assert len(unscored) == 1
    assert [o["match"]["score"] for o in scored] == sorted(
        (o["match"]["score"] for o in scored), reverse=True
    )
    assert offers[-1]["match"] is None


def test_match_run_requires_profile(client) -> None:
    response = client.post("/api/v1/match/run", json={"top_n": 2}, headers=HEADERS)
    assert response.status_code == 422
    assert "profile" in response.json()["detail"].lower()
