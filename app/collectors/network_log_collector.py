"""Buffers failed requests and non-2xx responses for the lifetime of one test.

Same dual-role design as `ConsoleLogCollector`: an event sink wired to
`page.on("requestfailed", ...)` / `page.on("response", ...)` in
app/playwright/fixtures.py, and an `ArtifactCollector` that flushes what it
saw. We only record failures/non-2xx responses rather than every request —
a passing test's console is quiet by default, but its network tab never is,
so logging everything would drown the one failed call that mattered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.collectors.base_collector import ArtifactCollector, FailureContext

if TYPE_CHECKING:
    from playwright.sync_api import Request, Response


class NetworkLogCollector(ArtifactCollector):
    def __init__(self) -> None:
        self._lines: list[str] = []

    def handle_request_failed(self, request: Request) -> None:
        failure = request.failure
        reason = failure["errorText"] if failure else "unknown error"
        self._lines.append(f"[REQUEST FAILED] {request.method} {request.url} -> {reason}")

    def handle_response(self, response: Response) -> None:
        if response.status < 400:
            return
        self._lines.append(f"[HTTP {response.status}] {response.request.method} {response.url}")

    def collect(self, ctx: FailureContext) -> str | None:
        if not self._lines:
            return None

        dest = ctx.artifacts_dir / "network.log"
        dest.write_text("\n".join(self._lines), encoding="utf-8")
        return str(dest)
