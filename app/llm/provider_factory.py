"""Picks the active LLM provider based on `Settings.llm_provider`. This is
the one place in the whole codebase that decides *which* provider runs —
callers (analyze_failure.py, the dashboard's Analyze button) just call
`get_provider().analyze(...)` and never import OpenAIProvider/ClaudeProvider
directly.

Provider modules are imported lazily, inside each branch, rather than at the
top of this file: that way a user who only ever uses one provider isn't
required to have the other provider's SDK importable, and — more
importantly — no provider's client is constructed, and no network code
runs, until a provider is actually requested.
"""

from __future__ import annotations

from app.config.settings import Settings, get_settings
from app.llm.base_provider import LLMProvider


class MissingAPIKeyError(RuntimeError):
    """Raised when the configured provider has no API key set. Callers should
    catch this and show a friendly message — never a stack trace — since a
    missing key is an expected, everyday state for this project.
    """


class UnknownProviderError(RuntimeError):
    pass


_ENV_VAR_BY_PROVIDER = {"openai": "OPENAI_API_KEY", "claude": "CLAUDE_API_KEY"}


def get_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    provider_name = settings.llm_provider

    if provider_name not in _ENV_VAR_BY_PROVIDER:
        raise UnknownProviderError(
            f"Unknown LLM provider {provider_name!r}. Expected one of: " f"{', '.join(_ENV_VAR_BY_PROVIDER)}."
        )

    api_key = settings.api_key_for(provider_name)
    if not api_key:
        raise MissingAPIKeyError(
            f"No API key configured for provider '{provider_name}'. "
            f"Set {_ENV_VAR_BY_PROVIDER[provider_name]} in your .env file, or change "
            f"LLM_PROVIDER to a provider you do have a key for."
        )

    if provider_name == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=api_key, model=settings.openai_model)

    from app.llm.claude_provider import ClaudeProvider

    return ClaudeProvider(api_key=api_key, model=settings.claude_model)
