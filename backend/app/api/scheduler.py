"""Scheduler settings API, manual run, and follow-up notifications."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import DbDep
from app.db.models import Offer
from app.services import scheduler as scheduler_service
from app.services.scheduler import (
    DEFAULT_SCHEDULER_SETTINGS,
    record_follow_up_notifications,
    run_all_criteria,
)
from app.services.settings import get_setting, set_setting

router = APIRouter()


def get_sources(request: Request) -> dict:
    return request.app.state.job_sources


SourcesDep = Annotated[dict, Depends(get_sources)]


class SchedulerSettings(BaseModel):
    enabled: bool = False
    search_interval_minutes: int = 240
    follow_up_check_minutes: int = 15


class RunStats(BaseModel):
    criteria: int
    new: int
    duplicates: int
    errors: list[str]


class FollowUp(BaseModel):
    application_id: int
    follow_up_date: str
    status: str
    offer_title: str


@router.get("/settings/scheduler", response_model=SchedulerSettings)
def read_scheduler_settings(session: DbDep) -> SchedulerSettings:
    stored = get_setting(session, "scheduler")
    return SchedulerSettings(
        enabled=bool(stored.get("enabled", DEFAULT_SCHEDULER_SETTINGS["enabled"])),
        search_interval_minutes=int(stored.get("search_interval_minutes", 240)),
        follow_up_check_minutes=int(stored.get("follow_up_check_minutes", 15)),
    )


@router.put("/settings/scheduler", response_model=SchedulerSettings)
def update_scheduler_settings(
    payload: SchedulerSettings, request: Request, session: DbDep
) -> SchedulerSettings:
    set_setting(session, "scheduler", payload.model_dump())
    _sync_scheduler(request, payload.model_dump())
    return read_scheduler_settings(session)


def _sync_scheduler(request: Request, settings: dict) -> None:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return
    scheduler_service.register_jobs(
        scheduler,
        run_searches=lambda: _run_searches_with_app(request.app),
        check_follow_ups=lambda: _check_follow_ups_with_app(request.app),
        settings=settings,
    )


def _run_searches_with_app(app) -> dict:
    with Session(app.state.db_engine) as session:
        return run_all_criteria(session, app.state.job_sources)


def _check_follow_ups_with_app(app) -> list[dict]:
    with Session(app.state.db_engine) as session:
        return record_follow_up_notifications(session)


@router.post("/scheduler/run-searches", response_model=RunStats)
def manual_run(session: DbDep, sources: SourcesDep) -> RunStats:
    """Run the periodic search job now (same path the scheduler uses)."""
    stats = run_all_criteria(session, sources)
    return RunStats(**stats)


@router.get("/follow-ups", response_model=list[FollowUp])
def list_follow_ups(session: DbDep) -> list[FollowUp]:
    """Applications whose follow-up is due (drives the desktop notification)."""
    result = []
    for application in scheduler_service.due_follow_ups(session):
        offer = session.get(Offer, application.offer_id)
        result.append(
            FollowUp(
                application_id=application.id,
                follow_up_date=application.follow_up_date,
                status=application.status,
                offer_title=offer.title if offer else "",
            )
        )
    return result


@router.post("/follow-ups/notify", response_model=list[dict])
def notify_follow_ups(session: DbDep) -> list[dict]:
    """Record follow-up notifications (idempotent per day)."""
    return record_follow_up_notifications(session)
