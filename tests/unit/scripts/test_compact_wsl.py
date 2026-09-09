from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "compact_wsl.ps1"
HARNESS = Path(__file__).with_name("compact_wsl_harness.ps1")


def _powershell() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("pwsh")


@pytest.mark.parametrize(
    "scenario",
    [
        "Preview",
        "BackupFailure",
        "ActiveWsl",
        "ExistingBackup",
        "SourceChanged",
        "DiskPartOutput",
        "DetachFailure",
        "CompactFailure",
        "Apply",
    ],
)
def test_compaction_script_safety_scenarios(tmp_path: Path, scenario: str) -> None:
    powershell = _powershell()
    if os.name != "nt" or powershell is None:
        pytest.skip("Windows PowerShell is required for this native script harness")

    completed = subprocess.run(  # noqa: S603 - native harness path is fixed by this test.
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARNESS),
            "-Scenario",
            scenario,
            "-ScriptPath",
            str(SCRIPT),
            "-TempRoot",
            str(tmp_path / scenario),
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip())
    assert payload["passed"] is True
    expected_events = {
        "Preview": [],
        "BackupFailure": [],
        "ActiveWsl": [],
        "ExistingBackup": [],
        "SourceChanged": [],
        "DiskPartOutput": [],
        "DetachFailure": ["attach", "compact"],
        "CompactFailure": ["attach", "detach"],
        "Apply": ["attach", "compact", "detach", "postcheck"],
    }
    assert payload["events"] == expected_events[scenario]
