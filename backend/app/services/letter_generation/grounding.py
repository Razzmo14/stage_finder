"""Claim grounding: every factual claim is checked against the profile.

Two implementations:
- HeuristicGroundingChecker (default): flags claims whose named entities
  (capitalized terms, e.g. a technology or company) do not appear anywhere
  in the profile corpus.
- LLMGroundingChecker: structured claim-by-claim verification via the
  claim_check task (mockable in tests).
"""

import re
from typing import Protocol

from pydantic import BaseModel, Field

from app.db.models import Experience, Profile
from app.llm.provider import LLMProvider
from app.llm.structured import structured_completion


class ClaimCheck(BaseModel):
    claims: list["ClaimVerdict"] = Field(default_factory=list)


class ClaimVerdict(BaseModel):
    claim: str
    supported: bool
    reason: str = ""


class GroundingChecker(Protocol):
    def check(
        self, claims: list[str], profile: Profile, experiences: list[Experience]
    ) -> list[ClaimVerdict]:
        ...


STOPWORDS = {"i", "the", "a", "an", "and", "with", "for", "have", "has", "of", "at", "in", "my"}


def profile_corpus(profile: Profile, experiences: list[Experience]) -> set[str]:
    """Lowercase vocabulary of everything the profile actually says."""
    parts: list[str] = [
        profile.full_name,
        profile.headline,
        profile.summary,
        *(profile.skills or []),
        *(profile.languages or []),
    ]
    for experience in experiences:
        parts.extend(
            [
                experience.company,
                experience.position,
                experience.description,
                *(experience.skills or []),
            ]
        )
    corpus: set[str] = set()
    for part in parts:
        corpus.update(re.findall(r"[a-zA-Z0-9+#.]+", part.lower()))
    return corpus


def _claim_entities(claim: str) -> set[str]:
    """Capitalized terms in a claim, ignoring sentence-initial words."""
    sentences = re.split(r"[.!?]\s*", claim)
    entities: set[str] = set()
    for sentence in sentences:
        words = re.findall(r"[A-Za-zÀ-ÿ0-9+#.]+", sentence)
        for word in words[1:]:  # skip the first word of each sentence
            if word[0].isupper() and len(word) >= 2:
                entities.add(word)
    return entities


class HeuristicGroundingChecker:
    """Flags claims naming entities absent from the profile corpus."""

    def check(
        self, claims: list[str], profile: Profile, experiences: list[Experience]
    ) -> list[ClaimVerdict]:
        corpus = profile_corpus(profile, experiences)
        verdicts: list[ClaimVerdict] = []
        for claim in claims:
            unknown = [
                entity for entity in _claim_entities(claim) if entity.lower() not in corpus
            ]
            verdicts.append(
                ClaimVerdict(
                    claim=claim,
                    supported=not unknown,
                    reason=f"Unknown in profile: {', '.join(unknown)}" if unknown else "",
                )
            )
        return verdicts


LLM_SYSTEM = (
    "You verify factual claims made about a candidate against their profile. "
    "A claim is supported only if the profile contains evidence for it. "
    "Be strict: any skill, experience, degree or fact not present in the "
    "profile makes the claim unsupported."
)


class LLMGroundingChecker:
    """Claim verification via the claim_check LLM task."""

    def __init__(self, provider: LLMProvider, model: str, supports_structured: bool) -> None:
        self.provider = provider
        self.model = model
        self.supports_structured = supports_structured

    def check(
        self, claims: list[str], profile: Profile, experiences: list[Experience]
    ) -> list[ClaimVerdict]:
        import json

        if not claims:
            return []
        corpus = sorted(profile_corpus(profile, experiences))
        result, _ = structured_completion(
            self.provider,
            model=self.model,
            system=LLM_SYSTEM,
            user=(
                f"Profile vocabulary and facts:\n{json.dumps(corpus, ensure_ascii=False)}\n\n"
                f"Claims to verify:\n{json.dumps(claims, ensure_ascii=False)}"
            ),
            schema_model=ClaimCheck,
            supports_structured=self.supports_structured,
            temperature=0,
        )
        return result.claims
