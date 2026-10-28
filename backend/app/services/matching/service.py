"""Matching pipeline: embedding similarity (stage 1) + LLM re-ranking (stage 2)."""

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.models import MatchResult, Offer, Profile
from app.llm.provider import LLMProvider
from app.llm.structured import structured_completion
from app.services.matching.embeddings import (
    EmbeddingProvider,
    HashingEmbedder,
    cosine,
    decode_vector,
    encode_vector,
)


class MatchJudgement(BaseModel):
    """Structured stage-2 result returned by the LLM."""

    score: int = Field(ge=0, le=100)
    rationale: str = ""
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


STAGE2_SYSTEM = (
    "You are a rigorous career advisor. Score how well the candidate profile "
    "matches the job offer, from 0 to 100. Only use facts present in the "
    "profile and the offer. Never invent skills, experiences or requirements. "
    "Report matched skills, missing skills and any red flags (unpaid, "
    "mismatched seniority, relocation issues, ...)."
)


def profile_text(profile: Profile, experiences: list | None = None) -> str:
    """Text representation of the profile used for embedding and prompts."""
    parts = [
        profile.headline,
        profile.summary,
        "Skills: " + ", ".join(profile.skills),
        "Languages: " + ", ".join(profile.languages),
    ]
    for experience in experiences or []:
        parts.append(
            f"{experience.position} at {experience.company}: {experience.description} "
            f"[{', '.join(experience.skills)}]"
        )
    return "\n".join(p for p in parts if p)


def offer_text(offer: Offer) -> str:
    parts = [offer.title, offer.company, offer.location, offer.description]
    return "\n".join(p for p in parts if p)


def get_or_compute_embedding(
    session: Session, offer: Offer, embedder: EmbeddingProvider
) -> list[float]:
    """Return the stored embedding for an offer, computing it if needed."""
    if offer.embedding is not None and offer.embedding_model == embedder.name:
        return decode_vector(offer.embedding)
    vectors = embedder.embed([offer_text(offer)])
    vector = vectors[0]
    offer.embedding = encode_vector(vector)
    offer.embedding_model = embedder.name
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return vector


def stage1_similarity(
    session: Session,
    profile: Profile,
    offers: list[Offer],
    embedder: EmbeddingProvider,
) -> list[tuple[Offer, float]]:
    """Embed every offer once, then rank by cosine similarity to the profile."""
    if not offers:
        return []
    profile_vector = embedder.embed([profile_text(profile)])[0]
    scored: list[tuple[Offer, float]] = []
    for offer in offers:
        vector = get_or_compute_embedding(session, offer, embedder)
        scored.append((offer, cosine(profile_vector, vector)))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def stage2_rerank(
    provider: LLMProvider,
    *,
    model: str,
    supports_structured: bool,
    profile: Profile,
    offer: Offer,
    experiences: list | None = None,
    similarity_hint: float | None = None,
) -> tuple[MatchJudgement, object]:
    """LLM re-ranking of a single offer. Returns (judgement, completion)."""
    import json

    profile_payload = {
        "headline": profile.headline,
        "summary": profile.summary,
        "skills": profile.skills,
        "languages": profile.languages,
        "experiences": [
            {
                "position": e.position,
                "company": e.company,
                "description": e.description,
                "skills": e.skills,
            }
            for e in experiences or []
        ],
    }
    if similarity_hint is not None:
        profile_payload["stage1_embedding_similarity"] = round(similarity_hint, 4)
    offer_payload = {
        "title": offer.title,
        "company": offer.company,
        "location": offer.location,
        "description": offer.description[:4000],
        "contract_type": offer.contract_type,
    }
    return structured_completion(
        provider,
        model=model,
        system=STAGE2_SYSTEM,
        user=(
            f"Candidate profile:\n{json.dumps(profile_payload, ensure_ascii=False)}\n\n"
            f"Job offer:\n{json.dumps(offer_payload, ensure_ascii=False)}"
        ),
        schema_model=MatchJudgement,
        supports_structured=supports_structured,
        temperature=0,
    )


def run_matching(
    session: Session,
    provider: LLMProvider,
    *,
    model: str,
    supports_structured: bool,
    profile: Profile,
    offers: list[Offer],
    top_n: int = 10,
    embedder: EmbeddingProvider | None = None,
    record_usage=None,
) -> list[MatchResult]:
    """Full pipeline: stage 1 ranking then stage 2 LLM re-ranking of the top N.

    `record_usage(completion)` is called for every LLM call when provided.
    """
    embedder = embedder or HashingEmbedder()
    ranked = stage1_similarity(session, profile, offers, embedder)

    from app.db.models import Experience

    experiences = session.exec(
        select(Experience).where(Experience.profile_id == profile.id)
    ).all()

    results: list[MatchResult] = []
    for offer, similarity in ranked[:top_n]:
        judgement, completion = stage2_rerank(
            provider,
            model=model,
            supports_structured=supports_structured,
            profile=profile,
            offer=offer,
            experiences=experiences,
            similarity_hint=similarity,
        )
        if record_usage is not None:
            record_usage(completion)
        match = MatchResult(
            offer_id=offer.id,
            profile_id=profile.id,
            score=judgement.score,
            rationale=judgement.rationale,
            matched_skills=judgement.matched_skills,
            missing_skills=judgement.missing_skills,
            red_flags=judgement.red_flags,
            model=completion.model,
        )
        session.add(match)
        session.commit()
        session.refresh(match)
        results.append(match)
    return results
