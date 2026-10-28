"""Local Ollama provider (fully local mode, no key required)."""

import httpx

from app.llm.provider import Completion, CompletionRequest, LLMError

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider:
    name = "ollama"
    supports_structured = False

    def __init__(
        self, base_url: str | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.base_url = base_url or DEFAULT_BASE_URL
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=120)

    def complete(self, request: CompletionRequest) -> Completion:
        body: dict = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
        }
        if request.temperature is not None:
            body["options"] = {"temperature": request.temperature}
        try:
            response = self._client().post(f"{self.base_url}/api/chat", json=body)
            response.raise_for_status()
            payload = response.json()
        except Exception as error:  # noqa: BLE001
            raise LLMError(
                f"Ollama call failed (is the server running at {self.base_url}?): {error}"
            ) from error
        return Completion(
            content=payload.get("message", {}).get("content", ""),
            model=payload.get("model", request.model),
            prompt_tokens=int(payload.get("prompt_eval_count", 0)),
            completion_tokens=int(payload.get("eval_count", 0)),
        )

    def stream(self, request: CompletionRequest):
        body: dict = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": True,
        }
        try:
            with self._client() as client:
                with client.stream("POST", f"{self.base_url}/api/chat", json=body) as response:
                    for line in response.iter_lines():
                        if not line:
                            continue
                        import json

                        chunk = json.loads(line)
                        piece = chunk.get("message", {}).get("content", "")
                        if piece:
                            yield piece
        except Exception as error:  # noqa: BLE001
            raise LLMError(f"Ollama stream failed: {error}") from error
