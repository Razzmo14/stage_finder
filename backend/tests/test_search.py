"""Tests for search-005: France Travail source, criteria, dedup ingestion."""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import config, secrets
from app.db.models import Offer
from app.main import create_app
from app.services.job_sources.base import NormalizedOffer, SearchParams
from app.services.job_sources.france_travail import FranceTravailJobSource
from app.services.offers import ingest_offers

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

TOKEN_RESPONSE = {"access_token": "fake-token", "expires_in": 3600}

FT_FIXTURE = {
    "resultats": [
        {
            "id": "ABC123",
            "intitule": "Stage Python - developpement web",
            "description": "Stage de 6 mois en developpement Python/React.",
            "typeContrat": "CDD",
            "dateCreation": "2026-10-20T10:00:00+02:00",
            "lieuTravail": {"libelle": "75001 - Paris"},
            "entreprise": {"nom": "Acme SARL"},
            "salaire": {"libelle": "Mensuel brut: 1000 EUR"},
            "origineOffre": {"urlOrigine": "https://example.com/abc123"},
        },
        {
            "id": "DEF456",
            "intitule": "Developpeur React (stage)",
            "description": "Stage front-end React.",
            "typeContrat": "CDD",
            "dateCreation": "2026-10-21T10:00:00+02:00",
            "lieuTravail": {"libelle": "69003 - Lyon"},
            "entreprise": {"nom": "Gizmo"},
            "origineOffre": {"urlOrigine": "https://example.com/def456"},
        },
    ]
}


class FakeSource:
    """A source with canned results; records the params it received."""

    name = "france_travail"

    def __init__(self, offers: list[NormalizedOffer]) -> None:
        self.offers = offers
        self.calls: list[SearchParams] = []

    def search(self, params: SearchParams) -> list[NormalizedOffer]:
        self.calls.append(params)
        return self.offers


def make_offer(source_id: str, title: str, company: str = "Acme SARL", **kwargs) -> NormalizedOffer:
    offer = NormalizedOffer(
        source="france_travail",
        source_id=source_id,
        title=title,
        company=company,
        location=kwargs.get("location", "75001 - Paris"),
        description=kwargs.get("description", ""),
        url=kwargs.get("url", ""),
        contract_type=kwargs.get("contract_type", "CDD"),
        published_at=kwargs.get("published_at", ""),
    )
    offer.compute_hash()
    return offer


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    application = create_app(session_token=TOKEN)
    application.state.fake_source = FakeSource(
        [
            make_offer("ABC123", "Stage Python - developpement web", company="Acme SARL"),
            make_offer("GHI789", "Stage data engineer", company="Other Corp"),
        ]
    )
    application.state.job_sources = {"france_travail": application.state.fake_source}
    yield application
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.KeyringBackend())


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


# --- France Travail source contract (recorded fixtures, mocked HTTP) --------


def test_france_travail_source_contract(engine) -> None:
    secrets.use_backend(secrets.MemoryBackend())
    try:
        _run_ft_contract()
    finally:
        secrets.use_backend(secrets.KeyringBackend())


def _run_ft_contract() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/oauth/token"):
            assert "grant_type=client_credentials" in request.content.decode()
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(200, json=FT_FIXTURE)

    secrets.set_secret("france_travail_client_id", "cid")
    secrets.set_secret("france_travail_client_secret", "csecret")

    source = FranceTravailJobSource(transport=httpx.MockTransport(handler))
    results = source.search(SearchParams(keywords=["python"], location="75001", radius_km=10))

    assert len(results) == 2
    first = results[0]
    assert first.source == "france_travail"
    assert first.source_id == "ABC123"
    assert first.title == "Stage Python - developpement web"
    assert first.company == "Acme SARL"
    assert first.location == "75001 - Paris"
    assert first.contract_type == "CDD"
    assert first.url == "https://example.com/abc123"
    assert first.dedup_hash
    # Bearer token sent on the search call
    search_calls = [c for c in calls if not c.url.path.endswith("/oauth/token")]
    assert search_calls[0].headers["Authorization"] == "Bearer fake-token"
    assert "motsCles=python" in str(search_calls[0].url)


def test_france_travail_missing_credentials() -> None:
    secrets.use_backend(secrets.MemoryBackend())
    try:
        source = FranceTravailJobSource(
            transport=httpx.MockTransport(lambda r: httpx.Response(500))
        )
        with pytest.raises(Exception, match="credentials are not configured"):
            source.search(SearchParams(keywords=["python"]))
    finally:
        secrets.use_backend(secrets.KeyringBackend())


# --- Dedup ingestion ---------------------------------------------------------


def test_ingest_dedup_by_hash_and_source_id(engine) -> None:
    with Session(engine) as session:
        result = ingest_offers(session, [make_offer("ABC123", "Stage Python")])
        assert result.new_count == 1
        assert result.duplicate_count == 0

        # Same offer again: hash duplicate
        result = ingest_offers(session, [make_offer("ABC123", "Stage Python")])
        assert result.new_count == 0
        assert result.duplicate_count == 1

        # Same source_id, slightly different content: still duplicate
        result = ingest_offers(
            session, [make_offer("ABC123", "Stage Python (remote ok)")]
        )
        assert result.duplicate_count == 1


def test_ingest_fuzzy_dedup(engine) -> None:
    with Session(engine) as session:
        first = make_offer("X1", "Stage Python developpement web", company="Acme SARL")
        ingest_offers(session, [first])
        # Different id + slightly different title/company: fuzzy duplicate
        result = ingest_offers(
            session,
            [make_offer("X2", "Stage Python  developpement web!", company="Acme S.A.R.L.")],
        )
        assert result.new_count == 0
        assert result.duplicate_count == 1


def test_ingest_keeps_distinct_offers(engine) -> None:
    with Session(engine) as session:
        result = ingest_offers(
            session,
            [
                make_offer("A1", "Stage Python", company="Acme"),
                make_offer("B2", "Stage Rust", company="Acme"),
                make_offer("C3", "Stage Python", company="Other"),
            ],
        )
        assert result.new_count == 3
        assert len(session.exec(select(Offer)).all()) == 3


# --- Criteria API + search run -----------------------------------------------


def test_criteria_crud_and_rerun(client) -> None:
    payload = {
        "name": "Python stages",
        "keywords": ["python", "stage"],
        "location": "75001",
        "radius_km": 10,
        "contract_types": ["CDD"],
        "sources": ["france_travail"],
    }
    created = client.post("/api/v1/criteria", json=payload, headers=HEADERS)
    assert created.status_code == 200
    criteria_id = created.json()["id"]
    assert created.json()["enabled"] is True

    read = client.get(f"/api/v1/criteria/{criteria_id}", headers=HEADERS).json()
    assert read["keywords"] == ["python", "stage"]

    updated = client.put(
        f"/api/v1/criteria/{criteria_id}",
        json={**payload, "radius_km": 25},
        headers=HEADERS,
    )
    assert updated.json()["radius_km"] == 25

    # First run: both offers are new
    run = client.post("/api/v1/search/run", json={"criteria_id": criteria_id}, headers=HEADERS)
    assert run.status_code == 200
    assert run.json() == {"new": 2, "duplicates": 0}
    assert client.app.state.fake_source.calls[0].keywords == ["python", "stage"]
    assert client.app.state.fake_source.calls[0].radius_km == 25

    # Rerun: same offers are deduplicated and persisted
    run = client.post("/api/v1/search/run", json={"criteria_id": criteria_id}, headers=HEADERS)
    assert run.json() == {"new": 0, "duplicates": 2}

    offers = client.get("/api/v1/offers", headers=HEADERS).json()
    assert len(offers) == 2
    assert offers[0]["source"] == "france_travail"

    client.delete(f"/api/v1/criteria/{criteria_id}", headers=HEADERS)
    assert client.get(f"/api/v1/criteria/{criteria_id}", headers=HEADERS).status_code == 404


def test_offer_flags_and_filters(client) -> None:
    criteria_id = client.post(
        "/api/v1/criteria", json={"name": "x", "keywords": ["python"]}, headers=HEADERS
    ).json()["id"]
    client.post("/api/v1/search/run", json={"criteria_id": criteria_id}, headers=HEADERS)
    offers = client.get("/api/v1/offers", headers=HEADERS).json()
    offer_id = offers[0]["id"]

    patched = client.patch(
        f"/api/v1/offers/{offer_id}", json={"ignored": True}, headers=HEADERS
    )
    assert patched.json()["ignored"] is True

    visible = client.get("/api/v1/offers", headers=HEADERS).json()
    assert all(o["id"] != offer_id for o in visible)

    detail = client.get(f"/api/v1/offers/{offer_id}", headers=HEADERS).json()
    assert detail["ignored"] is True


def test_search_run_unknown_criteria(client) -> None:
    response = client.post("/api/v1/search/run", json={"criteria_id": 999}, headers=HEADERS)
    assert response.status_code == 404


def test_search_run_requires_auth(client) -> None:
    assert client.post("/api/v1/search/run", json={"criteria_id": 1}).status_code == 401
