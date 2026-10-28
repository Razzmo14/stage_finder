"""Direct OpenAI provider (Chat Completions, httpx)."""

import httpx

from app.core import secrets
from app.llm.provider import Completion, CompletionRequest, LLMError

API_KEY_SECRET = "openai_api_key"
BASE_URL = "https://api.openai.com"


class OpenAIDirectProvider:
    name = "openai"
    supports_structured = True

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=60)

    def complete(self, request: CompletionRequest) -> Completion:
        api_key = secrets.get_secret(API_KEY_SECRET)
        if not api_key:
            raise LLMError("OpenAI API key is not configured (keychain)")
        body: dict = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            body["response_format"] = request.response_format
        try:
            response = self._client().post(
                f"{BASE_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:  # noqa: BLE001
            raise LLMError(f"OpenAI call failed: {error}") from error
        usage = payload.get("usage", {})
        return Completion(
            content=payload["choices"][0]["message"]["content"],
            model=payload.get("model", request.model),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )

    def stream(self, request: CompletionRequest):
        yield self.complete(request).content
