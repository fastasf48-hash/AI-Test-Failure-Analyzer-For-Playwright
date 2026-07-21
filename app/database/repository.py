"""Data-access layer. Every query in the project goes through `Repository` so
the pytest hooks, the CLI, and the Streamlit dashboard never write raw SQL or
manage a `Session`'s lifetime themselves.

`Repository` takes a `Session` via its constructor (dependency injection)
instead of importing a global engine — that's what lets the unit tests in
`tests/test_database.py` point it at an in-memory SQLite engine with zero
mocking.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database.models import AIAnalysis, FailureCategory, ResultStatus, TestResult, TestRun, utc_now
from app.database.session import session_scope


class Repository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- Test runs --------------------------------------------------------------------
    def create_test_run(
        self,
        *,
        execution_id: str,
        os_name: str | None = None,
        browser_name: str | None = None,
        browser_version: str | None = None,
        git_branch: str | None = None,
        git_commit: str | None = None,
    ) -> TestRun:
        run = TestRun(
            execution_id=execution_id,
            os_name=os_name,
            browser_name=browser_name,
            browser_version=browser_version,
            git_branch=git_branch,
            git_commit=git_commit,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def finish_test_run(self, run: TestRun) -> None:
        """Recomputes counts from the results already attached to `run` and stamps
        `finished_at`. Called once, after the pytest session that populated `run`
        has collected every result.
        """
        counts = {status: 0 for status in ResultStatus}
        for result in run.results:
            counts[result.status] += 1

        run.total_tests = len(run.results)
        run.passed_count = counts[ResultStatus.PASSED]
        run.failed_count = counts[ResultStatus.FAILED]
        run.skipped_count = counts[ResultStatus.SKIPPED]
        run.finished_at = utc_now()
        self._session.flush()

    def get_test_run(self, run_id: int) -> TestRun | None:
        return self._session.get(TestRun, run_id)

    def list_test_runs(self, limit: int = 50) -> Sequence[TestRun]:
        stmt = select(TestRun).order_by(TestRun.started_at.desc()).limit(limit)
        return self._session.scalars(stmt).all()

    def get_latest_test_run(self) -> TestRun | None:
        stmt = select(TestRun).order_by(TestRun.started_at.desc()).limit(1)
        return self._session.scalars(stmt).first()

    # --- Test results -------------------------------------------------------------------
    def add_test_result(self, *, run_id: int, test_name: str, status: ResultStatus, **fields) -> TestResult:
        result = TestResult(run_id=run_id, test_name=test_name, status=status, **fields)
        self._session.add(result)
        self._session.flush()
        return result

    def get_test_result(self, result_id: int) -> TestResult | None:
        return self._session.get(TestResult, result_id)

    def list_failures(
        self,
        *,
        search: str | None = None,
        category: FailureCategory | None = None,
        run_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[TestResult]:
        stmt = select(TestResult).where(TestResult.status == ResultStatus.FAILED)
        if run_id is not None:
            stmt = stmt.where(TestResult.run_id == run_id)
        if category is not None:
            stmt = stmt.where(TestResult.rule_based_category == category)
        if search:
            stmt = stmt.where(TestResult.test_name.ilike(f"%{search}%"))
        stmt = stmt.order_by(TestResult.timestamp.desc()).limit(limit).offset(offset)
        return self._session.scalars(stmt).all()

    # --- AI analyses -----------------------------------------------------------------------
    def add_ai_analysis(self, *, test_result_id: int, provider: str, model: str, **fields) -> AIAnalysis:
        analysis = AIAnalysis(test_result_id=test_result_id, provider=provider, model=model, **fields)
        self._session.add(analysis)
        self._session.flush()
        return analysis

    def get_latest_ai_analysis(self, test_result_id: int) -> AIAnalysis | None:
        stmt = (
            select(AIAnalysis)
            .where(AIAnalysis.test_result_id == test_result_id)
            .order_by(AIAnalysis.created_at.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    # --- Aggregates for the dashboard (Phase 5) -----------------------------------------------
    @dataclass
    class SummaryStats:
        total_tests: int
        passed: int
        failed: int
        failure_rate: float
        avg_duration_seconds: float
        latest_run: TestRun | None

    def get_summary_stats(self) -> Repository.SummaryStats:
        total = self._session.scalar(select(func.count(TestResult.id))) or 0
        passed = (
            self._session.scalar(
                select(func.count(TestResult.id)).where(TestResult.status == ResultStatus.PASSED)
            )
            or 0
        )
        failed = (
            self._session.scalar(
                select(func.count(TestResult.id)).where(TestResult.status == ResultStatus.FAILED)
            )
            or 0
        )
        avg_duration = self._session.scalar(select(func.avg(TestResult.duration_seconds))) or 0.0
        failure_rate = (failed / total * 100) if total else 0.0

        return Repository.SummaryStats(
            total_tests=total,
            passed=passed,
            failed=failed,
            failure_rate=round(failure_rate, 2),
            avg_duration_seconds=round(avg_duration, 3),
            latest_run=self.get_latest_test_run(),
        )

    def get_failure_trends(self, days: int = 14) -> Sequence[tuple[str, int]]:
        """Failures per day for the last `days` days. Assumes SQLite's `date()`
        function (documented trade-off if the project ever moves to Postgres:
        swap for `func.date_trunc`).
        """
        since = utc_now() - timedelta(days=days)
        stmt = (
            select(func.date(TestResult.timestamp), func.count(TestResult.id))
            .where(TestResult.status == ResultStatus.FAILED, TestResult.timestamp >= since)
            .group_by(func.date(TestResult.timestamp))
            .order_by(func.date(TestResult.timestamp))
        )
        return self._session.execute(stmt).all()

    def get_top_failing_tests(self, limit: int = 10) -> Sequence[tuple[str, int]]:
        stmt = (
            select(TestResult.test_name, func.count(TestResult.id).label("failures"))
            .where(TestResult.status == ResultStatus.FAILED)
            .group_by(TestResult.test_name)
            .order_by(func.count(TestResult.id).desc())
            .limit(limit)
        )
        return self._session.execute(stmt).all()

    def get_flaky_tests(self, min_runs: int = 3) -> Sequence[tuple[str, int, int]]:
        """A test is 'flaky' here if it has *both* passes and failures across all
        runs recorded so far — the textbook operational definition.
        """
        stmt = (
            select(
                TestResult.test_name,
                func.sum(case((TestResult.status == ResultStatus.PASSED, 1), else_=0)).label("passes"),
                func.sum(case((TestResult.status == ResultStatus.FAILED, 1), else_=0)).label("failures"),
            )
            .group_by(TestResult.test_name)
            .having(func.count(TestResult.id) >= min_runs)
        )
        rows = self._session.execute(stmt).all()
        return [(name, passes, failures) for name, passes, failures in rows if passes > 0 and failures > 0]

    def get_average_duration_per_run(self, limit: int = 30) -> Sequence[tuple[str, float]]:
        """Average test duration per run, most recent `limit` runs, returned in
        chronological order (oldest first) so it plots as a left-to-right trend.
        """
        stmt = (
            select(TestRun.execution_id, func.avg(TestResult.duration_seconds))
            .join(TestResult, TestResult.run_id == TestRun.id)
            .group_by(TestRun.id)
            .order_by(TestRun.started_at.desc())
            .limit(limit)
        )
        rows = self._session.execute(stmt).all()
        return list(reversed(rows))


@contextmanager
def get_repository() -> Iterator[Repository]:
    """Convenience for callers that just want one unit of work:

    with get_repository() as repo:
        repo.create_test_run(...)
    """
    with session_scope() as session:
        yield Repository(session)
