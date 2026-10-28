"""LLM-based structured profile extraction from CV text."""

from pydantic import BaseModel, Field

from app.llm.provider import LLMProvider
from app.llm.structured import structured_completion


class ExtractedExperience(BaseModel):
    company: str = ""
    position: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)


class ExtractedEducation(BaseModel):
    school: str = ""
    degree: str = ""
    field: str = ""
    start_date: str = ""
    end_date: str = ""


class ExtractedProject(BaseModel):
    name: str = ""
    description: str = ""
    url: str = ""
    skills: list[str] = Field(default_factory=list)


class ExtractedProfile(BaseModel):
    """Structured profile returned by the LLM; the user corrects everything."""

    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    headline: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    experiences: list[ExtractedExperience] = Field(default_factory=list)
    education: list[ExtractedEducation] = Field(default_factory=list)
    projects: list[ExtractedProject] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You extract a structured professional profile from a CV. "
    "Only include facts present in the CV text. Never invent skills, "
    "experiences, degrees or dates. Dates use YYYY-MM or YYYY format when known."
)


def extract_profile(
    provider: LLMProvider,
    *,
    model: str,
    supports_structured: bool,
    cv_text: str,
    temperature: float | None = 0,
) -> tuple[ExtractedProfile, object]:
    """Extract an ExtractedProfile from raw CV text.

    Returns (profile, completion) so the caller can record usage.
    """
    return structured_completion(
        provider,
        model=model,
        system=SYSTEM_PROMPT,
        user=f"CV text:\n\n{cv_text}",
        schema_model=ExtractedProfile,
        supports_structured=supports_structured,
        temperature=temperature,
    )
