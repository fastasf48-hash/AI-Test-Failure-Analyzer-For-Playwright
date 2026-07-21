"""Thin wrapper around the Allure commandline tool.

The `allure-pytest` plugin (a normal pip dependency) writes raw result JSON
into `allure-results/` during a `pytest --alluredir=allure-results` run —
that part needs nothing extra. Turning those results into the interactive
`allure-report/` HTML site requires the separate Allure commandline, a
Java-based tool `pip install` cannot provide. This wrapper shells out to it
and degrades gracefully — a clear, actionable log message rather than a
stack trace — when it isn't installed, since that's an expected, common
state (a fresh clone won't have it), not an error.

Used identically by local dev and by CI (see .github/workflows/ci.yml) —
one code path, not a shell script that quietly does something different in
each place.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.utilities.logger import get_logger

logger = get_logger(__name__)


def generate_allure_report(results_dir: Path, output_dir: Path) -> bool:
    if shutil.which("allure") is None:
        logger.warning(
            "Allure commandline not found on PATH; skipping HTML report generation. "
            "Install it via `npm install -g allure-commandline` or see "
            "https://allurereport.org/docs/install/ for other options."
        )
        return False

    try:
        subprocess.run(
            ["allure", "generate", str(results_dir), "-o", str(output_dir), "--clean"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            # npm installs `allure` as a `.cmd` shim on Windows, which CreateProcess
            # can't execute directly without going through a shell — POSIX's real
            # `allure` script/binary runs fine either way, so this only changes
            # behavior on the platform that actually needs it.
            shell=(os.name == "nt"),
        )
    except subprocess.CalledProcessError as exc:
        logger.error("Allure report generation failed: %s", exc.stderr)
        return False
    except subprocess.SubprocessError as exc:
        logger.error("Allure report generation failed: %s", exc)
        return False

    logger.info("Allure report generated at %s", output_dir)
    return True
