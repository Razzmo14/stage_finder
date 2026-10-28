"""Direct Anthropic provider (Messages API, httpx).

No structured-output capability: the capability-aware fallback path
(JSON-mode prompt with validation retry) is used instead.
"""

import httpx

from app.core import secrets
from app.llm.provider import Completion, CompletionRequest, LLMError

API_KEY_SECRET = "anthropic_api_key"
BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"
    supports_structured = False

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=60)

    def complete(self, request: CompletionRequest) -> Completion:
        api_key = secrets.get_secret(API_KEY_SECRET)
        if not api_key:
            raise LLMError("Anthropic API key is not configured (keychain)")
        system = " ".join(m.content for m in request.messages if m.role == "system")
        messages = [
            {"role": m.role, "content": m.content} for m in request.messages if m.role != "system"
        ]
        body: dict = {
            "model": request.model,
            "max_tokens": request.max_tokens or 1024,
            "messages": messages,
        }
        if system:
            body["system"] = system
        if request.temperature is not None:
            body["temperature"] = request.temperature
        try:
            response = self._client().post(
                f"{BASE_URL}/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:  # noqa: BLE001
            raise LLMError(f"Anthropic call failed: {error}") from error
        text = "".join(block.get("text", "") for block in payload.get("content", []))
        usage = payload.get("usage", {})
        return Completion(
            content=text,
            model=payload.get("model", request.model),
            prompt_tokens=int(usage.get("input_tokens", 0)),
            completion_tokens=int(usage.get("output_tokens", 0)),
        )

    def stream(self, request: CompletionRequest):
        result = self.complete(request)
        yield result.content
