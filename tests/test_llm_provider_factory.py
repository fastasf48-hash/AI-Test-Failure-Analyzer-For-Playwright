"""Tests the graceful missing-key detection directly — no network involved.
`Settings` is a plain dataclass, so these construct one explicitly rather
than touching real environment variables or the process-wide cached
`get_settings()` singleton.
"""

import pytest

from app.config.settings import Settings
from app.llm.provider_factory import MissingAPIKeyError, UnknownProviderError, get_provider


def test_missing_openai_key_raises_friendly_error_before_any_client_is_built():
    settings = Settings(llm_provider="openai", openai_api_key=None, claude_api_key=None)
    with pytest.raises(MissingAPIKeyError, match="OPENAI_API_KEY"):
        get_provider(settings)


def test_missing_claude_key_raises_friendly_error_before_any_client_is_built():
    settings = Settings(llm_provider="claude", openai_api_key=None, claude_api_key=None)
    with pytest.raises(MissingAPIKeyError, match="CLAUDE_API_KEY"):
        get_provider(settings)


def test_unknown_provider_raises_clear_error():
    settings = Settings(llm_provider="not-a-real-provider")
    with pytest.raises(UnknownProviderError):
        get_provider(settings)


def test_openai_provider_constructed_when_key_present():
    settings = Settings(llm_provider="openai", openai_api_key="sk-fake-for-test", openai_model="gpt-4o-mini")
    provider = get_provider(settings)
    assert provider.name == "openai"


def test_claude_provider_constructed_when_key_present():
    settings = Settings(
        llm_provider="claude", claude_api_key="fake-key-for-test", claude_model="claude-sonnet-5"
    )
    provider = get_provider(settings)
    assert provider.name == "claude"
