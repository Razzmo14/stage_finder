"""Scheduler: periodic offer searches and follow-up reminders.

HARD RULE (ADR 0003): the scheduler may never trigger a send. The search
job only ingests offers; the follow-up job only records notifications.
Jobs use stable IDs and replace_existing=True so restarting the app or
re-running registration never duplicates them.
"""

from datetime import UTC, datetime

from sqlmodel import Session, select

from app.db.models import Application, EventLog, SearchCriteria
from app.services.job_sources.base import JobSource, SearchParams
from app.services.offers import ingest_offers

SEARCH_JOB_ID = "stage_finder_periodic_search"
FOLLOW_UP_JOB_ID = "stage_finder_follow_up_check"

DEFAULT_SCHEDULER_SETTINGS: dict = {
    "enabled": False,
    "search_interval_minutes": 240,
    "follow_up_check_minutes": 15,
}


def run_all_criteria(session: Session, sources: dict[str, JobSource]) -> dict:
    """Run a search for every enabled criteria. Used by the periodic job."""
    stats = {"criteria": 0, "new": 0, "duplicates": 0, "errors": []}
    enabled = SearchCriteria.enabled.is_(True)  # type: ignore[union-attr]
    for criteria in session.exec(select(SearchCriteria).where(enabled)).all():
        stats["criteria"] += 1
        params = SearchParams(
            keywords=criteria.keywords,
            location=criteria.location,
            radius_km=criteria.radius_km,
            contract_types=criteria.contract_types,
            remote=criteria.remote,
            date_posted_days=criteria.date_posted_days,
        )
        for source_name in criteria.sources:
            source = sources.get(source_name)
            if source is None:
                stats["errors"].append(f"{criteria.name}: unknown source {source_name}")
                continue
            try:
                results = source.search(params)
            except Exception as error:  # noqa: BLE001 - keep other sources running
                stats["errors"].append(f"{criteria.name}/{source_name}: {error}")
                continue
            outcome = ingest_offers(session, results)
            stats["new"] += outcome.new_count
            stats["duplicates"] += outcome.duplicate_count
    return stats


def due_follow_ups(session: Session) -> list[Application]:
    """Applications whose follow-up date is due and that are not closed."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    rows = session.exec(select(Application)).all()
    due = []
    for row in rows:
        if not row.follow_up_date:
            continue
        if row.status in ("rejected",):
            continue
        if row.follow_up_date <= today:
            due.append(row)
    return due


def record_follow_up_notifications(session: Session) -> list[dict]:
    """Record a notification EventLog entry per due follow-up (idempotent per day)."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    notifications = []
    for application in due_follow_ups(session):
        already = session.exec(
            select(EventLog).where(
                EventLog.application_id == application.id,
                EventLog.event_type == "follow_up_due",
                EventLog.detail == today,
            )
        ).first()
        if already is not None:
            continue
        session.add(
            EventLog(
                event_type="follow_up_due",
                application_id=application.id,
                detail=today,
            )
        )
        notifications.append(
            {
                "application_id": application.id,
                "follow_up_date": application.follow_up_date,
            }
        )
    session.commit()
    return notifications


def make_scheduler():
    """Create and start the scheduler.

    Started immediately so that add_job(replace_existing=True) deduplicates
    pending jobs right away (idempotent registration across restarts).
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.start()
    return scheduler


def register_jobs(scheduler, *, run_searches, check_follow_ups, settings: dict) -> None:
    """(Re)register the jobs with stable IDs; idempotent across restarts."""
    if settings.get("enabled", False):
        scheduler.add_job(
            run_searches,
            "interval",
            minutes=int(settings.get("search_interval_minutes", 240)),
            id=SEARCH_JOB_ID,
            replace_existing=True,
        )
        scheduler.add_job(
            check_follow_ups,
            "interval",
            minutes=int(settings.get("follow_up_check_minutes", 15)),
            id=FOLLOW_UP_JOB_ID,
            replace_existing=True,
        )
    else:
        for job_id in (SEARCH_JOB_ID, FOLLOW_UP_JOB_ID):
            try:
                scheduler.remove_job(job_id)
            except Exception:  # noqa: BLE001 - job not registered
                pass
        for job in scheduler.get_jobs():
            if job.id in (SEARCH_JOB_ID, FOLLOW_UP_JOB_ID):
                scheduler.remove_job(job.id)
