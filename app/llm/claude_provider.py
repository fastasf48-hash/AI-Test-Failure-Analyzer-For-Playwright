"""Claude provider. Anthropic's SDK has no direct equivalent to OpenAI's
Pydantic-native `.parse()`, so structured output is forced the way Anthropic
documents for this exact use case: define one tool whose `input_schema` is
`AIAnalysisResult`'s JSON schema, then force `tool_choice` so the model must
call it — the tool's `input` *is* the structured JSON, no free-text parsing
required.
"""

from __future__ import annotations

import anthropic

from app.llm.base_provider import LLMProvider, LLMResponseError, ProviderResponse
from app.llm.schemas import AIAnalysisResult
from app.utilities.logger import get_logger

logger = get_logger(__name__)

_TOOL_NAME = "submit_failure_analysis"


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def analyze(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        tool = {
            "name": _TOOL_NAME,
            "description": "Submit the structured failure analysis.",
            "input_schema": AIAnalysisResult.model_json_schema(),
        }

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[tool],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
            )
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller as one error type
            raise LLMResponseError(f"Claude request failed: {exc}") from exc

        tool_use = next((block for block in response.content if block.type == "tool_use"), None)
        if tool_use is None:
            raise LLMResponseError("Claude did not return the required tool call")

        try:
            result = AIAnalysisResult.model_validate(tool_use.input)
        except Exception as exc:  # noqa: BLE001 — pydantic.ValidationError, wrapped for one error type
            raise LLMResponseError(f"Claude's response didn't match the required schema: {exc}") from exc

        return ProviderResponse(result=result, raw_response=tool_use.input, model=self._model)
