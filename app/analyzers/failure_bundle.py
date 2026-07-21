"""Assembles collector output + rule-based classification into one bundle
ready to hand straight to `Repository.add_test_result(**bundle.as_result_fields())`.

This is the one place that knows about every collector *and* the database
field names — fixtures.py doesn't need to know either; it just builds a
`FailureContext` and a list of collectors to run.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analyzers.category_classifier import classify
from app.collectors.base_collector import ArtifactCollector, FailureContext
from app.database.models import FailureCategory
from app.utilities.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FailureBundle:
    error_message: str
    stack_trace: str
    rule_based_category: FailureCategory
    screenshot_path: str | None = None
    video_path: str | None = None
    trace_path: str | None = None
    console_log_path: str | None = None
    network_log_path: str | None = None

    def as_result_fields(self) -> dict:
        """Kwargs matching `TestResult` columns, for `Repository.add_test_result`."""
        return {
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "rule_based_category": self.rule_based_category,
            "screenshot_path": self.screenshot_path,
            "video_path": self.video_path,
            "trace_path": self.trace_path,
            "console_log_path": self.console_log_path,
            "network_log_path": self.network_log_path,
        }


def build_failure_bundle(
    ctx: FailureContext,
    collectors: dict[str, ArtifactCollector],
    pre_collected: dict[str, str | None] | None = None,
) -> FailureBundle:
    """Runs every collector in `collectors` (keyed by the FailureBundle field it
    fills, e.g. "screenshot_path") against `ctx`, and merges in `pre_collected`
    — results from collectors the caller already had to run earlier (e.g.
    screenshot/trace, which must run before `context.close()`; see
    app/playwright/fixtures.py for why). One collector failing is logged and
    treated as `None` — it never aborts the others.
    """
    ctx.artifacts_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str | None] = dict(pre_collected or {})
    for field_name, collector in collectors.items():
        try:
            paths[field_name] = collector.collect(ctx)
        except Exception as exc:  # belt-and-suspenders: collectors already guard themselves
            logger.warning("%s raised while collecting %s: %s", type(collector).__name__, field_name, exc)
            paths[field_name] = None

    return FailureBundle(
        error_message=ctx.error_message,
        stack_trace=ctx.traceback_text,
        rule_based_category=classify(ctx.error_message, ctx.traceback_text),
        **paths,
    )
