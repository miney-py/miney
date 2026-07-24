"""Tests for miney.env.upgrade."""
import subprocess
import sys

import pytest

from miney.env import upgrade
from miney.exceptions import MineyRunError

#: The real function, captured at import time. tests/conftest.py replaces the module
#: attribute for every test, so that no test suite run installs pip for real; these
#: tests are the ones that have to exercise the genuine article.
REAL_INSTALL_PIP = upgrade.install_pip


@pytest.fixture
def installed(monkeypatch):
    """Make ``plan()`` believe Miney was installed, not checked out."""
    monkeypatch.setattr(upgrade, "source_checkout", lambda: None)


def test_plan_prefers_pip(installed, monkeypatch):
    """
    pip first is not taste. On Windows the upgrade replaces the running miney.exe, and
    only pip survives that: it moves the file aside, while uv deletes it and stops with
    "Access denied".
    """
    monkeypatch.setattr(upgrade, "has_pip", lambda: True)
    monkeypatch.setattr(upgrade.shutil, "which", lambda name: "/usr/bin/uv")
    plan = upgrade.plan()
    assert plan.runnable
    assert plan.command == [
        sys.executable, "-m", "pip", "install", "--upgrade", "miney",
        "--disable-pip-version-check",
    ]


def test_plan_uses_uv_when_the_venv_has_no_pip(installed, monkeypatch):
    # A venv made by "uv venv" - what the documentation tells a beginner to do - has
    # no pip in it at all.
    monkeypatch.setattr(upgrade, "has_pip", lambda: False)
    monkeypatch.setattr(upgrade.shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(upgrade.sys, "platform", "linux")
    plan = upgrade.plan()
    assert plan.runnable
    # --python is what keeps the upgrade in the venv this command runs from, rather
    # than in whatever VIRTUAL_ENV points at.
    assert plan.command == [
        "uv", "pip", "install", "--upgrade", "miney", "--python", sys.executable
    ]


def test_plan_only_shows_the_uv_command_on_windows(installed, monkeypatch):
    monkeypatch.setattr(upgrade, "has_pip", lambda: False)
    monkeypatch.setattr(upgrade.shutil, "which", lambda name: "C:\\uv.exe")
    monkeypatch.setattr(upgrade.sys, "platform", "win32")
    plan = upgrade.plan()
    assert not plan.runnable
    assert plan.command[0] == "uv"
    assert "miney.exe" in plan.manual


def test_plan_refuses_without_pip_and_without_uv(installed, monkeypatch):
    monkeypatch.setattr(upgrade, "has_pip", lambda: False)
    monkeypatch.setattr(upgrade.shutil, "which", lambda name: None)
    plan = upgrade.plan()
    assert plan.command == []
    assert "uv" in plan.refusal


def test_has_pip_answers_for_this_interpreter():
    # Whatever the answer is here, it must be a decision and not an exception.
    assert isinstance(upgrade.has_pip(), bool)


def test_plan_refuses_in_a_source_checkout(monkeypatch, tmp_path):
    monkeypatch.setattr(upgrade, "source_checkout", lambda: tmp_path)
    plan = upgrade.plan()
    assert plan.command == []
    assert "git pull" in plan.refusal
    assert str(tmp_path) in plan.refusal


def test_source_checkout_finds_this_repository():
    # These tests run against the repository itself, which does have a pyproject.toml.
    root = upgrade.source_checkout()
    assert root is not None
    assert (root / "pyproject.toml").is_file()


def test_run_passes_the_command_through(monkeypatch):
    seen = []

    def fake_run(command):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(upgrade.subprocess, "run", fake_run)
    upgrade.run(upgrade.Plan(["uv", "pip", "install", "--upgrade", "miney"]))
    assert seen == [["uv", "pip", "install", "--upgrade", "miney"]]


def test_run_reports_a_failed_upgrade_with_the_command(monkeypatch):
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda command: subprocess.CompletedProcess(command, 1),
    )
    with pytest.raises(MineyRunError) as error:
        upgrade.run(upgrade.Plan(["uv", "pip", "install", "--upgrade", "miney"]))
    assert "uv pip install --upgrade miney" in str(error.value)


def test_run_reports_an_installer_that_cannot_be_started(monkeypatch):
    def explode(command):
        raise OSError("no such file")

    monkeypatch.setattr(upgrade.subprocess, "run", explode)
    with pytest.raises(MineyRunError) as error:
        upgrade.run(upgrade.Plan(["uv", "pip", "install", "--upgrade", "miney"]))
    assert "no such file" in str(error.value)


def test_install_pip_runs_ensurepip(monkeypatch):
    seen = []

    def fake_run(command, capture_output, text):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(upgrade.subprocess, "run", fake_run)
    assert REAL_INSTALL_PIP() is None
    # ensurepip, not "uv pip install pip": it is stdlib, so this needs no network and
    # no uv on the PATH.
    assert seen == [[sys.executable, "-m", "ensurepip", "--upgrade"]]


def test_install_pip_reports_a_failure_instead_of_raising(monkeypatch):
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda command, capture_output, text: subprocess.CompletedProcess(
            command, 1, "", "No module named ensurepip"
        ),
    )
    assert "No module named ensurepip" in REAL_INSTALL_PIP()


def test_install_pip_survives_an_interpreter_that_cannot_be_started(monkeypatch):
    def explode(command, capture_output, text):
        raise OSError("gone")

    monkeypatch.setattr(upgrade.subprocess, "run", explode)
    assert "gone" in REAL_INSTALL_PIP()


def test_pip_needed_here_only_on_windows(installed, monkeypatch):
    monkeypatch.setattr(upgrade, "has_pip", lambda: False)
    monkeypatch.setattr(upgrade.sys, "platform", "win32")
    assert upgrade.pip_needed_here() is True
    monkeypatch.setattr(upgrade.sys, "platform", "linux")
    assert upgrade.pip_needed_here() is False
    monkeypatch.setattr(upgrade.sys, "platform", "darwin")
    assert upgrade.pip_needed_here() is False
