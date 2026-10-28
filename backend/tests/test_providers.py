"""Tests for providers-014: Anthropic/OpenAI/Ollama providers and budget cap."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import config, secrets
from app.db.models import Offer, Profile
from app.llm.anthropic import AnthropicProvider
from app.llm.budget import BudgetExceededError, ensure_budget, spent_this_month
from app.llm.ollama import OllamaProvider
from app.llm.openai_direct import OpenAIDirectProvider
from app.llm.provider import CompletionRequest, messages
from app.llm.registry import (
    build_provider,
    get_active_provider,
    provider_supports_structured,
)
from app.main import create_app
from app.services.settings import set_setting

TOKEN = "test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def memory_secrets():
    secrets.use_backend(secrets.MemoryBackend())
    secrets.set_secret("anthropic_api_key", "anthropic-key")
    secrets.set_secret("openai_api_key", "openai-key")
    yield
    secrets.use_backend(secrets.KeyringBackend())


# --- Provider contract tests (mocked endpoints) -------------------------------


def test_anthropic_contract() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Bonjour"}],
                "model": "claude-3-5-sonnet",
                "usage": {"input_tokens": 11, "output_tokens": 7},
            },
        )

    provider = AnthropicProvider(transport=httpx.MockTransport(handler))
    completion = provider.complete(
        CompletionRequest(
            model="claude-3-5-sonnet",
            messages=messages(("system", "Be strict."), ("user", "Salut")),
            temperature=0,
        )
    )
    assert completion.content == "Bonjour"
    assert completion.prompt_tokens == 11
    assert completion.completion_tokens == 7
    request = calls[0]
    assert request.headers["x-api-key"] == "anthropic-key"
    body = json.loads(request.content)
    assert body["system"] == "Be strict."
    assert body["messages"] == [{"role": "user", "content": "Salut"}]


def test_anthropic_missing_key() -> None:
    secrets.delete_secret("anthropic_api_key")
    provider = AnthropicProvider(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    )
    from app.llm.provider import LLMError

    with pytest.raises(LLMError, match="API key is not configured"):
        provider.complete(CompletionRequest(model="m", messages=messages(("user", "x"))))


def test_openai_direct_contract_passes_response_format() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"score": 10}'}}],
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            },
        )

    provider = OpenAIDirectProvider(transport=httpx.MockTransport(handler))
    completion = provider.complete(
        CompletionRequest(
            model="gpt-4o-mini",
            messages=messages(("user", "Rate this")),
            response_format={"type": "json_object"},
        )
    )
    assert completion.content == '{"score": 10}'
    body = json.loads(calls[0].content)
    assert body["response_format"] == {"type": "json_object"}
    assert calls[0].headers["Authorization"] == "Bearer openai-key"


def test_ollama_contract_local_no_key() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "message": {"content": "Salut"},
                "model": "llama3",
                "prompt_eval_count": 4,
                "eval_count": 2,
            },
        )

    provider = OllamaProvider(
        base_url="http://localhost:11434", transport=httpx.MockTransport(handler)
    )
    completion = provider.complete(
        CompletionRequest(model="llama3", messages=messages(("user", "Salut")))
    )
    assert completion.content == "Salut"
    assert completion.prompt_tokens == 4
    assert calls[0].url.host == "localhost"


def test_ollama_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        lines = [
            json.dumps({"message": {"content": "Hel"}}),
            json.dumps({"message": {"content": "lo"}}),
        ]
        return httpx.Response(200, text="\n".join(lines))

    provider = OllamaProvider(transport=httpx.MockTransport(handler))
    request = CompletionRequest(model="llama3", messages=messages(("user", "x")))
    chunks = list(provider.stream(request))
    assert chunks == ["Hel", "lo"]


# --- Capability flags ---------------------------------------------------------


def test_capability_flags() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    anthropic = AnthropicProvider(transport=transport)
    openai = OpenAIDirectProvider(transport=transport)
    ollama = OllamaProvider(transport=transport)

    class FakeCatalog:
        def supports_structured_output(self, model: str) -> bool:
            return True

    assert provider_supports_structured(anthropic, FakeCatalog(), "m") is False
    assert provider_supports_structured(openai, FakeCatalog(), "m") is True
    assert provider_supports_structured(ollama, FakeCatalog(), "m") is False


# --- Registry -----------------------------------------------------------------


class FakeApp:
    class state:  # noqa: N801
        pass


def test_active_provider_switching() -> None:
    app = FakeApp()
    provider = get_active_provider(app.state, {"active_provider": "anthropic"}, catalog=None)
    assert provider.name == "anthropic"
    # cache reused for the same provider
    assert get_active_provider(app.state, {"active_provider": "anthropic"}) is provider
    other = get_active_provider(app.state, {"active_provider": "ollama"}, catalog=None)
    assert other.name == "ollama"
    # unknown provider falls back to openrouter
    assert get_active_provider(app.state, {"active_provider": "nope"}).name == "openrouter"


def test_build_provider_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        build_provider("nope")


# --- Budget cap ----------------------------------------------------------------


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_FINDER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    application = create_app(session_token=TOKEN)
    yield application
    config.get_settings.cache_clear()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def test_budget_cap_blocks_generations_with_clear_message(client, app) -> None:
    with Session(app.state.db_engine) as session:
        set_setting(session, "llm", {"active_provider": "openrouter", "monthly_budget_usd": 1.0})
        from app.db.models import LLMUsage

        session.add(
            LLMUsage(
                task="letter_generation",
                model="m",
                cost=1.5,
                prompt_tokens=1,
                completion_tokens=1,
            )
        )
        session.commit()
        # Seed profile + offers so the match endpoint reaches the budget check
        session.add(Profile(full_name="Ada", headline="Python", skills=["python"]))
        session.add(Offer(source="ft", source_id="1", title="T", company="C", dedup_hash="h"))
        session.commit()

    response = client.post("/api/v1/match/run", json={"top_n": 5}, headers=HEADERS)
    assert response.status_code == 422
    assert "budget" in response.json()["detail"].lower()
    assert "1.5000" in response.json()["detail"]

    with pytest.raises(BudgetExceededError, match="budget exceeded"):
        with Session(app.state.db_engine) as session:
            ensure_budget(session)


def test_budget_disabled_when_not_set(client, app) -> None:
    with Session(app.state.db_engine) as session:
        from app.db.models import LLMUsage

        session.add(
            LLMUsage(task="t", model="m", cost=50.0, prompt_tokens=1, completion_tokens=1)
        )
        session.commit()
        assert spent_this_month(session) == 50.0
        # No budget configured: ensure_budget does not raise
        assert ensure_budget(session) == 50.0


def test_llm_config_endpoints(client) -> None:
    updated = client.put(
        "/api/v1/settings/llm-config",
        json={"active_provider": "ollama", "monthly_budget_usd": 5.0,
              "ollama_base_url": "http://127.0.0.1:11434"},
        headers=HEADERS,
    ).json()
    assert updated["active_provider"] == "ollama"

    read = client.get("/api/v1/settings/llm-config", headers=HEADERS).json()
    assert read["monthly_budget_usd"] == 5.0

    bad = client.put(
        "/api/v1/settings/llm-config",
        json={"active_provider": "unknown-provider"},
        headers=HEADERS,
    )
    assert bad.status_code == 422

    budget = client.get("/api/v1/budget", headers=HEADERS).json()
    assert budget["monthly_budget_usd"] == 5.0
    assert budget["spent_usd"] == 0.0
