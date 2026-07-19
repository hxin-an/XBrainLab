#!/usr/bin/env python3
"""Exercise real Qt plot lifecycles in a subprocess so native aborts are observable."""

from __future__ import annotations

import argparse
import gc
import itertools
import json
import os
import sys
import threading
import time
import traceback
import weakref
from dataclasses import replace
from pathlib import Path
from typing import Any, cast


def _disable_core_dumps_for_native_stress() -> bool:
    """Disable core files for this stress process before native libraries load."""
    try:
        import resource
    except ImportError:
        return False
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        core_limit = resource.getrlimit(resource.RLIMIT_CORE)
    except (AttributeError, OSError, ValueError):
        return False
    return core_limit == (0, 0)


_CORE_DUMPS_DISABLED = _disable_core_dumps_for_native_stress()
if os.name == "posix" and not _CORE_DUMPS_DISABLED:
    raise RuntimeError(
        "Native render stress refused to load Qt because RLIMIT_CORE=0 failed."
    )

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import psutil
from matplotlib.figure import Figure
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QRunnable, QThreadPool, QTimer
from PyQt6.QtWidgets import QApplication, QLabel

from scripts.dev.ui_navigation import open_workflow_panel
from XBrainLab.backend.application import (
    ApplicationViewPublication,
    LoadDataCommand,
    SaliencyPlanIdentity,
    SaliencyRenderData,
    SaliencyRenderPublication,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
    get_application_service,
)
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    SaliencyClassCoverageSnapshot,
    SaliencyMethodCoverageSnapshot,
    SaliencyRunCoverageSnapshot,
    VisualizationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewStore
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.backend.visualization.saliency_3d_engine import Saliency3DEngine
from XBrainLab.ui.main_window import MainWindow
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel
from XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view import (
    BaseSaliencyView,
)
from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_head import Saliency3D
from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
    Saliency3DPlotWidget,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "data" / "A01T.gdf"
MAX_STRESS_RSS_GROWTH_BYTES = 256 * 1024 * 1024
MAX_PRODUCT_INITIALIZATION_RSS_GROWTH_BYTES = 384 * 1024 * 1024
MAX_PRODUCT_WARMUP_RSS_GROWTH_BYTES = 448 * 1024 * 1024
MAX_STEADY_RSS_SLOPE_BYTES_PER_CYCLE = 8 * 1024 * 1024
MAX_STEADY_RSS_CYCLE_DELTA_BYTES = 64 * 1024 * 1024
DEFAULT_PRODUCT_WARMUP_CYCLES = 2
PRODUCT_2D_VIEW_NAMES = ("map", "spectrogram", "topomap")


def _native_stress_saliency_state() -> ApplicationStateSnapshot:
    coverage = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=True,
        complete=True,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="left",
                event_code=0,
                available=True,
            ),
        ],
    )
    return replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="evaluated",
        visualization=VisualizationStateSnapshot(
            saliency_available=True,
            saliency_coverage=[
                SaliencyRunCoverageSnapshot(
                    plan_index=0,
                    run_index=0,
                    model_name="NativeStressEEGNet",
                    run_name="Native render fixture",
                    methods=[coverage],
                ),
            ],
        ),
    )


def _native_stress_render_data(sequence: int) -> SaliencyRenderData:
    sample_count = 256
    channel_count = 9
    time_axis = np.linspace(-0.25, 1.25, sample_count, dtype=float)
    channel_scale = np.linspace(0.7, 1.3, channel_count, dtype=float)[:, None]
    phase = float(sequence) * 0.11
    waveform = np.sin((2.0 * np.pi * 7.0 * time_axis) + phase)[None, :]
    base = channel_scale * waveform
    saliency = np.stack(
        (
            base,
            (base * 0.8) + 0.03,
            (base * 1.1) - 0.02,
        ),
        axis=0,
    )
    angles = np.linspace(0.0, 2.0 * np.pi, channel_count - 1, endpoint=False)
    positions = [
        (0.085 * float(np.cos(angle)), 0.085 * float(np.sin(angle)), 0.075)
        for angle in angles
    ]
    positions.append((0.0, 0.0, 0.105))
    return SaliencyRenderData(
        method="Gradient",
        saliency_by_class={0: saliency},
        class_map=((0, "left"),),
        event_ids={"left": 0},
        channel_names=(
            "Fp1",
            "Fp2",
            "C3",
            "C4",
            "P3",
            "P4",
            "O1",
            "O2",
            "Cz",
        ),
        channel_positions=tuple(positions),
        sfreq=128.0,
        tmin=-0.25,
    )


def _native_stress_render_publication(sequence: int) -> SaliencyRenderPublication:
    generation = 10_000 + sequence
    request = SaliencyRenderRequest(
        publication_generation=generation,
        run=SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=0),
            run_index=0,
        ),
        method="Gradient",
    )
    return SaliencyRenderPublication(
        request=request,
        generation=generation,
        training_generation=1,
        data=_native_stress_render_data(sequence),
    )


class _NativeStressApplicationRuntime:
    """Minimal typed application publication fixture for product render stress."""

    def __init__(self) -> None:
        self._state = _native_stress_saliency_state()
        self._store = ApplicationViewStore(
            self._state,
            TrainingReadBoundary.no_trainer(),
        )
        self.render_publications_served = 0
        self._shutdown_fenced = False

    def get_view_publication(self) -> ApplicationViewPublication:
        return self._store.read()

    def execute(
        self,
        command: Any,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        del expected_publication_generation
        command_name = getattr(getattr(command, "name", None), "value", "stress")
        return CommandResult.success_result(
            command_name=str(command_name),
            message="Native saliency publication fixture ready.",
            state=self._state,
            changed_state=ChangedState(),
        )

    def get_interpretation_review(
        self,
        *,
        expected_identity: Any | None = None,
    ) -> dict[str, Any]:
        del expected_identity
        return {}

    def get_saliency_render(
        self,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication:
        publication = self._store.read()
        expected_run = SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(0),
            run_index=0,
        )
        if (
            request.publication_generation != publication.generation
            or request.run != expected_run
            or request.method != "Gradient"
        ):
            raise RuntimeError("Native stress received a stale saliency request.")
        self.render_publications_served += 1
        return SaliencyRenderPublication(
            request=request,
            generation=publication.generation,
            training_generation=1,
            data=_native_stress_render_data(self.render_publications_served),
        )

    def request_shutdown_fence(self) -> None:
        self._shutdown_fenced = True

    def release_shutdown_fence(self) -> bool:
        self._shutdown_fenced = False
        return True

    def wait_for_background_tasks(self, timeout: float | None = None) -> bool:
        del timeout
        return True


def _pump_events(app: QApplication, milliseconds: int = 30) -> None:
    deadline = time.monotonic() + (milliseconds / 1000.0)
    while time.monotonic() < deadline:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        time.sleep(0.002)


def _pump_until(
    app: QApplication,
    predicate,
    *,
    timeout_seconds: float = 3.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for native render lifecycle cleanup.")
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        gc.collect()
        time.sleep(0.002)


def _sample_process_memory(
    *,
    app: QApplication,
    process: psutil.Process,
) -> dict[str, int]:
    """Collect RSS/USS after queued Qt deletion and Python GC have settled."""
    _pump_events(app, 40)
    gc.collect()
    _pump_events(app, 40)
    rss_bytes = int(process.memory_info().rss)
    try:
        uss_bytes = int(process.memory_full_info().uss)
    except (AttributeError, psutil.AccessDenied, psutil.Error):
        uss_bytes = rss_bytes
    tracked_objects = gc.get_objects()
    return {
        "rss_bytes": rss_bytes,
        "uss_bytes": uss_bytes,
        "saliency_3d_scene_count": sum(
            type(obj) is Saliency3D for obj in tracked_objects
        ),
        "saliency_3d_engine_count": sum(
            type(obj) is Saliency3DEngine for obj in tracked_objects
        ),
        "qt_interactor_wrapper_count": sum(
            type(obj).__name__ == "QtInteractor"
            and type(obj).__module__.startswith("pyvistaqt")
            for obj in tracked_objects
        ),
    }


def _memory_series_metrics(
    samples: list[dict[str, int]],
    *,
    warmup_cycles: int,
    measurement_cycles: int,
) -> dict[str, object]:
    """Separate one-time native initialization from post-warm-up memory trend."""
    expected_samples = warmup_cycles + measurement_cycles + 1
    if warmup_cycles < 1 or measurement_cycles < 1 or len(samples) != expected_samples:
        raise ValueError(
            "product memory samples must contain one baseline, every warm-up "
            "cycle, and every measurement cycle"
        )

    rss_samples = [int(sample["rss_bytes"]) for sample in samples]
    uss_samples = [int(sample["uss_bytes"]) for sample in samples]
    steady_rss_samples = rss_samples[warmup_cycles:]
    steady_uss_samples = uss_samples[warmup_cycles:]
    steady_rss_deltas = [
        current - previous
        for previous, current in itertools.pairwise(steady_rss_samples)
    ]
    steady_uss_deltas = [
        current - previous
        for previous, current in itertools.pairwise(steady_uss_samples)
    ]
    steady_rss_baseline = steady_rss_samples[0]
    steady_uss_baseline = steady_uss_samples[0]
    return {
        "product_memory_sample_count": len(samples),
        "product_initialization_rss_growth_bytes": max(
            rss_samples[1] - rss_samples[0],
            0,
        ),
        "product_initialization_uss_growth_bytes": max(
            uss_samples[1] - uss_samples[0],
            0,
        ),
        "product_warmup_rss_growth_bytes": max(
            rss_samples[warmup_cycles] - rss_samples[0],
            0,
        ),
        "product_warmup_uss_growth_bytes": max(
            uss_samples[warmup_cycles] - uss_samples[0],
            0,
        ),
        "steady_rss_samples_bytes": steady_rss_samples,
        "steady_uss_samples_bytes": steady_uss_samples,
        "steady_rss_cycle_deltas_bytes": steady_rss_deltas,
        "steady_uss_cycle_deltas_bytes": steady_uss_deltas,
        "steady_rss_growth_bytes": max(
            steady_rss_samples[-1] - steady_rss_baseline,
            0,
        ),
        "steady_uss_growth_bytes": max(
            steady_uss_samples[-1] - steady_uss_baseline,
            0,
        ),
        "steady_rss_peak_growth_bytes": max(
            max(steady_rss_samples) - steady_rss_baseline,
            0,
        ),
        "steady_uss_peak_growth_bytes": max(
            max(steady_uss_samples) - steady_uss_baseline,
            0,
        ),
        "steady_rss_slope_bytes_per_cycle": (
            steady_rss_samples[-1] - steady_rss_baseline
        )
        / measurement_cycles,
        "steady_uss_slope_bytes_per_cycle": (
            steady_uss_samples[-1] - steady_uss_baseline
        )
        / measurement_cycles,
    }


def _replace_visualization_panel_with_publication_fixture(
    *,
    app: QApplication,
    window: MainWindow,
    runtime: _NativeStressApplicationRuntime,
) -> VisualizationPanel:
    """Install a real product panel backed by typed application publications."""
    previous_panel = cast(Any, open_workflow_panel(window, 4))
    begin_shutdown = getattr(previous_panel, "begin_native_render_shutdown", None)
    if callable(begin_shutdown):
        begin_shutdown()
    native_idle = getattr(previous_panel, "native_render_work_idle", None)
    if callable(native_idle):
        _pump_until(app, lambda: bool(native_idle()), timeout_seconds=8.0)
    finalize = getattr(previous_panel, "finalize_native_render_resources", None)
    if callable(finalize):
        _pump_until(app, lambda: bool(finalize()), timeout_seconds=8.0)

    panel = VisualizationPanel(
        controller=Observable(),
        parent=window,
        application_runtime=runtime,
    )
    panel.resize(1100, 700)
    window.stack.removeWidget(previous_panel)
    window.stack.insertWidget(4, panel)
    cast(Any, window).visualization_panel = panel
    window._loaded_panel_indices.add(4)
    previous_panel.deleteLater()
    window.stack.setCurrentIndex(4)
    panel.show()
    _pump_events(app, 80)
    return panel


def _activate_saliency_tab(panel: VisualizationPanel, index: int) -> None:
    if panel.tabs.currentIndex() == index:
        panel.on_update()
        return
    panel.tabs.setCurrentIndex(index)


def _three_d_actor_count(plotter: object) -> int:
    renderer = getattr(plotter, "renderer", None)
    actors = getattr(renderer, "actors", None)
    if actors is None:
        return 0
    if isinstance(actors, dict):
        return len(actors)
    try:
        return len(actors)
    except TypeError:
        return 0


def _visible_3d_message(view: Saliency3DPlotWidget) -> str:
    messages: list[str] = []
    for index in range(view.plot_layout.count()):
        item = view.plot_layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, QLabel) and widget.isVisible():
            messages.append(widget.text())
    return " ".join(messages)


def _exercise_product_saliency_tabs(
    *,
    app: QApplication,
    panel: VisualizationPanel,
    runtime: _NativeStressApplicationRuntime,
    process: psutil.Process,
    cycles: int,
) -> dict[str, object]:
    """Render every real saliency tab through the public panel path."""
    views = (panel.tab_map, panel.tab_spectro, panel.tab_topo)
    if not all(isinstance(view, BaseSaliencyView) for view in views):
        raise RuntimeError("Visualization panel did not expose the real saliency tabs.")

    panel.on_update()
    panel.refresh_combos()
    panel.on_update()
    _pump_until(
        app,
        lambda: (
            panel.tab_map.native_render_work_idle()
            and panel.tab_map.fig is not None
            and panel.tab_map.canvas is not None
            and panel.tab_map.error_label.isHidden()
        ),
        timeout_seconds=12.0,
    )

    interactive_3d_probe = _probe_interactive_3d_gate()
    two_d_installed = 0
    two_d_loading_cleared = 0
    two_d_replaced_resources_released = 0
    installed_by_view = dict.fromkeys(PRODUCT_2D_VIEW_NAMES, 0)
    three_d_installed = 0
    three_d_replaced_interactors_closed = 0
    three_d_block_reason = ""
    three_d_tab_updates = 0
    publications_before_cycles = runtime.render_publications_served
    product_memory_samples = [_sample_process_memory(app=app, process=process)]

    for _cycle in range(cycles):
        for view_index, (view_name, view) in enumerate(
            zip(PRODUCT_2D_VIEW_NAMES, views, strict=True),
        ):
            previous_figure = view.fig
            previous_canvas = view.canvas
            _activate_saliency_tab(panel, view_index)
            _pump_until(
                app,
                lambda target=view,
                old_figure=previous_figure,
                old_canvas=previous_canvas: (
                    target.native_render_work_idle()
                    and target.fig is not None
                    and target.canvas is not None
                    and target.fig is not old_figure
                    and target.canvas is not old_canvas
                    and bool(target.fig.axes)
                    and target.fig.canvas is target.canvas
                    and target.canvas.figure is target.fig
                    and target.error_label.isHidden()
                ),
                timeout_seconds=12.0,
            )
            two_d_installed += 1
            installed_by_view[view_name] += 1
            if view.error_label.isHidden():
                two_d_loading_cleared += 1
            if previous_canvas is not None:
                _pump_until(
                    app,
                    lambda old_canvas=previous_canvas: sip.isdeleted(old_canvas),
                    timeout_seconds=3.0,
                )
            if previous_figure is not None and previous_canvas is not None:
                if (
                    previous_figure.canvas is not None
                    or previous_canvas.figure is not None
                ):
                    raise RuntimeError(
                        f"{view_name} retained its replaced QTAgg resources."
                    )
                two_d_replaced_resources_released += 1

        previous_plotter = panel.tab_3d.plotter_widget
        previous_plotter_ref = (
            weakref.ref(previous_plotter) if previous_plotter is not None else None
        )
        publications_before_3d = runtime.render_publications_served
        _activate_saliency_tab(panel, 3)
        if interactive_3d_probe["status"] == "PASS":
            _pump_until(
                app,
                lambda old_plotter=previous_plotter: (
                    panel.tab_3d.native_render_work_idle()
                    and panel.tab_3d.plotter_widget is not None
                    and panel.tab_3d.plotter_widget is not old_plotter
                    and not sip.isdeleted(panel.tab_3d.plotter_widget)
                    and getattr(
                        panel.tab_3d.plotter_widget,
                        "interactor",
                        None,
                    )
                    is not None
                    and _three_d_actor_count(panel.tab_3d.plotter_widget) > 0
                ),
                timeout_seconds=30.0,
            )
            three_d_installed += 1
            if previous_plotter is not None:
                _pump_until(
                    app,
                    lambda old_plotter=previous_plotter: sip.isdeleted(old_plotter),
                    timeout_seconds=5.0,
                )
                previous_plotter = None
                _pump_until(
                    app,
                    lambda old_ref=previous_plotter_ref: old_ref is not None
                    and old_ref() is None,
                    timeout_seconds=5.0,
                )
                three_d_replaced_interactors_closed += 1
        else:
            _pump_until(
                app,
                lambda: panel.tab_3d.native_render_work_idle(),
                timeout_seconds=3.0,
            )
            if panel.tab_3d.plotter_widget is not None:
                raise RuntimeError(
                    "3D created an interactor after its runtime gate was blocked."
                )
            three_d_block_reason = _visible_3d_message(panel.tab_3d) or str(
                interactive_3d_probe["reason"]
            )
        three_d_tab_updates += (
            runtime.render_publications_served - publications_before_3d
        )
        product_memory_samples.append(_sample_process_memory(app=app, process=process))

    return {
        "product_saliency_cycles": cycles,
        "product_saliency_publications_served": (
            runtime.render_publications_served - publications_before_cycles
        ),
        "product_2d_renders_installed": two_d_installed,
        "product_2d_loading_cleared": two_d_loading_cleared,
        "product_2d_replaced_resources_released": (two_d_replaced_resources_released),
        "product_map_renders_installed": installed_by_view["map"],
        "product_spectrogram_renders_installed": installed_by_view["spectrogram"],
        "product_topomap_renders_installed": installed_by_view["topomap"],
        "product_3d_status": interactive_3d_probe["status"],
        "product_3d_tab_updates": three_d_tab_updates,
        "product_3d_renders_installed": three_d_installed,
        "product_3d_replaced_interactors_closed": (three_d_replaced_interactors_closed),
        "product_3d_block_reason": three_d_block_reason,
        "interactive_3d_probe": interactive_3d_probe,
        "product_memory_samples": product_memory_samples,
    }


def _exercise_one_active_3d_worker_deletion(
    *,
    app: QApplication,
    worker_kind: str,
) -> tuple[bool, int, int]:
    """Delete one 3D view while its owned engine or probe worker is active."""
    started = threading.Event()
    release = threading.Event()
    late_callbacks: list[str] = []
    heartbeat_ticks = 0
    heartbeat = QTimer()

    def on_heartbeat() -> None:
        nonlocal heartbeat_ticks
        heartbeat_ticks += 1

    heartbeat.timeout.connect(on_heartbeat)
    heartbeat.start(1)
    view = Saliency3DPlotWidget(parent=None)
    view.resize(320, 240)
    view.show()
    _pump_events(app, 4)
    view_ref = weakref.ref(view)
    view_any = cast(Any, view)

    def record_late_callback(*_args, **_kwargs) -> None:
        receiver = view_ref()
        if receiver is not None and sip.isdeleted(receiver):
            late_callbacks.append(worker_kind)

    if worker_kind == "engine":

        def controlled_engine(*_args, **_kwargs):
            started.set()
            if not release.wait(timeout=5.0):
                raise RuntimeError("Active 3D engine stress release timed out.")
            return object(), 1

        original_prepare_engine = Saliency3D.__dict__["prepare_engine"]
        saliency_3d_class = cast(Any, Saliency3D)
        saliency_3d_class.prepare_engine = staticmethod(controlled_engine)
        view_any._on_3d_engine_ready = record_late_callback
        view_any._on_3d_engine_error = record_late_callback
        view_any._on_engine_worker_finished = record_late_callback
        publication = _native_stress_render_publication(101)
        request_id = view._invalidate_async_requests()
        view._current_publication_generation = publication.generation
        try:
            view._start_3d_engine_worker(
                publication.data,
                "left",
                method=publication.data.method,
                absolute=False,
                request_id=request_id,
                publication_generation=publication.generation,
            )
        finally:
            saliency_3d_class.prepare_engine = original_prepare_engine
    elif worker_kind == "probe":

        def controlled_probe() -> tuple[bool, str]:
            started.set()
            if not release.wait(timeout=5.0):
                raise RuntimeError("Active 3D probe stress release timed out.")
            return True, ""

        view_any._probe_interactive_3d_runtime = controlled_probe
        view_any._on_interactive_3d_runtime_probe_result = record_late_callback
        view_any._on_interactive_3d_runtime_probe_error = record_late_callback
        view_any._on_runtime_probe_worker_finished = record_late_callback
        publication = _native_stress_render_publication(102)
        view._start_interactive_3d_runtime_probe(publication, False)
    else:
        heartbeat.stop()
        raise ValueError(f"Unsupported active 3D worker kind: {worker_kind}")

    owner = view._worker_pool_owner
    try:
        _pump_until(
            app,
            lambda started_event=started, cleanup_owner=owner: (
                started_event.is_set() and cleanup_owner.active_worker_count == 1
            ),
            timeout_seconds=3.0,
        )
        heartbeat_before_delete = heartbeat_ticks
        view.deleteLater()
        _pump_until(app, lambda target=view: sip.isdeleted(target))
        _pump_events(app, 12)
        gui_remained_responsive = heartbeat_ticks > heartbeat_before_delete
    finally:
        release.set()

    _pump_until(
        app,
        lambda cleanup_owner=owner: cleanup_owner.active_worker_count == 0,
        timeout_seconds=5.0,
    )
    _pump_until(
        app,
        lambda cleanup_owner=owner: sip.isdeleted(cleanup_owner),
        timeout_seconds=3.0,
    )
    safe = bool(
        sip.isdeleted(view)
        and not late_callbacks
        and gui_remained_responsive
        and sip.isdeleted(owner)
    )
    heartbeat.stop()
    return safe, len(late_callbacks), heartbeat_ticks


def _exercise_active_3d_worker_deletion(
    *,
    app: QApplication,
) -> dict[str, object]:
    """Cover active engine and probe deletion using application-owned pools."""
    metrics: dict[str, object] = {}
    heartbeat_ticks = 0
    for worker_kind in ("engine", "probe"):
        safe, late_callback_count, worker_heartbeat_ticks = (
            _exercise_one_active_3d_worker_deletion(
                app=app,
                worker_kind=worker_kind,
            )
        )
        metrics[f"active_3d_{worker_kind}_close_safe"] = safe
        metrics[f"active_3d_{worker_kind}_late_callbacks"] = late_callback_count
        heartbeat_ticks += worker_heartbeat_ticks

    metrics["active_3d_worker_gui_heartbeat_ticks"] = heartbeat_ticks
    return metrics


def _probe_interactive_3d_gate() -> dict[str, object]:
    """Classify interactive PyVista availability without false PASS results."""
    available, reason = Saliency3DPlotWidget._interactive_3d_runtime_available()
    if available is False:
        return {
            "status": "SKIP",
            "actual_probe_executed": False,
            "reason": reason or "Interactive OpenGL runtime is unavailable.",
        }

    probed, probe_reason = Saliency3DPlotWidget._probe_interactive_3d_runtime()
    return {
        "status": "PASS" if probed else "BLOCKED",
        "actual_probe_executed": True,
        "reason": "" if probed else probe_reason,
    }


def _exercise_saliency_lifecycle(
    *,
    app: QApplication,
    cycles: int,
) -> dict[str, int]:
    metrics = {
        "saliency_cycles": cycles,
        "saliency_cleanup_owners_drained": 0,
        "saliency_cleanup_owners_deleted": 0,
        "saliency_views_deleted": 0,
        "saliency_canvases_deleted": 0,
        "saliency_figures_released": 0,
        "saliency_workers_released": 0,
        "saliency_signals_released": 0,
        "saliency_gui_heartbeat_ticks": 0,
    }
    heartbeat_ticks = 0
    timer = QTimer()

    def heartbeat() -> None:
        nonlocal heartbeat_ticks
        heartbeat_ticks += 1

    timer.timeout.connect(heartbeat)
    timer.start(1)

    for cycle in range(cycles):
        view = BaseSaliencyView()
        view.resize(320, 240)
        view.show()
        _pump_events(app, 4)

        initial_canvas = view.canvas
        initial_figure = view.fig
        if initial_canvas is None or initial_figure is None:
            raise RuntimeError("Saliency view did not create its initial Qt canvas.")
        initial_canvas_ref = weakref.ref(initial_canvas)
        initial_figure_ref = weakref.ref(initial_figure)

        replacement = Figure(figsize=(3, 2), dpi=80)
        replacement.add_subplot(111).plot([0, 1], [cycle, cycle + 1])
        if not view._replace_figure(replacement):
            raise RuntimeError("Saliency replacement figure could not be installed.")
        _pump_until(
            app,
            lambda canvas=initial_canvas: sip.isdeleted(canvas),
        )
        metrics["saliency_canvases_deleted"] += 1
        initial_canvas = None
        initial_figure = None
        _pump_until(
            app,
            lambda canvas_ref=initial_canvas_ref, figure_ref=initial_figure_ref: (
                canvas_ref() is None and figure_ref() is None
            ),
        )
        metrics["saliency_figures_released"] += 1

        rendered_figure_refs: list[weakref.ReferenceType[Figure]] = []
        render_started = threading.Event()
        release_render = threading.Event()

        def render(
            *,
            cycle_number: int = cycle,
            figure_refs=rendered_figure_refs,
            started=render_started,
            release=release_render,
        ) -> Figure:
            figure = Figure(figsize=(3, 2), dpi=80)
            figure.add_subplot(111).plot(
                [0, 1],
                [cycle_number + 1, cycle_number],
            )
            figure_refs.append(weakref.ref(figure))
            started.set()
            if not release.wait(timeout=3.0):
                raise RuntimeError("Stress render release timed out.")
            return figure

        installed_canvas = view.canvas
        installed_figure = view.fig
        if installed_canvas is None or installed_figure is None:
            raise RuntimeError("Replacement Qt canvas was not retained.")
        installed_canvas_ref = weakref.ref(installed_canvas)
        installed_figure_ref = weakref.ref(installed_figure)

        view._render_figure_async(render, error_context="native stress")
        _pump_until(app, render_started.is_set)
        owner = view._render_cleanup_owner
        if owner.active_worker_count != 1:
            raise RuntimeError("Cleanup owner did not retain the active worker.")
        worker = next(iter(view._render_workers.values()))
        worker_ref = weakref.ref(worker)
        signals_ref = weakref.ref(worker.signals)
        worker = None

        _pump_until(
            app,
            lambda canvas=installed_canvas: sip.isdeleted(canvas),
        )
        metrics["saliency_canvases_deleted"] += 1
        installed_canvas = None
        installed_figure = None
        replacement = None
        _pump_until(
            app,
            lambda canvas_ref=installed_canvas_ref, figure_ref=installed_figure_ref: (
                canvas_ref() is None and figure_ref() is None
            ),
        )
        metrics["saliency_figures_released"] += 1

        heartbeat_before_wait = heartbeat_ticks
        _pump_events(app, 12)
        if heartbeat_ticks <= heartbeat_before_wait:
            raise RuntimeError("GUI heartbeat stopped during saliency worker render.")

        view.deleteLater()
        _pump_until(app, lambda target=view: sip.isdeleted(target))
        metrics["saliency_views_deleted"] += 1
        if owner.active_worker_count != 1:
            raise RuntimeError("View deletion released its worker before finished.")

        release_render.set()
        _pump_until(
            app,
            lambda cleanup_owner=owner: cleanup_owner.active_worker_count == 0,
        )
        metrics["saliency_cleanup_owners_drained"] += 1
        _pump_until(app, lambda cleanup_owner=owner: sip.isdeleted(cleanup_owner))
        metrics["saliency_cleanup_owners_deleted"] += 1
        view = None
        _pump_until(
            app,
            lambda worker_weakref=worker_ref,
            signals_weakref=signals_ref,
            figure_refs=rendered_figure_refs: (
                worker_weakref() is None
                and signals_weakref() is None
                and figure_refs
                and figure_refs[0]() is None
            ),
        )
        metrics["saliency_workers_released"] += 1
        metrics["saliency_signals_released"] += 1
        metrics["saliency_figures_released"] += 1

    timer.stop()
    metrics["saliency_gui_heartbeat_ticks"] = heartbeat_ticks
    return metrics


def _exercise_render_cycle(
    *,
    app: QApplication,
    window: MainWindow,
    panel: Any,
    cycle: int,
) -> None:
    tabs = panel.preview_widget.plot_tabs
    slider = panel.preview_widget.time_slider
    tabs.setCurrentIndex(0)
    slider.setValue(min(slider.maximum(), cycle * 3))
    panel.update_panel()
    _pump_events(app)

    tabs.setCurrentIndex(1)
    panel.update_plot_only()
    _pump_events(app)

    for page in (0, 1, 3, 1, 4, 1):
        open_workflow_panel(window, page)
        _pump_events(app, 12)


class _UnrelatedGlobalPoolWork(QRunnable):
    """Global-pool work intentionally outside MainWindow ownership."""

    def __init__(
        self,
        *,
        started: threading.Event,
        release: threading.Event,
        finished: threading.Event,
    ) -> None:
        super().__init__()
        self._started = started
        self._release = release
        self._finished = finished

    def run(self) -> None:
        self._started.set()
        self._release.wait(timeout=20.0)
        self._finished.set()


def _capture_2d_resource_refs(
    panel: VisualizationPanel,
) -> list[tuple[weakref.ReferenceType[Figure], weakref.ReferenceType[Any]]]:
    refs: list[tuple[weakref.ReferenceType[Figure], weakref.ReferenceType[Any]]] = []
    for view in (panel.tab_map, panel.tab_spectro, panel.tab_topo):
        if view.fig is not None and view.canvas is not None:
            refs.append((weakref.ref(view.fig), weakref.ref(view.canvas)))
    return refs


def _captured_2d_resources_released(
    refs: list[tuple[weakref.ReferenceType[Figure], weakref.ReferenceType[Any]]],
) -> bool:
    return all(
        figure_ref() is None and canvas_ref() is None for figure_ref, canvas_ref in refs
    )


def _interactor_closed(
    interactor_ref: weakref.ReferenceType[Any] | None,
) -> bool:
    if interactor_ref is None:
        return True
    interactor = interactor_ref()
    return interactor is None or sip.isdeleted(interactor)


def _interactor_wrapper_released(
    interactor_ref: weakref.ReferenceType[Any] | None,
) -> bool:
    return interactor_ref is None or interactor_ref() is None


def _exercise_active_render_close(
    *,
    app: QApplication,
    window: MainWindow,
    visualization_panel: VisualizationPanel,
    thread_pool: QThreadPool,
    interactive_3d_status: str,
) -> dict[str, object]:
    """Close while a product saliency worker and unrelated pool work coexist."""
    two_d_resource_refs = _capture_2d_resource_refs(visualization_panel)
    plotter = visualization_panel.tab_3d.plotter_widget
    interactor_ref = weakref.ref(plotter) if plotter is not None else None
    plotter = None

    _activate_saliency_tab(visualization_panel, 0)
    if visualization_panel.tab_map.native_render_work_idle():
        raise RuntimeError("Product map render did not retain active close ownership.")

    unrelated_started = threading.Event()
    unrelated_release = threading.Event()
    unrelated_finished = threading.Event()
    unrelated_work = _UnrelatedGlobalPoolWork(
        started=unrelated_started,
        release=unrelated_release,
        finished=unrelated_finished,
    )
    thread_pool.start(unrelated_work)
    _pump_until(app, unrelated_started.is_set, timeout_seconds=3.0)

    owned_idle_observations: list[bool] = []
    global_pool_observations: list[int] = []
    unrelated_active_observations: list[bool] = []
    finalizer_results: list[bool] = []
    child_finalizer_observations: list[bool] = []
    original_finalize = visualization_panel.finalize_native_render_resources

    def finalize_with_measurements() -> bool:
        owned_idle_observations.append(visualization_panel.native_render_work_idle())
        global_pool_observations.append(thread_pool.activeThreadCount())
        unrelated_active_observations.append(
            unrelated_started.is_set() and not unrelated_finished.is_set()
        )
        finalized = bool(original_finalize())
        finalizer_results.append(finalized)
        child_finalizer_observations.append(
            visualization_panel.native_render_resources_finalized()
        )
        return finalized

    visualization_panel.finalize_native_render_resources = finalize_with_measurements
    window.close()
    close_fenced = window.isVisible() and window._closing_in_progress
    if not close_fenced:
        unrelated_release.set()
        raise RuntimeError("MainWindow did not fence the active product render.")

    try:
        _pump_until(
            app,
            lambda: not window.isVisible(),
            timeout_seconds=15.0,
        )
    finally:
        unrelated_release.set()
    _pump_until(app, unrelated_finished.is_set, timeout_seconds=3.0)
    _pump_until(
        app,
        lambda: _captured_2d_resources_released(two_d_resource_refs),
        timeout_seconds=5.0,
    )
    _pump_until(
        app,
        lambda: _interactor_closed(interactor_ref),
        timeout_seconds=5.0,
    )
    _pump_until(
        app,
        lambda: _interactor_wrapper_released(interactor_ref),
        timeout_seconds=5.0,
    )

    cleanup_states = [
        view._native_plot_cleanup_state
        for view in (
            visualization_panel.tab_map,
            visualization_panel.tab_spectro,
            visualization_panel.tab_topo,
        )
    ]
    child_finalizers_exactly_once = all(
        state is not None and state.finalized and state.release_count == 1
        for state in cleanup_states
    )
    three_d_cleanup_state = visualization_panel.tab_3d._native_interactor_cleanup_state
    child_finalizers_exactly_once = bool(
        child_finalizers_exactly_once
        and three_d_cleanup_state.finalized
        and three_d_cleanup_state.finalize_count == 1
    )
    resources_finalized = (
        bool(finalizer_results)
        and finalizer_results[-1]
        and bool(child_finalizer_observations)
        and child_finalizer_observations[-1]
        and visualization_panel.native_render_resources_finalized()
        and _interactor_wrapper_released(interactor_ref)
    )
    pool_drained_before_close = bool(owned_idle_observations) and all(
        owned_idle_observations
    )
    three_d_interactor_closed: bool | None = (
        _interactor_closed(interactor_ref) if interactive_3d_status == "PASS" else None
    )
    three_d_interactor_wrapper_released: bool | None = (
        _interactor_wrapper_released(interactor_ref)
        if interactive_3d_status == "PASS"
        else None
    )
    three_d_interactor_close_verified: bool | None = (
        bool(
            three_d_cleanup_state.close_attempts > 0
            and three_d_cleanup_state.close_attempts
            == three_d_cleanup_state.close_successes
            and not three_d_cleanup_state.failure
        )
        if interactive_3d_status == "PASS"
        else None
    )
    return {
        "active_render_close_fenced": close_fenced,
        "active_render_close_completed": not window.isVisible(),
        "pool_drained_before_close": pool_drained_before_close,
        "pool_drained_measurement": "application_owned_visualization",
        "app_owned_render_idle_after_close": (
            visualization_panel.native_render_work_idle()
        ),
        "global_pool_active_at_finalize": max(
            global_pool_observations,
            default=0,
        ),
        "unrelated_global_work_started": unrelated_started.is_set(),
        "unrelated_global_work_active_at_finalize": bool(unrelated_active_observations)
        and all(unrelated_active_observations),
        "unrelated_global_work_completed": unrelated_finished.is_set(),
        "child_finalizers_completed": bool(child_finalizer_observations)
        and child_finalizer_observations[-1],
        "child_finalizers_exactly_once": child_finalizers_exactly_once,
        "two_d_resources_released": _captured_2d_resources_released(
            two_d_resource_refs
        ),
        "three_d_interactor_closed": three_d_interactor_closed,
        "three_d_interactor_wrapper_released": (three_d_interactor_wrapper_released),
        "three_d_interactor_close_verified": three_d_interactor_close_verified,
        "three_d_interactor_close_attempts": (three_d_cleanup_state.close_attempts),
        "three_d_interactor_close_successes": (three_d_cleanup_state.close_successes),
        "three_d_finalizer_count": three_d_cleanup_state.finalize_count,
        "resources_finalized": resources_finalized,
    }


def _stress_contract_failures(
    result: dict[str, object],
    *,
    cycles: int,
    warmup_cycles: int = 0,
) -> list[str]:
    required_true_metrics = (
        "core_dumps_disabled",
        "active_render_close_fenced",
        "active_render_close_completed",
        "pool_drained_before_close",
        "app_owned_render_idle_after_close",
        "unrelated_global_work_started",
        "unrelated_global_work_active_at_finalize",
        "unrelated_global_work_completed",
        "child_finalizers_completed",
        "child_finalizers_exactly_once",
        "two_d_resources_released",
        "active_3d_engine_close_safe",
        "active_3d_probe_close_safe",
        "resources_finalized",
    )
    failures = [
        metric for metric in required_true_metrics if result.get(metric) is not True
    ]
    product_cycles = cycles + warmup_cycles
    expected_2d_renders = product_cycles * len(PRODUCT_2D_VIEW_NAMES)
    expected_publications = expected_2d_renders + product_cycles
    if result.get("product_saliency_cycles") != product_cycles:
        failures.append("product_saliency_cycles")
    if result.get("product_saliency_warmup_cycles", 0) != warmup_cycles:
        failures.append("product_saliency_warmup_cycles")
    if result.get("product_saliency_measurement_cycles", cycles) != cycles:
        failures.append("product_saliency_measurement_cycles")
    if result.get("product_saliency_publications_served") != expected_publications:
        failures.append("product_saliency_publications_served")
    if result.get("product_2d_renders_installed") != expected_2d_renders:
        failures.append("product_2d_renders_installed")
    if result.get("product_2d_loading_cleared") != expected_2d_renders:
        failures.append("product_2d_loading_cleared")
    if result.get("product_2d_replaced_resources_released") != expected_2d_renders:
        failures.append("product_2d_replaced_resources_released")
    for view_name in PRODUCT_2D_VIEW_NAMES:
        metric = f"product_{view_name}_renders_installed"
        if result.get(metric) != product_cycles:
            failures.append(metric)
    for worker_kind in ("engine", "probe"):
        metric = f"active_3d_{worker_kind}_late_callbacks"
        if result.get(metric) != 0:
            failures.append(metric)
    active_3d_heartbeat_ticks = result.get(
        "active_3d_worker_gui_heartbeat_ticks",
    )
    if not isinstance(active_3d_heartbeat_ticks, int) or active_3d_heartbeat_ticks < 2:
        failures.append("active_3d_worker_gui_heartbeat_ticks")
    if result.get("product_3d_tab_updates") != product_cycles:
        failures.append("product_3d_tab_updates")
    if result.get("product_3d_status") == "PASS":
        if result.get("product_3d_renders_installed") != product_cycles:
            failures.append("product_3d_renders_installed")
        if result.get("product_3d_replaced_interactors_closed") != max(
            product_cycles - 1,
            0,
        ):
            failures.append("product_3d_replaced_interactors_closed")
        if result.get("three_d_interactor_closed") is not True:
            failures.append("three_d_interactor_closed")
        if result.get("three_d_interactor_wrapper_released") is not True:
            failures.append("three_d_interactor_wrapper_released")
        if result.get("three_d_interactor_close_verified") is not True:
            failures.append("three_d_interactor_close_verified")
        if result.get("three_d_interactor_close_attempts") != product_cycles:
            failures.append("three_d_interactor_close_attempts")
        if result.get("three_d_interactor_close_successes") != product_cycles:
            failures.append("three_d_interactor_close_successes")
        if result.get("three_d_finalizer_count") != 1:
            failures.append("three_d_finalizer_count")
    elif result.get("product_3d_status") in {"SKIP", "BLOCKED"}:
        if not str(result.get("product_3d_block_reason", "")).strip():
            failures.append("product_3d_block_reason")
        if result.get("product_3d_renders_installed") != 0:
            failures.append("product_3d_renders_installed")
        if result.get("product_3d_replaced_interactors_closed") != 0:
            failures.append("product_3d_replaced_interactors_closed")
        if result.get("three_d_interactor_close_attempts") != 0:
            failures.append("three_d_interactor_close_attempts")
        if result.get("three_d_interactor_close_successes") != 0:
            failures.append("three_d_interactor_close_successes")
        if result.get("three_d_finalizer_count") != 1:
            failures.append("three_d_finalizer_count")
        for metric in (
            "three_d_interactor_closed",
            "three_d_interactor_wrapper_released",
            "three_d_interactor_close_verified",
        ):
            if result.get(metric) is not None:
                failures.append(metric)
    else:
        failures.append("product_3d_status")
    return failures


def _memory_contract_failures(
    result: dict[str, object],
    *,
    warmup_cycles: int,
    measurement_cycles: int,
) -> list[str]:
    """Fail closed on oversized initialization or an unbounded steady trend."""
    failures: list[str] = []
    expected_samples = warmup_cycles + measurement_cycles + 1
    if result.get("product_memory_sample_count") != expected_samples:
        failures.append("product_memory_sample_count")

    samples = result.get("product_memory_samples")
    if not isinstance(samples, list) or len(samples) != expected_samples:
        failures.append("product_memory_samples")
    else:
        expected_owner_count = 1 if result.get("product_3d_status") == "PASS" else 0
        owner_keys = (
            "saliency_3d_scene_count",
            "saliency_3d_engine_count",
            "qt_interactor_wrapper_count",
        )
        if any(
            not isinstance(sample, dict)
            or any(sample.get(key) != expected_owner_count for key in owner_keys)
            for sample in samples[1:]
        ):
            failures.append("product_3d_python_owner_counts")

    limits = {
        "product_initialization_rss_growth_bytes": (
            MAX_PRODUCT_INITIALIZATION_RSS_GROWTH_BYTES
        ),
        "product_warmup_rss_growth_bytes": (MAX_PRODUCT_WARMUP_RSS_GROWTH_BYTES),
        "steady_rss_peak_growth_bytes": MAX_STRESS_RSS_GROWTH_BYTES,
        "steady_rss_slope_bytes_per_cycle": (MAX_STEADY_RSS_SLOPE_BYTES_PER_CYCLE),
    }
    for metric, limit in limits.items():
        value = result.get(metric)
        if not isinstance(value, (int, float)) or value > limit:
            failures.append(metric)

    cycle_deltas = result.get("steady_rss_cycle_deltas_bytes")
    if (
        not isinstance(cycle_deltas, list)
        or len(cycle_deltas) != measurement_cycles
        or any(
            not isinstance(delta, (int, float))
            or delta > MAX_STEADY_RSS_CYCLE_DELTA_BYTES
            for delta in cycle_deltas
        )
    ):
        failures.append("steady_rss_cycle_deltas_bytes")
    return failures


def run_stress(
    *,
    fixture: Path,
    cycles: int,
    warmup_cycles: int = DEFAULT_PRODUCT_WARMUP_CYCLES,
) -> dict[str, object]:
    existing_app = QApplication.instance()
    app = existing_app if isinstance(existing_app, QApplication) else QApplication([])
    process = psutil.Process()
    initial_rss = process.memory_info().rss

    study = Study()
    service = get_application_service(study)
    load_result = service.execute(LoadDataCommand(paths=[str(fixture)]))
    if load_result.failed:
        raise RuntimeError(load_result.message)

    window = MainWindow(study)
    window.resize(1280, 800)
    window.show()
    _pump_events(app, 80)
    panel = cast(Any, open_workflow_panel(window, 1))
    _pump_events(app, 80)

    _exercise_render_cycle(app=app, window=window, panel=panel, cycle=0)
    warmed_rss = process.memory_info().rss
    for cycle in range(cycles):
        _exercise_render_cycle(app=app, window=window, panel=panel, cycle=cycle + 1)

    saliency_metrics = _exercise_saliency_lifecycle(app=app, cycles=cycles)
    publication_runtime = _NativeStressApplicationRuntime()
    visualization_panel = _replace_visualization_panel_with_publication_fixture(
        app=app,
        window=window,
        runtime=publication_runtime,
    )
    product_saliency_metrics = _exercise_product_saliency_tabs(
        app=app,
        panel=visualization_panel,
        runtime=publication_runtime,
        process=process,
        cycles=cycles + warmup_cycles,
    )
    product_memory_samples = cast(
        list[dict[str, int]],
        product_saliency_metrics.pop("product_memory_samples"),
    )
    product_memory_metrics = _memory_series_metrics(
        product_memory_samples,
        warmup_cycles=warmup_cycles,
        measurement_cycles=cycles,
    )
    active_3d_worker_metrics = _exercise_active_3d_worker_deletion(app=app)
    thread_pool = QThreadPool.globalInstance()
    if thread_pool is None:
        raise RuntimeError("Qt global thread pool is unavailable.")
    active_close_metrics = _exercise_active_render_close(
        app=app,
        window=window,
        visualization_panel=visualization_panel,
        thread_pool=thread_pool,
        interactive_3d_status=str(product_saliency_metrics["product_3d_status"]),
    )
    _pump_events(app, 80)
    gc.collect()
    _pump_events(app, 30)

    final_rss = process.memory_info().rss
    result = {
        "cycles": cycles,
        "fixture": str(fixture),
        "startup_rss_growth_bytes": max(warmed_rss - initial_rss, 0),
        "total_post_startup_rss_growth_bytes": max(final_rss - warmed_rss, 0),
        "active_qthreadpool_workers": (
            thread_pool.activeThreadCount() if thread_pool is not None else 0
        ),
        **saliency_metrics,
        **product_saliency_metrics,
        "product_saliency_warmup_cycles": warmup_cycles,
        "product_saliency_measurement_cycles": cycles,
        "product_memory_samples": product_memory_samples,
        **product_memory_metrics,
        **active_3d_worker_metrics,
        **active_close_metrics,
        "core_dumps_disabled": _CORE_DUMPS_DISABLED,
    }

    failed_contracts = _stress_contract_failures(
        result,
        cycles=cycles,
        warmup_cycles=warmup_cycles,
    )
    if failed_contracts:
        raise RuntimeError(
            "Native render lifecycle contract failed "
            f"({', '.join(failed_contracts)}): {result}"
        )
    memory_failures = _memory_contract_failures(
        result,
        warmup_cycles=warmup_cycles,
        measurement_cycles=cycles,
    )
    result["memory_contract_failures"] = memory_failures
    if memory_failures:
        raise RuntimeError(
            "Native render memory contract failed "
            f"({', '.join(memory_failures)}): {result}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--cycles", type=int, default=12)
    parser.add_argument(
        "--warmup-cycles",
        type=int,
        default=DEFAULT_PRODUCT_WARMUP_CYCLES,
    )
    parser.add_argument(
        "--require-interactive-3d",
        action="store_true",
        help="Exit nonzero unless the real PyVista/OpenGL probe passes.",
    )
    args = parser.parse_args()
    if args.cycles < 1:
        parser.error("--cycles must be positive")
    if args.warmup_cycles < 1:
        parser.error("--warmup-cycles must be positive")
    fixture = args.fixture.expanduser().resolve()
    if not fixture.is_file():
        parser.error(f"fixture does not exist: {fixture}")

    try:
        result = run_stress(
            fixture=fixture,
            cycles=args.cycles,
            warmup_cycles=args.warmup_cycles,
        )
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    print("UI_NATIVE_STRESS=" + json.dumps(result, sort_keys=True))
    probe = cast(dict[str, object], result["interactive_3d_probe"])
    if args.require_interactive_3d and probe["status"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
