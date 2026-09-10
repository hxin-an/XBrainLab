"""Contracts for explicit Qt modal policy in the shared test harness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_CHILD_LOAD_CONFTEST = """
import json
import os
from pathlib import Path
import runpy
import sys

repository_root = Path(sys.argv[1])
scenario = sys.argv[2]
system_root = Path(sys.argv[3])
sys.path.insert(0, str(repository_root))
os.chdir(repository_root)
for name in ("QT_QPA_PLATFORM", "QT_QPA_FONTDIR", "SystemRoot"):
    os.environ.pop(name, None)
if scenario != "default":
    os.environ["QT_QPA_PLATFORM"] = "windows" if scenario == "non-offscreen" else "offscreen"
if scenario == "override":
    os.environ["QT_QPA_FONTDIR"] = str(system_root / "custom-fonts")
os.environ["SystemRoot"] = str(system_root)
if scenario != "missing-directory":
    (system_root / "Fonts").mkdir(parents=True, exist_ok=True)
runpy.run_path(str(repository_root / "tests" / "conftest.py"), run_name="xbrainlab_test_conftest")
print(json.dumps({
    "platform": os.environ.get("QT_QPA_PLATFORM"),
    "fontdir": os.environ.get("QT_QPA_FONTDIR"),
}))
"""


@pytest.mark.skipif(sys.platform != "win32", reason="Windows test-environment contract")
@pytest.mark.parametrize(
    ("scenario", "expected_platform", "expected_font_directory"),
    [
        ("default", "offscreen", "Fonts"),
        ("override", "offscreen", "custom-fonts"),
        ("non-offscreen", "windows", None),
        ("missing-directory", "offscreen", None),
    ],
)
def test_conftest_windows_offscreen_font_default_is_environment_scoped(
    tmp_path: Path,
    scenario: str,
    expected_platform: str,
    expected_font_directory: str | None,
) -> None:
    system_root = tmp_path / "SystemRoot"
    result = subprocess.run(  # noqa: S603 - current Python and checked-in child code.
        [
            sys.executable,
            "-c",
            _CHILD_LOAD_CONFTEST,
            str(_REPOSITORY_ROOT),
            scenario,
            str(system_root),
        ],
        cwd=_REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=30,
    )
    loaded_environment = json.loads(result.stdout)

    assert loaded_environment["platform"] == expected_platform
    if expected_font_directory is None:
        assert loaded_environment["fontdir"] is None
    else:
        assert loaded_environment["fontdir"] == str(
            system_root / expected_font_directory
        )


def test_undeclared_blocking_modal_fails_fast() -> None:
    with pytest.raises(AssertionError, match="Unexpected blocking Qt modal"):
        QMessageBox.information(None, "Title", "Message")


def test_component_test_can_explicitly_accept_modals(
    auto_accept_modals: None,
    qtbot,
) -> None:
    del auto_accept_modals, qtbot
    assert (
        QMessageBox.question(None, "Question", "Continue?")
        == QMessageBox.StandardButton.Yes
    )
    assert QDialog().exec() == QDialog.DialogCode.Accepted
