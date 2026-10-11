"""Failure paths must release stress-runner resources before the loop starts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def test_async_stress_failed_import_releases_real_application_service(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.dev import run_preprocess_async_filter_stress as runner
    from XBrainLab.backend.application import ApplicationService

    service = ApplicationService()
    monkeypatch.setattr(runner, "get_application_service", lambda _study: service)
    try:
        with pytest.raises(RuntimeError):
            runner.run_stress((tmp_path / "missing.gdf",), cycles=1)
        assert service.is_closed
    finally:
        service.close()


def test_native_stress_failed_load_restores_exception_hook(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.dev import run_preprocess_native_lifecycle_stress as runner

    original_hook = sys.excepthook
    monkeypatch.setattr(runner, "load_gdf_file", lambda _path: None)
    try:
        with pytest.raises(RuntimeError, match="Could not load real GDF"):
            runner.run_stress(tmp_path / "missing.gdf", cycles=1)
        assert sys.excepthook is original_hook
    finally:
        sys.excepthook = original_hook


@pytest.mark.parametrize("emit_update", [True, False])
def test_native_stress_observes_debounced_update_or_fails_closed(
    qapp, monkeypatch: pytest.MonkeyPatch, emit_update: bool
) -> None:
    from scripts.dev import run_preprocess_native_lifecycle_stress as runner

    def delayed_update(widget):
        if emit_update:
            widget.plot_timer.start(150)
        else:
            widget.plot_timer.stop()

    monkeypatch.setattr(runner.PreviewWidget, "_on_plot_param_changed", delayed_update)
    if emit_update:
        result = runner.run_stress(runner.DEFAULT_FIXTURE, cycles=1)
        assert result["plot_update_callbacks"] >= 1
        assert result["destroy_recreate_cycles"] == 1
    else:
        with pytest.raises(TimeoutError, match="plot update"):
            runner.run_stress(runner.DEFAULT_FIXTURE, cycles=1)
