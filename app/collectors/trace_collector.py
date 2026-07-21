"""Stops Playwright's trace recording and exports it. Tracing is started for
every test in the `context` fixture (see app/playwright/fixtures.py) so a
trace is available the instant a failure is detected — starting it only
after a failure happens is too late, tracing must span the whole test.
"""

from __future__ import annotations

from app.collectors.base_collector import ArtifactCollector, FailureContext
from app.utilities.logger import get_logger

logger = get_logger(__name__)


class TraceCollector(ArtifactCollector):
    def collect(self, ctx: FailureContext) -> str | None:
        if ctx.browser_context is None:
            return None

        dest = ctx.artifacts_dir / "trace.zip"
        try:
            ctx.browser_context.tracing.stop(path=str(dest))
        except Exception as exc:
            logger.warning("Trace collection failed for %s: %s", ctx.test_name, exc)
            return None
        return str(dest)
