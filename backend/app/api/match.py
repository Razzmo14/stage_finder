"""Matching API: run the pipeline, expose scores on offers."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import DbDep
from app.db.models import MatchResult, Offer, Profile
from app.llm.registry import provider_supports_structured
from app.llm.usage import record_completion
from app.services.matching.service import run_matching

router = APIRouter()


class RunMatchIn(BaseModel):
    top_n: int = 10


class MatchOut(BaseModel):
    offer_id: int
    score: int
    rationale: str
    matched_skills: list[str]
    missing_skills: list[str]
    red_flags: list[str]
    model: str


def get_embedder(request: Request):
    return request.app.state.embedder


def _match_out(match: MatchResult) -> MatchOut:
    return MatchOut(
        offer_id=match.offer_id,
        score=match.score,
        rationale=match.rationale,
        matched_skills=match.matched_skills,
        missing_skills=match.missing_skills,
        red_flags=match.red_flags,
        model=match.model,
    )


@router.post("/match/run", response_model=list[MatchOut])
def run_match(
    payload: RunMatchIn,
    request: Request,
    session: DbDep,
    embedder: Annotated[object, Depends(get_embedder)],
) -> list[MatchOut]:
    """Stage 1 (embedding similarity) + stage 2 (LLM re-ranking)."""
    profile = session.exec(select(Profile)).first()
    if profile is None:
        raise HTTPException(status_code=422, detail="Create a profile first")

    statement = select(Offer).where(Offer.ignored.is_(False))  # type: ignore[union-attr]
    offers = session.exec(statement).all()
    if not offers:
        return []

    provider = request.app.state.llm_provider()
    catalog = request.app.state.catalog
    model = request.app.state.get_task_model("matching")

    from app.llm.budget import BudgetExceededError, ensure_budget

    try:
        ensure_budget(session)
    except BudgetExceededError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    def record_usage(completion) -> None:
        info = catalog.get(completion.model)
        cost = (
            info.estimate_cost(completion.prompt_tokens, completion.completion_tokens)
            if info
            else 0.0
        )
        record_completion(session, task="matching", completion=completion, cost=cost)

    try:
        results = run_matching(
            session,
            provider,
            model=model,
            supports_structured=provider_supports_structured(provider, catalog, model),
            profile=profile,
            offers=offers,
            top_n=payload.top_n,
            embedder=embedder,
            record_usage=record_usage,
        )
    except Exception as error:  # noqa: BLE001 - provider failures are 502
        raise HTTPException(status_code=502, detail=f"Matching failed: {error}") from error
    return [_match_out(r) for r in results]
