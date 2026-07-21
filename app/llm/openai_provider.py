"""OpenAI provider. Uses the SDK's native structured-output `.parse()`
helper, which takes a Pydantic model directly as `response_format` — the
model is constrained at the API level to return JSON matching
`AIAnalysisResult`, not merely asked nicely to via the prompt.
"""

from __future__ import annotations

from openai import OpenAI

from app.llm.base_provider import LLMProvider, LLMResponseError, ProviderResponse
from app.llm.schemas import AIAnalysisResult
from app.utilities.logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def analyze(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        try:
            completion = self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=AIAnalysisResult,
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller as one error type
            raise LLMResponseError(f"OpenAI request failed: {exc}") from exc

        message = completion.choices[0].message
        if message.refusal:
            raise LLMResponseError(f"OpenAI refused to analyze this failure: {message.refusal}")
        if message.parsed is None:
            raise LLMResponseError("OpenAI returned a response that didn't match the required schema")

        raw_response = completion.model_dump(mode="json")
        return ProviderResponse(result=message.parsed, raw_response=raw_response, model=self._model)
