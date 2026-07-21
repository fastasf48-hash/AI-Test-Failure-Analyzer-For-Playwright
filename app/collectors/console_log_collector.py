"""Buffers browser console output for the lifetime of one test.

This collector plays two roles by design: it's a Playwright event *sink*
(`handle_console_message` is wired to `page.on("console", ...)` in
app/playwright/fixtures.py, called for every message the whole test long)
and, at failure time, an `ArtifactCollector` that flushes its own buffer to
disk. Splitting those into two objects would mean passing the buffer between
them for no benefit — the buffer's only reader is this class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.collectors.base_collector import ArtifactCollector, FailureContext

if TYPE_CHECKING:
    from playwright.sync_api import ConsoleMessage


class ConsoleLogCollector(ArtifactCollector):
    def __init__(self) -> None:
        self._lines: list[str] = []

    def handle_console_message(self, message: ConsoleMessage) -> None:
        self._lines.append(f"[{message.type.upper()}] {message.text}")

    def collect(self, ctx: FailureContext) -> str | None:
        if not self._lines:
            return None

        dest = ctx.artifacts_dir / "console.log"
        dest.write_text("\n".join(self._lines), encoding="utf-8")
        return str(dest)
