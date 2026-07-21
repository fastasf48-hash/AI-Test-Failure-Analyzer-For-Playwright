"""Overrides pytest-playwright's `page` fixture to add automatic, zero-config
failure collection: on any test failure, screenshot + video + trace +
console logs + network logs + stack trace + environment snapshot are all
captured and persisted to the database. Passing tests pay only the small
constant overhead of tracing/video recording (discarded on teardown) and a
lightweight DB row so summary stats add up correctly.

Playwright's artifact lifecycle forces a two-phase collection order that's
worth stating explicitly, because it's the one non-obvious thing here:

1. **Before `context.close()`**: screenshot (needs the page still open) and
   `tracing.stop()` (must be called on a live context) both have to happen
   here, or not at all.
2. **After `context.close()`**: only once closed does Playwright know a
   video's final path — anything that runs earlier gets an error, not an
   empty result.

Console/network/stack-trace/environment collectors don't care about that
boundary (they only touch in-memory buffers or plain data), so they run in
the second phase for simplicity, alongside the video collector.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.analyzers.failure_bundle import build_failure_bundle
from app.collectors.base_collector import FailureContext
from app.collectors.console_log_collector import ConsoleLogCollector
from app.collectors.environment_collector import EnvironmentCollector
from app.collectors.environment_collector import gather as gather_environment
from app.collectors.network_log_collector import NetworkLogCollector
from app.collectors.screenshot_collector import ScreenshotCollector
from app.collectors.stacktrace_collector import StacktraceCollector
from app.collectors.trace_collector import TraceCollector
from app.collectors.video_collector import VideoCollector
from app.config.settings import get_settings
from app.database.models import ResultStatus
from app.database.repository import get_repository
from app.utilities.logger import get_logger

if TYPE_CHECKING:
    from playwright.sync_api import Browser

logger = get_logger(__name__)


def _sanitize(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid)


def _artifacts_dir_for(execution_id: str, nodeid: str) -> Path:
    return get_settings().artifacts_dir / execution_id / _sanitize(nodeid)


def _determine_status(node: pytest.Item) -> tuple[ResultStatus, object | None]:
    """Reads the reports `pytest_runtest_makereport` stashed (see
    conftest_hooks.py) to classify the test outcome. `rep_call` (the test
    body itself) takes priority; `rep_setup` is the fallback for tests that
    never got to run at all.
    """
    rep_call = getattr(node, "rep_call", None)
    if rep_call is not None:
        if rep_call.failed:
            return ResultStatus.FAILED, rep_call
        if rep_call.skipped:
            return ResultStatus.SKIPPED, rep_call
        return ResultStatus.PASSED, rep_call

    rep_setup = getattr(node, "rep_setup", None)
    if rep_setup is not None:
        if rep_setup.failed:
            return ResultStatus.FAILED, rep_setup
        if rep_setup.skipped:
            return ResultStatus.SKIPPED, rep_setup

    return ResultStatus.PASSED, None


def _extract_error_message(report: object | None) -> str:
    longrepr = getattr(report, "longrepr", None)
    reprcrash = getattr(longrepr, "reprcrash", None)
    if reprcrash is not None:
        return reprcrash.message
    return str(longrepr) if longrepr else ""


def _extract_traceback_text(report: object | None) -> str:
    return getattr(report, "longreprtext", "") or ""


@pytest.fixture(scope="session", autouse=True)
def _capture_browser_metadata(browser: Browser, request: pytest.FixtureRequest):
    """Session-scoped and autouse so it runs exactly once, the first time any
    test requests `browser` — that's the earliest point a real `Browser`
    instance (and therefore its version string) exists; `pytest_sessionstart`
    (conftest_hooks.py) runs before any browser is launched, so it can't
    capture this itself.
    """
    run_id = getattr(request.config, "_att_run_id", None)
    if run_id is not None:
        with get_repository() as repo:
            run = repo.get_test_run(run_id)
            if run is not None:
                run.browser_version = browser.version
    yield


@pytest.fixture
def page(browser: Browser, request: pytest.FixtureRequest):
    execution_id = getattr(request.config, "_att_execution_id", "adhoc")
    artifacts_dir = _artifacts_dir_for(execution_id, request.node.nodeid)
    video_dir = Path(tempfile.mkdtemp(prefix="pw-video-"))

    context = browser.new_context(record_video_dir=str(video_dir))
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()

    console_collector = ConsoleLogCollector()
    network_collector = NetworkLogCollector()
    page.on("console", console_collector.handle_console_message)
    page.on("requestfailed", network_collector.handle_request_failed)
    page.on("response", network_collector.handle_response)

    yield page

    status, report = _determine_status(request.node)
    duration_seconds = float(getattr(report, "duration", 0.0) or 0.0)

    ctx = FailureContext(
        execution_id=execution_id,
        test_name=request.node.nodeid,
        test_file=str(request.node.path),
        artifacts_dir=artifacts_dir,
        page=page,
        browser_context=context,
    )

    result_fields: dict = {}

    if status == ResultStatus.FAILED:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        ctx.error_message = _extract_error_message(report)
        ctx.traceback_text = _extract_traceback_text(report)
        ctx.environment = gather_environment()

        # Phase 1 — must happen before context.close().
        pre_close_paths = {
            "screenshot_path": ScreenshotCollector().collect(ctx),
            "trace_path": TraceCollector().collect(ctx),
        }
    else:
        try:
            context.tracing.stop()  # discard — still required to release resources
        except Exception as exc:
            logger.debug("Discarding trace failed for %s: %s", request.node.nodeid, exc)
        pre_close_paths = {}

    context.close()  # finalizes the video file

    if status == ResultStatus.FAILED:
        try:
            ctx.video_source_path = Path(page.video.path()) if page.video else None
        except Exception as exc:
            logger.debug("Video not available for %s: %s", request.node.nodeid, exc)
            ctx.video_source_path = None

        # Phase 2 — only valid after context.close().
        bundle = build_failure_bundle(
            ctx,
            collectors={
                "video_path": VideoCollector(),
                "console_log_path": console_collector,
                "network_log_path": network_collector,
            },
            pre_collected=pre_close_paths,
        )
        StacktraceCollector().collect(ctx)
        EnvironmentCollector().collect(ctx)
        result_fields = bundle.as_result_fields()

    _persist_result(request, status, duration_seconds, result_fields)
    shutil.rmtree(video_dir, ignore_errors=True)


def _persist_result(
    request: pytest.FixtureRequest,
    status: ResultStatus,
    duration_seconds: float,
    result_fields: dict,
) -> None:
    run_id = getattr(request.config, "_att_run_id", None)
    if run_id is None:
        logger.warning("No active TestRun; skipping DB persistence for %s", request.node.nodeid)
        return

    with get_repository() as repo:
        repo.add_test_result(
            run_id=run_id,
            test_name=request.node.nodeid,
            test_file=str(request.node.path),
            status=status,
            duration_seconds=duration_seconds,
            **result_fields,
        )
