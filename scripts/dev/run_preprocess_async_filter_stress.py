#!/usr/bin/env python3
"""Exercise real GDF filtering through the desktop async command lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any


def _disable_core_dumps() -> bool:
    if os.name != "posix":
        return False
    import resource

    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
    except (OSError, ValueError):
        return False


_CORE_DUMPS_DISABLED = _disable_core_dumps()

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication

from scripts.dev.ui_navigation import open_workflow_panel
from XBrainLab.backend.application import (
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    ResetPreprocessCommand,
)
from XBrainLab.backend.application.runtime import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import execute_application_command_async
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = tuple(
    ROOT / "tests" / "fixtures" / "data" / f"A0{index}T.gdf" for index in (1, 2, 3)
)


class _RecordingRuntime:
    """Record command thread ownership while delegating to the real service."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self.execution_threads: list[str] = []

    def execute(
        self,
        command: Any,
        *,
        expected_publication_generation: int | None = None,
    ) -> Any:
        self.execution_threads.append(threading.current_thread().name)
        return self.service.execute(
            command,
            expected_publication_generation=expected_publication_generation,
        )


def _wait_for_result(
    app: QApplication,
    results: list[Any],
    errors: list[tuple],
    *,
    timeout_seconds: float,
    on_tick,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    tick = 0
    while time.monotonic() < deadline and not results and not errors:
        on_tick(tick)
        app.processEvents()
        time.sleep(0.01)
        tick += 1
    if errors:
        raise RuntimeError(f"Async preprocess failed: {errors[0]}")
    if not results:
        raise TimeoutError("Async preprocess did not return a result.")
    if not results[0].ok:
        raise RuntimeError(results[0].message)


def _pump_until(
    app: QApplication,
    predicate,
    *,
    timeout_seconds: float,
    timeout_message: str,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError(timeout_message)
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        time.sleep(0.005)


def run_stress(fixtures: tuple[Path, ...], cycles: int) -> dict[str, Any]:
    app_instance = QApplication.instance()
    app = (
        app_instance
        if isinstance(app_instance, QApplication)
        else QApplication([sys.argv[0]])
    )
    study = Study()
    service = get_application_service(study)
    fixture_paths = [str(path) for path in fixtures]
    load_result = service.execute(LoadDataCommand(paths=fixture_paths))
    if not load_result.ok:
        raise RuntimeError(load_result.message)

    window = MainWindow(study)
    window.resize(1280, 900)
    window.show()
    app.processEvents()
    panel = open_workflow_panel(window, 1, timeout_ms=15_000)
    panel.update_panel()
    app.processEvents()
    runtime = _RecordingRuntime(service)
    completed_cycles = 0
    minimum_time_samples: int | None = None
    minimum_psd_bins: int | None = None

    try:
        for cycle in range(cycles):
            if cycle:
                reset = service.execute(ResetPreprocessCommand(confirmed=True))
                if not reset.ok:
                    raise RuntimeError(reset.message)
                app.processEvents()
                panel.update_panel()
                app.processEvents()

            results: list[Any] = []
            errors: list[tuple] = []
            started = execute_application_command_async(
                panel.sidebar,
                PreprocessCommand(
                    operation=PreprocessOperation.BANDPASS,
                    low_freq=1.0,
                    high_freq=40.0,
                ),
                on_result=results.append,
                on_error=errors.append,
                busy_target=panel,
                runtime=runtime,
            )
            if not started:
                raise RuntimeError("Async preprocess command did not start.")

            def exercise_preview(tick: int) -> None:
                if tick % 5 == 0:
                    tabs = panel.preview_widget.plot_tabs
                    tabs.setCurrentIndex((tabs.currentIndex() + 1) % 2)
                if tick % 7 == 0:
                    panel.preview_widget.time_spin.setValue((tick % 20) / 10.0)

            _wait_for_result(
                app,
                results,
                errors,
                timeout_seconds=180.0,
                on_tick=exercise_preview,
            )
            _pump_until(
                app,
                lambda: application_command_registry().active_count(panel.sidebar) == 0,
                timeout_seconds=10.0,
                timeout_message="Async preprocess worker ownership was not released.",
            )
            panel.update_panel()
            app.processEvents()

            panel.preview_widget.plot_tabs.setCurrentIndex(0)
            panel.update_plot_only()
            app.processEvents()
            time_data = panel.preview_widget.time_current_curve.xData
            time_samples = 0 if time_data is None else len(time_data)
            if time_samples <= 0:
                raise RuntimeError("Filtered time-domain preview is empty.")

            panel.preview_widget.plot_tabs.setCurrentIndex(1)
            panel.update_plot_only()
            app.processEvents()
            frequency_data = panel.preview_widget.freq_current_curve.xData
            psd_bins = 0 if frequency_data is None else len(frequency_data)
            if psd_bins <= 0:
                raise RuntimeError("Filtered PSD preview is empty.")

            minimum_time_samples = (
                time_samples
                if minimum_time_samples is None
                else min(minimum_time_samples, time_samples)
            )
            minimum_psd_bins = (
                psd_bins
                if minimum_psd_bins is None
                else min(minimum_psd_bins, psd_bins)
            )
            completed_cycles += 1
    finally:
        window.close()
        _pump_until(
            app,
            lambda: not window.isVisible(),
            timeout_seconds=30.0,
            timeout_message="MainWindow did not complete its safe shutdown protocol.",
        )

    return {
        "core_dumps_disabled": _CORE_DUMPS_DISABLED,
        "cycles": cycles,
        "completed_cycles": completed_cycles,
        "fixture_count": len(fixtures),
        "fixture_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in fixtures
        },
        "platform": app.platformName(),
        "execution_threads": runtime.execution_threads,
        "minimum_time_samples": minimum_time_samples or 0,
        "minimum_psd_bins": minimum_psd_bins or 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        action="append",
        type=Path,
        dest="fixtures",
        help="Repeat to select GDF fixtures; defaults to A01T/A02T/A03T.",
    )
    parser.add_argument("--cycles", type=int, default=2)
    args = parser.parse_args()
    fixtures = tuple(
        path.expanduser().resolve()
        for path in (args.fixtures if args.fixtures else DEFAULT_FIXTURES)
    )
    missing = [str(path) for path in fixtures if not path.is_file()]
    if missing:
        parser.error(f"fixtures do not exist: {missing}")
    if args.cycles <= 0:
        parser.error("--cycles must be greater than zero")
    result = run_stress(fixtures, args.cycles)
    print("PREPROCESS_ASYNC_FILTER_STRESS=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
