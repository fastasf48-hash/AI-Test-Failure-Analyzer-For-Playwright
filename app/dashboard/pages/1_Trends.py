"""Trends page: failure frequency, top failing tests, flaky tests, and
historical run data. Read-only — no LLM call anywhere on this page.
"""

import sys
from pathlib import Path

_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "requirements.txt").is_file())
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from app.database.repository import get_repository
from app.database.session import init_db

st.set_page_config(page_title="Trends — AI Test Failure Analyzer", page_icon="📈", layout="wide")
init_db()

st.title("📈 Trends")

with get_repository() as repo:
    failure_trend = repo.get_failure_trends(days=30)
    top_failing = repo.get_top_failing_tests(limit=10)
    flaky = repo.get_flaky_tests(min_runs=2)
    duration_trend = repo.get_average_duration_per_run(limit=30)
    runs = repo.list_test_runs(limit=30)

st.subheader("Failure frequency (last 30 days)")
if failure_trend:
    df = pd.DataFrame(failure_trend, columns=["day", "failures"])
    df["day"] = df["day"].astype(str)
    fig = px.bar(df, x="day", y="failures")
    # Without this, Plotly infers a continuous datetime axis for the "day"
    # column — harmless with weeks of data, but with only one or two days
    # recorded so far it auto-zooms to a sub-second tick range and the axis
    # labels become unreadable. Treating "day" as categorical fixes both cases.
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")
else:
    st.info("Not enough data yet — run your Playwright suite a few times to see trends.")

left, right = st.columns(2)

with left:
    st.subheader("Top failing tests")
    if top_failing:
        df = pd.DataFrame(top_failing, columns=["test_name", "failures"])
        fig = px.bar(df, x="failures", y="test_name", orientation="h")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No failures recorded yet.")

with right:
    st.subheader("Flaky tests")
    st.caption("Tests with both passes and failures across recorded runs.")
    if flaky:
        df = pd.DataFrame(flaky, columns=["test_name", "passes", "failures"])
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("No flaky tests detected yet.")

st.subheader("Average execution time per run")
if duration_trend:
    df = pd.DataFrame(duration_trend, columns=["execution_id", "avg_duration_seconds"])
    st.plotly_chart(
        px.line(df, x="execution_id", y="avg_duration_seconds", markers=True),
        width="stretch",
    )
else:
    st.info("No runs recorded yet.")

st.subheader("Historical runs")
if runs:
    df = pd.DataFrame(
        [
            {
                "execution_id": r.execution_id,
                "started_at": r.started_at,
                "total": r.total_tests,
                "passed": r.passed_count,
                "failed": r.failed_count,
                "failure_rate_%": round(r.failure_rate, 1),
            }
            for r in runs
        ]
    )
    st.dataframe(df, width="stretch", hide_index=True)
else:
    st.info("No runs recorded yet.")
