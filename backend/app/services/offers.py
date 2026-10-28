"""Offer ingestion: normalization to the Offer table, hash + fuzzy dedup."""

import re
from difflib import SequenceMatcher

from sqlmodel import Session, select

from app.db.models import Offer
from app.services.job_sources.base import NormalizedOffer

FUZZY_THRESHOLD = 0.92


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _fuzzy_key(value: str) -> str:
    """Normalization for fuzzy comparison: also drop punctuation."""
    return _normalize(re.sub(r"[^\w\s]", "", value))


class IngestResult:
    def __init__(self) -> None:
        self.new: list[Offer] = []
        self.duplicates: list[str] = []

    @property
    def new_count(self) -> int:
        return len(self.new)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicates)


def _fuzzy_duplicate(session: Session, offer: NormalizedOffer) -> Offer | None:
    """Return an existing offer that is a near-duplicate of the new one."""
    company_key = _fuzzy_key(offer.company)
    title_key = _fuzzy_key(offer.title)
    candidates = session.exec(select(Offer)).all()
    for candidate in candidates:
        if _fuzzy_key(candidate.company) != company_key:
            continue
        ratio = SequenceMatcher(None, _fuzzy_key(candidate.title), title_key).ratio()
        if ratio >= FUZZY_THRESHOLD:
            return candidate
    return None


def ingest_offers(session: Session, offers: list[NormalizedOffer]) -> IngestResult:
    """Persist new offers; skip exact (hash, source+id) and fuzzy duplicates."""
    result = IngestResult()
    for normalized in offers:
        if not normalized.dedup_hash:
            normalized.compute_hash()

        existing = session.exec(
            select(Offer).where(Offer.dedup_hash == normalized.dedup_hash)
        ).first()
        if existing is not None:
            result.duplicates.append(normalized.source_id)
            continue

        by_source_id = session.exec(
            select(Offer).where(
                Offer.source == normalized.source,
                Offer.source_id == normalized.source_id,
            )
        ).first()
        if by_source_id is not None:
            result.duplicates.append(normalized.source_id)
            continue

        fuzzy = _fuzzy_duplicate(session, normalized)
        if fuzzy is not None:
            result.duplicates.append(normalized.source_id)
            continue

        row = Offer(
            source=normalized.source,
            source_id=normalized.source_id,
            title=normalized.title,
            company=normalized.company,
            location=normalized.location,
            description=normalized.description,
            url=normalized.url,
            contract_type=normalized.contract_type,
            salary_text=normalized.salary_text,
            published_at=normalized.published_at,
            raw_payload=normalized.raw_payload,
            dedup_hash=normalized.dedup_hash,
            language=normalized.language,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        result.new.append(row)
    return result
