"""OpenRouter provider: official OpenAI SDK pointed at OpenRouter.

Privacy-preserving routing by default: data_collection="deny" and
require_parameters=true when a JSON schema response format is requested
(ADR 0002).
"""

from openai import OpenAI

from app.core import secrets
from app.llm.catalog import ModelCatalog
from app.llm.provider import Completion, CompletionRequest, LLMError

BASE_URL = "https://openrouter.ai/api/v1"
API_KEY_SECRET = "openrouter_api_key"


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key: str | None = None, catalog: ModelCatalog | None = None) -> None:
        self._api_key = api_key
        self.catalog = catalog or ModelCatalog()

    @property
    def api_key(self) -> str | None:
        if self._api_key is not None:
            return self._api_key
        return secrets.get_secret(API_KEY_SECRET)

    def _client(self) -> OpenAI:
        key = self.api_key
        if not key:
            raise LLMError("OpenRouter API key is not configured")
        return OpenAI(
            api_key=key,
            base_url=BASE_URL,
            default_headers={
                "HTTP-Referer": "https://stage-finder.local",
                "X-Title": "Stage Finder",
            },
        )

    def complete(self, request: CompletionRequest) -> Completion:
        extra_body = {"provider": {"data_collection": "deny"}}
        if request.response_format is not None:
            # Only route to providers that honor the schema we require.
            extra_body["provider"]["require_parameters"] = True
        if request.extra_body:
            extra_body.update(request.extra_body)

        kwargs: dict = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "extra_body": extra_body,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            kwargs["response_format"] = request.response_format

        try:
            response = self._client().chat.completions.create(**kwargs)
        except Exception as error:  # noqa: BLE001 - normalize provider errors
            raise LLMError(f"OpenRouter call failed: {error}") from error

        usage = response.usage
        return Completion(
            content=response.choices[0].message.content or "",
            model=response.model or request.model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
