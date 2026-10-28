"""Tests for profile-004: manual entry, CV parsing, LLM extraction."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import config, secrets
from app.db.models import Document, LLMUsage, Profile
from app.llm.provider import Completion, CompletionRequest
from app.main import create_app
from tests.fixtures import make_docx, make_pdf

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

PROFILE_PAYLOAD = {
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": "+33 6 00 00 00 00",
    "location": "Paris, France",
    "headline": "Software engineering student",
    "summary": "Passionate about Python and automation.",
    "skills": ["python", "react", "sql"],
    "languages": ["fr", "en"],
    "base_letter": "Dear hiring manager,",
    "letter_tone": "professional",
    "letter_language": "fr",
    "never_say_rules": ["never mention salary"],
    "experiences": [
        {
            "company": "Acme",
            "position": "Python intern",
            "start_date": "2025-06",
            "end_date": "2025-12",
            "description": "Built internal tooling.",
            "skills": ["python"],
        }
    ],
    "education": [
        {
            "school": "ENSIMAG",
            "degree": "Master",
            "field": "CS",
            "start_date": "2023",
            "end_date": "2026",
        }
    ],
    "projects": [
        {"name": "Stage Finder", "description": "This app", "url": "", "skills": ["tauri"]}
    ],
}

EXTRACTED_JSON = {
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": "+33 6 00 00 00 00",
    "location": "Paris",
    "headline": "Python developer",
    "summary": "Student in computer science.",
    "skills": ["python", "sql"],
    "languages": ["english", "french"],
    "experiences": [
        {
            "company": "Acme",
            "position": "Intern",
            "start_date": "2025-06",
            "end_date": "2025-12",
            "description": "Automation tooling",
            "skills": ["python"],
        }
    ],
    "education": [
        {
            "school": "ENSIMAG",
            "degree": "Master",
            "field": "CS",
            "start_date": "2023",
            "end_date": "2026",
        }
    ],
    "projects": [],
}


class FakeProvider:
    name = "fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.calls.append(request)
        return Completion(
            content=self.reply, model=request.model, prompt_tokens=50, completion_tokens=20
        )


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    application = create_app(session_token=TOKEN)
    application.state.fake_provider = FakeProvider(json.dumps(EXTRACTED_JSON))
    application.state.llm_provider = lambda: application.state.fake_provider
    yield application
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.KeyringBackend())


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def test_profile_requires_auth(app) -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/profile").status_code == 401


def test_manual_profile_create_read_update(client) -> None:
    assert client.get("/api/v1/profile", headers=HEADERS).status_code == 404

    created = client.put("/api/v1/profile", json=PROFILE_PAYLOAD, headers=HEADERS)
    assert created.status_code == 200
    assert created.json()["id"] == 1

    read = client.get("/api/v1/profile", headers=HEADERS).json()
    assert read["full_name"] == "Ada Lovelace"
    assert read["skills"] == ["python", "react", "sql"]
    assert len(read["experiences"]) == 1 and read["experiences"][0]["company"] == "Acme"
    assert read["education"][0]["school"] == "ENSIMAG"
    assert read["projects"][0]["name"] == "Stage Finder"
    assert read["base_letter"] == "Dear hiring manager,"
    assert read["never_say_rules"] == ["never mention salary"]

    # Update replaces children and edits identity
    updated_payload = {**PROFILE_PAYLOAD, "headline": "Updated headline", "experiences": []}
    updated = client.put("/api/v1/profile", json=updated_payload, headers=HEADERS)
    assert updated.json()["headline"] == "Updated headline"
    read = client.get("/api/v1/profile", headers=HEADERS).json()
    assert read["experiences"] == []
    assert read["education"][0]["school"] == "ENSIMAG"


def test_parse_pdf_text(tmp_path) -> None:
    from app.services.parsing.extract import extract_text

    path = tmp_path / "cv.pdf"
    path.write_bytes(make_pdf("Ada Lovelace - Python developer"))
    text = extract_text(path)
    assert "Ada Lovelace" in text
    assert "Python developer" in text


def test_parse_docx_text(tmp_path) -> None:
    from app.services.parsing.extract import extract_text

    path = tmp_path / "cv.docx"
    path.write_bytes(make_docx(["Ada Lovelace", "Skills: Python, SQL"]))
    text = extract_text(path)
    assert "Ada Lovelace" in text
    assert "Python, SQL" in text


def test_parse_unsupported_type(tmp_path) -> None:
    from app.services.parsing.extract import ParsingError, extract_text

    path = tmp_path / "cv.txt"
    path.write_text("plain text")
    with pytest.raises(ParsingError, match="Unsupported file type"):
        extract_text(path)


def test_cv_import_docx_with_mocked_llm(client, app) -> None:
    docx_bytes = make_docx(["Ada Lovelace", "Python developer at Acme"])
    files = {
        "file": (
            "cv.docx",
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    response = client.post("/api/v1/profile/cv", files=files, headers=HEADERS)
    assert response.status_code == 200
    extracted = response.json()
    assert extracted["full_name"] == "Ada Lovelace"
    assert extracted["skills"] == ["python", "sql"]
    assert extracted["experiences"][0]["company"] == "Acme"

    # The CV text was passed to the LLM
    provider = app.state.fake_provider
    assert "Ada Lovelace" in provider.calls[0].messages[-1].content

    # Usage recorded with the profile_extraction task; Document stored
    with Session(app.state.db_engine) as session:
        usage = session.exec(select(LLMUsage)).all()
        assert len(usage) == 1
        assert usage[0].task == "profile_extraction"
        documents = session.exec(select(Document)).all()
        assert len(documents) == 1
        assert documents[0].kind == "cv"
        assert "Ada Lovelace" in documents[0].extracted_text

    # The draft is NOT saved as the profile until the user confirms
    with Session(app.state.db_engine) as session:
        assert session.exec(select(Profile)).all() == []


def test_cv_import_pdf_with_mocked_llm(client) -> None:
    files = {"file": ("cv.pdf", make_pdf("Ada Lovelace - Python developer"), "application/pdf")}
    response = client.post("/api/v1/profile/cv", files=files, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["full_name"] == "Ada Lovelace"


def test_cv_import_unsupported_extension(client) -> None:
    files = {"file": ("cv.txt", b"plain", "text/plain")}
    response = client.post("/api/v1/profile/cv", files=files, headers=HEADERS)
    assert response.status_code == 422


def test_saved_profile_linked_document(app, client) -> None:
    files = {"file": ("cv.pdf", make_pdf("Ada Lovelace - Python developer"), "application/pdf")}
    client.post("/api/v1/profile/cv", files=files, headers=HEADERS)
    client.put("/api/v1/profile", json=PROFILE_PAYLOAD, headers=HEADERS)
    with Session(app.state.db_engine) as session:
        profile = session.exec(select(Profile)).one()
        document = session.exec(select(Document)).one()
        assert document.profile_id == profile.id
        assert Path(Document.__name__)  # sanity: Document import works
