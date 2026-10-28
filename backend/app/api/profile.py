"""Profile API: manual entry and CV import with LLM extraction."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import DbDep
from app.db.models import Document, Education, Experience, Profile, Project
from app.services.parsing.extract import ParsingError, extract_text
from app.services.profile_extraction import ExtractedProfile, extract_profile

router = APIRouter()


class ExperienceIn(BaseModel):
    company: str = ""
    position: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)


class EducationIn(BaseModel):
    school: str = ""
    degree: str = ""
    field: str = ""
    start_date: str = ""
    end_date: str = ""


class ProjectIn(BaseModel):
    name: str = ""
    description: str = ""
    url: str = ""
    skills: list[str] = Field(default_factory=list)


class ProfileIn(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    headline: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    base_letter: str = ""
    letter_tone: str = ""
    letter_language: str = ""
    never_say_rules: list[str] = Field(default_factory=list)
    experiences: list[ExperienceIn] = Field(default_factory=list)
    education: list[EducationIn] = Field(default_factory=list)
    projects: list[ProjectIn] = Field(default_factory=list)


class ProfileOut(ProfileIn):
    id: int


def _get_or_404(session: Session) -> Profile:
    profile = session.exec(select(Profile)).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="No profile exists yet")
    return profile


def _to_out(session: Session, profile: Profile) -> ProfileOut:
    profile_id = profile.id
    experiences = session.exec(
        select(Experience).where(Experience.profile_id == profile_id)
    ).all()
    education = session.exec(select(Education).where(Education.profile_id == profile_id)).all()
    projects = session.exec(select(Project).where(Project.profile_id == profile_id)).all()
    return ProfileOut(
        id=profile_id,
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        location=profile.location,
        headline=profile.headline,
        summary=profile.summary,
        skills=profile.skills,
        languages=profile.languages,
        base_letter=profile.base_letter,
        letter_tone=profile.letter_tone,
        letter_language=profile.letter_language,
        never_say_rules=profile.never_say_rules,
        experiences=[
            ExperienceIn(
                company=e.company,
                position=e.position,
                start_date=e.start_date,
                end_date=e.end_date,
                description=e.description,
                skills=e.skills,
            )
            for e in experiences
        ],
        education=[
            EducationIn(
                school=e.school,
                degree=e.degree,
                field=e.field,
                start_date=e.start_date,
                end_date=e.end_date,
            )
            for e in education
        ],
        projects=[
            ProjectIn(name=p.name, description=p.description, url=p.url, skills=p.skills)
            for p in projects
        ],
    )


def _replace_children(session: Session, profile: Profile, payload: ProfileIn) -> None:
    profile_id = profile.id
    for table in (Experience, Education, Project):
        for row in session.exec(select(table).where(table.profile_id == profile_id)).all():
            session.delete(row)
    session.flush()
    for e in payload.experiences:
        session.add(
            Experience(
                profile_id=profile_id,
                company=e.company,
                position=e.position,
                start_date=e.start_date,
                end_date=e.end_date,
                description=e.description,
                skills=e.skills,
            )
        )
    for e in payload.education:
        session.add(
            Education(
                profile_id=profile_id,
                school=e.school,
                degree=e.degree,
                field=e.field,
                start_date=e.start_date,
                end_date=e.end_date,
            )
        )
    for p in payload.projects:
        session.add(
            Project(
                profile_id=profile_id,
                name=p.name,
                description=p.description,
                url=p.url,
                skills=p.skills,
            )
        )


@router.get("/profile", response_model=ProfileOut)
def read_profile(session: DbDep) -> ProfileOut:
    return _to_out(session, _get_or_404(session))


@router.put("/profile", response_model=ProfileOut)
def upsert_profile(payload: ProfileIn, session: DbDep) -> ProfileOut:
    """Create or update the (single) profile, replacing the child lists."""
    profile = session.exec(select(Profile)).first()
    if profile is None:
        profile = Profile()
        session.add(profile)
    for field in (
        "full_name",
        "email",
        "phone",
        "location",
        "headline",
        "summary",
        "skills",
        "languages",
        "base_letter",
        "letter_tone",
        "letter_language",
        "never_say_rules",
    ):
        setattr(profile, field, getattr(payload, field))
    session.add(profile)
    session.commit()
    session.refresh(profile)

    # Attach CV documents imported before the profile existed.
    for document in session.exec(select(Document).where(Document.profile_id.is_(None))).all():  # type: ignore[union-attr]
        document.profile_id = profile.id
        session.add(document)

    _replace_children(session, profile, payload)
    session.commit()
    session.refresh(profile)
    return _to_out(session, profile)


@router.post("/profile/cv", response_model=ExtractedProfile)
async def import_cv(file: UploadFile, request: Request, session: DbDep) -> ExtractedProfile:
    """Import a CV file (PDF/DOCX), extract text, run LLM extraction.

    Returns a structured draft for the user to correct; nothing is saved
    to the profile until the user PUTs /profile.
    """
    suffix = f".{file.filename.rsplit('.', 1)[-1].lower()}" if "." in (file.filename or "") else ""
    raw = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(raw)
        tmp.flush()
        try:
            cv_text = extract_text(Path(tmp.name))
        except ParsingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    provider = request.app.state.llm_provider()
    catalog = request.app.state.catalog
    model = request.app.state.get_task_model("profile_extraction")
    try:
        extracted, completion = extract_profile(
            provider,
            model=model,
            supports_structured=catalog.supports_structured_output(model),
            cv_text=cv_text,
        )
    except Exception as error:  # noqa: BLE001 - provider errors surface as 502
        raise HTTPException(status_code=502, detail=f"CV extraction failed: {error}") from error

    # Record usage and keep the CV text as a document for traceability.
    from app.llm.usage import record_completion

    info = catalog.get(completion.model)
    cost = (
        info.estimate_cost(completion.prompt_tokens, completion.completion_tokens) if info else 0.0
    )
    record_completion(session, task="profile_extraction", completion=completion, cost=cost)

    profile = session.exec(select(Profile)).first()
    session.add(
        Document(
            profile_id=profile.id if profile else None,
            kind="cv",
            filename=file.filename or "cv",
            extracted_text=cv_text,
        )
    )
    session.commit()
    return extracted
