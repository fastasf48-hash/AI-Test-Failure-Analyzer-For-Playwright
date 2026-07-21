"""Unit tests for the repository layer, against a real in-memory SQLite engine
(not a mock) — `Repository` takes a `Session` directly, so no monkeypatching
of the app's global engine is needed to isolate these from `data/analyzer.db`.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, FailureCategory, ResultStatus, Severity
from app.database.repository import Repository


@pytest.fixture()
def repo():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield Repository(session)
    finally:
        session.close()


def test_create_run_and_result_tracks_counts(repo):
    run = repo.create_test_run(execution_id="run-1", os_name="Windows", browser_name="chromium")
    repo.add_test_result(
        run_id=run.id,
        test_name="test_login",
        status=ResultStatus.FAILED,
        duration_seconds=1.2,
        rule_based_category=FailureCategory.TIMEOUT,
    )
    repo.add_test_result(run_id=run.id, test_name="test_logout", status=ResultStatus.PASSED, duration_seconds=0.5)
    repo.finish_test_run(run)

    assert run.total_tests == 2
    assert run.passed_count == 1
    assert run.failed_count == 1
    assert run.failure_rate == 50.0


def test_list_failures_filters_by_search_and_category(repo):
    run = repo.create_test_run(execution_id="run-2")
    repo.add_test_result(
        run_id=run.id,
        test_name="test_checkout_timeout",
        status=ResultStatus.FAILED,
        rule_based_category=FailureCategory.TIMEOUT,
    )
    repo.add_test_result(
        run_id=run.id,
        test_name="test_login_locator",
        status=ResultStatus.FAILED,
        rule_based_category=FailureCategory.LOCATOR_CHANGED,
    )

    timeouts = repo.list_failures(category=FailureCategory.TIMEOUT)
    assert [f.test_name for f in timeouts] == ["test_checkout_timeout"]

    searched = repo.list_failures(search="login")
    assert [f.test_name for f in searched] == ["test_login_locator"]


def test_ai_analysis_latest_returns_most_recent(repo):
    run = repo.create_test_run(execution_id="run-3")
    result = repo.add_test_result(run_id=run.id, test_name="test_flaky", status=ResultStatus.FAILED)

    repo.add_ai_analysis(
        test_result_id=result.id,
        provider="openai",
        model="gpt-4o-mini",
        root_cause="First guess",
        confidence_score=0.4,
        failure_category=FailureCategory.UNKNOWN,
        severity=Severity.LOW,
        suggested_fix="Try again",
    )
    second = repo.add_ai_analysis(
        test_result_id=result.id,
        provider="openai",
        model="gpt-4o-mini",
        root_cause="Better guess",
        confidence_score=0.9,
        failure_category=FailureCategory.TIMEOUT,
        severity=Severity.MEDIUM,
        suggested_fix="Increase timeout",
    )

    latest = repo.get_latest_ai_analysis(result.id)
    assert latest.id == second.id
    assert latest.root_cause == "Better guess"
    assert result.latest_ai_analysis.id == second.id


def test_summary_stats_computes_failure_rate(repo):
    run = repo.create_test_run(execution_id="run-4")
    repo.add_test_result(run_id=run.id, test_name="a", status=ResultStatus.PASSED)
    repo.add_test_result(run_id=run.id, test_name="b", status=ResultStatus.PASSED)
    repo.add_test_result(run_id=run.id, test_name="c", status=ResultStatus.FAILED)

    stats = repo.get_summary_stats()
    assert stats.total_tests == 3
    assert stats.failed == 1
    assert stats.failure_rate == pytest.approx(33.33, rel=1e-2)


def test_flaky_tests_requires_both_pass_and_fail(repo):
    run = repo.create_test_run(execution_id="run-5")
    for status in (ResultStatus.PASSED, ResultStatus.FAILED, ResultStatus.PASSED):
        repo.add_test_result(run_id=run.id, test_name="test_intermittent", status=status)
    for _ in range(3):
        repo.add_test_result(run_id=run.id, test_name="test_always_fails", status=ResultStatus.FAILED)

    flaky = {name for name, _passes, _failures in repo.get_flaky_tests(min_runs=3)}
    assert flaky == {"test_intermittent"}


def test_trends_and_top_failing_tests_use_tz_aware_comparison(repo):
    """Regression check: `timestamp`/`created_at` are stored via the tz-aware
    `utc_now()` default (see app/database/models.py), so `get_failure_trends`'s
    `since = utc_now() - timedelta(...)` comparison must not silently exclude
    every row against SQLite.
    """
    run = repo.create_test_run(execution_id="run-6")
    repo.add_test_result(run_id=run.id, test_name="test_a", status=ResultStatus.FAILED)
    repo.add_test_result(run_id=run.id, test_name="test_a", status=ResultStatus.FAILED)
    repo.add_test_result(run_id=run.id, test_name="test_b", status=ResultStatus.FAILED)

    trends = repo.get_failure_trends(days=1)
    assert sum(count for _day, count in trends) == 3

    top = repo.get_top_failing_tests(limit=1)
    assert top[0] == ("test_a", 2)
