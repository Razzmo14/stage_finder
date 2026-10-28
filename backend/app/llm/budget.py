"""Monthly budget cap: blocks further generations when exceeded."""

from datetime import UTC, datetime

from sqlmodel import Session, select

from app.db.models import LLMUsage
from app.services.settings import get_setting


class BudgetExceededError(Exception):
    pass


def spent_this_month(session: Session) -> float:
    """Total LLM spend (USD) since the start of the current month."""
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = session.exec(select(LLMUsage)).all()
    return round(sum(r.cost for r in rows if r.created_at >= start), 8)


def monthly_budget(session: Session) -> float | None:
    value = get_setting(session, "llm").get("monthly_budget_usd")
    try:
        budget = float(value) if value is not None else None
    except (TypeError, ValueError):
        budget = None
    return budget


def ensure_budget(session: Session) -> float:
    """Raise BudgetExceededError when the monthly budget is exhausted.

    Returns the spend so far. A budget of None/0 disables the cap.
    """
    spent = spent_this_month(session)
    budget = monthly_budget(session)
    if budget and budget > 0 and spent >= budget:
        raise BudgetExceededError(
            f"Monthly LLM budget exceeded: spent {spent:.4f} USD of {budget:.4f} USD. "
            "Generation blocked; raise the budget in Settings."
        )
    return spent
