"""Applications API: review actions, inline edits, status transitions.

HARD RULE (ADR 0003): no endpoint in this module ever sends an email and
no endpoint may set a sent status. Sending exists only behind the mailer
feature with its per-application confirmation.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import DbDep
from app.db.models import Application, EventLog, Offer

router = APIRouter()

# Statuses this module may set; "sent"/"draft_sent" intentionally absent.
REVIEW_STATUSES = {"pending_review", "draft", "approved", "rejected"}


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
    offer: dict | None = None
    events: list[dict] = []


class ApplicationEdit(BaseModel):
    letter_text: str | None = None
    email_subject: str | None = None
    email_body: str | None = None
    follow_up_date: str | None = None
    attachments: list[str] | None = None


class StatusIn(BaseModel):
    pass


def _offer_out(offer: Offer) -> dict:
    return {
        "id": offer.id,
        "title": offer.title,
        "company": offer.company,
        "location": offer.location,
        "description": offer.description,
        "url": offer.url,
        "contract_type": offer.contract_type,
    }


def _events_out(session: Session, application_id: int) -> list[dict]:
    rows = session.exec(
        select(EventLog)
        .where(EventLog.application_id == application_id)
        .order_by(EventLog.id)  # type: ignore[union-attr]
    ).all()
    return [
        {"event_type": r.event_type, "detail": r.detail, "created_at": str(r.created_at)}
        for r in rows
    ]


def application_out(session: Session, row: Application) -> ApplicationOut:
    offer = session.get(Offer, row.offer_id)
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
        offer=_offer_out(offer) if offer else None,
        events=_events_out(session, row.id),
    )


def _get_application(session: Session, application_id: int) -> Application:
    row = session.get(Application, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return row


def _log(session: Session, application_id: int, event_type: str, detail: str = "") -> None:
    session.add(EventLog(event_type=event_type, application_id=application_id, detail=detail))
    session.commit()


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(
    session: DbDep, status: str | None = None, limit: int = 200
) -> list[ApplicationOut]:
    statement = select(Application).order_by(Application.id)  # type: ignore[union-attr]
    if status:
        statement = statement.where(Application.status == status)
    rows = session.exec(statement.limit(limit)).all()
    return [application_out(session, r) for r in rows]


@router.get("/applications/{application_id}", response_model=ApplicationOut)
def read_application(application_id: int, session: DbDep) -> ApplicationOut:
    return application_out(session, _get_application(session, application_id))


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
def edit_application(
    application_id: int, payload: ApplicationEdit, session: DbDep
) -> ApplicationOut:
    """Inline edits from the review screen. Status is never changed here."""
    row = _get_application(session, application_id)
    changed = []
    for field_name in (
        "letter_text",
        "email_subject",
        "email_body",
        "follow_up_date",
        "attachments",
    ):
        value = getattr(payload, field_name)
        if value is not None:
            setattr(row, field_name, value)
            changed.append(field_name)
    row.updated_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    session.refresh(row)
    _log(session, row.id, "edited", ", ".join(changed))
    return application_out(session, row)


def _set_status(session: Session, application_id: int, status: str, event: str) -> ApplicationOut:
    if status not in REVIEW_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unsupported status: {status}")
    row = _get_application(session, application_id)
    row.status = status
    row.updated_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    session.refresh(row)
    _log(session, row.id, event, status)
    return application_out(session, row)


@router.post("/applications/{application_id}/approve", response_model=ApplicationOut)
def approve(application_id: int, session: DbDep) -> ApplicationOut:
    """Mark the letter as approved by the user.

    This is an intent only: nothing is sent. The mailer feature performs
    the actual draft creation / send behind its own confirmation dialog.
    """
    return _set_status(session, application_id, "approved", "approved")


@router.post("/applications/{application_id}/reject", response_model=ApplicationOut)
def reject(application_id: int, session: DbDep) -> ApplicationOut:
    return _set_status(session, application_id, "rejected", "rejected")


@router.post("/applications/{application_id}/save-for-later", response_model=ApplicationOut)
def save_for_later(application_id: int, session: DbDep) -> ApplicationOut:
    return _set_status(session, application_id, "draft", "saved_for_later")
