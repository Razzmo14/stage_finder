"""SQLModel database models.

Tables follow docs/ARCHITECTURE.md -> Data Storage. No secrets are ever
stored here: API keys and OAuth tokens live in the OS keychain only.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Profile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    headline: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    languages: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    preferences: dict = Field(default_factory=dict, sa_column=Column(JSON))
    base_letter: str = ""
    letter_tone: str = ""
    letter_language: str = ""
    never_say_rules: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Experience(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    company: str = ""
    position: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Education(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    school: str = ""
    degree: str = ""
    field: str = ""
    start_date: str = ""
    end_date: str = ""


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    name: str = ""
    description: str = ""
    url: str = ""
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int | None = Field(default=None, foreign_key="profile.id", index=True)
    kind: str = ""  # "cv" | "base_letter" | ...
    filename: str = ""
    extracted_text: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class SearchCriteria(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = ""
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    location: str = ""
    radius_km: int | None = None
    contract_types: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    remote: bool = False
    salary_min: int | None = None
    seniority: str = ""
    languages: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    sources: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    date_posted_days: int | None = None
    schedule: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Offer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_id: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    contract_type: str = ""
    salary_text: str = ""
    published_at: str = ""
    raw_payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    dedup_hash: str = Field(index=True)
    embedding: bytes | None = None
    embedding_model: str = ""
    language: str = ""
    seen: bool = False
    ignored: bool = False
    fetched_at: datetime = Field(default_factory=utcnow)

    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_offer_source_id"),)


class MatchResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    offer_id: int = Field(foreign_key="offer.id", index=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    score: int = 0  # 0-100
    rationale: str = ""
    matched_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    missing_skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    red_flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    model: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Application(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    offer_id: int = Field(foreign_key="offer.id", index=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    status: str = "draft"  # draft|pending_review|approved|sent|rejected|replied...
    recipient: str = ""
    email_subject: str = ""
    email_body: str = ""
    letter_text: str = ""
    attachments: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    claims: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    flagged_claims: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    follow_up_date: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    sent_at: datetime | None = None


class LLMUsage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task: str = ""  # profile_extraction|matching|letter_generation|claim_check
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)


class EventLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    event_type: str = Field(index=True)
    application_id: int | None = Field(default=None, foreign_key="application.id", index=True)
    detail: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ModelConfig(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task: str = Field(unique=True)  # per-task model assignment
    provider: str = ""
    model: str = ""
    options: dict = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utcnow)
