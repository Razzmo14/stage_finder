"""Mail API: Gmail connect (OAuth2 PKCE), settings, and the delivery gateway.

The delivery endpoint is the single path to the mailbox; it requires an
explicit confirmation and, for direct sends, the opt-in setting (ADR 0003).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import DbDep
from app.db.models import Application
from app.services.mailer.gmail import GmailClient
from app.services.mailer.mailer import DeliveryError, deliver, get_setting, sends_today, set_setting

router = APIRouter()


def get_gmail_client(request: Request) -> GmailClient:
    return request.app.state.gmail_client


GmailDep = Annotated[GmailClient, Depends(get_gmail_client)]


class MailStatus(BaseModel):
    gmail_connected: bool
    allow_direct_send: bool
    daily_send_limit: int
    sends_today: int
    sender_email: str


class MailSettingsIn(BaseModel):
    allow_direct_send: bool = False
    daily_send_limit: int = 20
    sender_email: str = ""


class ConnectStart(BaseModel):
    redirect_uri: str | None = None


class ConnectComplete(BaseModel):
    code: str
    state: str


class DeliverIn(BaseModel):
    mode: str = "draft"
    confirm: bool = False


class DeliverOut(BaseModel):
    id: int
    status: str


@router.get("/mail/status", response_model=MailStatus)
def mail_status(session: DbDep, client: GmailDep) -> MailStatus:
    settings = get_setting(session, "mail")
    return MailStatus(
        gmail_connected=client.connected(),
        allow_direct_send=bool(settings.get("allow_direct_send", False)),
        daily_send_limit=int(settings.get("daily_send_limit", 20)),
        sends_today=sends_today(session),
        sender_email=str(settings.get("sender_email", "")),
    )


@router.put("/mail/settings", response_model=MailStatus)
def update_mail_settings(payload: MailSettingsIn, session: DbDep, client: GmailDep) -> MailStatus:
    set_setting(
        session,
        "mail",
        {
            "allow_direct_send": payload.allow_direct_send,
            "daily_send_limit": payload.daily_send_limit,
            "sender_email": payload.sender_email,
        },
    )
    return mail_status(session, client)


@router.post("/mail/gmail/connect/start")
def connect_start(
    payload: ConnectStart, request: Request, session: DbDep, client: GmailDep
) -> dict:
    default_uri = "http://localhost:1420/oauth/gmail/callback"
    redirect = payload.redirect_uri or get_setting(session, "gmail_redirect_uri").get(
        "uri", default_uri
    )
    try:
        state, url = client.start_connect(redirect)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=str(error)) from error
    request.app.state.gmail_oauth_state = state
    return {"authorize_url": url, "state": state.state}


@router.post("/mail/gmail/connect/complete")
def connect_complete(payload: ConnectComplete, request: Request, client: GmailDep) -> dict:
    state = getattr(request.app.state, "gmail_oauth_state", None)
    if state is None or state.state != payload.state:
        raise HTTPException(status_code=422, detail="Unknown OAuth state; restart the connection")
    try:
        return client.complete_connect(state, payload.code)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/applications/{application_id}/deliver", response_model=DeliverOut)
def deliver_application(
    application_id: int, payload: DeliverIn, session: DbDep, client: GmailDep
) -> DeliverOut:
    """Single gateway to the mailbox (ADR 0003)."""
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        result = deliver(
            session,
            application,
            mode=payload.mode,
            confirm=payload.confirm,
            client=client,
        )
    except DeliveryError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return DeliverOut(id=result.id, status=result.status)
