"""Capability-aware structured output (ADR 0002).

Strategy:
1. Model supports structured outputs -> response_format with the JSON schema
   generated from the Pydantic model.
2. Otherwise -> "reply with JSON only" prompt, Pydantic validation, retry
   with the validation error fed back (max N attempts).

The provider is injected, so contract tests run against a fake provider and
never hit the real API.
"""

import json
import re

from pydantic import BaseModel, ValidationError

from app.llm.provider import Completion, CompletionRequest, LLMProvider, messages

MAX_ATTEMPTS = 3

JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def json_schema_for(model_cls: type[BaseModel]) -> dict:
    """OpenAI-style JSON schema response format for a Pydantic model."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model_cls.__name__,
            "schema": model_cls.model_json_schema(),
        },
    }


def extract_json(text: str) -> dict:
    """Parse JSON from a raw reply, tolerating code fences."""
    candidate = text.strip()
    fenced = JSON_FENCE_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    return json.loads(candidate)


def structured_completion[ModelType: BaseModel](
    provider: LLMProvider,
    *,
    model: str,
    system: str,
    user: str,
    schema_model: type[ModelType],
    supports_structured: bool,
    temperature: float | None = None,
) -> tuple[ModelType, Completion]:
    """Get a validated Pydantic result from the provider.

    Returns (validated_result, raw_completion) so callers can record usage.
    """
    if supports_structured:
        request = CompletionRequest(
            model=model,
            messages=messages(("system", system), ("user", user)),
            response_format=json_schema_for(schema_model),
            temperature=temperature,
        )
        completion = provider.complete(request)
        try:
            return schema_model.model_validate(extract_json(completion.content)), completion
        except (json.JSONDecodeError, ValidationError):
            # Even capable models can fail; fall through to the retry path.
            pass

    fallback_system = (
        f"{system}\n\nReply with a single JSON object only. "
        f"It must validate against this schema:\n{json.dumps(schema_model.model_json_schema())}"
    )
    conversation = [("system", fallback_system), ("user", user)]
    last_error: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        if last_error is not None:
            conversation.append(
                ("user", f"Your reply was invalid: {last_error}. Reply with corrected JSON only.")
            )
        completion = provider.complete(
            CompletionRequest(
                model=model,
                messages=messages(*conversation),
                temperature=temperature,
            )
        )
        conversation.append(("assistant", completion.content))
        try:
            return schema_model.model_validate(extract_json(completion.content)), completion
        except (json.JSONDecodeError, ValidationError) as error:
            last_error = error
    raise ValueError(
        f"Model {model} failed to produce valid output after {MAX_ATTEMPTS} attempts: {last_error}"
    )
