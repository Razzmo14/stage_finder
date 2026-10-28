"""Offer language detection (French/English) by stopword ratio."""

FRENCH_STOP = {
    "le", "la", "les", "des", "une", "un", "et", "ou", "dans", "pour", "avec",
    "sur", "nous", "vous", "poste", "mission", "entreprise", "stage", "offre",
    "candidature", "expérience", "profil", "compétences", "développement",
}
ENGLISH_STOP = {
    "the", "a", "an", "of", "in", "for", "with", "on", "we", "you", "job",
    "position", "role", "company", "internship", "offer", "candidate",
    "experience", "profile", "skills", "development", "and", "to", "our",
}


def detect_language(text: str) -> str:
    """Return "fr" or "en" (default en) for a job offer's text."""
    words = [w.strip(".,;:!?()").lower() for w in text.lower().split()]
    if not words:
        return "en"
    french = sum(1 for w in words if w in FRENCH_STOP)
    english = sum(1 for w in words if w in ENGLISH_STOP)
    return "fr" if french > english else "en"
