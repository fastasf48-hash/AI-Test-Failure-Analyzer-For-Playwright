"""Snapshots the machine/interpreter environment a failure happened in.

`gather()` is a pure function with no Playwright or pytest dependency —
callers (or unit tests) can call it directly without a browser or a test
session, which is exactly why it's split out from `.collect()`.
"""

from __future__ import annotations

import json
import platform
import socket
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from app.collectors.base_collector import ArtifactCollector, FailureContext


def _playwright_version() -> str:
    try:
        return version("playwright")
    except PackageNotFoundError:
        return "unknown"


def gather() -> dict[str, str]:
    return {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "playwright_version": _playwright_version(),
        "hostname": socket.gethostname(),
    }


class EnvironmentCollector(ArtifactCollector):
    def collect(self, ctx: FailureContext) -> str | None:
        environment = ctx.environment or gather()
        dest = ctx.artifacts_dir / "environment.json"
        dest.write_text(json.dumps(environment, indent=2), encoding="utf-8")
        return str(dest)
