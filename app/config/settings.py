"""Centralized, typed application configuration.

Every other module reads configuration through `get_settings()` instead of
calling `os.getenv` directly. This gives us one place to change defaults,
one place to validate, and one place to mock in tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Loaded once, at import time, from the .env file at the project root.
# python-dotenv does NOT overwrite variables already present in the real
# environment (e.g. exported in CI), so CI secrets always win over .env.
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # --- LLM provider selection -------------------------------------------------
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai").lower())
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY") or None)
    claude_api_key: str | None = field(default_factory=lambda: os.getenv("CLAUDE_API_KEY") or None)
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    claude_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-sonnet-5"))

    # --- Storage locations --------------------------------------------------------
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'analyzer.db'}"
        )
    )
    artifacts_dir: Path = field(
        default_factory=lambda: Path(os.getenv("ARTIFACTS_DIR", str(PROJECT_ROOT / "data" / "artifacts")))
    )

    # --- Logging --------------------------------------------------------------------
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    log_dir: Path = field(default_factory=lambda: Path(os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs"))))

    def api_key_for(self, provider: str | None = None) -> str | None:
        """Return the API key for `provider` (or the configured default provider)."""
        provider = (provider or self.llm_provider).lower()
        if provider == "openai":
            return self.openai_api_key
        if provider == "claude":
            return self.claude_api_key
        raise ValueError(f"Unknown LLM provider: {provider!r}. Expected 'openai' or 'claude'.")

    def has_key_for(self, provider: str | None = None) -> bool:
        """Used by the CLI/dashboard to show a friendly message instead of crashing."""
        return bool(self.api_key_for(provider))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings are immutable and cheap to compute once, so we cache the singleton."""
    return Settings()
