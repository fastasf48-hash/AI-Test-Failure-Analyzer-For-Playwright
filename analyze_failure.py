#!/usr/bin/env python
"""Manual CLI entrypoint for AI failure analysis.

This script — together with the dashboard's "Analyze Failure" button
(Phase 5) — is the ONLY place in this entire project that ever calls an
LLM API. Nothing runs automatically: no test failure, dashboard page load,
or CI run triggers an API request on its own. You only spend a token by
running this script or clicking that button.

Usage:
    python analyze_failure.py --list          # list recent failures, no API call
    python analyze_failure.py --latest         # analyze the most recent failure
    python analyze_failure.py --id 42          # analyze a specific failure by id
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.analyzers.test_source_locator import find_test_source
from app.config.settings import get_settings
from app.database.models import ResultStatus, TestResult
from app.database.repository import Repository, get_repository
from app.database.session import init_db
from app.llm.base_provider import LLMProvider, LLMResponseError
from app.llm.prompts import SYSTEM_PROMPT, AnalysisContext, build_user_prompt
from app.llm.provider_factory import MissingAPIKeyError, UnknownProviderError, get_provider
from app.llm.schemas import AIAnalysisResult
from app.utilities.logger import get_logger

logger = get_logger(__name__)

MAX_ARTIFACT_CHARS = 5000


def _read_capped(path: str | None) -> str | None:
    """Reads a log artifact, capped to keep prompt size (and cost) bounded."""
    if not path:
        return None
    file_path = Path(path)
    if not file_path.is_file():
        return None
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if len(text) > MAX_ARTIFACT_CHARS:
        text = text[:MAX_ARTIFACT_CHARS] + "\n... (truncated)"
    return text


def _build_context(result: TestResult) -> AnalysisContext:
    return AnalysisContext(
        test_name=result.test_name,
        status=result.status.value,
        duration_seconds=result.duration_seconds,
        error_message=result.error_message or "",
        stack_trace=result.stack_trace or "",
        rule_based_category=(result.rule_based_category.value if result.rule_based_category else None),
        console_log=_read_capped(result.console_log_path),
        network_log=_read_capped(result.network_log_path),
        test_source=find_test_source(result.test_file, result.test_name),
    )


def analyze_test_result(repo: Repository, result_id: int, provider: LLMProvider) -> AIAnalysisResult | None:
    """Core orchestration: fetch, build the prompt, call the provider, persist.

    Takes an explicit `Repository` and `LLMProvider` (dependency injection,
    same pattern as the rest of the project) rather than reaching for global
    state — that's what lets tests/test_analyze_failure.py exercise this
    against an in-memory database and a fake provider, with zero mocking and
    zero real API calls.

    Returns `None` (rather than raising) when there is simply nothing to
    analyze — an unknown id or a non-failed result — leaving the CLI-facing
    caller responsible for the user-facing message in that case.
    """
    result = repo.get_test_result(result_id)
    if result is None or result.status != ResultStatus.FAILED:
        return None

    ctx = _build_context(result)
    user_prompt = build_user_prompt(ctx)
    response = provider.analyze(SYSTEM_PROMPT, user_prompt)

    repo.add_ai_analysis(
        test_result_id=result_id,
        provider=provider.name,
        model=response.model,
        root_cause=response.result.root_cause,
        confidence_score=response.result.confidence_score,
        failure_category=response.result.failure_category,
        severity=response.result.severity,
        suggested_fix=response.result.suggested_fix,
        alternative_fixes=response.result.alternative_fixes,
        possible_developer_issue=response.result.possible_developer_issue,
        possible_automation_issue=response.result.possible_automation_issue,
        relevant_documentation=response.result.relevant_documentation,
        improved_locator=response.result.improved_locator,
        example_code=response.result.example_code,
        raw_response=response.raw_response,
    )
    return response.result


def _print_recent_failures(limit: int = 20) -> None:
    with get_repository() as repo:
        failures = repo.list_failures(limit=limit)
        if not failures:
            print("No failures recorded yet. Run your Playwright suite first (see README).")
            return
        print(f"{'ID':>5}  {'Category':<22} Test")
        print("-" * 90)
        for f in failures:
            category = f.rule_based_category.value if f.rule_based_category else "-"
            has_analysis = " [analyzed]" if f.latest_ai_analysis else ""
            print(f"{f.id:>5}  {category:<22} {f.test_name}{has_analysis}")


def _print_report(result: AIAnalysisResult) -> None:
    print("=" * 88)
    print(f"Root cause    : {result.root_cause}")
    print(f"Confidence    : {result.confidence_score:.0%}")
    print(f"Category      : {result.failure_category.value}")
    print(f"Severity      : {result.severity.value}")
    print(f"Suggested fix : {result.suggested_fix}")
    if result.alternative_fixes:
        print("Alternative fixes:")
        for fix in result.alternative_fixes:
            print(f"  - {fix}")
    if result.possible_developer_issue:
        print(f"Possible application bug : {result.possible_developer_issue}")
    if result.possible_automation_issue:
        print(f"Possible automation issue: {result.possible_automation_issue}")
    if result.improved_locator:
        print(f"Improved locator: {result.improved_locator}")
    if result.example_code:
        print("Example code:")
        print(result.example_code)
    if result.relevant_documentation:
        print("Relevant documentation:")
        for url in result.relevant_documentation:
            print(f"  - {url}")
    print("=" * 88)


def _run_analysis(result_id: int) -> int:
    settings = get_settings()

    try:
        provider = get_provider(settings)
    except MissingAPIKeyError as exc:
        print(f"\n{exc}\n\nSee .env.example for how to configure a key. No API request was made.")
        return 1
    except UnknownProviderError as exc:
        print(f"\n{exc}")
        return 1

    with get_repository() as repo:
        result = repo.get_test_result(result_id)
        if result is None:
            print(f"No test result with id {result_id}. Run with --list to see available ids.")
            return 1
        if result.status != ResultStatus.FAILED:
            print(f"Test result {result_id} is '{result.status.value}', not failed — nothing to analyze.")
            return 1

        print(f"Analyzing failure #{result_id}: {result.test_name}")
        print(f"Using provider: {provider.name}\n")

        try:
            analysis = analyze_test_result(repo, result_id, provider)
        except LLMResponseError as exc:
            print(f"Analysis failed: {exc}")
            return 1

    if analysis is None:
        print("Nothing to analyze.")
        return 1

    _print_report(analysis)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manually trigger AI analysis of a recorded Playwright test failure. "
        "This is the only way (besides the dashboard's Analyze Failure button) this project "
        "ever calls an LLM API — nothing runs automatically."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="List recent failures (no API call).")
    group.add_argument("--latest", action="store_true", help="Analyze the most recent failure.")
    group.add_argument("--id", type=int, help="Analyze the failure with this id.")
    args = parser.parse_args()

    init_db()

    if args.id is not None:
        return _run_analysis(args.id)

    if args.latest:
        with get_repository() as repo:
            failures = repo.list_failures(limit=1)
        if not failures:
            print("No failures recorded yet. Run your Playwright suite first (see README).")
            return 1
        return _run_analysis(failures[0].id)

    _print_recent_failures()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
