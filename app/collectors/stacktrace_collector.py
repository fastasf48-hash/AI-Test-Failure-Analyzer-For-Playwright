"""Writes the pytest failure traceback to disk.

The full text is already stored directly in `TestResult.stack_trace` by the
orchestrator (see app/analyzers/failure_bundle.py) — this collector exists
so the trace is also available as a plain-text artifact alongside the
screenshot/video/trace.zip, consistent with every other artifact type, and
so the AI prompt (Phase 4) can be pointed at a file rather than a DB row.
"""

from __future__ import annotations

from app.collectors.base_collector import ArtifactCollector, FailureContext


class StacktraceCollector(ArtifactCollector):
    def collect(self, ctx: FailureContext) -> str | None:
        if not ctx.traceback_text:
            return None

        dest = ctx.artifacts_dir / "stacktrace.txt"
        dest.write_text(ctx.traceback_text, encoding="utf-8")
        return str(dest)
