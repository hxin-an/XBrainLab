"""Subprocess coverage for native-safe async filtering in the desktop UI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "run_preprocess_async_filter_stress.py"
ABORT_MARKERS = (
    "double free",
    "corruption (out)",
    "segmentation fault",
    "core dumped",
)


def test_three_real_gdf_files_filter_in_python_owned_worker_and_render() -> None:
    env = dict(os.environ)
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "MPLBACKEND": "Agg",
            "PYTHONFAULTHANDLER": "1",
        }
    )
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), "--cycles", "2"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
    )

    combined = f"{completed.stdout}\n{completed.stderr}".casefold()
    assert completed.returncode == 0, combined
    assert not any(marker in combined for marker in ABORT_MARKERS)
    result_line = next(
        line
        for line in completed.stdout.splitlines()
        if line.startswith("PREPROCESS_ASYNC_FILTER_STRESS=")
    )
    result = json.loads(result_line.split("=", 1)[1])
    assert result["core_dumps_disabled"] is True
    assert result["fixture_count"] == 3
    assert result["cycles"] == 2
    assert result["completed_cycles"] == 2
    assert result["execution_threads"] == [
        "XBrainLab-preprocess",
        "XBrainLab-preprocess",
    ]
    assert result["minimum_time_samples"] > 0
    assert result["minimum_psd_bins"] > 0
