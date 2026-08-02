"""Subprocess coverage for real-data Preprocess PyQtGraph ownership."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "run_preprocess_native_lifecycle_stress.py"
ABORT_MARKERS = (
    "double free",
    "corruption (out)",
    "segmentation fault",
    "core dumped",
)


def test_real_gdf_time_psd_cancelled_close_and_final_close_are_native_safe():
    env = dict(os.environ)
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "MPLBACKEND": "Agg",
        }
    )
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), "--cycles", "8"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )

    combined = f"{completed.stdout}\n{completed.stderr}".casefold()
    assert completed.returncode == 0, combined
    assert not any(marker in combined for marker in ABORT_MARKERS)
    result_line = next(
        line
        for line in completed.stdout.splitlines()
        if line.startswith("PREPROCESS_NATIVE_STRESS=")
    )
    result = json.loads(result_line.split("=", 1)[1])
    assert result["core_dumps_disabled"] is True
    assert result["cycles"] == 8
    assert result["time_render_cycles"] == 8
    assert result["psd_render_cycles"] == 8
    assert result["cancelled_close_resume_cycles"] == 8
    assert result["detached_shutdown_cycles"] == 8
    assert result["restored_ownership_cycles"] == 8
    assert result["destroy_recreate_cycles"] == 8
    assert result["parent_owned_plot_teardown_cycles"] == 8
    assert result["minimum_owned_items_checked"] >= 20
    assert result["plot_update_callbacks"] >= 8
    assert result["minimum_time_samples"] > 0
    assert result["minimum_psd_bins"] > 0
    assert result["final_shutdown"] is True
    assert result["final_proxy_slots_disconnected"] is True
    assert result["final_items_detached"] is True
    assert result["uncaught_exceptions"] == []
