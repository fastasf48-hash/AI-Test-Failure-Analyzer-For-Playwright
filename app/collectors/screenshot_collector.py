"""Takes the failure screenshot. Must run before the page closes — see the
`page` fixture teardown in app/playwright/fixtures.py for exactly when that is.
"""

from __future__ import annotations

from app.collectors.base_collector import ArtifactCollector, FailureContext
from app.utilities.logger import get_logger

logger = get_logger(__name__)


class ScreenshotCollector(ArtifactCollector):
    def collect(self, ctx: FailureContext) -> str | None:
        if ctx.page is None:
            return None

        dest = ctx.artifacts_dir / "screenshot.png"
        try:
            ctx.page.screenshot(path=str(dest), full_page=True)
        except Exception as exc:  # page may already be closed or crashed
            logger.warning("Screenshot collection failed for %s: %s", ctx.test_name, exc)
            return None
        return str(dest)
