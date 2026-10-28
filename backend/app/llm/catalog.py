"""Live OpenRouter model catalog (ADR 0002).

Fetched from GET https://openrouter.ai/api/v1/models (public endpoint),
cached in memory, refreshed on demand. Capability detection
(supported_parameters) drives the structured-output strategy.
"""

import time
from dataclasses import dataclass, field

import httpx

CATALOG_URL = "https://openrouter.ai/api/v1/models"
CACHE_TTL_SECONDS = 24 * 3600


@dataclass
class ModelInfo:
    id: str
    name: str
    context_length: int | None = None
    pricing: dict = field(default_factory=dict)
    supported_parameters: list[str] = field(default_factory=list)

    def supports_structured_output(self) -> bool:
        """True if the model accepts a JSON-schema response format."""
        return (
            "response_format" in self.supported_parameters
            or "structured_outputs" in self.supported_parameters
        )

    def price_per_token(self) -> tuple[float, float]:
        """(prompt, completion) price per token, USD."""
        prompt = float(self.pricing.get("prompt", 0) or 0)
        completion = float(self.pricing.get("completion", 0) or 0)
        return prompt, completion

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        p, c = self.price_per_token()
        return round(prompt_tokens * p + completion_tokens * c, 8)


def _parse_model(entry: dict) -> ModelInfo:
    return ModelInfo(
        id=entry.get("id", ""),
        name=entry.get("name", entry.get("id", "")),
        context_length=entry.get("context_length"),
        pricing=entry.get("pricing", {}) or {},
        supported_parameters=entry.get("supported_parameters", []) or [],
    )


class ModelCatalog:
    """In-memory cached catalog over the live OpenRouter endpoint."""

    def __init__(self, transport: httpx.BaseTransport | None = None, ttl: int = CACHE_TTL_SECONDS):
        self._transport = transport  # injected MockTransport in tests
        self._ttl = ttl
        self._models: dict[str, ModelInfo] = {}
        self._fetched_at: float = 0.0

    def _fetch(self) -> dict[str, ModelInfo]:
        with httpx.Client(transport=self._transport, timeout=30) as client:
            response = client.get(CATALOG_URL)
            response.raise_for_status()
            payload = response.json()
        return {m.id: m for m in (_parse_model(e) for e in payload.get("data", []))}

    def refresh(self) -> None:
        self._models = self._fetch()
        self._fetched_at = time.monotonic()

    def all_models(self, refresh: bool = False) -> list[ModelInfo]:
        stale = (time.monotonic() - self._fetched_at) > self._ttl
        if refresh or not self._models or stale:
            self.refresh()
        return sorted(self._models.values(), key=lambda m: m.id)

    def get(self, model_id: str) -> ModelInfo | None:
        self.all_models()
        return self._models.get(model_id)

    def supports_structured_output(self, model_id: str) -> bool:
        info = self.get(model_id)
        return bool(info and info.supports_structured_output())
