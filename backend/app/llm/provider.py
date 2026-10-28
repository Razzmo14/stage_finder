"""LLMProvider abstraction (ADR 0002).

A thin interface over chat completions. Implementations: OpenRouter
(default), plus direct OpenAI/Anthropic/Ollama later (providers-014).
No LangChain; direct SDK/HTTP calls only.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class CompletionRequest:
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    # JSON schema response format for models that support structured outputs.
    response_format: dict | None = None
    # Provider routing/privacy options (data_collection, require_parameters...).
    extra_body: dict = field(default_factory=dict)


@dataclass
class Completion:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMError(Exception):
    pass


class LLMProvider(Protocol):
    """Every provider implements this minimal surface."""

    name: str

    def complete(self, request: CompletionRequest) -> Completion:
        """Synchronous completion call."""
        ...


def messages(*pairs: tuple[str, str]) -> list[ChatMessage]:
    return [ChatMessage(role=role, content=content) for role, content in pairs]
