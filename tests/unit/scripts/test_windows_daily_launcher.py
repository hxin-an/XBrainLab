"""Exercise the daily entry point with real Windows CMD and the installed Python."""

import os
import shutil
import subprocess
import sys
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
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )


@pytest.fixture
def daily_source(tmp_path):
    """Use the current interpreter via a junction, without installing an environment."""
    source = tmp_path / "source 測試 with spaces & symbols"
    source.mkdir()
    for name in ("start.cmd", "run.py"):
        shutil.copyfile(ROOT / name, source / name)
    environment = source / ".venv"
    if sys.prefix != sys.base_prefix:
        junction, target = environment, Path(sys.prefix)
    else:
        environment.mkdir()
        junction, target = environment / "Scripts", Path(sys.executable).parent
    result = subprocess.run(  # noqa: S603 - fixed native CMD junction operation.
        [
            os.environ["COMSPEC"],
            "/d",
            "/c",
            "mklink",
            "/J",
            str(junction),
            str(target),
        ],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    try:
        yield source
    finally:
        # Remove only the junction; never traverse/delete the shared interpreter.
        junction.rmdir()


def test_daily_launcher_runs_existing_entrypoint_from_other_directory(
    tmp_path, daily_source
):
    result = _invoke(daily_source / "start.cmd", tmp_path, "--help")
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


def test_daily_launcher_preserves_entrypoint_failure_exit_code(tmp_path, daily_source):
    result = _invoke(daily_source / "start.cmd", tmp_path, "--not-a-supported-argument")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "unrecognized arguments" in result.stderr
