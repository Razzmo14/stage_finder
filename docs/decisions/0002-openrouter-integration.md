# ADR 0002: OpenRouter-first LLM gateway with capability-aware structured output

Date: 2026-10-28
Status: Accepted (planned)

## Context

The spec requires access to any model via OpenRouter, per-task model
assignment, structured outputs, and privacy-preserving routing. Not every
model supports structured outputs or tools, so a fixed calling strategy
would fail on part of the catalog. CVs contain personal data, so data policy
matters (GDPR).

## Decision

- Use the official OpenAI Python SDK pointed at
  `base_url="https://openrouter.ai/api/v1"` (with optional `HTTP-Referer` and
  `X-Title` headers) behind a thin `LLMProvider` interface; OpenRouter is
  the default provider, direct Anthropic/OpenAI and Ollama are alternates.
- The model catalog is fetched live from `GET /api/v1/models`, cached
  locally, refreshed periodically, and rendered in a searchable picker. No
  hardcoded model list anywhere.
- Separate model roles, each user-assignable: CV/profile extraction, offer
  matching/re-ranking, letter generation, claim verification. Sensible
  defaults plus "cheap/fast" and "high quality" presets.
- Structured-output strategy is capability-aware, read from the catalog's
  `supported_parameters`:
  1. If supported: `response_format` with a JSON schema generated from the
     Pydantic model, plus `provider.require_parameters=true`.
  2. Else: JSON mode or a "reply with JSON only" prompt, then Pydantic
     validation, retrying (max N times) with the validation error fed back.
  3. The UI warns when the selected model lacks reliable structured output.
- Routing defaults to the most privacy-preserving options
  (`data_collection="deny"`, Zero Data Retention routing only), with the
  implications of relaxing them explained in Settings.
- Usage and cost per request are stored in the EventLog; bulk generation
  shows an estimated cost first; optional monthly budget cap.
- Errors: exponential backoff on 429, automatic fallback model on
  unavailability, truncation/summarization on context overflow, and a clear
  message on insufficient credits.
- Streaming for letter generation and regeneration in the review screen.

## Consequences

- The same task code works across hundreds of models without per-model
  branches; capability detection is centralized.
- Contract tests with a mocked OpenRouter endpoint cover both the native
  structured-output path and the fallback path.
- Embeddings stay a separate, pluggable concern so changing the chat model
  never invalidates stored vectors (model name stored with each vector).
