"""Adzuna source (official API).

Credentials in the keychain: adzuna_app_id / adzuna_app_key.
HTTP transport is injectable; contract tests use recorded fixtures.
"""

import time

import httpx

from app.core import secrets
from app.services.job_sources.base import (
    NormalizedOffer,
    SearchParams,
)

BASE_URL = "https://api.adzuna.com/v1/api/jobs"
APP_ID_SECRET = "adzuna_app_id"
APP_KEY_SECRET = "adzuna_app_key"

RATE_LIMIT_SECONDS = 1.0
_last_call: list[float] = []


class AdzunaError(Exception):
    pass


class AdzunaJobSource:
    name = "adzuna"

    def __init__(self, transport: httpx.BaseTransport | None = None, country: str = "fr") -> None:
        self._transport = transport
        self.country = country

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=30)

    def _to_params(self, params: SearchParams) -> dict:
        query: dict = {"results_per_page": params.limit}
        if params.keywords:
            query["what"] = " ".join(params.keywords)
        if params.location:
            query["where"] = params.location
        if params.radius_km:
            query["distance"] = params.radius_km
        if params.contract_types:
            query["contract_type"] = params.contract_types[0]
        if params.date_posted_days:
            query["max_days_old"] = params.date_posted_days
        return query

    def search(self, params: SearchParams) -> list[NormalizedOffer]:
        app_id = secrets.get_secret(APP_ID_SECRET)
        app_key = secrets.get_secret(APP_KEY_SECRET)
        if not app_id or not app_key:
            raise AdzunaError(
                "Adzuna credentials are not configured "
                f"({APP_ID_SECRET} / {APP_KEY_SECRET} in the keychain)"
            )
        _rate_limit()
        with self._client() as client:
            response = client.get(
                f"{BASE_URL}/{self.country}/search/1",
                params={**self._to_params(params), "app_id": app_id, "app_key": app_key},
            )
        if response.status_code != 200:
            raise AdzunaError(f"Adzuna search failed: HTTP {response.status_code}")
        results = response.json().get("results", [])
        return [self._normalize(entry) for entry in results]

    @staticmethod
    def _normalize(entry: dict) -> NormalizedOffer:
        salary = ""
        if entry.get("salary_min") or entry.get("salary_max"):
            salary = f"{entry.get('salary_min', '?')} - {entry.get('salary_max', '?')}"
        offer = NormalizedOffer(
            source="adzuna",
            source_id=str(entry.get("id", "")),
            title=entry.get("title", "") or "",
            company=(entry.get("company") or {}).get("display_name", "") or "",
            location=(entry.get("location") or {}).get("display_name", "") or "",
            description=entry.get("description", "") or "",
            url=entry.get("redirect_url", "") or "",
            contract_type=entry.get("contract_time", "") or "",
            salary_text=salary,
            published_at=entry.get("created", "") or "",
            raw_payload=entry,
        )
        offer.compute_hash()
        return offer


def _rate_limit() -> None:
    """Respect Adzuna's terms: at most one call per second."""
    now = time.monotonic()
    if _last_call and (now - _last_call[0]) < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - (now - _last_call[0]))
    if _last_call:
        _last_call[0] = time.monotonic()
    else:
        _last_call.append(time.monotonic())
