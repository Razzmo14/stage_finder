"""Letter generation API: create an application draft for an offer,
and streamed regeneration for the review screen."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import DbDep
from app.db.models import Application, EventLog, Experience, Offer, Profile
from app.llm.provider import CompletionRequest, LLMProvider, messages
from app.llm.registry import provider_supports_structured
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


ProviderDep = Annotated[LLMProvider, Depends(lambda request: request.app.state.llm_provider())]


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
        record_completion(session, task="letter_generation", completion=completion, cost=cost)

    try:
        letter, completion = generate_letter(
            provider,
            model=model,
            supports_structured=provider_supports_structured(provider, catalog, model),
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
    session.add(
        EventLog(
            event_type="letter_generated",
            application_id=application.id,
            detail="regenerated" if payload.regenerate else "generated",
        )
    )
    session.commit()
    return application_out(application)


class RegenerateIn(BaseModel):
    application_id: int
    instructions: str = ""
    model: str | None = None


REGENERATE_SYSTEM = (
    "You adapt a cover letter a second time, following the user's editing "
    "instructions. Keep the base letter's facts: never invent skills, "
    "experiences, degrees or facts that are not in the original letter or "
    "the profile context it was written from. Reply with the full revised "
    "letter text only, no commentary."
)


@router.post("/letters/regenerate")
def regenerate(payload: RegenerateIn, request: Request, session: DbDep) -> StreamingResponse:
    """Stream a regenerated letter into the review editor (plain text)."""
    application = session.get(Application, payload.application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    provider = request.app.state.llm_provider()
    model = payload.model or request.app.state.get_task_model("letter_generation")

    instructions = payload.instructions.strip() or "Improve the letter."
    user_prompt = (
        f"Current letter:\n{application.letter_text}\n\n"
        f"Apply these instructions from the user:\n{instructions}\n\n"
        "Return the full revised letter."
    )
    request_obj = CompletionRequest(
        model=model,
        messages=messages(("system", REGENERATE_SYSTEM), ("user", user_prompt)),
        temperature=0.4,
    )

    application_id = application.id

    def generate_stream():
        chunks: list[str] = []
        try:
            for chunk in provider.stream(request_obj):
                chunks.append(chunk)
                yield chunk
        except Exception as error:  # noqa: BLE001
            yield f"\n[generation error: {error}]"
            return
        full = "".join(chunks)
        row = session.get(Application, application_id)
        if row is not None and full:
            row.letter_text = full
            session.add(row)
            session.commit()
        session.add(
            EventLog(
                event_type="letter_regenerated",
                application_id=application_id,
                detail=instructions,
            )
        )
        session.commit()

    return StreamingResponse(generate_stream(), media_type="text/plain")

