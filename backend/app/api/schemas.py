"""Request/response schemas for the API layer."""

from pydantic import BaseModel, Field


class LLMKeyIn(BaseModel):
    api_key: str = Field(min_length=8)


class LLMSettingsOut(BaseModel):
    provider: str
    api_key_masked: str | None
    data_collection: str


class ModelOut(BaseModel):
    id: str
    name: str
    context_length: int | None
    supported_parameters: list[str]
    supports_structured_output: bool
    pricing: dict


class LLMTestIn(BaseModel):
    model: str
    prompt: str = "Reply with the single word: OK"


class LLMTestOut(BaseModel):
    reply: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost: float
