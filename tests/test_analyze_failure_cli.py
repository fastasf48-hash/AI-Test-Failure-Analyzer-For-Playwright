"""Exercises analyze_failure.py exactly as a user would run it: as a
subprocess, with an isolated temp SQLite database. This is what actually
proves the "no API request without explicit action" and "graceful missing
key" requirements end to end — a subprocess is a fresh Python process, so
there's no risk of the real `.env`/API keys on this machine being used, and
no risk of polluting the developer's real data/analyzer.db.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT = PROJECT_ROOT / "analyze_failure.py"


def _env(tmp_path: Path, **overrides) -> dict:
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}",
            "ARTIFACTS_DIR": str(tmp_path / "artifacts"),
            "LOG_DIR": str(tmp_path / "logs"),
            "OPENAI_API_KEY": "",
            "CLAUDE_API_KEY": "",
            "LLM_PROVIDER": "openai",
        }
    )
    env.update(overrides)
    return env


def _run(args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _seed_one_failure(env: dict) -> int:
    seed_code = (
        "from app.database.session import init_db\n"
        "from app.database.repository import get_repository\n"
        "from app.database.models import ResultStatus, FailureCategory\n"
        "init_db()\n"
        "with get_repository() as repo:\n"
        "    run = repo.create_test_run(execution_id='seed-run')\n"
        "    result = repo.add_test_result(\n"
        "        run_id=run.id, test_name='tests/ui/test_x.py::test_y',\n"
        "        status=ResultStatus.FAILED, error_message='boom', stack_trace='trace',\n"
        "        rule_based_category=FailureCategory.ASSERTION_FAILURE,\n"
        "    )\n"
        "    print(result.id)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", seed_code],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return int(proc.stdout.strip().splitlines()[-1])


def test_list_with_no_failures_shows_friendly_message_and_exits_zero(tmp_path):
    result = _run(["--list"], _env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "No failures recorded yet" in result.stdout


def test_list_shows_seeded_failure(tmp_path):
    env = _env(tmp_path)
    failure_id = _seed_one_failure(env)

    result = _run(["--list"], env)

    assert result.returncode == 0, result.stderr
    assert str(failure_id) in result.stdout
    assert "tests/ui/test_x.py::test_y" in result.stdout
    assert "Assertion Failure" in result.stdout


def test_analyze_without_api_key_shows_friendly_message_and_exits_nonzero(tmp_path):
    env = _env(tmp_path)
    failure_id = _seed_one_failure(env)

    result = _run(["--id", str(failure_id)], env)

    assert result.returncode == 1
    assert "No API key configured" in result.stdout
    assert "OPENAI_API_KEY" in result.stdout


def test_analyze_unknown_id_shows_friendly_message(tmp_path):
    env = _env(tmp_path, OPENAI_API_KEY="sk-fake-key-present-so-we-get-past-the-key-check")

    result = _run(["--id", "9999"], env)

    assert result.returncode == 1
    assert "No test result with id 9999" in result.stdout
