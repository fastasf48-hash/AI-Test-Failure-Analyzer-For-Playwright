"""Tests the prompt-construction logic itself — no LLM call involved."""

from app.llm.prompts import AnalysisContext, build_user_prompt


def test_omits_optional_sections_when_absent():
    ctx = AnalysisContext(
        test_name="tests/x.py::test_y",
        status="failed",
        duration_seconds=1.0,
        error_message="boom",
        stack_trace="trace",
    )
    prompt = build_user_prompt(ctx)

    assert "## Browser console log" not in prompt
    assert "## Failed network requests" not in prompt
    assert "## Test source code" not in prompt
    assert "## Environment" not in prompt


def test_includes_sections_when_present():
    ctx = AnalysisContext(
        test_name="tests/x.py::test_y",
        status="failed",
        duration_seconds=1.0,
        error_message="boom",
        stack_trace="trace",
        rule_based_category="Timeout",
        console_log="[ERROR] oops",
        network_log="[HTTP 404] GET /missing",
        environment={"os": "Windows"},
        test_source="def test_y(): pass",
    )
    prompt = build_user_prompt(ctx)

    assert "heuristic, not authoritative" in prompt
    assert "[ERROR] oops" in prompt
    assert "[HTTP 404] GET /missing" in prompt
    assert "os: Windows" in prompt
    assert "def test_y(): pass" in prompt
