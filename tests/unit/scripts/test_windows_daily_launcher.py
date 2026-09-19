"""Exercise the daily entry point with real Windows CMD and the installed Python."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows CMD launcher")


def _invoke(launcher: Path, cwd: Path, arguments: str = ""):
    return subprocess.run(  # noqa: S603 - fixed local launcher, no user input.
        f'"{os.environ["COMSPEC"]}" /d /s /c ""{launcher}" {arguments}"',
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        check=False,
    )


def test_daily_launcher_runs_existing_entrypoint_from_other_directory(tmp_path):
    assert (ROOT / "start.cmd").is_file(), "Daily launcher does not exist"
    if not (ROOT / ".venv/Scripts/python.exe").is_file():
        pytest.skip("Daily source launch requires the existing Windows environment")
    result = _invoke(ROOT / "start.cmd", tmp_path, "--help")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--model" in result.stdout
    assert "--tool-debug" in result.stdout


def test_daily_launcher_reports_missing_environment_without_creating_one(tmp_path):
    source = tmp_path / "source 測試 with spaces & symbols"
    source.mkdir()
    launcher = source / "start.cmd"
    shutil.copyfile(ROOT / "start.cmd", launcher)
    result = _invoke(launcher, tmp_path)
    assert result.returncode != 0
    assert "Windows Python is missing" in result.stdout + result.stderr
    assert "setup-windows.cmd" in result.stdout + result.stderr
    assert not (source / ".venv").exists()


def test_daily_launcher_preserves_entrypoint_failure_exit_code(tmp_path):
    assert (ROOT / "start.cmd").is_file(), "Daily launcher does not exist"
    if not (ROOT / ".venv/Scripts/python.exe").is_file():
        pytest.skip("Daily source launch requires the existing Windows environment")
    result = _invoke(ROOT / "start.cmd", tmp_path, "--not-a-supported-argument")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "unrecognized arguments" in result.stderr
