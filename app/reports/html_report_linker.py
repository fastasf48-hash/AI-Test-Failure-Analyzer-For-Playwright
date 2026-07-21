"""Links a generated pytest-html report back to the TestResults it covers.

pytest-html produces one shared report file per test *session*, not one per
test, so every failed TestResult from a run points at the same file — the
dashboard's job is to offer a link into it, not to deep-link a specific row
(pytest-html's self-contained HTML doesn't expose stable per-test anchors
without extra JS wiring, which isn't worth the fragility here).
"""

from __future__ import annotations

from app.database.models import ResultStatus
from app.database.repository import Repository
from app.utilities.logger import get_logger

logger = get_logger(__name__)


def link_html_report(repo: Repository, run_id: int, report_path: str) -> int:
    """Sets `html_report_path` on every failed result of `run_id`. Returns how
    many results were linked (0 if the run doesn't exist or has no failures).
    """
    run = repo.get_test_run(run_id)
    if run is None:
        return 0

    linked = 0
    for result in run.results:
        if result.status == ResultStatus.FAILED:
            result.html_report_path = report_path
            linked += 1

    if linked:
        logger.info("Linked pytest-html report %s to %d failed result(s)", report_path, linked)
    return linked
