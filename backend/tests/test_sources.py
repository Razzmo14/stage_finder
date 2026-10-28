"""Tests for sources-011: Adzuna, Jooble, cross-source dedup."""

import httpx
import pytest
from sqlmodel import Session, select

from app.core import secrets
from app.db.models import Offer
from app.services.job_sources.adzuna import AdzunaJobSource
from app.services.job_sources.base import NormalizedOffer, SearchParams
from app.services.job_sources.jooble import JoobleJobSource
from app.services.offers import ingest_offers

ADZUNA_FIXTURE = {
    "results": [
        {
            "id": "az-1",
            "title": "Stage Python developpement web",
            "description": "Stage de 6 mois, Python et React.",
            "company": {"display_name": "Acme SARL"},
            "location": {"display_name": "Paris"},
            "contract_time": "full_time",
            "salary_min": 1000,
            "salary_max": 1400,
            "redirect_url": "https://adzuna.example/az-1",
            "created": "2026-10-20T10:00:00Z",
        }
    ]
}

JOOBLE_FIXTURE = {
    "jobs": [
        {
            "id": "jb-1",
            "title": "Stage Python developpement web",
            "description": "Stage de 6 mois, Python et React.",
            "company": "Acme SARL",
            "location": "Paris",
            "salary": "1000-1400 EUR",
            "link": "https://jooble.example/jb-1",
            "updated": "2026-10-20",
            "type": "Stage",
        }
    ]
}


@pytest.fixture(autouse=True)
def memory_secrets():
    secrets.use_backend(secrets.MemoryBackend())
    secrets.set_secret("adzuna_app_id", "app-id")
    secrets.set_secret("adzuna_app_key", "app-key")
    secrets.set_secret("jooble_api_key", "jooble-key")
    yield
    secrets.use_backend(secrets.KeyringBackend())


def test_adzuna_contract_with_recorded_fixture() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=ADZUNA_FIXTURE)

    source = AdzunaJobSource(transport=httpx.MockTransport(handler))
    results = source.search(SearchParams(keywords=["python"], location="Paris", radius_km=10))

    assert len(results) == 1
    offer = results[0]
    assert offer.source == "adzuna"
    assert offer.source_id == "az-1"
    assert offer.company == "Acme SARL"
    assert offer.title == "Stage Python developpement web"
    assert offer.salary_text == "1000 - 1400"
    assert offer.url == "https://adzuna.example/az-1"
    assert offer.dedup_hash
    assert "app_id=app-id" in str(calls[0].url)
    assert "what=python" in str(calls[0].url)


def test_adzuna_missing_credentials() -> None:
    secrets.delete_secret("adzuna_app_id")
    source = AdzunaJobSource(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(Exception, match="credentials are not configured"):
        source.search(SearchParams(keywords=["python"]))


def test_jooble_contract_with_recorded_fixture() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=JOOBLE_FIXTURE)

    source = JoobleJobSource(transport=httpx.MockTransport(handler))
    results = source.search(SearchParams(keywords=["python"], location="Paris"))

    assert len(results) == 1
    offer = results[0]
    assert offer.source == "jooble"
    assert offer.source_id == "jb-1"
    assert offer.company == "Acme SARL"
    assert offer.url == "https://jooble.example/jb-1"
    assert offer.dedup_hash
    # API key is in the URL path, credentials sent via POST body JSON
    assert "jooble-key" in str(calls[0].url)
    assert calls[0].method == "POST"


def test_jooble_missing_credentials() -> None:
    secrets.delete_secret("jooble_api_key")
    source = JoobleJobSource(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(Exception, match="API key is not configured"):
        source.search(SearchParams(keywords=["python"]))


def test_cross_source_dedup_same_offer_appears_once(engine) -> None:
    """The same offer found on two sources appears once."""
    adzuna = AdzunaJobSource(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=ADZUNA_FIXTURE))
    )
    jooble = JoobleJobSource(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=JOOBLE_FIXTURE))
    )
    with Session(engine) as session:
        first = ingest_offers(session, adzuna.search(SearchParams(keywords=["python"])))
        assert first.new_count == 1

        second = ingest_offers(session, jooble.search(SearchParams(keywords=["python"])))
        assert second.new_count == 0
        assert second.duplicate_count == 1

        rows = session.exec(select(Offer)).all()
        assert len(rows) == 1
        assert rows[0].source == "adzuna"


def make_offer(source: str, source_id: str, title: str) -> NormalizedOffer:
    offer = NormalizedOffer(
        source=source, source_id=source_id, title=title, company="C", location="L"
    )
    offer.compute_hash()
    return offer
