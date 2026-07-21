"""Unit tests for the deterministic, rule-based classifier. Pure function,
no browser needed — deliberately kept trivial to unit test (see
app/analyzers/category_classifier.py).
"""

from app.analyzers.category_classifier import classify
from app.database.models import FailureCategory


def test_playwright_timeout_error_classified_as_timeout():
    category = classify(
        error_message="",
        traceback_text="playwright._impl._errors.TimeoutError: Page.click: Timeout 2000ms exceeded.",
    )
    assert category == FailureCategory.TIMEOUT


def test_expect_assertion_mismatch_is_not_misclassified_as_timeout():
    """Regression: Playwright's auto-retrying `expect()` failures mention
    'waiting for' even when the real failure is an assertion mismatch, not a
    timeout — this used to make every assertion failure classify as Timeout.
    """
    category = classify(
        error_message="AssertionError: Locator expected to have text 'You are now logged in'",
        traceback_text=(
            "AssertionError: Locator expected to have text 'You are now logged in'\n"
            "Actual value: Welcome!\n"
            "Call log:\n"
            '  - Expect "to_have_text" with timeout 2000ms\n'
            '  - waiting for locator("#welcome")'
        ),
    )
    assert category == FailureCategory.ASSERTION_FAILURE


def test_network_error_classified_as_network_failure():
    category = classify(error_message="net::ERR_CONNECTION_REFUSED", traceback_text="")
    assert category == FailureCategory.NETWORK_FAILURE


def test_unrecognized_text_falls_back_to_unknown():
    category = classify(error_message="something bizarre happened", traceback_text="")
    assert category == FailureCategory.UNKNOWN
