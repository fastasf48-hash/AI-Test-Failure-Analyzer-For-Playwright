"""Moves the finalized video into the failure's artifact folder.

Playwright only knows a video's real path once its owning `BrowserContext`
has been closed, so this collector must run *after* `context.close()` — the
`context` fixture teardown resolves `ctx.video_source_path` at exactly that
point, once, before calling this collector.
"""

from __future__ import annotations

import shutil

from app.collectors.base_collector import ArtifactCollector, FailureContext
from app.utilities.logger import get_logger

logger = get_logger(__name__)


class VideoCollector(ArtifactCollector):
    def collect(self, ctx: FailureContext) -> str | None:
        if ctx.video_source_path is None or not ctx.video_source_path.exists():
            return None

        dest = ctx.artifacts_dir / "video.webm"
        try:
            shutil.move(str(ctx.video_source_path), str(dest))
        except OSError as exc:
            logger.warning("Video collection failed for %s: %s", ctx.test_name, exc)
            return None
        return str(dest)
