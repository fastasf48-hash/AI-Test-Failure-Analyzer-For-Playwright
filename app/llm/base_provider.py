"""Pluggable LLM provider interface. `OpenAIProvider` and `ClaudeProvider`
both implement `.analyze()` with this exact signature — `provider_factory.py`
is the only code that needs to know which one is active, so adding a third
provider later means adding one class, not touching any calling code
(Open/Closed, Liskov substitution).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.llm.schemas import AIAnalysisResult


class LLMResponseError(RuntimeError):
    """Raised when a provider's response can't be turned into a valid
    AIAnalysisResult — a refusal, malformed JSON, or a schema violation.
    """


@dataclass
class ProviderResponse:
    result: AIAnalysisResult
    raw_response: dict
    model: str


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def analyze(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        """Send the prompts to the provider and return a validated result.

        Must raise `LLMResponseError` (not a provider-specific exception) on
        anything that isn't a valid `AIAnalysisResult` — callers only need to
        catch one exception type regardless of which provider is active.
        """
        raise NotImplementedError
