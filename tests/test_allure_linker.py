"""Tests the graceful-degradation paths — no real Allure installation or
subprocess execution required.
"""

import subprocess

from app.reports import allure_linker


def test_returns_false_when_allure_not_on_path(monkeypatch, tmp_path):
    monkeypatch.setattr(allure_linker.shutil, "which", lambda _name: None)

    result = allure_linker.generate_allure_report(tmp_path / "allure-results", tmp_path / "allure-report")

    assert result is False


def test_returns_false_when_allure_command_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(allure_linker.shutil, "which", lambda _name: "/usr/bin/allure")

    def _raise(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0], stderr="boom")

    monkeypatch.setattr(allure_linker.subprocess, "run", _raise)

    result = allure_linker.generate_allure_report(tmp_path / "allure-results", tmp_path / "allure-report")

    assert result is False


def test_returns_true_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(allure_linker.shutil, "which", lambda _name: "/usr/bin/allure")
    monkeypatch.setattr(allure_linker.subprocess, "run", lambda *a, **k: None)

    result = allure_linker.generate_allure_report(tmp_path / "allure-results", tmp_path / "allure-report")

    assert result is True
