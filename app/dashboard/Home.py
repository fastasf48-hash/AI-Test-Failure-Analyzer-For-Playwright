"""Dashboard home page: execution summary, searchable/filterable failed-tests
list, and per-failure detail (artifacts + AI report). The only place an LLM
API call can happen on this page is the "Analyze Failure" button below —
everything else here only ever reads from the database.

Streamlit only puts the directory of the launched script (this file's own
directory) on sys.path, not the project root two levels up where the `app`
package actually lives — so this bootstrap runs before any `app.*` import.
"""

import sys
from pathlib import Path

_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "requirements.txt").is_file())
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from analyze_failure import analyze_test_result

from app.config.settings import get_settings
from app.dashboard.components import (
    render_ai_analysis_card,
    render_execution_summary,
    render_failure_artifacts,
    render_failure_metadata,
)
from app.database.models import FailureCategory
from app.database.repository import get_repository
from app.database.session import init_db
from app.llm.base_provider import LLMResponseError
from app.llm.provider_factory import MissingAPIKeyError, UnknownProviderError, get_provider

st.set_page_config(page_title="AI Test Failure Analyzer", page_icon="🧪", layout="wide")
init_db()

st.title("🧪 AI Test Failure Analyzer")
st.caption(
    "Offline by default — screenshots, video, traces, and logs are collected automatically on every "
    "test run. No API request is made anywhere in this app until you explicitly click **Analyze Failure**."
)

# --- Sidebar filters ---------------------------------------------------------------
with get_repository() as repo:
    runs = repo.list_test_runs(limit=50)

run_options: dict[str, int | None] = {"All runs": None}
for run in runs:
    run_options[f"{run.execution_id}  ({run.started_at:%Y-%m-%d %H:%M})"] = run.id

st.sidebar.header("Filters")
selected_run_label = st.sidebar.selectbox("Test run", list(run_options.keys()))
selected_run_id = run_options[selected_run_label]

search = st.sidebar.text_input("Search test name")

category_labels = ["All"] + [c.value for c in FailureCategory]
selected_category_label = st.sidebar.selectbox("Rule-based category", category_labels)
selected_category = None if selected_category_label == "All" else FailureCategory(selected_category_label)

sort_option = st.sidebar.radio("Sort by", ["Newest first", "Test name", "Duration (longest first)"])

# --- Execution summary ---------------------------------------------------------------
with get_repository() as repo:
    stats = repo.get_summary_stats()
render_execution_summary(stats)

st.divider()

# --- Failed tests ---------------------------------------------------------------------
st.subheader("Failed tests")

with get_repository() as repo:
    failures = repo.list_failures(
        search=search or None, category=selected_category, run_id=selected_run_id, limit=200
    )

    if sort_option == "Test name":
        failures = sorted(failures, key=lambda f: f.test_name)
    elif sort_option == "Duration (longest first)":
        failures = sorted(failures, key=lambda f: f.duration_seconds, reverse=True)

    if not failures:
        st.info("No failures match the current filters.")

    for failure in failures:
        category = failure.rule_based_category.value if failure.rule_based_category else "Unknown"
        analyzed_marker = " · 🤖 analyzed" if failure.latest_ai_analysis else ""
        header = f"❌ {failure.test_name}  —  {category}{analyzed_marker}"

        # `st.expander`'s `expanded=` argument only sets its *initial* state for
        # this script run — mutating session_state after the expander is
        # already created can't reopen it retroactively. So a button click
        # inside the expander sets these flags and calls `st.rerun()`
        # immediately; the *next* run reads `expanded_key` before creating the
        # expander, so it opens already-expanded, with the pending action's
        # result rendered inside it where the user can actually see it.
        expanded_key = f"expanded_{failure.id}"
        pending_key = f"pending_analysis_{failure.id}"

        with st.expander(header, expanded=st.session_state.get(expanded_key, False)):
            render_failure_metadata(failure)
            st.divider()
            render_failure_artifacts(failure)
            st.divider()

            if failure.latest_ai_analysis is not None:
                render_ai_analysis_card(failure.latest_ai_analysis)
                button_label = "🔁 Re-analyze"
            else:
                st.info("Not yet analyzed.")
                button_label = "🤖 Analyze Failure"

            if st.session_state.get(pending_key):
                st.session_state[pending_key] = False
                settings = get_settings()
                try:
                    provider = get_provider(settings)
                except MissingAPIKeyError as exc:
                    st.warning(f"{exc}\n\nNo API request was made.")
                except UnknownProviderError as exc:
                    st.error(str(exc))
                else:
                    with st.spinner(f"Calling {provider.name}..."):
                        try:
                            analyze_test_result(repo, failure.id, provider)
                        except LLMResponseError as exc:
                            st.error(f"Analysis failed: {exc}")
                        else:
                            st.success("Analysis complete.")
                            st.rerun()

            if st.button(button_label, key=f"analyze-{failure.id}"):
                st.session_state[expanded_key] = True
                st.session_state[pending_key] = True
                st.rerun()
