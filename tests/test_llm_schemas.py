"""Tests the actual enforcement mechanism behind "no hallucinations": Pydantic
validation of the LLM's response against AIAnalysisResult, independent of
any provider or network call.
"""

import pytest
from pydantic import ValidationError

from app.database.models import FailureCategory, Severity
from app.llm.schemas import AIAnalysisResult

VALID_PAYLOAD = {
    "root_cause": "The #login-button selector no longer exists in the DOM.",
    "confidence_score": 0.9,
    "failure_category": "Locator Changed",
    "severity": "High",
    "suggested_fix": "Update the locator to #login-btn.",
}


def test_valid_payload_parses_successfully():
    result = AIAnalysisResult.model_validate(VALID_PAYLOAD)
    assert result.failure_category == FailureCategory.LOCATOR_CHANGED
    assert result.severity == Severity.HIGH
    assert result.alternative_fixes == []


def test_confidence_score_out_of_range_is_rejected():
    payload = {**VALID_PAYLOAD, "confidence_score": 1.4}
    with pytest.raises(ValidationError):
        AIAnalysisResult.model_validate(payload)


def test_unrecognized_category_is_rejected():
    """The concrete mechanism behind "no hallucinations": a category the LLM
    invented that isn't in our enum must not silently pass through.
    """
    payload = {**VALID_PAYLOAD, "failure_category": "Something Made Up"}
    with pytest.raises(ValidationError):
        AIAnalysisResult.model_validate(payload)


def test_extra_fields_are_rejected():
    payload = {**VALID_PAYLOAD, "unexpected_field": "should not be allowed"}
    with pytest.raises(ValidationError):
        AIAnalysisResult.model_validate(payload)


def test_missing_required_field_is_rejected():
    payload = dict(VALID_PAYLOAD)
    del payload["suggested_fix"]
    with pytest.raises(ValidationError):
        AIAnalysisResult.model_validate(payload)
