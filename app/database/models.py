"""SQLAlchemy 2.0 declarative models.

Three tables, one clear responsibility each:

- `TestRun`     — one row per pytest session.
- `TestResult`  — one row per test within that session (pass/fail/skip + artifacts).
- `AIAnalysis`  — one row per AI analysis *invocation* against a TestResult.

`AIAnalysis` is intentionally many-to-one against `TestResult` rather than a
flat set of nullable columns on it: LLM output isn't deterministic, and a user
re-running "Analyze Failure" for a second opinion should keep history instead
of overwriting it. `TestResult.latest_ai_analysis` gives callers the common
case without them needing to know about the history.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import JSON, Float, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Timezone-aware replacement for the deprecated `datetime.utcnow()`."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ResultStatus(enum.StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BROKEN = "broken"


class FailureCategory(enum.StrEnum):
    """Mirrors the categories called out in the project spec. `UNKNOWN` is the
    safe fallback both the rule-based classifier and the LLM prompt can use
    instead of forcing a guess.
    """

    LOCATOR_CHANGED = "Locator Changed"
    TIMEOUT = "Timeout"
    ASSERTION_FAILURE = "Assertion Failure"
    API_FAILURE = "API Failure"
    AUTHENTICATION_FAILURE = "Authentication Failure"
    NETWORK_FAILURE = "Network Failure"
    ENVIRONMENT_ISSUE = "Environment Issue"
    DATABASE_FAILURE = "Database Failure"
    JAVASCRIPT_EXCEPTION = "JavaScript Exception"
    FLAKY_TEST = "Flaky Test"
    SLOW_BACKEND = "Slow Backend"
    ELEMENT_HIDDEN = "Element Hidden"
    INCORRECT_WAIT_STRATEGY = "Incorrect Wait Strategy"
    INCORRECT_ASSERTION = "Incorrect Assertion"
    TEST_DATA_ISSUE = "Test Data Issue"
    UNKNOWN = "Unknown"


class Severity(enum.StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    total_tests: Mapped[int] = mapped_column(default=0)
    passed_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)
    skipped_count: Mapped[int] = mapped_column(default=0)

    os_name: Mapped[str | None] = mapped_column(String(64), default=None)
    browser_name: Mapped[str | None] = mapped_column(String(32), default=None)
    browser_version: Mapped[str | None] = mapped_column(String(32), default=None)
    git_branch: Mapped[str | None] = mapped_column(String(128), default=None)
    git_commit: Mapped[str | None] = mapped_column(String(64), default=None)

    results: Mapped[list[TestResult]] = relationship(back_populates="run", cascade="all, delete-orphan")

    @property
    def failure_rate(self) -> float:
        return (self.failed_count / self.total_tests * 100) if self.total_tests else 0.0


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"))

    test_name: Mapped[str] = mapped_column(String(255), index=True)
    test_file: Mapped[str | None] = mapped_column(String(512), default=None)
    status: Mapped[ResultStatus] = mapped_column(SAEnum(ResultStatus))
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(default=utc_now)

    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    stack_trace: Mapped[str | None] = mapped_column(Text, default=None)

    screenshot_path: Mapped[str | None] = mapped_column(String(1024), default=None)
    video_path: Mapped[str | None] = mapped_column(String(1024), default=None)
    trace_path: Mapped[str | None] = mapped_column(String(1024), default=None)
    html_report_path: Mapped[str | None] = mapped_column(String(1024), default=None)
    console_log_path: Mapped[str | None] = mapped_column(String(1024), default=None)
    network_log_path: Mapped[str | None] = mapped_column(String(1024), default=None)

    # Cheap, deterministic, pre-AI guess (see app/analyzers/category_classifier.py in Phase 3/4).
    # Lets the dashboard show *something* useful for every failure with zero API cost.
    rule_based_category: Mapped[FailureCategory | None] = mapped_column(SAEnum(FailureCategory), default=None)

    run: Mapped[TestRun] = relationship(back_populates="results")
    ai_analyses: Mapped[list[AIAnalysis]] = relationship(
        back_populates="test_result",
        cascade="all, delete-orphan",
        order_by="AIAnalysis.created_at.desc()",
    )

    @property
    def latest_ai_analysis(self) -> AIAnalysis | None:
        return self.ai_analyses[0] if self.ai_analyses else None


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_result_id: Mapped[int] = mapped_column(ForeignKey("test_results.id"))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))

    root_cause: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(Float)
    failure_category: Mapped[FailureCategory] = mapped_column(SAEnum(FailureCategory))
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity))

    suggested_fix: Mapped[str] = mapped_column(Text)
    alternative_fixes: Mapped[list | None] = mapped_column(JSON, default=None)
    possible_developer_issue: Mapped[str | None] = mapped_column(Text, default=None)
    possible_automation_issue: Mapped[str | None] = mapped_column(Text, default=None)
    relevant_documentation: Mapped[list | None] = mapped_column(JSON, default=None)
    improved_locator: Mapped[str | None] = mapped_column(Text, default=None)
    example_code: Mapped[str | None] = mapped_column(Text, default=None)

    # Full raw JSON returned by the LLM, kept for audit/debugging even though every
    # field above is already extracted — cheap insurance if the schema evolves.
    raw_response: Mapped[dict | None] = mapped_column(JSON, default=None)

    test_result: Mapped[TestResult] = relationship(back_populates="ai_analyses")
