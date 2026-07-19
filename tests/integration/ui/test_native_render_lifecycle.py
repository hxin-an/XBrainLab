"""Subprocess coverage for native Qt/PyQtGraph render ownership."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "run_ui_native_render_stress.py"
ABORT_MARKERS = (
    "double free",
    "corruption (out)",
    "segmentation fault",
    "core dumped",
)


def test_real_eeg_panel_switching_exits_without_native_abort():
    env = dict(os.environ)
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "PYVISTA_OFF_SCREEN": "true",
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
        if line.startswith("UI_NATIVE_STRESS=")
    )
    result = json.loads(result_line.split("=", 1)[1])
    assert result["active_qthreadpool_workers"] == 0
    assert isinstance(result["core_dumps_disabled"], bool)
    if os.name == "posix":
        assert result["core_dumps_disabled"] is True
    assert result["saliency_cycles"] == 8
    assert result["saliency_cleanup_owners_drained"] == 8
    assert result["saliency_cleanup_owners_deleted"] == 8
    assert result["saliency_views_deleted"] == 8
    assert result["saliency_canvases_deleted"] == 16
    assert result["saliency_figures_released"] == 24
    assert result["saliency_workers_released"] == 8
    assert result["saliency_signals_released"] == 8
    assert result["saliency_gui_heartbeat_ticks"] >= 8
    assert result["active_render_close_fenced"] is True
    assert result["active_render_close_completed"] is True
    assert result["pool_drained_before_close"] is True
    assert result["pool_drained_measurement"] == "application_owned_visualization"
    assert result["app_owned_render_idle_after_close"] is True
    assert result["global_pool_active_at_finalize"] >= 1
    assert result["unrelated_global_work_started"] is True
    assert result["unrelated_global_work_completed"] is True
    assert result["child_finalizers_completed"] is True
    assert result["child_finalizers_exactly_once"] is True
    assert result["two_d_resources_released"] is True
    assert result["active_3d_engine_close_safe"] is True
    assert result["active_3d_probe_close_safe"] is True
    assert result["active_3d_engine_late_callbacks"] == 0
    assert result["active_3d_probe_late_callbacks"] == 0
    assert result["active_3d_worker_gui_heartbeat_ticks"] >= 2
    assert result["resources_finalized"] is True
    assert result["product_saliency_warmup_cycles"] == 2
    assert result["product_saliency_measurement_cycles"] == 8
    assert result["product_saliency_cycles"] == 10
    assert result["product_saliency_publications_served"] >= 40
    assert result["product_2d_renders_installed"] == 30
    assert result["product_2d_loading_cleared"] == 30
    assert result["product_2d_replaced_resources_released"] == 30
    assert result["product_map_renders_installed"] == 10
    assert result["product_spectrogram_renders_installed"] == 10
    assert result["product_topomap_renders_installed"] == 10
    assert result["product_3d_tab_updates"] == 10
    assert result["product_3d_renders_installed"] == 0
    assert result["product_3d_replaced_interactors_closed"] == 0
    assert result["three_d_interactor_closed"] is None
    assert result["three_d_interactor_wrapper_released"] is None
    probe = result["interactive_3d_probe"]
    assert probe["status"] in {"SKIP", "BLOCKED"}
    assert probe["status"] != "PASS"
    assert probe["actual_probe_executed"] is False
    assert result["product_3d_status"] == probe["status"]
    assert result["product_3d_block_reason"]
    assert result["product_memory_sample_count"] == 11
    assert len(result["steady_rss_samples_bytes"]) == 9
    assert len(result["steady_rss_cycle_deltas_bytes"]) == 8
    assert result["memory_contract_failures"] == []
    assert result["steady_rss_peak_growth_bytes"] <= 256 * 1024 * 1024
    assert result["total_post_startup_rss_growth_bytes"] >= 0
