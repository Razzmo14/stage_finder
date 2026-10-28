"""Provider registry and active-provider resolution."""

from app.llm.anthropic import AnthropicProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai_direct import OpenAIDirectProvider
from app.llm.openrouter import OpenRouterProvider

PROVIDER_NAMES = ("openrouter", "anthropic", "openai", "ollama")

DEFAULT_LLM_SETTINGS: dict = {
    "active_provider": "openrouter",
    "monthly_budget_usd": None,
    "ollama_base_url": "http://localhost:11434",
}


def build_provider(name: str, catalog=None, ollama_base_url: str | None = None):
    """Build a provider instance by name."""
    if name == "openrouter":
        return OpenRouterProvider(catalog=catalog)
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openai":
        return OpenAIDirectProvider()
    if name == "ollama":
        return OllamaProvider(base_url=ollama_base_url)
    raise ValueError(f"Unknown provider: {name}")


def get_active_provider(app_state, llm_settings: dict, catalog=None) -> object:
    """Return the provider selected in settings, with a per-app cache."""
    name = llm_settings.get("active_provider", "openrouter")
    if name not in PROVIDER_NAMES:
        name = "openrouter"
    cache: dict = getattr(app_state, "provider_cache", None) or {}
    key = name if name != "ollama" else f"ollama:{llm_settings.get('ollama_base_url')}"
    if key not in cache:
        cache[key] = build_provider(
            name, catalog=catalog, ollama_base_url=llm_settings.get("ollama_base_url")
        )
    app_state.provider_cache = cache
    return cache[key]


def provider_supports_structured(provider, catalog, model: str) -> bool:
    """OpenRouter uses the live catalog; other providers declare statically."""
    if hasattr(provider, "supports_structured"):
        return bool(provider.supports_structured)
    return catalog.supports_structured_output(model)
