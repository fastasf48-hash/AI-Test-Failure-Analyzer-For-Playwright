"""Pure-function tests for app/analyzers/test_source_locator.py — no browser,
no pytest fixtures beyond tmp_path.
"""

from app.analyzers.test_source_locator import find_test_source

SAMPLE_FILE = """
import pytest


def test_login_with_valid_credentials_succeeds(page):
    page.goto("https://example.com")


def test_login_button_selector_has_changed(page):
    page.click("#login-button", timeout=2000)
"""


def test_finds_matching_function_by_name(tmp_path):
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(SAMPLE_FILE, encoding="utf-8")

    source = find_test_source(
        str(test_file), "tests/ui/test_sample.py::test_login_button_selector_has_changed[chromium]"
    )

    assert source is not None
    assert "def test_login_button_selector_has_changed(page):" in source
    assert "#login-button" in source
    assert "test_login_with_valid_credentials_succeeds" not in source


def test_returns_none_for_missing_file():
    assert find_test_source("does/not/exist.py", "does/not/exist.py::test_x") is None


def test_returns_none_when_test_file_is_absent():
    assert find_test_source(None, "tests/x.py::test_x") is None


def test_returns_none_when_function_not_found(tmp_path):
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(SAMPLE_FILE, encoding="utf-8")

    assert find_test_source(str(test_file), "tests/ui/test_sample.py::test_nonexistent") is None
