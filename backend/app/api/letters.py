"""Letter generation API: create an application draft for an offer."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import DbDep
from app.db.models import Application, Experience, Offer, Profile
from app.llm.usage import record_completion
from app.services.letter_generation.grounding import GroundingChecker
from app.services.letter_generation.service import generate_letter

router = APIRouter()


class ApplicationOut(BaseModel):
    id: int
    offer_id: int
    profile_id: int
    status: str
    recipient: str
    email_subject: str
    email_body: str
    letter_text: str
    claims: list[dict]
    flagged_claims: list[dict]
    follow_up_date: str


class GenerateIn(BaseModel):
    offer_id: int
    regenerate: bool = False


def get_grounding_checker(request: Request) -> GroundingChecker:
    return request.app.state.grounding_checker


def application_out(row: Application) -> ApplicationOut:
    return ApplicationOut(
        id=row.id,
        offer_id=row.offer_id,
        profile_id=row.profile_id,
        status=row.status,
        recipient=row.recipient,
        email_subject=row.email_subject,
        email_body=row.email_body,
        letter_text=row.letter_text,
        claims=row.claims,
        flagged_claims=row.flagged_claims,
        follow_up_date=row.follow_up_date,
    )


@router.post("/letters/generate", response_model=ApplicationOut)
def generate(
    payload: GenerateIn,
    request: Request,
    session: DbDep,
    checker: Annotated[GroundingChecker, Depends(get_grounding_checker)],
) -> ApplicationOut:
    """Generate (or regenerate) the letter for an offer.

    Creates an Application row in status "pending_review" with the letter,
    email fields, claims and grounding verdicts. Nothing is ever sent here.
    """
    profile = session.exec(select(Profile)).first()
    if profile is None:
        raise HTTPException(status_code=422, detail="Create a profile first")
    offer = session.get(Offer, payload.offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")

    experiences = session.exec(
        select(Experience).where(Experience.profile_id == profile.id)
    ).all()

    provider = request.app.state.llm_provider()
    catalog = request.app.state.catalog
    model = request.app.state.get_task_model("letter_generation")

    def record_usage(completion) -> None:
        info = catalog.get(completion.model)
        cost = (
            info.estimate_cost(completion.prompt_tokens, completion.completion_tokens)
            if info
            else 0.0
        )
        record_completion(session, task="letter_generation", completion=completion, cost=cost)

    try:
        letter, completion = generate_letter(
            provider,
            model=model,
            supports_structured=catalog.supports_structured_output(model),
            profile=profile,
            offer=offer,
            experiences=experiences,
        )
        record_usage(completion)
        verdicts = checker.check(letter.claims, profile, experiences)
    except Exception as error:  # noqa: BLE001 - provider failures are 502
        raise HTTPException(status_code=502, detail=f"Letter generation failed: {error}") from error

    flagged = [v.model_dump() for v in verdicts if not v.supported]

    application = session.exec(
        select(Application).where(Application.offer_id == offer.id)
    ).first()
    if application is None:
        application = Application(offer_id=offer.id, profile_id=profile.id)
    application.status = "pending_review"
    application.letter_text = letter.letter
    application.email_subject = letter.email_subject
    application.email_body = letter.email_body
    application.claims = [v.model_dump() for v in verdicts]
    application.flagged_claims = flagged
    session.add(application)
    session.commit()
    session.refresh(application)
    return application_out(application)
