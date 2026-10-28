"""Usage and cost tracking: one LLMUsage row per LLM request."""

from sqlmodel import Session

from app.db.models import LLMUsage
from app.llm.provider import Completion


def record_completion(
    session: Session,
    *,
    task: str,
    completion: Completion,
    cost: float = 0.0,
) -> LLMUsage:
    """Persist token usage and cost for a completed LLM request."""
    usage = LLMUsage(
        task=task,
        model=completion.model,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        cost=cost,
    )
    session.add(usage)
    session.commit()
    session.refresh(usage)
    return usage
