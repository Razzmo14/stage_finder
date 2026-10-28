"""Letter generation: adapt the base cover letter to an offer.

Structured output: adapted letter, email subject, email body, and the list
of factual claims made, which the grounding check then verifies.
"""

import json

from pydantic import BaseModel, Field

from app.db.models import Offer, Profile
from app.llm.provider import LLMProvider
from app.llm.structured import structured_completion
from app.services.langdetect import detect_language


class LetterOutput(BaseModel):
    letter: str
    email_subject: str
    email_body: str
    claims: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You adapt a base cover letter to a specific job offer. Rules: "
    "(1) never invent skills, experiences, degrees or facts that are not in "
    "the profile; (2) respect the tone, length and never-say rules; "
    "(3) write in the requested language; "
    "(4) list every factual claim you make about the candidate in `claims`, "
    "each as a short standalone sentence."
)


def build_user_prompt(
    profile: Profile, offer: Offer, experiences: list, language: str
) -> str:
    profile_payload = {
        "full_name": profile.full_name,
        "headline": profile.headline,
        "summary": profile.summary,
        "skills": profile.skills,
        "languages_spoken": profile.languages,
        "experiences": [
            {
                "position": e.position,
                "company": e.company,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "description": e.description,
                "skills": e.skills,
            }
            for e in experiences
        ],
    }
    offer_payload = {
        "title": offer.title,
        "company": offer.company,
        "location": offer.location,
        "description": offer.description[:4000],
    }
    style = {
        "tone": profile.letter_tone,
        "never_say": profile.never_say_rules,
    }
    return (
        f"Profile:\n{json.dumps(profile_payload, ensure_ascii=False)}\n\n"
        f"Base letter:\n{profile.base_letter}\n\n"
        f"Style rules:\n{json.dumps(style, ensure_ascii=False)}\n\n"
        f"Job offer:\n{json.dumps(offer_payload, ensure_ascii=False)}\n\n"
        f"Write the adapted letter, the email subject and the email body in "
        f"{'French' if language == 'fr' else 'English'}."
    )


def generate_letter(
    provider: LLMProvider,
    *,
    model: str,
    supports_structured: bool,
    profile: Profile,
    offer: Offer,
    experiences: list,
    language: str | None = None,
) -> tuple[LetterOutput, object]:
    """Generate the structured LetterOutput for one offer."""
    language = language or detect_language(f"{offer.title}\n{offer.description}")
    return structured_completion(
        provider,
        model=model,
        system=SYSTEM_PROMPT,
        user=build_user_prompt(profile, offer, experiences, language),
        schema_model=LetterOutput,
        supports_structured=supports_structured,
        temperature=0.4,
    )
