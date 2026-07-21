"""Rendering helpers for the Streamlit dashboard. Plain functions that call
`st.*` directly — Streamlit has no component/class model of its own, so
there's nothing to gain from wrapping these in objects; a function per
section (metadata, artifacts, AI card) is the SRP-equivalent here.

None of these functions ever call an LLM. The only LLM call site in the
whole dashboard is the "Analyze Failure" button in Home.py, and it calls the
exact same `analyze_test_result()` used by analyze_failure.py — the CLI and
the dashboard share one code path, not two.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.database.models import AIAnalysis, TestResult


def render_execution_summary(stats) -> None:
    cols = st.columns(6)
    cols[0].metric("Total tests", stats.total_tests)
    cols[1].metric("Passed", stats.passed)
    cols[2].metric("Failed", stats.failed)
    cols[3].metric("Failure %", f"{stats.failure_rate:.1f}%")
    cols[4].metric("Avg duration", f"{stats.avg_duration_seconds:.2f}s")
    cols[5].metric("Latest run", stats.latest_run.execution_id if stats.latest_run else "—")


def render_failure_metadata(failure: TestResult) -> None:
    cols = st.columns(4)
    cols[0].markdown(f"**Status**\n\n{failure.status.value}")
    cols[1].markdown(f"**Duration**\n\n{failure.duration_seconds:.2f}s")
    category = failure.rule_based_category.value if failure.rule_based_category else "—"
    cols[2].markdown(f"**Rule-based category**\n\n{category}")
    cols[3].markdown(f"**Timestamp**\n\n{failure.timestamp:%Y-%m-%d %H:%M:%S}")
    st.markdown(f"**Error message**\n\n{failure.error_message or '(none captured)'}")


def render_failure_artifacts(failure: TestResult) -> None:
    media_cols = st.columns(2)
    with media_cols[0]:
        if failure.screenshot_path and Path(failure.screenshot_path).is_file():
            st.image(failure.screenshot_path, caption="Screenshot", width="stretch")
        else:
            st.caption("No screenshot captured.")
    with media_cols[1]:
        if failure.video_path and Path(failure.video_path).is_file():
            st.video(failure.video_path)
        else:
            st.caption("No video captured.")

    if failure.trace_path and Path(failure.trace_path).is_file():
        st.download_button(
            "⬇️ Download trace.zip  (open with `playwright show-trace trace.zip`)",
            data=Path(failure.trace_path).read_bytes(),
            file_name="trace.zip",
            key=f"trace-{failure.id}",
        )

    log_cols = st.columns(2)
    with log_cols[0]:
        if failure.console_log_path and Path(failure.console_log_path).is_file():
            with st.expander("Console log"):
                st.code(Path(failure.console_log_path).read_text(encoding="utf-8"), language="text")
    with log_cols[1]:
        if failure.network_log_path and Path(failure.network_log_path).is_file():
            with st.expander("Network log"):
                st.code(Path(failure.network_log_path).read_text(encoding="utf-8"), language="text")

    with st.expander("Full stack trace"):
        st.code(failure.stack_trace or "(none captured)", language="text")

    if failure.html_report_path:
        st.caption(f"📄 Also in the pytest-html report: `{failure.html_report_path}`")


def render_ai_analysis_card(analysis: AIAnalysis) -> None:
    st.markdown("#### 🤖 AI Analysis")

    badge_cols = st.columns(4)
    badge_cols[0].metric("Confidence", f"{analysis.confidence_score:.0%}")
    badge_cols[1].markdown(f"**Severity**\n\n{analysis.severity.value}")
    badge_cols[2].markdown(f"**Failure category**\n\n{analysis.failure_category.value}")
    badge_cols[3].markdown(f"**Model**\n\n{analysis.provider} / {analysis.model}")

    st.markdown(f"**Root cause**\n\n{analysis.root_cause}")
    st.markdown(f"**Recommended fix**\n\n{analysis.suggested_fix}")

    if analysis.alternative_fixes:
        with st.expander("Alternative fixes"):
            for fix in analysis.alternative_fixes:
                st.markdown(f"- {fix}")

    if analysis.possible_developer_issue:
        st.warning(f"**Possible application bug:** {analysis.possible_developer_issue}")
    if analysis.possible_automation_issue:
        st.info(f"**Possible automation issue:** {analysis.possible_automation_issue}")

    if analysis.improved_locator:
        st.markdown("**Improved locator**")
        st.code(analysis.improved_locator, language="python")

    if analysis.example_code:
        st.markdown("**Example code**")
        st.code(analysis.example_code, language="python")

    if analysis.relevant_documentation:
        st.markdown("**Playwright documentation**")
        for url in analysis.relevant_documentation:
            st.markdown(f"- [{url}]({url})")

    st.caption(f"Analyzed {analysis.created_at:%Y-%m-%d %H:%M:%S} UTC")
