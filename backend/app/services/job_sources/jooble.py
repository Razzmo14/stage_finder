"""Jooble source (official API).

API key in the keychain: jooble_api_key. POST JSON search; HTTP transport
is injectable for contract tests with recorded fixtures.
"""

import httpx

from app.core import secrets
from app.services.job_sources.base import (
    NormalizedOffer,
    SearchParams,
)

BASE_URL = "https://jooble.org/api"
API_KEY_SECRET = "jooble_api_key"


class JoobleError(Exception):
    pass


class JoobleJobSource:
    name = "jooble"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=30)

    def search(self, params: SearchParams) -> list[NormalizedOffer]:
        api_key = secrets.get_secret(API_KEY_SECRET)
        if not api_key:
            raise JoobleError(
                f"Jooble API key is not configured ({API_KEY_SECRET} in the keychain)"
            )
        payload: dict = {"page": 1}
        if params.keywords:
            payload["keywords"] = " ".join(params.keywords)
        if params.location:
            payload["location"] = params.location
        with self._client() as client:
            response = client.post(f"{BASE_URL}/{api_key}", json=payload)
        if response.status_code != 200:
            raise JoobleError(f"Jooble search failed: HTTP {response.status_code}")
        jobs = response.json().get("jobs", [])
        return [self._normalize(entry) for entry in jobs]

    @staticmethod
    def _normalize(entry: dict) -> NormalizedOffer:
        offer = NormalizedOffer(
            source="jooble",
            source_id=str(entry.get("id", "")),
            title=entry.get("title", "") or "",
            company=entry.get("company", "") or "",
            location=entry.get("location", "") or "",
            description=entry.get("description", "") or "",
            url=entry.get("link", "") or "",
            contract_type=entry.get("type", "") or "",
            salary_text=str(entry.get("salary", "") or ""),
            published_at=str(entry.get("updated", "") or ""),
            raw_payload=entry,
        )
        offer.compute_hash()
        return offer
