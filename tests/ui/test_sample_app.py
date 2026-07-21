"""Sample UI tests against a small local demo page (tests/fixtures/sample_page.html,
served over loopback HTTP by the `demo_server` fixture in tests/conftest.py —
no external network required). Several of these fail on purpose: the point is
to exercise the full failure-collection pipeline end to end and produce real
artifacts for the dashboard to display, the same way a broken real-world
suite would.
"""

import pytest
from playwright.sync_api import expect


@pytest.fixture
def sample_page_url(demo_server: str) -> str:
    return f"{demo_server}/sample_page.html"


@pytest.mark.ui
def test_login_with_valid_credentials_succeeds(page, sample_page_url):
    page.goto(sample_page_url)
    page.fill("#username", "admin")
    page.fill("#password", "secret")
    page.click("#login-btn")
    expect(page.locator("#welcome")).to_be_visible()


@pytest.mark.ui
def test_login_button_selector_has_changed(page, sample_page_url):
    """References a selector that no longer exists, the way a real locator
    breaks after a UI change — demonstrates Timeout/Locator-Changed
    classification and the full artifact pipeline.
    """
    page.goto(sample_page_url)
    page.fill("#username", "admin")
    page.fill("#password", "secret")
    page.click("#login-button", timeout=2000)  # real id is #login-btn


@pytest.mark.ui
def test_login_assertion_uses_wrong_expected_text(page, sample_page_url):
    page.goto(sample_page_url)
    page.fill("#username", "admin")
    page.fill("#password", "secret")
    page.click("#login-btn")
    expect(page.locator("#welcome")).to_have_text("You are now logged in", timeout=2000)


@pytest.mark.ui
def test_clicking_a_hidden_element(page, sample_page_url):
    page.goto(sample_page_url)
    page.click("#hidden-btn", timeout=2000)


@pytest.mark.ui
def test_failed_data_load_is_captured_in_network_and_console_logs(page, sample_page_url):
    page.goto(sample_page_url)
    page.click("#load-data-btn")
    expect(page.locator("#data-status")).to_have_text("loaded", timeout=2000)
