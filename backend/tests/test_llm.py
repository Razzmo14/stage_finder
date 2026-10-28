"""Contract tests for llm-003 (ADR 0002).

The OpenRouter endpoint is always mocked (httpx.MockTransport for the
catalog, a fake provider for completions). No test reaches the network.
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core import config, secrets
from app.db.models import LLMUsage
from app.llm.catalog import ModelCatalog
from app.llm.provider import Completion, CompletionRequest, LLMError
from app.llm.structured import extract_json, json_schema_for, structured_completion
from app.llm.usage import record_completion
from app.main import create_app

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

CATALOG_FIXTURE = {
    "data": [
        {
            "id": "vendor/capable",
            "name": "Capable",
            "context_length": 8192,
            "supported_parameters": ["tools", "response_format", "structured_outputs"],
            "pricing": {"prompt": "0.000001", "completion": "0.000002"},
        },
        {
            "id": "vendor/basic",
            "name": "Basic",
            "supported_parameters": ["tools"],
            "pricing": {"prompt": "0.000003", "completion": "0.000004"},
        },
    ]
}


class FakeProvider:
    name = "fake"

    def __init__(self, replies: list) -> None:
        self.replies = list(replies)
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.calls.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Completion(content=reply, model=request.model, prompt_tokens=10, completion_tokens=5)


def mock_catalog(counter: list | None = None) -> ModelCatalog:
    def handler(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter.append(request)
        return httpx.Response(200, json=CATALOG_FIXTURE)

    return ModelCatalog(transport=httpx.MockTransport(handler))


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.MemoryBackend())
    application = create_app(session_token=TOKEN)
    application.state.catalog = mock_catalog()
    application.state.llm_provider = lambda: FakeProvider(["OK"])
    yield application
    config.get_settings.cache_clear()
    secrets.use_backend(secrets.KeyringBackend())


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


# --- API key: keychain only, masked display -------------------------------


def test_api_key_saved_to_keychain_and_masked(app, client) -> None:
    raw_key = "sk-or-v1-abcdef1234567890"
    response = client.put("/api/v1/settings/llm/key", json={"api_key": raw_key}, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["api_key_masked"].startswith("sk-o")
    assert raw_key not in response.text

    settings = client.get("/api/v1/settings/llm", headers=HEADERS).json()
    assert settings["api_key_masked"] == body["api_key_masked"]
    assert settings["provider"] == "openrouter"
    assert settings["data_collection"] == "deny"

    # The raw key lives only in the (memory) keychain backend
    assert secrets.get_secret("openrouter_api_key") == raw_key


def test_api_key_never_in_database(app, client, tmp_path) -> None:
    raw_key = "sk-or-v1-zzzzzzzzzz999999"
    client.put("/api/v1/settings/llm/key", json={"api_key": raw_key}, headers=HEADERS)
    db_bytes = (tmp_path / "stage-finder.db").read_bytes()
    assert raw_key.encode() not in db_bytes


def test_api_key_delete(client) -> None:
    client.put("/api/v1/settings/llm/key", json={"api_key": "sk-or-v1-todelete"}, headers=HEADERS)
    assert client.delete("/api/v1/settings/llm/key", headers=HEADERS).status_code == 204
    assert client.get("/api/v1/settings/llm", headers=HEADERS).json()["api_key_masked"] is None


# --- Model catalog: live fetch, cache, capabilities ------------------------


def test_model_catalog_lists_models_with_capabilities(client) -> None:
    models = {m["id"]: m for m in client.get("/api/v1/models", headers=HEADERS).json()}
    assert models["vendor/capable"]["supports_structured_output"] is True
    assert models["vendor/basic"]["supports_structured_output"] is False
    assert models["vendor/capable"]["context_length"] == 8192


def test_model_catalog_is_cached(client, app) -> None:
    counter: list = []
    app.state.catalog = mock_catalog(counter)
    client.get("/api/v1/models", headers=HEADERS)
    client.get("/api/v1/models", headers=HEADERS)
    assert len(counter) == 1  # second call served from cache
    client.get("/api/v1/models?refresh=true", headers=HEADERS)
    assert len(counter) == 2


def test_unknown_model_returns_404(client) -> None:
    response = client.get("/api/v1/models/nope/missing", headers=HEADERS)
    assert response.status_code == 404


# --- Capability-aware structured output -------------------------------------


class Sample(BaseModel):
    score: int
    rationale: str


VALID = '{"score": 42, "rationale": "solid overlap"}'


def test_structured_native_path_uses_response_format() -> None:
    provider = FakeProvider([VALID])
    result, completion = structured_completion(
        provider,
        model="vendor/capable",
        system="You rate offers.",
        user="Offer text",
        schema_model=Sample,
        supports_structured=True,
    )
    assert result.score == 42
    assert provider.calls[0].response_format == json_schema_for(Sample)
    assert completion.model == "vendor/capable"


def test_structured_fallback_retries_with_validation_error() -> None:
    provider = FakeProvider(['```json\n{"score": 42}\n```', VALID])
    result, _ = structured_completion(
        provider,
        model="vendor/basic",
        system="You rate offers.",
        user="Offer text",
        schema_model=Sample,
        supports_structured=False,
    )
    assert result.rationale == "solid overlap"
    assert len(provider.calls) == 2
    # The validation error is fed back to the model
    retry_messages = provider.calls[1].messages
    assert any(
        "rationale" in m.content.lower() and "invalid" in m.content.lower() for m in retry_messages
    )


def test_structured_fallback_survives_invalid_json_then_succeeds() -> None:
    provider = FakeProvider(["Sure! Here is my answer as plain prose.", VALID])
    result, _ = structured_completion(
        provider,
        model="vendor/basic",
        system="You rate offers.",
        user="Offer text",
        schema_model=Sample,
        supports_structured=False,
    )
    assert result.score == 42


def test_structured_fallback_gives_up_after_max_attempts() -> None:
    provider = FakeProvider(["nope"] * 3)
    with pytest.raises(ValueError, match="failed to produce valid output"):
        structured_completion(
            provider,
            model="vendor/basic",
            system="You rate offers.",
            user="Offer text",
            schema_model=Sample,
            supports_structured=False,
        )
    assert len(provider.calls) == 3


def test_extract_json_strips_code_fences() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('  {"a": 1} ') == {"a": 1}


# --- Test-call endpoint and usage recording ----------------------------------


def test_llm_test_call_records_usage_and_cost(app, client) -> None:
    provider = FakeProvider(["OK"])
    app.state.llm_provider = lambda: provider
    response = client.post(
        "/api/v1/settings/llm/test", json={"model": "vendor/capable"}, headers=HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "OK"
    assert body["prompt_tokens"] == 10
    # catalog pricing: 10 * 1e-6 + 5 * 2e-6
    assert body["cost"] == pytest.approx(2e-5)

    with Session(app.state.db_engine) as session:
        rows = session.exec(select(LLMUsage)).all()
        assert len(rows) == 1
        assert rows[0].task == "test_call"
        assert rows[0].model == "vendor/capable"
        assert rows[0].cost == pytest.approx(2e-5)


def test_llm_test_call_provider_error_returns_502(app, client) -> None:
    app.state.llm_provider = lambda: FakeProvider([LLMError("no key configured")])
    response = client.post(
        "/api/v1/settings/llm/test", json={"model": "vendor/capable"}, headers=HEADERS
    )
    assert response.status_code == 502


def test_record_completion_writes_llmusage_row(engine) -> None:
    with Session(engine) as session:
        usage = record_completion(
            session,
            task="letter_generation",
            completion=Completion(content="hi", model="m", prompt_tokens=3, completion_tokens=7),
            cost=0.5,
        )
        row = session.get(LLMUsage, usage.id)
        assert row is not None
        assert row.task == "letter_generation"
        assert row.prompt_tokens == 3
        assert row.completion_tokens == 7
        assert row.cost == 0.5
