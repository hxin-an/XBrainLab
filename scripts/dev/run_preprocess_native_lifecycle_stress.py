#!/usr/bin/env python3
"""Exercise real-data Preprocess Time/PSD native lifecycle in one subprocess."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from scripts.dev.native_process_safety import disable_core_dumps

_NATIVE_PROCESS_SAFETY = disable_core_dumps()
if (
    _NATIVE_PROCESS_SAFETY.core_dump_limit_supported
    and not _NATIVE_PROCESS_SAFETY.core_dumps_disabled
):
    raise RuntimeError(
        "Preprocess stress refused to load Qt because RLIMIT_CORE=0 failed."
    )

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderPublisher,
    PreprocessRenderRequest,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
)
from XBrainLab.backend.load_data.raw_data_loader import load_gdf_file
from XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter import (
    PreprocessPlotter,
)
from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "data" / "A01T.gdf"


class _RealDataProjection:
    """Expose real fixture objects only to the application publisher under test."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def get_preprocessed_data_list(self) -> list[Any]:
        return [self._raw]

    def get_loaded_data_list(self) -> list[Any]:
        return [self._raw]


def _curve_sample_count(curve: Any) -> int:
    x_data = getattr(curve, "xData", None)
    return 0 if x_data is None else len(x_data)


def _owned_plot_item_roots(widget: PreviewWidget) -> list[tuple[str, Any, Any]]:
    return [
        (
            "time",
            widget.plot_time,
            [
                widget.time_original_curve,
                widget.time_current_curve,
                widget.v_line_time,
                widget.h_line_time,
                widget.label_time,
                *widget.time_event_markers,
                *widget.time_excluded_regions,
            ],
        ),
        (
            "frequency",
            widget.plot_freq,
            [
                widget.freq_original_curve,
                widget.freq_current_curve,
                widget.v_line_freq,
                widget.h_line_freq,
                widget.label_freq,
            ],
        ),
    ]


def _graphics_item_tree(item: Any):
    yield item
    for child in item.childItems():
        yield from _graphics_item_tree(child)


def _assert_plot_item_ownership(widget: PreviewWidget, *, attached: bool) -> int:
    checked = 0
    for plot_name, plot, roots in _owned_plot_item_roots(widget):
        scene = plot.scene()
        view_box = plot.getPlotItem().vb
        registered_roots = set(plot.getPlotItem().items)
        expected_roots = set(roots)
        if attached and registered_roots != expected_roots:
            raise RuntimeError(f"{plot_name} plot ownership inventory is incomplete.")
        if not attached and registered_roots:
            raise RuntimeError(
                f"{plot_name} plot retained registered items after shutdown."
            )
        for root in roots:
            for item in _graphics_item_tree(root):
                checked += 1
                get_view_box = getattr(item, "getViewBox", None)
                item_view_box = get_view_box() if callable(get_view_box) else None
                if attached:
                    if item.scene() is not scene or (
                        callable(get_view_box) and item_view_box is not view_box
                    ):
                        raise RuntimeError(
                            f"{plot_name} plot item was not restored to its ViewBox."
                        )
                elif item.scene() is not None or item_view_box is not None:
                    raise RuntimeError(
                        f"{plot_name} plot item retained deleted ViewBox ownership."
                    )
    return checked


def run_stress(fixture: Path, cycles: int) -> dict[str, Any]:
    app_instance = QApplication.instance()
    app = (
        app_instance
        if isinstance(app_instance, QApplication)
        else QApplication([sys.argv[0]])
    )
    app.setStyle("Fusion")
    uncaught_exceptions: list[str] = []
    original_hook = sys.excepthook

    def _record_exception(exctype, value, tb) -> None:
        uncaught_exceptions.append(
            "".join(traceback.format_exception(exctype, value, tb))
        )
        original_hook(exctype, value, tb)

    sys.excepthook = _record_exception
    raw = load_gdf_file(str(fixture))
    if raw is None:
        raise RuntimeError(f"Could not load real GDF fixture: {fixture}")

    mne_raw = raw.get_mne()
    state = ApplicationStateSnapshot.empty()
    view_publication = ApplicationViewPublication(
        generation=1,
        state=state,
        capabilities=build_capability_policy(state),
    )
    render_publication = PreprocessRenderPublisher(
        dataset=_RealDataProjection(raw),
        get_publication=lambda: view_publication,
    ).publish(PreprocessRenderRequest(publication_generation=1))
    plot_update_callbacks = 0

    def _count_plot_update() -> None:
        nonlocal plot_update_callbacks
        plot_update_callbacks += 1

    minimum_time_samples: int | None = None
    minimum_psd_bins: int | None = None
    resumed_cycles = 0
    time_render_cycles = 0
    psd_render_cycles = 0
    detached_shutdown_cycles = 0
    restored_ownership_cycles = 0
    minimum_owned_items_checked: int | None = None
    final_shutdown = False
    final_proxy_slots_disconnected = False
    final_items_detached = False
    destroy_recreate_cycles = 0
    parent_owned_plot_teardown_cycles = 0
    widget: PreviewWidget | None = None
    try:
        for _cycle in range(cycles):
            widget = PreviewWidget()
            widget.resize(920, 620)
            widget.show()
            widget.chan_combo.addItems(list(render_publication.data.channels))
            widget._set_preview_interactive(True, state="loaded")
            widget.request_plot_update.connect(_count_plot_update)
            plotter = PreprocessPlotter(widget)

            widget.plot_tabs.setCurrentIndex(0)
            plotter.plot_sample_data(render_publication)
            app.processEvents()
            time_samples = _curve_sample_count(widget.time_current_curve)
            if time_samples <= 0:
                raise RuntimeError("Time-domain render did not publish real samples.")
            minimum_time_samples = (
                time_samples
                if minimum_time_samples is None
                else min(minimum_time_samples, time_samples)
            )
            time_render_cycles += 1
            widget.show_time_event_markers(
                [
                    (0.25, "stress-event", 0.0),
                    (0.5, "BAD_stress", 0.25),
                ]
            )

            previous_time_proxy = widget.proxy_time
            previous_freq_proxy = widget.proxy_freq
            widget.prepare_for_shutdown()
            if (
                previous_time_proxy.slot is not None
                or previous_freq_proxy.slot is not None
                or widget.plot_time.updatesEnabled()
                or widget.plot_freq.updatesEnabled()
            ):
                raise RuntimeError("Preprocess shutdown did not quiesce native plots.")
            detached_item_count = _assert_plot_item_ownership(widget, attached=False)
            minimum_owned_items_checked = (
                detached_item_count
                if minimum_owned_items_checked is None
                else min(minimum_owned_items_checked, detached_item_count)
            )
            detached_shutdown_cycles += 1
            widget.prepare_for_shutdown()

            widget.resume_after_cancelled_shutdown()
            if (
                widget.proxy_time is previous_time_proxy
                or widget.proxy_freq is previous_freq_proxy
                or widget.proxy_time.slot is None
                or widget.proxy_freq.slot is None
                or not widget.plot_time.updatesEnabled()
                or not widget.plot_freq.updatesEnabled()
            ):
                raise RuntimeError("Cancelled close did not restore native plots.")
            _assert_plot_item_ownership(widget, attached=True)
            restored_ownership_cycles += 1
            resumed_cycles += 1

            widget.plot_tabs.setCurrentIndex(1)
            plotter.plot_sample_data(render_publication)
            app.processEvents()
            psd_bins = _curve_sample_count(widget.freq_current_curve)
            if psd_bins <= 0:
                raise RuntimeError("PSD render did not publish real frequency bins.")
            minimum_psd_bins = (
                psd_bins
                if minimum_psd_bins is None
                else min(minimum_psd_bins, psd_bins)
            )
            psd_render_cycles += 1
            widget._on_plot_param_changed()
            wait_loop = QEventLoop()
            QTimer.singleShot(70, wait_loop.quit)
            wait_loop.exec()

            widget.prepare_for_shutdown()
            final_shutdown = widget._native_plot_shutdown
            final_proxy_slots_disconnected = (
                widget.proxy_time.slot is None and widget.proxy_freq.slot is None
            )
            _assert_plot_item_ownership(widget, attached=False)
            final_items_detached = True
            widget.close()
            if widget.plot_time.closed or widget.plot_freq.closed:
                raise RuntimeError(
                    "Final close cleared a PyQtGraph scene before parent teardown."
                )
            parent_owned_plot_teardown_cycles += 1
            widget.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            destroy_recreate_cycles += 1
            widget = None
    finally:
        if widget is not None and not sip.isdeleted(widget):
            widget.prepare_for_shutdown()
            widget.close()
            widget.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        close_raw = getattr(mne_raw, "close", None)
        if callable(close_raw):
            close_raw()
        sys.excepthook = original_hook

    return {
        "fixture": str(fixture),
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "core_dump_limit_supported": (_NATIVE_PROCESS_SAFETY.core_dump_limit_supported),
        "core_dumps_disabled": _NATIVE_PROCESS_SAFETY.core_dumps_disabled,
        "cycles": cycles,
        "time_render_cycles": time_render_cycles,
        "psd_render_cycles": psd_render_cycles,
        "cancelled_close_resume_cycles": resumed_cycles,
        "detached_shutdown_cycles": detached_shutdown_cycles,
        "restored_ownership_cycles": restored_ownership_cycles,
        "destroy_recreate_cycles": destroy_recreate_cycles,
        "parent_owned_plot_teardown_cycles": parent_owned_plot_teardown_cycles,
        "minimum_owned_items_checked": minimum_owned_items_checked or 0,
        "plot_update_callbacks": plot_update_callbacks,
        "minimum_time_samples": minimum_time_samples or 0,
        "minimum_psd_bins": minimum_psd_bins or 0,
        "final_shutdown": final_shutdown,
        "final_proxy_slots_disconnected": final_proxy_slots_disconnected,
        "final_items_detached": final_items_detached,
        "uncaught_exceptions": uncaught_exceptions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--cycles", type=int, default=8)
    args = parser.parse_args()
    fixture = args.fixture.expanduser().resolve()
    if not fixture.is_file():
        parser.error(f"fixture does not exist: {fixture}")
    if args.cycles <= 0:
        parser.error("--cycles must be greater than zero")
    result = run_stress(fixture, args.cycles)
    print("PREPROCESS_NATIVE_STRESS=" + json.dumps(result, sort_keys=True))
    return 0 if not result["uncaught_exceptions"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
