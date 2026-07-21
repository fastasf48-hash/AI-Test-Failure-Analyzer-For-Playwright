"""The only module in the project allowed to implement pytest hook functions.
Everything else that needs pytest/Playwright context goes through fixtures
(app/playwright/fixtures.py) or reads data these hooks stash on `item`/`session.config`.

- `pytest_runtest_makereport` is the standard pytest cookbook recipe for
  making a test's pass/fail outcome visible to fixture teardowns: fixture
  teardown code runs *during* the test's lifecycle, before pytest has
  computed a final result, so without this hook a fixture has no reliable
  way to ask "did the test I'm tearing down for just fail?".
- `pytest_sessionstart` / `pytest_sessionfinish` own the single `TestRun` row
  for the whole pytest session — run-level bookkeeping doesn't fit cleanly
  into any one test's fixtures.
"""

from __future__ import annotations

import platform
import uuid
from datetime import UTC, datetime

import pytest

from app.database.repository import get_repository
from app.database.session import init_db
from app.utilities.git_info import get_git_branch, get_git_commit
from app.utilities.logger import get_logger

logger = get_logger(__name__)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


def _resolve_browser_name(config: pytest.Config) -> str:
    try:
        browsers = config.getoption("--browser")
    except (ValueError, AttributeError):
        browsers = None
    if not browsers:
        return "chromium"
    return browsers[0]


def pytest_sessionstart(session: pytest.Session) -> None:
    init_db()

    execution_id = f"run-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    session.config._att_execution_id = execution_id  # noqa: SLF001 — deliberate, scoped stash

    with get_repository() as repo:
        run = repo.create_test_run(
            execution_id=execution_id,
            os_name=platform.platform(),
            browser_name=_resolve_browser_name(session.config),
            git_branch=get_git_branch(),
            git_commit=get_git_commit(),
        )
        session.config._att_run_id = run.id  # noqa: SLF001

    logger.info("Test session %s started (run id=%s)", execution_id, run.id)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    run_id = getattr(session.config, "_att_run_id", None)
    if run_id is None:
        return

    with get_repository() as repo:
        run = repo.get_test_run(run_id)
        if run is not None:
            repo.finish_test_run(run)
            logger.info(
                "Test session %s finished: %s passed, %s failed, %s skipped",
                run.execution_id,
                run.passed_count,
                run.failed_count,
                run.skipped_count,
            )
