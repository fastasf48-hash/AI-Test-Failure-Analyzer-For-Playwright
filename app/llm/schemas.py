"""The structured JSON contract every LLM provider must return.

This one Pydantic model does two jobs:

1. **Outbound**: `AIAnalysisResult.model_json_schema()` becomes the schema
   handed to the LLM (OpenAI's native structured-output `response_format`,
   or a forced tool-call `input_schema` for Claude — see
   openai_provider.py / claude_provider.py).
2. **Inbound**: `AIAnalysisResult.model_validate(raw_json)` is what turns the
   model's response back into a typed object — and where hallucinated
   output actually gets caught. If the model invents a `failure_category`
   value outside our enum, or a `confidence_score` of 1.4, this raises
   `pydantic.ValidationError` *before* any of it reaches the database.
   "No hallucinations" is enforced here, not just requested in the prompt.

Reusing `FailureCategory`/`Severity` from app.database.models (rather than
redefining a parallel set of literals here) keeps the rule-based classifier,
the LLM, and the database speaking about exactly the same set of categories.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.database.models import FailureCategory, Severity


class AIAnalysisResult(BaseModel):
    model_config = {"extra": "forbid"}

    root_cause: str = Field(
        description="A concise, specific explanation of why the test failed, grounded only in "
        "the evidence provided."
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="How confident you are in root_cause, from 0.0 to 1.0."
    )
    failure_category: FailureCategory
    severity: Severity

    suggested_fix: str = Field(
        description="One concrete, actionable fix — a specific code change, wait strategy, or "
        "next investigation step. Not a vague suggestion."
    )
    alternative_fixes: list[str] = Field(
        default_factory=list, description="Other plausible fixes, if the primary one turns out wrong."
    )

    possible_developer_issue: str | None = Field(
        default=None, description="If the root cause may be an application bug, describe it here."
    )
    possible_automation_issue: str | None = Field(
        default=None,
        description="If the root cause may be a problem with the test/automation itself, describe it here.",
    )
    relevant_documentation: list[str] = Field(
        default_factory=list,
        description="Official Playwright documentation URLs, only if you are confident they exist.",
    )
    improved_locator: str | None = Field(
        default=None, description="A more robust Playwright locator, if the failure is locator-related."
    )
    example_code: str | None = Field(
        default=None, description="A short Playwright code snippet demonstrating the fix."
    )
