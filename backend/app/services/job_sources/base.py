"""JobSource plugin interface.

Every source (France Travail, Adzuna, Jooble, ...) normalizes its results to
NormalizedOffer. Sources respect their provider's terms and rate limits.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field


class SearchParams(BaseModel):
    """User-facing search parameters, mapped by each source to its API."""

    keywords: list[str] = Field(default_factory=list)
    location: str = ""
    radius_km: int | None = None
    contract_types: list[str] = Field(default_factory=list)
    remote: bool = False
    date_posted_days: int | None = None
    limit: int = 30


@dataclass
class NormalizedOffer:
    source: str
    source_id: str
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    contract_type: str = ""
    salary_text: str = ""
    published_at: str = ""
    raw_payload: dict = field(default_factory=dict)
    language: str = ""
    dedup_hash: str = ""

    def compute_hash(self) -> str:
        """Stable hash over the identity of the offer (company/title/location)."""
        identity = "|".join(
            _normalize(part)
            for part in (
                self.company,
                self.title,
                self.location,
            )
        )
        self.dedup_hash = hashlib.sha256(identity.encode()).hexdigest()
        return self.dedup_hash


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


class JobSource(Protocol):
    """A job board connector."""

    name: str

    def search(self, params: SearchParams) -> list[NormalizedOffer]:
        """Query the source and return normalized offers."""
        ...
