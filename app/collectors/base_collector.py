"""Shared contract for every artifact collector.

`FailureContext` carries everything any collector might need. Not every
collector uses every field (a `StacktraceCollector` doesn't need `page`,
a `ScreenshotCollector` doesn't need `traceback_text`) — that duck-typed
looseness is the trade-off for giving all collectors one uniform
`collect(ctx) -> str | None` signature, which is what lets
`app/analyzers/failure_bundle.py` run an arbitrary list of them identically
without a chain of if/elif branches.

A collector returns the artifact's saved path, or `None` if there was
nothing to collect. A collector must never let an internal failure (a
closed page, a missing video file) propagate — one collector failing must
not cost the run the artifacts every other collector already gathered.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page


@dataclass
class FailureContext:
    execution_id: str
    test_name: str
    test_file: str
    artifacts_dir: Path

    error_message: str = ""
    traceback_text: str = ""

    page: Page | None = None
    browser_context: BrowserContext | None = None
    # Set only after the context has been closed (see app/playwright/fixtures.py) —
    # Playwright can't resolve a video's final path until then.
    video_source_path: Path | None = None

    environment: dict[str, str] = field(default_factory=dict)


class ArtifactCollector(ABC):
    @abstractmethod
    def collect(self, ctx: FailureContext) -> str | None:
        """Gather/persist this collector's artifact and return its saved path."""
        raise NotImplementedError
