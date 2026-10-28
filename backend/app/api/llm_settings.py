"""LLM settings and model catalog endpoints.

The API key lives in the OS keychain; only a masked form is ever returned.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from app.api.schemas import (
    LLMKeyIn,
    LLMSettingsOut,
    LLMTestIn,
    LLMTestOut,
    ModelOut,
)
from app.core import secrets
from app.db.engine import get_db
from app.llm.catalog import ModelCatalog
from app.llm.openrouter import API_KEY_SECRET
from app.llm.provider import CompletionRequest, LLMError, LLMProvider, messages
from app.llm.usage import record_completion
from app.services.settings import get_setting, set_setting

router = APIRouter()


def get_catalog(request: Request) -> ModelCatalog:
    return request.app.state.catalog


def get_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider()


CatalogDep = Annotated[ModelCatalog, Depends(get_catalog)]
ProviderDep = Annotated[LLMProvider, Depends(get_provider)]
DbDep = Annotated[Session, Depends(get_db)]


def _model_out(info) -> ModelOut:  # noqa: ANN001 (ModelInfo)
    return ModelOut(
        id=info.id,
        name=info.name,
        context_length=info.context_length,
        supported_parameters=info.supported_parameters,
        supports_structured_output=info.supports_structured_output(),
        pricing=info.pricing,
    )


@router.get("/settings/llm", response_model=LLMSettingsOut)
def read_llm_settings() -> LLMSettingsOut:
    return LLMSettingsOut(
        provider="openrouter",
        api_key_masked=secrets.mask(secrets.get_secret(API_KEY_SECRET)),
        data_collection="deny",
    )


@router.put("/settings/llm/key", response_model=LLMSettingsOut)
def save_llm_key(payload: LLMKeyIn) -> LLMSettingsOut:
    secrets.set_secret(API_KEY_SECRET, payload.api_key)
    return read_llm_settings()


@router.delete("/settings/llm/key", status_code=204)
def delete_llm_key() -> None:
    secrets.delete_secret(API_KEY_SECRET)


class LLMConfigIn(BaseModel):
    active_provider: str = "openrouter"
    monthly_budget_usd: float | None = None
    ollama_base_url: str = "http://localhost:11434"


@router.get("/settings/llm-config", response_model=LLMConfigIn)
def read_llm_config(session: DbDep) -> LLMConfigIn:
    stored = get_setting(session, "llm")
    return LLMConfigIn(
        active_provider=stored.get("active_provider", "openrouter"),
        monthly_budget_usd=stored.get("monthly_budget_usd"),
        ollama_base_url=stored.get("ollama_base_url", "http://localhost:11434"),
    )


@router.put("/settings/llm-config", response_model=LLMConfigIn)
def update_llm_config(payload: LLMConfigIn, request: Request, session: DbDep) -> LLMConfigIn:
    if payload.active_provider not in ("openrouter", "anthropic", "openai", "ollama"):
        raise HTTPException(status_code=422, detail=f"Unknown provider: {payload.active_provider}")
    set_setting(session, "llm", payload.model_dump())
    request.app.state.provider_cache = {}  # rebuild with the new provider
    return read_llm_config(session)


@router.get("/budget")
def budget_status(session: DbDep) -> dict:
    from app.llm.budget import monthly_budget, spent_this_month

    return {
        "spent_usd": spent_this_month(session),
        "monthly_budget_usd": monthly_budget(session),
    }


@router.get("/models", response_model=list[ModelOut])
def list_models(catalog: CatalogDep, refresh: bool = False) -> list[ModelOut]:
    try:
        return [_model_out(m) for m in catalog.all_models(refresh=refresh)]
    except Exception as error:  # noqa: BLE001 - catalog fetch is external
        raise HTTPException(
            status_code=502, detail=f"Model catalog unavailable: {error}"
        ) from error


@router.get("/models/{model_id}", response_model=ModelOut)
def read_model(model_id: str, catalog: CatalogDep) -> ModelOut:
    info = catalog.get(model_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_id}")
    return _model_out(info)


@router.post("/settings/llm/test", response_model=LLMTestOut)
def test_llm(
    payload: LLMTestIn, catalog: CatalogDep, provider: ProviderDep, session: DbDep
) -> LLMTestOut:
    try:
        completion = provider.complete(
            CompletionRequest(
                model=payload.model,
                messages=messages(("user", payload.prompt)),
                temperature=0,
            )
        )
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    cost = 0.0
    info = catalog.get(completion.model)
    if info is not None:
        cost = info.estimate_cost(completion.prompt_tokens, completion.completion_tokens)
    record_completion(session, task="test_call", completion=completion, cost=cost)
    return LLMTestOut(
        reply=completion.content,
        model=completion.model,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        cost=cost,
    )
