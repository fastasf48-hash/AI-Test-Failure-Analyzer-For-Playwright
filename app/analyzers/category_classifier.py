"""Deterministic, zero-cost failure classification.

This runs on *every* failure, automatically, before anyone spends an API
token — it's what lets the dashboard show a useful category on the very
first run, with AI analysis available as an opt-in upgrade rather than a
prerequisite for a usable failure list.

Keyword matching against the error message + traceback is intentionally
simple (no ML, no external calls): it's cheap, deterministic, and easy to
extend by adding a row to `_KEYWORD_RULES`. It will misclassify novel
failure text — that's an accepted trade-off `FailureCategory.UNKNOWN` exists
to make explicit, versus a system that pretends to be more confident than
rule-matching can support.
"""

from __future__ import annotations

from app.database.models import FailureCategory

_KEYWORD_RULES: list[tuple[FailureCategory, tuple[str, ...]]] = [
    # NOTE: deliberately does *not* include the generic "waiting for" phrase —
    # Playwright's auto-retrying `expect()` assertions always mention what
    # they were "waiting for" even when the real failure is a plain assertion
    # mismatch, which made every assertion failure misclassify as Timeout.
    (FailureCategory.TIMEOUT, ("timeouterror", "timeout exceeded", "timeout of")),
    (
        FailureCategory.LOCATOR_CHANGED,
        ("strict mode violation", "no such element", "resolved to 0 elements", "selector resolved to"),
    ),
    (
        FailureCategory.ELEMENT_HIDDEN,
        ("element is not visible", "outside of the viewport", "intercepts pointer events", "is not attached"),
    ),
    (FailureCategory.ASSERTION_FAILURE, ("assertionerror", "expect(", "assert ")),
    (
        FailureCategory.AUTHENTICATION_FAILURE,
        ("401", "unauthorized", "403 forbidden", "invalid credentials", "authentication failed"),
    ),
    (
        FailureCategory.API_FAILURE,
        ("500 internal server error", "502 bad gateway", "503 service unavailable", "apierror"),
    ),
    (
        FailureCategory.NETWORK_FAILURE,
        ("net::err_", "econnrefused", "connection refused", "networkerror", "connection reset"),
    ),
    (
        FailureCategory.DATABASE_FAILURE,
        ("operationalerror", "integrityerror", "could not connect to server", "sqlite3."),
    ),
    (
        FailureCategory.JAVASCRIPT_EXCEPTION,
        ("uncaught (in promise)", "referenceerror", "typeerror: cannot read"),
    ),
    (FailureCategory.TEST_DATA_ISSUE, ("keyerror", "no data found", "fixture not found")),
]


def classify(error_message: str, traceback_text: str) -> FailureCategory:
    haystack = f"{error_message}\n{traceback_text}".lower()
    for category, keywords in _KEYWORD_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category
    return FailureCategory.UNKNOWN
