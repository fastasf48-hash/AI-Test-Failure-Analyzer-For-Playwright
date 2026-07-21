"""Tests the core orchestration in analyze_failure.py — against an in-memory
SQLite `Repository` and a `FakeProvider` that returns a canned result. No
network call, no real API key, no subprocess: `analyze_test_result` takes
its `Repository` and `LLMProvider` as arguments (dependency injection) rather
than reaching for global state, specifically so this is possible.
"""

import pytest
from analyze_failure import analyze_test_result
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, FailureCategory, ResultStatus, Severity
from app.database.repository import Repository
from app.llm.base_provider import LLMProvider, ProviderResponse
from app.llm.schemas import AIAnalysisResult


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, result: AIAnalysisResult) -> None:
        self._result = result
        self.calls = 0

    def analyze(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        self.calls += 1
        return ProviderResponse(
            result=self._result, raw_response=self._result.model_dump(mode="json"), model="fake-model-v1"
        )


def _fake_result(**overrides) -> AIAnalysisResult:
    defaults = {
        "root_cause": "The #login-button selector no longer exists.",
        "confidence_score": 0.85,
        "failure_category": FailureCategory.LOCATOR_CHANGED,
        "severity": Severity.HIGH,
        "suggested_fix": "Update the locator to #login-btn.",
    }
    defaults.update(overrides)
    return AIAnalysisResult(**defaults)


@pytest.fixture()
def repo():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield Repository(session)
    finally:
        session.close()


def test_analyze_test_result_persists_ai_analysis(repo):
    run = repo.create_test_run(execution_id="run-1")
    result = repo.add_test_result(
        run_id=run.id,
        test_name="tests/ui/test_x.py::test_y",
        status=ResultStatus.FAILED,
        error_message="boom",
        stack_trace="trace",
    )
    provider = FakeProvider(_fake_result())

    analysis = analyze_test_result(repo, result.id, provider)

    assert analysis is not None
    assert provider.calls == 1

    stored = repo.get_latest_ai_analysis(result.id)
    assert stored is not None
    assert stored.provider == "fake"
    assert stored.model == "fake-model-v1"
    assert stored.root_cause == "The #login-button selector no longer exists."
    assert stored.confidence_score == 0.85
    assert stored.failure_category == FailureCategory.LOCATOR_CHANGED


def test_analyze_test_result_returns_none_for_passed_test(repo):
    run = repo.create_test_run(execution_id="run-2")
    result = repo.add_test_result(run_id=run.id, test_name="t", status=ResultStatus.PASSED)
    provider = FakeProvider(_fake_result())

    analysis = analyze_test_result(repo, result.id, provider)

    assert analysis is None
    assert provider.calls == 0  # never spends a call analyzing a test that didn't fail
    assert repo.get_latest_ai_analysis(result.id) is None


def test_analyze_test_result_returns_none_for_unknown_id(repo):
    provider = FakeProvider(_fake_result())
    analysis = analyze_test_result(repo, 9999, provider)
    assert analysis is None
    assert provider.calls == 0
