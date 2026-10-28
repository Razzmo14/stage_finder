"""France Travail "Offres d'emploi" source (official API v2).

OAuth2 client credentials (keychain: france_travail_client_id /
france_travail_client_secret) -> POST /oauth/token, then
GET /partenaire/offresdemploi/v2/recherche.
The HTTP layer is injectable so contract tests run against recorded
fixtures without touching the network.
"""

import time

import httpx

from app.core import secrets
from app.services.job_sources.base import (
    NormalizedOffer,
    SearchParams,
)

TOKEN_URL = "https://api.francetravail.io/oauth/token"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/recherche"
SCOPE = "api_offresdemploiv2 oAuth2Password or API_oAuth2Password"

CLIENT_ID_SECRET = "france_travail_client_id"
CLIENT_SECRET_SECRET = "france_travail_client_secret"


class FranceTravailError(Exception):
    pass


class FranceTravailJobSource:
    name = "france_travail"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at: float = 0

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=30)

    def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        client_id = secrets.get_secret(CLIENT_ID_SECRET)
        client_secret = secrets.get_secret(CLIENT_SECRET_SECRET)
        if not client_id or not client_secret:
            raise FranceTravailError(
                "France Travail credentials are not configured "
                f"({CLIENT_ID_SECRET} / {CLIENT_SECRET_SECRET} in the keychain)"
            )
        with self._client() as client:
            response = client.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": SCOPE,
                },
            )
        if response.status_code != 200:
            raise FranceTravailError(f"Token request failed: HTTP {response.status_code}")
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.monotonic() + float(payload.get("expires_in", 3600)) - 60
        return self._token

    def _to_params(self, params: SearchParams) -> dict:
        query: dict = {"range": f"0-{params.limit - 1}"}
        if params.keywords:
            query["motsCles"] = " ".join(params.keywords)
        if params.location:
            query["commune"] = params.location  # commune code or postal handled by caller
        if params.radius_km:
            query["distance"] = params.radius_km
        if params.contract_types:
            query["typeContrat"] = ",".join(params.contract_types)
        if params.date_posted_days:
            query["minCreationTimestamp"] = params.date_posted_days  # simplified mapping
        return query

    def search(self, params: SearchParams) -> list[NormalizedOffer]:
        token = self._access_token()
        with self._client() as client:
            response = client.get(
                SEARCH_URL,
                params=self._to_params(params),
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code != 200:
            raise FranceTravailError(f"Search failed: HTTP {response.status_code}")
        results = response.json().get("resultats", [])
        return [self._normalize(entry) for entry in results]

    @staticmethod
    def _normalize(entry: dict) -> NormalizedOffer:
        offer = NormalizedOffer(
            source="france_travail",
            source_id=str(entry.get("id", "")),
            title=entry.get("intitule", "") or "",
            company=(entry.get("entreprise") or {}).get("nom", "") or "",
            location=(entry.get("lieuTravail") or {}).get("libelle", "") or "",
            description=entry.get("description", "") or "",
            url=(entry.get("origineOffre") or {}).get("urlOrigine", "") or "",
            contract_type=entry.get("typeContrat", "") or "",
            salary_text=(entry.get("salaire") or {}).get("libelle", "") or "",
            published_at=entry.get("dateCreation", "") or "",
            raw_payload=entry,
        )
        offer.compute_hash()
        return offer
