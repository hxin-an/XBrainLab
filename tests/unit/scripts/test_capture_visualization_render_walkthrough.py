import hashlib
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PIL import Image
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from scripts.dev import capture_visualization_render_walkthrough as capture_script
from scripts.dev.capture_visualization_render_walkthrough import (
    RENDER_TAB_SPECS,
    ROOT,
    THREE_D_TAB_SPECS,
    _artifact_metadata_for_runtime,
    _artifact_path,
    _capture_matplotlib_window,
    _claim_boundary_for_runtime,
    _command_payload,
    _compose_native_framebuffer,
    _compute_saliency_for_capture,
    _content_addressed_screenshot_path,
    _control_label_pair_gaps,
    _explanation_context_from_panel,
    _matplotlib_layout_evidence,
    _normalize_png_artifact,
    _prepare_tiny_trained_state,
    _provenance_context_matches,
    _screenshot_region_evidence,
    _three_d_runtime_contract,
    _validate_screenshot,
    _visible_label_text,
    _wait_for_3d_capture_terminal_state,
    _wait_for_saliency_render,
    render_markdown,
    stable_artifact_payload,
    validate_visualization_render_payload,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    source_identity_digest,
)
from XBrainLab.backend.application import SaliencyCommand, TrainCommand
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.ui.interaction_outcome import InteractionOutcome


def test_capture_saliency_uses_explicit_panel_action_and_waits_for_terminal(
    qapp,
) -> None:
    button = QWidget()
    button.setProperty("operationPhase", "idle")

    class Panel:
        compute_calls = 0
        compute_saliency_btn = button

        def compute_saliency(self):
            self.compute_calls += 1
            QTimer.singleShot(
                10,
                lambda: button.setProperty("operationPhase", "completed"),
            )
            return InteractionOutcome.accepted("Saliency computation started.")

    class State:
        @staticmethod
        def to_dict():
            return {
                "visualization": {
                    "saliency_available": (
                        button.property("operationPhase") == "completed"
                    )
                }
            }

    panel = Panel()
    service = SimpleNamespace(get_state=lambda: State())

    evidence = _compute_saliency_for_capture(
        qapp,
        panel,
        service,
        timeout_seconds=1,
    )

    assert panel.compute_calls == 1
    assert evidence == {
        "ok": True,
        "action_status": "accepted",
        "action_message": "Saliency computation started.",
        "operation_phase": "completed",
        "saliency_available": True,
    }


def test_explanation_context_comes_from_information_control(qapp) -> None:
    expected = "A01T.gdf +2 files · Fold 1 · Run 1 · True class · Mean over EEG epochs"
    tabs = QTabWidget()
    tabs.setToolTip(expected)
    panel = SimpleNamespace(tabs=tabs)

    assert _explanation_context_from_panel(panel) == expected


def test_visualization_provenance_contract_requires_result_identity() -> None:
    aggregation = "True class · Mean over EEG epochs"
    assert _provenance_context_matches(
        "A01T.gdf +2 files · Fold 1 · Run 1 · " + aggregation,
        aggregation,
    )
    assert not _provenance_context_matches(aggregation, aggregation)
    assert not _provenance_context_matches(
        "Fold 1 · Run 1 · " + aggregation,
        aggregation,
    )
    assert not _provenance_context_matches(
        "A01T.gdf +2 files · Fold 1 (EEGNet) · Run 1 · " + aggregation,
        aggregation,
    )


def test_wait_for_saliency_render_observes_worker_completion(qapp) -> None:
    widget = SimpleNamespace(
        _render_workers={1: object()},
        error_label=QLabel("Rendering saliency..."),
    )

    def finish() -> None:
        widget._render_workers.clear()
        widget.error_label.setText("")

    QTimer.singleShot(10, finish)

    assert _wait_for_saliency_render(qapp, widget, timeout_ms=1000)


def test_wait_for_saliency_render_times_out_while_worker_is_pending(qapp) -> None:
    widget = SimpleNamespace(
        _render_workers={1: object()},
        error_label=QLabel("Rendering saliency..."),
    )

    assert not _wait_for_saliency_render(qapp, widget, timeout_ms=1)


def test_wait_for_saliency_render_ignores_hidden_stale_loading_text(qapp) -> None:
    label = QLabel("Rendering saliency...")
    label.hide()
    widget = SimpleNamespace(
        _render_workers={},
        error_label=label,
    )

    started_at = time.monotonic()

    assert _wait_for_saliency_render(qapp, widget, timeout_ms=1000)
    assert time.monotonic() - started_at < 0.1


def test_wait_for_saliency_render_requires_target_generation_and_visible_canvas(
    qapp,
) -> None:
    canvas = QLabel()
    canvas.hide()
    error_label = QLabel()
    error_label.hide()
    widget = SimpleNamespace(
        _plot_generation=2,
        _render_workers={},
        error_label=error_label,
        canvas=canvas,
    )

    def publish_target_render() -> None:
        widget._plot_generation = 3
        canvas.show()

    QTimer.singleShot(10, publish_target_render)

    assert _wait_for_saliency_render(
        qapp,
        widget,
        timeout_ms=1000,
        minimum_generation=3,
        require_visible_result=True,
    )


def test_wait_for_3d_capture_observes_runtime_probe_terminal_state(qapp) -> None:
    expected_reason = "Saliency Map, Spectrogram, or Topographic Map"
    widget = cast(Any, QWidget())
    label = QLabel("Checking 3D runtime...", widget)
    label.show()
    widget._runtime_probe_worker = object()
    widget._engine_worker = None
    widget.plotter_widget = None

    def finish_probe() -> None:
        widget._runtime_probe_worker = None
        label.setText(
            "3D rendering requires an interactive OpenGL desktop session. "
            f"Use {expected_reason} in this headless environment."
        )

    # The product probe may take longer than the former fixed 500 ms delay.
    QTimer.singleShot(650, finish_probe)

    terminal = _wait_for_3d_capture_terminal_state(
        qapp,
        widget,
        expected_outcome="blocked",
        expected_reason=expected_reason,
        timeout_ms=2000,
    )

    assert terminal["settled"] is True
    assert terminal["outcome"] == "blocked"


def test_three_d_runtime_contract_blocks_noninteractive_platforms() -> None:
    for platform_name, environment in (
        ("offscreen", {}),
        ("minimal", {}),
        ("xcb", {"PYVISTA_OFF_SCREEN": "true"}),
    ):
        contract = _three_d_runtime_contract(
            platform_name=platform_name,
            environment=environment,
        )

        assert contract["expected_outcome"] == "blocked"
        assert contract["interactive_display"] is False


def test_three_d_runtime_contract_requires_interactive_render_on_xcb() -> None:
    contract = _three_d_runtime_contract(
        platform_name="xcb",
        environment={"DISPLAY": ":99", "PYVISTA_OFF_SCREEN": "0"},
    )

    assert contract["expected_outcome"] == "rendered"
    assert contract["interactive_display"] is True
    assert contract["qt_platform"] == "xcb"
    assert contract["capture_method"] == "vtk_framebuffer_composite"


def test_native_framebuffer_composite_places_render_in_plotter_geometry(
    tmp_path,
) -> None:
    screenshot = tmp_path / "window.png"
    Image.new("RGB", (200, 120), (24, 28, 32)).save(screenshot)
    framebuffer = np.zeros((30, 40, 3), dtype=np.uint8)
    framebuffer[:, :, 0] = 180
    framebuffer[:, :, 1] = 70
    framebuffer[:, :, 2] = 45

    _compose_native_framebuffer(
        screenshot,
        framebuffer,
        region_geometry={"x": 20, "y": 10, "width": 80, "height": 60},
        window_size={"width": 200, "height": 120},
    )

    with Image.open(screenshot) as image:
        assert image.getpixel((10, 10)) == (24, 28, 32)
        assert image.getpixel((60, 40)) == (180, 70, 45)


def test_matplotlib_window_capture_composes_canvas_without_losing_shell(
    qapp,
    tmp_path,
) -> None:
    class FramebufferCanvas(QWidget):
        def draw(self) -> None:
            return None

        def buffer_rgba(self) -> np.ndarray:
            frame = np.zeros((60, 160, 4), dtype=np.uint8)
            frame[:, :, 0] = 180
            frame[:, :, 1] = 70
            frame[:, :, 2] = 45
            frame[:, :, 3] = 255
            return frame

    window = QMainWindow()
    content = QWidget()
    layout = QVBoxLayout(content)
    header = QLabel("Visualization shell")
    header.setStyleSheet("background: rgb(40, 45, 50); color: white;")
    header.setFixedHeight(30)
    canvas = FramebufferCanvas()
    canvas.setStyleSheet("background: rgb(16, 18, 20);")
    canvas.setMinimumSize(160, 160)
    footer = QLabel("Application status")
    footer.setStyleSheet("background: rgb(35, 40, 45); color: white;")
    footer.setFixedHeight(30)
    layout.addWidget(header)
    layout.addWidget(canvas, 1)
    layout.addWidget(footer)
    window.setCentralWidget(content)
    window.resize(240, 280)
    window.show()
    qapp.processEvents()
    geometry = capture_script._widget_geometry(canvas, window)
    screenshot = tmp_path / "matplotlib-window.png"

    capture_code = _capture_matplotlib_window(
        window,
        canvas,
        screenshot,
        canvas_geometry=geometry,
        validate_complete=False,
    )

    assert capture_code == 0
    assert canvas.isVisible()
    with Image.open(screenshot) as image:
        assert image.getpixel((120, 120)) == (180, 70, 45)
        assert image.getpixel((20, 15)) != (180, 70, 45)


def test_matplotlib_window_capture_falls_back_to_visible_qt_canvas(
    qapp,
    tmp_path,
) -> None:
    class QtOnlyCanvas(QWidget):
        def draw(self) -> None:
            return None

        def buffer_rgba(self) -> np.ndarray:
            raise RuntimeError("renderer was released")

    window = QMainWindow()
    content = QWidget()
    layout = QVBoxLayout(content)
    canvas = QtOnlyCanvas()
    canvas.setStyleSheet("background: rgb(180, 70, 45);")
    canvas.setMinimumSize(160, 160)
    layout.addWidget(canvas)
    window.setCentralWidget(content)
    window.resize(240, 240)
    window.show()
    qapp.processEvents()
    geometry = capture_script._widget_geometry(canvas, window)
    screenshot = tmp_path / "qt-canvas-fallback.png"

    capture_code = _capture_matplotlib_window(
        window,
        canvas,
        screenshot,
        canvas_geometry=geometry,
        validate_complete=False,
    )

    assert capture_code == 0
    assert canvas.isVisible()
    with Image.open(screenshot) as image:
        red, green, blue = image.getpixel((120, 120))
        assert red > green > blue


def test_matplotlib_window_capture_preserves_scroll_area_canvas(
    qapp,
    tmp_path,
) -> None:
    class FramebufferCanvas(QWidget):
        def draw(self) -> None:
            return None

        def buffer_rgba(self) -> np.ndarray:
            frame = np.zeros((60, 160, 4), dtype=np.uint8)
            frame[:, :, 0] = 180
            frame[:, :, 1] = 70
            frame[:, :, 2] = 45
            frame[:, :, 3] = 255
            return frame

    window = QMainWindow()
    content = QWidget()
    layout = QHBoxLayout(content)
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(False)
    canvas = FramebufferCanvas()
    canvas.setFixedSize(260, 180)
    scroll_area.setWidget(canvas)
    sidebar = QLabel("Sidebar")
    sidebar.setStyleSheet("background: rgb(20, 150, 40); color: white;")
    sidebar.setFixedWidth(90)
    layout.addWidget(scroll_area, 1)
    layout.addWidget(sidebar)
    window.setCentralWidget(content)
    window.resize(340, 240)
    window.show()
    qapp.processEvents()
    geometry = capture_script._widget_geometry(canvas, window)
    screenshot = tmp_path / "scrollable-matplotlib-window.png"

    capture_code = _capture_matplotlib_window(
        window,
        canvas,
        screenshot,
        canvas_geometry=geometry,
        validate_complete=False,
    )

    assert capture_code == 0
    assert scroll_area.widget() is canvas
    assert canvas.isVisible()
    with Image.open(screenshot) as image:
        red, green, blue = image.getpixel((300, 120))
        assert green > blue > red


def test_three_d_artifact_claims_follow_the_actual_runtime() -> None:
    blocked = _three_d_runtime_contract(
        platform_name="offscreen",
        environment={"QT_QPA_PLATFORM": "offscreen"},
    )
    interactive = _three_d_runtime_contract(
        platform_name="xcb",
        environment={"QT_QPA_PLATFORM": "xcb", "DISPLAY": ":99"},
    )

    blocked_metadata = _artifact_metadata_for_runtime(blocked)
    interactive_metadata = _artifact_metadata_for_runtime(interactive)
    blocked_boundary = _claim_boundary_for_runtime(blocked)
    interactive_boundary = _claim_boundary_for_runtime(interactive)

    assert "offscreen" in blocked_metadata["environment"]
    assert "3D blocked state" in blocked_metadata["supports"]
    assert "interactive 3D render" in blocked_metadata["does_not_support"]
    assert "xcb" in interactive_metadata["environment"]
    assert "interactive 3D render" in interactive_metadata["supports"]
    assert "interactive 3D render" not in interactive_metadata["does_not_support"]
    assert any("blocked reason" in item for item in blocked_boundary["supports"])
    assert any(
        "interactive 3D rendering" in item for item in interactive_boundary["supports"]
    )


def test_wait_for_3d_capture_does_not_accept_plotter_creation_before_render(
    qapp,
) -> None:
    class FakeRenderWindow:
        never_rendered = 1

        def GetNeverRendered(self):
            return self.never_rendered

        @staticmethod
        def GetSize():
            return (640, 480)

    class FakeActors:
        count = 0

        def GetNumberOfItems(self):
            return self.count

    class FakeRenderer:
        render_time = 0.0
        actors = FakeActors()

        def GetActors(self):
            return self.actors

        def GetLastRenderTimeInSeconds(self):
            return self.render_time

    window = QWidget()
    window.resize(800, 600)
    window.show()
    plotter = cast(Any, QWidget(window))
    plotter.setGeometry(20, 20, 640, 480)
    plotter.show()
    plotter.render_window = FakeRenderWindow()
    plotter.renderer = FakeRenderer()
    widget = cast(Any, QWidget(window))
    widget.setGeometry(0, 0, 800, 600)
    widget.show()
    widget._runtime_probe_worker = None
    widget._engine_worker = None
    widget.plotter_widget = plotter

    incomplete = _wait_for_3d_capture_terminal_state(
        qapp,
        widget,
        window=window,
        expected_outcome="rendered",
        expected_reason="unused",
        timeout_ms=1,
    )
    assert incomplete["settled"] is False

    def publish_render() -> None:
        plotter.render_window.never_rendered = 0
        plotter.renderer.actors.count = 2
        plotter.renderer.render_time = 0.01

    QTimer.singleShot(10, publish_render)
    terminal = _wait_for_3d_capture_terminal_state(
        qapp,
        widget,
        window=window,
        expected_outcome="rendered",
        expected_reason="unused",
        timeout_ms=1000,
    )

    assert terminal["settled"] is True
    assert terminal["outcome"] == "rendered"
    assert terminal["render_evidence"]["actor_count"] == 2
    assert terminal["render_evidence"]["render_window_rendered"] is True


def _source_identity() -> dict[str, object]:
    identity: dict[str, object] = {
        "version": 3,
        "repo_root": str(ROOT),
        "branch": "test-branch",
        "commit_sha": "a" * 40,
        "head_tree_sha": "b" * 40,
        "dirty": True,
        "dirty_digest": "c" * 64,
        "source_content_digest": "d" * 64,
        "untracked_source_count": 1,
        "excluded_generated_prefixes": ["artifacts/"],
        "excluded_local_paths": ["settings.json"],
        "included_file_policy": "all-non-generated-tracked-and-untracked-files",
        "error": "",
    }
    identity["source_digest"] = source_identity_digest(identity)
    return identity


def _transform_controls(tab: str, *, absolute_visible: bool) -> dict[str, object]:
    return {
        "ok": True,
        "tab": tab,
        "absolute": {
            "visible": absolute_visible,
            "enabled": absolute_visible,
            "checked": True,
            "grid_position": [0, 7, 1, 1] if absolute_visible else [],
        },
        "normalize": {
            "visible": True,
            "enabled": True,
            "checked": True,
            "grid_position": [0, 6, 1, 1],
        },
        "selector_geometry": {
            "plan": [10, 12, 160, 28],
            "run": [190, 12, 120, 28],
            "method": [330, 12, 170, 28],
        },
    }


def _base_payload():
    source_identity = _source_identity()
    return {
        "status": "passed",
        "failure_reason": "",
        "source_identity_at_start": source_identity,
        "source_identity_at_completion": source_identity.copy(),
        "source_identity": source_identity.copy(),
        "source_capture": {
            "branch": "test-branch",
            "commit_sha": "a" * 40,
            "head_tree_sha": "b" * 40,
            "dirty": True,
            "dirty_digest": "c" * 64,
            "source_content_digest": "d" * 64,
            "source_digest_at_start": source_identity["source_digest"],
            "source_digest_at_completion": source_identity["source_digest"],
        },
        "source_path": "/tmp/source.fif",
        "training_output_dir": "/tmp/xbrainlab-viz-output",
        "dataset_preparation": {"ok": True, "commands": []},
        "training": {
            "commands": [
                {"command": "configure_training", "ok": True},
                {"command": "train", "ok": True},
                {"command": "saliency", "ok": True},
            ],
            "finished_run_count": 1,
            "metrics_available": True,
            "saliency_available": True,
        },
        "application_visualize": {
            "ok": True,
            "diagnostics": {
                "available_views": [
                    "saliency map",
                    "spectrogram",
                    "topographic map",
                    "3D plot",
                ],
            },
        },
        "saliency_compute": {
            "ok": True,
            "action_status": "accepted",
            "action_message": "Saliency computation started.",
            "operation_phase": "completed",
            "saliency_available": True,
        },
        "three_d_runtime": {
            "qt_platform": "offscreen",
            "configured_qt_platform": "offscreen",
            "pyvista_off_screen": True,
            "interactive_display": False,
            "expected_outcome": "blocked",
            "capture_method": "qt_widget_render",
        },
        "renders": [
            {
                "tab": "Saliency Map",
                "transform_controls": _transform_controls(
                    "Saliency Map", absolute_visible=True
                ),
                "explanation_context": (
                    "A01T.gdf +2 files · Fold 1 · Run 1 · "
                    "True class · Mean over EEG epochs"
                ),
                "screenshot": "map.png",
                "ok": True,
                "error_visible": False,
                "axes_count": 3,
                "image_count": 2,
                "canvas_visible": True,
                "canvas_geometry": {"ok": True},
                "artist_layout": {"ok": True},
                "screenshot_region": {"ok": True},
            },
            {
                "tab": "Spectrogram",
                "transform_controls": _transform_controls(
                    "Spectrogram", absolute_visible=False
                ),
                "explanation_context": (
                    "A01T.gdf +2 files · Fold 1 · Run 1 · "
                    "True class · Mean magnitude over EEG epochs and channels"
                ),
                "screenshot": "spectrogram.png",
                "ok": True,
                "error_visible": False,
                "axes_count": 3,
                "image_count": 2,
                "canvas_visible": True,
                "canvas_geometry": {"ok": True},
                "artist_layout": {"ok": True},
                "screenshot_region": {"ok": True},
            },
            {
                "tab": "Topographic Map",
                "transform_controls": _transform_controls(
                    "Topographic Map", absolute_visible=True
                ),
                "explanation_context": (
                    "A01T.gdf +2 files · Fold 1 · Run 1 · "
                    "True class · Mean over EEG epochs and time"
                ),
                "screenshot": "topomap.png",
                "ok": True,
                "error_visible": False,
                "axes_count": 3,
                "image_count": 2,
                "canvas_visible": True,
                "canvas_geometry": {"ok": True},
                "artist_layout": {"ok": True, "right_margin_pixels": 12.0},
                "screenshot_region": {"ok": True},
            },
        ],
        "blocked_renders": [
            {
                "tab": "3D Plot",
                "screenshot": "3d-blocked.png",
                "ok": True,
                "blocked_reason": (
                    "Configure a 3D Electrode Layout in Dataset before opening "
                    "the 3D plot."
                ),
                "message_evidence": {"ok": True},
                "screenshot_region": {"ok": True},
                "terminal_settled": True,
                "plotter_created": False,
            },
        ],
        "interactive_renders": [],
        "final_state": {
            "dataset": {"available": True},
            "training": {
                "has_trainer": True,
                "is_running": False,
                "finished_run_count": 1,
            },
            "evaluation": {"metrics_available": True},
            "visualization": {
                "saliency_configured": True,
                "saliency_available": True,
                "montage_available": True,
            },
        },
        "shutdown": {
            "ok": True,
            "timed_out": False,
            "window_visible": False,
            "snapshot": {
                "application_closed": True,
                "pre_close_application_idle": True,
                "pre_close_remaining_workers": 0,
                "pre_close_remaining_subprocesses": 0,
                "close_attempt_id": "capture-close-attempt",
            },
        },
        "ui_state": {
            "current_panel": "Visualization",
            "control_layout": {
                "ok": True,
                "hidden_or_empty": [],
                "overlaps": [],
                "rects": {},
            },
        },
        "uncaught_exceptions": [],
        "elapsed_seconds": 12.0,
    }


def _payload_with_screenshots(tmp_path):
    payload = _base_payload()
    for index, item in enumerate(
        [*payload["renders"], *payload["blocked_renders"]],
        start=1,
    ):
        path = tmp_path / item["screenshot"]
        image = Image.new("RGB", (160, 120), (30, 30, 30))
        for x in range(160):
            image.putpixel((x, 4), (50 + index, 110, 165))
            image.putpixel((x, 5), (50 + index, 110, 165))
        for y in range(10, 110, 8):
            for x in range(112, 154):
                image.putpixel((x, y), (190, 198, 206))
        image.save(path)
        item["screenshot"] = str(path)
        item["screenshot_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return payload


def _interactive_payload_with_screenshots(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["three_d_runtime"] = {
        "qt_platform": "xcb",
        "configured_qt_platform": "xcb",
        "pyvista_off_screen": False,
        "interactive_display": True,
        "expected_outcome": "rendered",
        "capture_method": "vtk_framebuffer_composite",
    }
    payload["blocked_renders"] = []
    screenshot = tmp_path / "3d-interactive.png"
    image = Image.new("RGB", (160, 120), (24, 28, 32))
    for x in range(160):
        image.putpixel((x, 4), (20, 112, 174))
        image.putpixel((x, 5), (20, 112, 174))
    for y in range(16, 108):
        for x in range(18, 146):
            image.putpixel(
                (x, y),
                (40 + (x % 160), 35 + (y % 120), 190 - (x % 90)),
            )
    image.save(screenshot)
    payload["interactive_renders"] = [
        {
            "tab": "3D Plot",
            "screenshot": str(screenshot),
            "screenshot_sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
            "ok": True,
            "outcome": "rendered",
            "terminal_settled": True,
            "plotter_created": True,
            "plotter_visible": True,
            "plotter_geometry": {"ok": True},
            "render_evidence": {
                "ok": True,
                "render_window_rendered": True,
                "render_window_size": {"width": 640, "height": 480},
                "actor_count": 4,
                "last_render_seconds": 0.01,
            },
            "screenshot_region": {
                "ok": True,
                "unique_color_count": 200,
                "chromatic_fraction": 0.4,
                "sentinel_fraction": 0.0,
            },
            "capture_method": "vtk_framebuffer_composite",
        }
    ]
    return payload


def test_render_tab_specs_cover_matplotlib_saliency_views():
    assert [spec["tab"] for spec in RENDER_TAB_SPECS] == [
        "Saliency Map",
        "Spectrogram",
        "Topographic Map",
    ]


def test_three_d_tab_specs_cover_blocked_and_interactive_artifacts():
    assert [spec["tab"] for spec in THREE_D_TAB_SPECS] == ["3D Plot"]
    assert THREE_D_TAB_SPECS[0]["screenshot"].endswith("3d-blocked.png")
    assert THREE_D_TAB_SPECS[0]["interactive_screenshot"].endswith("3d-interactive.png")


def test_capture_script_uses_product_qt_runtime_bootstrap() -> None:
    source = Path(capture_script.__file__).read_text(encoding="utf-8")

    configure_index = source.index("configure_qt_platform_for_runtime()")
    qt_import_index = source.index("from PyQt6.QtCore import")

    assert configure_index < qt_import_index


def test_blocked_reason_capture_does_not_concatenate_unrelated_labels(qtbot):
    container = QWidget()
    qtbot.addWidget(container)
    class_label = QLabel("Class: Left hand", container)
    blocked_label = QLabel(
        "3D rendering requires an interactive OpenGL desktop session.",
        container,
    )
    class_label.show()
    blocked_label.show()

    captured = _visible_label_text(container, "interactive OpenGL desktop")

    assert captured == "3D rendering requires an interactive OpenGL desktop session."


def test_artifact_path_prefers_repo_relative_paths():
    path = ROOT / "build" / "dev-artifacts" / "visualization-render" / "plot.png"

    assert _artifact_path(path) == "build/dev-artifacts/visualization-render/plot.png"


def test_stable_artifact_payload_masks_runtime_only_values():
    payload = {
        "elapsed_seconds": 9.2,
        "training": {
            "commands": [
                {
                    "diagnostics": {
                        "resource_preflight": {
                            "available_ram_bytes": 123,
                            "available_vram_bytes": None,
                        }
                    }
                }
            ],
        },
        "final_state": {
            "evaluation": {
                "metrics": {
                    "0": {"precision": 0.0},
                    "macro_avg": {"precision": 0.5},
                }
            }
        },
    }

    stable = stable_artifact_payload(payload)

    assert stable["elapsed_seconds"] == "<runtime-dependent>"
    preflight = stable["training"]["commands"][0]["diagnostics"]["resource_preflight"]
    assert preflight["available_ram_bytes"] == "<runtime-dependent>"
    assert preflight["available_vram_bytes"] == "<runtime-dependent>"
    assert stable["final_state"]["evaluation"]["metrics"] == {"status": "available"}
    assert payload["elapsed_seconds"] == 9.2


def test_validate_visualization_payload_accepts_rendered_tabs(tmp_path):
    ok, reason = validate_visualization_render_payload(
        _payload_with_screenshots(tmp_path)
    )

    assert ok is True, reason
    assert reason == ""


@pytest.mark.parametrize(
    "shutdown",
    [
        {},
        {
            "ok": False,
            "timed_out": True,
            "window_visible": True,
            "snapshot": {},
        },
        {
            "ok": True,
            "timed_out": False,
            "window_visible": False,
            "snapshot": {
                "application_closed": True,
                "pre_close_application_idle": True,
                "pre_close_remaining_workers": 1,
                "pre_close_remaining_subprocesses": 0,
                "close_attempt_id": "capture-close-attempt",
            },
        },
    ],
)
def test_validate_visualization_payload_requires_clean_shutdown(tmp_path, shutdown):
    payload = _payload_with_screenshots(tmp_path)
    payload["shutdown"] = shutdown

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert reason == "MainWindow did not publish a clean terminal shutdown."


def test_validate_visualization_payload_requires_explicit_compute_terminal(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["saliency_compute"] = {
        "ok": False,
        "action_status": "accepted",
        "operation_phase": "pending",
        "saliency_available": False,
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert reason == "The visible Compute Saliency action did not complete."


def test_validate_visualization_payload_requires_exact_source_identity(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload.pop("source_identity", None)

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "source identity" in reason.lower()


def test_validate_visualization_payload_rejects_source_change_during_capture(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    changed = dict(payload["source_identity_at_completion"])
    changed["dirty_digest"] = "f" * 64
    changed["source_digest"] = source_identity_digest(changed)
    payload["source_identity_at_completion"] = changed
    payload["source_identity"] = changed

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "source" in reason.lower()
    assert "changed" in reason.lower() or "stale" in reason.lower()


def test_validate_visualization_payload_requires_tab_transform_state(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][1]["transform_controls"]["absolute"]["visible"] = True

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Spectrogram" in reason
    assert "Absolute" in reason


def test_validate_visualization_payload_requires_absolute_restoration(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][2]["transform_controls"]["absolute"]["visible"] = False

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Topographic Map" in reason
    assert "restored" in reason


def test_validate_visualization_payload_rejects_hidden_absolute_layout_hole(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][1]["transform_controls"]["absolute"]["grid_position"] = [
        0,
        7,
        1,
        1,
    ]

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "empty Absolute control slot" in reason


def test_validate_visualization_payload_requires_normalize_before_absolute(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    for render in (payload["renders"][0], payload["renders"][2]):
        render["transform_controls"]["absolute"]["grid_position"] = [0, 6, 1, 1]
        render["transform_controls"]["normalize"]["grid_position"] = [0, 7, 1, 1]

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Normalize before Absolute" in reason


def test_validate_visualization_payload_rejects_selector_jump(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][1]["transform_controls"]["selector_geometry"]["method"] = [
        345,
        12,
        170,
        28,
    ]

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "selector geometry" in reason.lower()


def test_validate_visualization_payload_requires_each_render_tab(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"] = payload["renders"][:2]

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Topographic Map" in reason


def test_validate_visualization_payload_rejects_placeholder_canvas(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][0]["image_count"] = 0

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Saliency Map" in reason
    assert "rendered image" in reason


def test_validate_visualization_payload_rejects_blank_render_region(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][1]["screenshot_region"] = {
        "ok": False,
        "reason": "plot region is visually empty",
        "unique_color_count": 1,
        "dominant_color_fraction": 1.0,
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Spectrogram" in reason
    assert "visually empty" in reason


def test_validate_visualization_payload_rejects_stale_explanation_context(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][1]["explanation_context"] = (
        "Grouped by true class label · Mean across evaluated epochs"
    )

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Spectrogram" in reason
    assert "scientific context" in reason


def test_validate_visualization_payload_rejects_duplicate_tab_capture(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][2]["screenshot"] = payload["renders"][1]["screenshot"]
    payload["renders"][2]["screenshot_sha256"] = payload["renders"][1][
        "screenshot_sha256"
    ]

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "identical screenshot" in reason


def test_validate_visualization_payload_rejects_clipped_matplotlib_artist(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][1]["artist_layout"] = {
        "ok": False,
        "reason": "axes 0 extends beyond the canvas",
        "clipped_axes": [0],
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Spectrogram" in reason
    assert "extends beyond the canvas" in reason


def test_validate_visualization_payload_rejects_tight_topomap_colorbar(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][2]["artist_layout"] = {
        "ok": True,
        "right_margin_pixels": 1.0,
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Topographic Map" in reason
    assert "colorbar" in reason


def test_validate_visualization_payload_requires_3d_blocked_reason(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["blocked_renders"] = []

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "3D Plot" in reason


def test_validate_visualization_payload_requires_3d_terminal_state(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["blocked_renders"][0]["terminal_settled"] = False

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "3D Plot" in reason
    assert "terminal" in reason


def test_validate_visualization_payload_accepts_xcb_interactive_3d_render(
    tmp_path,
) -> None:
    ok, reason = validate_visualization_render_payload(
        _interactive_payload_with_screenshots(tmp_path)
    )

    assert ok is True, reason
    assert reason == ""


def test_validate_visualization_payload_rejects_plotter_only_xcb_evidence(
    tmp_path,
) -> None:
    payload = _interactive_payload_with_screenshots(tmp_path)
    render = payload["interactive_renders"][0]
    render["render_evidence"] = {
        "ok": False,
        "render_window_rendered": False,
        "actor_count": 0,
        "last_render_seconds": 0.0,
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "3D Plot" in reason
    assert "render" in reason.lower()


def test_validate_visualization_payload_rejects_unpainted_xcb_frame(
    tmp_path,
) -> None:
    payload = _interactive_payload_with_screenshots(tmp_path)
    payload["interactive_renders"][0]["screenshot_region"] = {
        "ok": False,
        "reason": "3D plot region contains unpainted capture pixels",
        "sentinel_fraction": 0.54,
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "3D Plot" in reason
    assert "unpainted" in reason


def test_validate_visualization_payload_rejects_control_overlap(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["ui_state"]["control_layout"] = {
        "ok": False,
        "hidden_or_empty": [],
        "overlaps": ["plan/run"],
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Visualization controls" in reason
    assert "plan/run" in reason


def test_validate_visualization_payload_rejects_distant_control_label_pair(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["ui_state"]["control_layout"] = {
        "ok": False,
        "hidden_or_empty": [],
        "overlaps": [],
        "distant_pairs": ["plan"],
        "pair_gaps": {
            "plan": {
                "horizontal_gap": 320,
                "row_delta": 0,
            },
        },
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Visualization controls" in reason
    assert "plan" in reason


def test_control_label_pair_gaps_flags_split_grid_distance():
    rects = {
        "plan": {"x": 720, "y": 110, "width": 220, "height": 28},
        "run": {"x": 720, "y": 150, "width": 180, "height": 28},
    }
    label_rects = {
        "Plan:": {"x": 30, "y": 113, "width": 35, "height": 20},
        "Run:": {"x": 30, "y": 153, "width": 30, "height": 20},
    }

    gaps, distant = _control_label_pair_gaps(
        rects,
        label_rects,
        {"plan": "Plan:", "run": "Run:"},
    )

    assert gaps["plan"]["horizontal_gap"] > 48
    assert distant == ["plan", "run"]


def test_validate_visualization_payload_rejects_uncaught_qt_exception(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["uncaught_exceptions"] = [
        "Traceback (most recent call last):\nTypeError: update_plot() missing token"
    ]

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Uncaught Qt/runtime exception" in reason
    assert "missing token" in reason


def test_validate_visualization_payload_rejects_clipped_3d_message(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["blocked_renders"][0]["message_evidence"] = {
        "ok": False,
        "clipped_by_hint": True,
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "3D Plot blocked reason" in reason


def test_validate_visualization_payload_rejects_unpainted_3d_message_region(
    tmp_path,
):
    payload = _payload_with_screenshots(tmp_path)
    payload["blocked_renders"][0]["screenshot_region"] = {
        "ok": False,
        "reason": "message region has no visible foreground",
    }

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "3D Plot" in reason
    assert "visible foreground" in reason


def test_validate_visualization_payload_rejects_missing_screenshot_file(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][0]["screenshot"] = str(tmp_path / "missing.png")

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Saliency Map screenshot file was not found" in reason


def test_validate_visualization_payload_rejects_screenshot_digest_mismatch(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][0]["screenshot_sha256"] = "0" * 64

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Saliency Map" in reason
    assert "SHA-256" in reason


def test_validate_screenshot_rejects_partially_black_main_window_shell(tmp_path):
    path = tmp_path / "partially-black.png"
    image = Image.new("RGB", (800, 800), (30, 30, 30))
    # Reproduce the offscreen tab-switch artifact: the full top shell and
    # right sidebar were never repainted even though the plot itself rendered.
    for x in range(800):
        for y in range(60):
            image.putpixel((x, y), (0, 0, 0))
    for x in range(540, 800):
        for y in range(60, 760):
            image.putpixel((x, y), (0, 0, 0))
    image.save(path)

    ok, reason = _validate_screenshot(path, "Visualization screenshot")

    assert ok is False
    assert "main window shell" in reason


def test_validate_screenshot_rejects_uniform_dark_theme_shell(tmp_path):
    path = tmp_path / "complete-shell.png"
    Image.new("RGB", (800, 800), (30, 30, 30)).save(path)

    ok, reason = _validate_screenshot(path, "Visualization screenshot")

    assert ok is False
    assert "main window shell" in reason


def test_validate_screenshot_accepts_painted_dark_theme_shell(tmp_path):
    path = tmp_path / "painted-shell.png"
    image = Image.new("RGB", (800, 800), (30, 30, 30))
    for x in range(800):
        image.putpixel((x, 18), (15, 116, 176))
        image.putpixel((x, 19), (15, 116, 176))
    for y in range(80, 760, 20):
        for x in range(570, 760):
            image.putpixel((x, y), (184, 191, 199))
    image.save(path)

    ok, reason = _validate_screenshot(path, "Visualization screenshot")

    assert ok is True
    assert reason == ""


def test_screenshot_region_evidence_rejects_flat_canvas(tmp_path):
    path = tmp_path / "flat-canvas.png"
    Image.new("RGB", (400, 300), (45, 45, 45)).save(path)

    evidence = _screenshot_region_evidence(
        path,
        {"x": 40, "y": 30, "width": 300, "height": 220},
        window_size={"width": 400, "height": 300},
        require_chromatic_content=True,
    )

    assert evidence["ok"] is False
    assert evidence["unique_color_count"] == 1
    assert "visually empty" in evidence["reason"]


def test_screenshot_region_evidence_accepts_rendered_canvas(tmp_path):
    path = tmp_path / "rendered-canvas.png"
    image = Image.new("RGB", (400, 300), (45, 45, 45))
    for x in range(80, 320):
        color = (40 + (x % 180), 60 + (x % 120), 180 - (x % 100))
        for y in range(70, 240):
            image.putpixel((x, y), color)
    image.save(path)

    evidence = _screenshot_region_evidence(
        path,
        {"x": 40, "y": 30, "width": 300, "height": 220},
        window_size={"width": 400, "height": 300},
        require_chromatic_content=True,
    )

    assert evidence["ok"] is True
    assert evidence["unique_color_count"] > 32
    assert evidence["chromatic_fraction"] > 0.01


def test_screenshot_region_evidence_accepts_sparse_blocked_message(tmp_path):
    path = tmp_path / "blocked-message.png"
    image = Image.new("RGB", (400, 300), (45, 45, 45))
    for x in range(160, 240):
        for y in range(145, 150):
            image.putpixel((x, y), (255, 170, 0))
    image.save(path)

    evidence = _screenshot_region_evidence(
        path,
        {"x": 40, "y": 30, "width": 300, "height": 220},
        window_size={"width": 400, "height": 300},
        require_chromatic_content=True,
        allow_sparse_foreground=True,
    )

    assert evidence["ok"] is True
    assert evidence["dominant_color_fraction"] > 0.98


def test_matplotlib_layout_evidence_detects_clipped_axis_label():
    figure = Figure(figsize=(2, 2), dpi=100)
    canvas = FigureCanvasAgg(figure)
    axis = figure.add_subplot(111)
    axis.set_ylabel("frequency")
    figure.subplots_adjust(left=0.01)

    clipped = _matplotlib_layout_evidence(figure, canvas)

    figure.subplots_adjust(left=0.32)
    fitted = _matplotlib_layout_evidence(figure, canvas)

    assert clipped["ok"] is False
    assert clipped["clipped_axes"] == [0]
    assert fitted["ok"] is True
    assert fitted["clipped_axes"] == []


def test_normalize_png_artifact_reencodes_as_opaque_rgb(tmp_path):
    path = tmp_path / "qt-capture.png"
    Image.new("RGBA", (24, 16), (45, 45, 45, 127)).save(path)

    evidence = _normalize_png_artifact(path)

    with Image.open(path) as normalized:
        assert normalized.mode == "RGB"
        assert normalized.size == (24, 16)
        assert normalized.getpixel((0, 0)) == (45, 45, 45)
    assert evidence == {
        "format": "PNG",
        "mode": "RGB",
        "width": 24,
        "height": 16,
    }


def test_content_addressed_screenshot_path_changes_when_pixels_change(tmp_path):
    first = tmp_path / "visualization-render-spectrogram.png"
    Image.new("RGB", (8, 8), (45, 45, 45)).save(first)

    first_path, first_digest = _content_addressed_screenshot_path(first)

    second = tmp_path / "visualization-render-spectrogram.png"
    Image.new("RGB", (8, 8), (20, 80, 160)).save(second)
    second_path, second_digest = _content_addressed_screenshot_path(second)

    assert first_path.is_file()
    assert second_path.is_file()
    assert first_path != second_path
    assert first_digest != second_digest
    assert first_digest[:12] in first_path.name
    assert second_digest[:12] in second_path.name


def test_render_markdown_records_render_claim_boundary():
    markdown = render_markdown(_base_payload())

    assert "# Visualization Render Walkthrough" in markdown
    assert "generator:" in markdown
    assert "does_not_support:" in markdown
    assert "Saliency Map" in markdown
    assert "Topographic Map" in markdown
    assert "3D" in markdown


def test_command_payload_uses_command_name_contract():
    result = SimpleNamespace(
        command_name="visualize",
        ok=True,
        failed=False,
        message="Visualization summary ready.",
        error_type=ErrorType.NONE,
        diagnostics={"payload_type": "visualization_summary"},
    )

    payload = _command_payload(result)

    assert payload["command"] == "visualize"
    assert payload["ok"] is True


def test_visualization_training_walkthrough_confirms_training_boundary():
    class FakeApp:
        def processEvents(self):
            pass

    class FakeService:
        def __init__(self):
            self.commands = []

        def execute(self, command):
            self.commands.append(command)
            return SimpleNamespace(
                command_name=command.name,
                ok=True,
                failed=False,
                message="ok",
                error_type=ErrorType.NONE,
                diagnostics={},
            )

        def get_state(self):
            return SimpleNamespace(
                to_dict=lambda: {
                    "training": {
                        "has_trainer": True,
                        "is_running": False,
                        "finished_run_count": 1,
                    },
                    "evaluation": {"metrics_available": True},
                    "visualization": {"saliency_available": True},
                },
            )

    service = FakeService()
    payload = {"training": {"commands": []}}

    ok = _prepare_tiny_trained_state(
        cast(Any, FakeApp()),
        service,
        training_output_dir=Path("/tmp/xbrainlab-viz-test"),
        timeout_seconds=1,
        started_at=time.monotonic(),
        payload=payload,
    )

    assert ok is True
    saliency = next(
        command for command in service.commands if isinstance(command, SaliencyCommand)
    )
    assert saliency.method == "Gradient"
    assert saliency.params == {}
    assert isinstance(service.commands[-1], TrainCommand)
    assert service.commands[-1].confirmed is True
    assert service.commands[-1].interactive is False
