"""Best-effort git metadata for a TestRun. Never raises — a shallow CI clone,
a missing git binary, or running outside a repo should degrade to `None`,
not crash the test session.
"""

from __future__ import annotations

import subprocess

from app.utilities.logger import get_logger

logger = get_logger(__name__)


def _run_git(*args: str) -> str | None:
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5, check=True)
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git %s failed: %s", " ".join(args), exc)
        return None


def get_git_branch() -> str | None:
    return _run_git("rev-parse", "--abbrev-ref", "HEAD")


def get_git_commit() -> str | None:
    return _run_git("rev-parse", "--short", "HEAD")
