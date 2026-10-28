"""Offers API: list, flag, and manual search runs."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import DbDep
from app.db.models import Offer, SearchCriteria
from app.services.job_sources.base import JobSource, NormalizedOffer, SearchParams
from app.services.offers import ingest_offers

router = APIRouter()


class OfferOut(BaseModel):
    id: int
    source: str
    source_id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    contract_type: str
    salary_text: str
    published_at: str
    language: str
    seen: bool
    ignored: bool
    dedup_hash: str


class OfferPatch(BaseModel):
    seen: bool | None = None
    ignored: bool | None = None


class RunSearchIn(BaseModel):
    criteria_id: int


class RunSearchOut(BaseModel):
    new: int
    duplicates: int


def get_sources(request: Request) -> dict[str, JobSource]:
    return request.app.state.job_sources


SourcesDep = Annotated[dict[str, JobSource], Depends(get_sources)]


def _to_out(row: Offer) -> OfferOut:
    return OfferOut(
        id=row.id,
        source=row.source,
        source_id=row.source_id,
        title=row.title,
        company=row.company,
        location=row.location,
        description=row.description,
        url=row.url,
        contract_type=row.contract_type,
        salary_text=row.salary_text,
        published_at=row.published_at,
        language=row.language,
        seen=row.seen,
        ignored=row.ignored,
        dedup_hash=row.dedup_hash,
    )


@router.get("/offers", response_model=list[OfferOut])
def list_offers(
    session: DbDep,
    source: str | None = None,
    include_ignored: bool = False,
    include_seen: bool = True,
    limit: int = 100,
) -> list[OfferOut]:
    statement = select(Offer).order_by(Offer.fetched_at.desc())  # type: ignore[union-attr]
    if source:
        statement = statement.where(Offer.source == source)
    if not include_ignored:
        statement = statement.where(Offer.ignored.is_(False))  # type: ignore[union-attr]
    if not include_seen:
        statement = statement.where(Offer.seen.is_(False))  # type: ignore[union-attr]
    rows = session.exec(statement.limit(limit)).all()
    return [_to_out(r) for r in rows]


@router.get("/offers/{offer_id}", response_model=OfferOut)
def read_offer(offer_id: int, session: DbDep) -> OfferOut:
    row = session.get(Offer, offer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    return _to_out(row)


@router.patch("/offers/{offer_id}", response_model=OfferOut)
def patch_offer(offer_id: int, payload: OfferPatch, session: DbDep) -> OfferOut:
    row = session.get(Offer, offer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    if payload.seen is not None:
        row.seen = payload.seen
    if payload.ignored is not None:
        row.ignored = payload.ignored
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


def _params_from_criteria(criteria: SearchCriteria) -> SearchParams:
    return SearchParams(
        keywords=criteria.keywords,
        location=criteria.location,
        radius_km=criteria.radius_km,
        contract_types=criteria.contract_types,
        remote=criteria.remote,
        date_posted_days=criteria.date_posted_days,
    )


@router.post("/search/run", response_model=RunSearchOut)
def run_search(
    payload: RunSearchIn,
    session: DbDep,
    sources: SourcesDep,
) -> RunSearchOut:
    """Run a manual search for the given criteria across its enabled sources."""
    criteria = session.get(SearchCriteria, payload.criteria_id)
    if criteria is None:
        raise HTTPException(status_code=404, detail="Criteria not found")
    if not criteria.enabled:
        raise HTTPException(status_code=422, detail="Criteria is disabled")

    new_total = 0
    duplicate_total = 0
    errors: list[str] = []
    params = _params_from_criteria(criteria)
    for source_name in criteria.sources:
        source = sources.get(source_name)
        if source is None:
            raise HTTPException(status_code=422, detail=f"Unknown source: {source_name}")
        try:
            results: list[NormalizedOffer] = source.search(params)
        except Exception as error:  # noqa: BLE001 - collect and report per-source
            raise HTTPException(status_code=502, detail=f"{source_name}: {error}") from error
        outcome = ingest_offers(session, results)
        new_total += outcome.new_count
        duplicate_total += outcome.duplicate_count
    if errors:  # pragma: no cover - reserved for multi-source aggregation
        raise HTTPException(status_code=502, detail="; ".join(errors))
    return RunSearchOut(new=new_total, duplicates=duplicate_total)
