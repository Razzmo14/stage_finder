"""Saved search criteria API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import DbDep
from app.db.models import SearchCriteria

router = APIRouter()


class CriteriaIn(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)
    location: str = ""
    radius_km: int | None = None
    contract_types: list[str] = Field(default_factory=list)
    remote: bool = False
    salary_min: int | None = None
    seniority: str = ""
    languages: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=lambda: ["france_travail"])
    date_posted_days: int | None = None
    schedule: str = ""
    enabled: bool = True


class CriteriaOut(CriteriaIn):
    id: int


def _to_out(row: SearchCriteria) -> CriteriaOut:
    return CriteriaOut(
        id=row.id,
        name=row.name,
        keywords=row.keywords,
        location=row.location,
        radius_km=row.radius_km,
        contract_types=row.contract_types,
        remote=row.remote,
        salary_min=row.salary_min,
        seniority=row.seniority,
        languages=row.languages,
        sources=row.sources,
        date_posted_days=row.date_posted_days,
        schedule=row.schedule,
        enabled=row.enabled,
    )


def _apply(row: SearchCriteria, payload: CriteriaIn) -> None:
    for field_name in (
        "name",
        "keywords",
        "location",
        "radius_km",
        "contract_types",
        "remote",
        "salary_min",
        "seniority",
        "languages",
        "sources",
        "date_posted_days",
        "schedule",
        "enabled",
    ):
        setattr(row, field_name, getattr(payload, field_name))


@router.get("/criteria", response_model=list[CriteriaOut])
def list_criteria(session: DbDep) -> list[CriteriaOut]:
    rows = session.exec(select(SearchCriteria).order_by(SearchCriteria.id)).all()
    return [_to_out(r) for r in rows]


@router.post("/criteria", response_model=CriteriaOut)
def create_criteria(payload: CriteriaIn, session: DbDep) -> CriteriaOut:
    row = SearchCriteria()
    _apply(row, payload)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.get("/criteria/{criteria_id}", response_model=CriteriaOut)
def read_criteria(criteria_id: int, session: DbDep) -> CriteriaOut:
    row = session.get(SearchCriteria, criteria_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Criteria not found")
    return _to_out(row)


@router.put("/criteria/{criteria_id}", response_model=CriteriaOut)
def update_criteria(criteria_id: int, payload: CriteriaIn, session: DbDep) -> CriteriaOut:
    row = session.get(SearchCriteria, criteria_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Criteria not found")
    _apply(row, payload)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.delete("/criteria/{criteria_id}", status_code=204)
def delete_criteria(criteria_id: int, session: DbDep) -> None:
    row = session.get(SearchCriteria, criteria_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Criteria not found")
    session.delete(row)
    session.commit()
