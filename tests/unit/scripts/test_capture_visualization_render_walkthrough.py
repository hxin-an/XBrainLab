import time
from types import SimpleNamespace

from PIL import Image

from scripts.dev.capture_visualization_render_walkthrough import (
    BLOCKED_TAB_SPECS,
    RENDER_TAB_SPECS,
    _command_payload,
    _prepare_tiny_trained_state,
    render_markdown,
    validate_visualization_render_payload,
)
from XBrainLab.backend.application import TrainCommand
from XBrainLab.backend.application.results import ErrorType


def _base_payload():
    return {
        "status": "passed",
        "failure_reason": "",
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
        "renders": [
            {
                "tab": "Saliency Map",
                "screenshot": "map.png",
                "ok": True,
                "error_visible": False,
                "axes_count": 3,
                "image_count": 2,
                "canvas_visible": True,
            },
            {
                "tab": "Spectrogram",
                "screenshot": "spectrogram.png",
                "ok": True,
                "error_visible": False,
                "axes_count": 3,
                "image_count": 2,
                "canvas_visible": True,
            },
            {
                "tab": "Topographic Map",
                "screenshot": "topomap.png",
                "ok": True,
                "error_visible": False,
                "axes_count": 3,
                "image_count": 2,
                "canvas_visible": True,
            },
        ],
        "blocked_renders": [
            {
                "tab": "3D Plot",
                "screenshot": "3d-blocked.png",
                "ok": True,
                "blocked_reason": (
                    "3D rendering requires an interactive OpenGL desktop session."
                ),
                "message_evidence": {"ok": True},
                "plotter_created": False,
            },
        ],
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
    for item in [*payload["renders"], *payload["blocked_renders"]]:
        path = tmp_path / item["screenshot"]
        Image.new("RGB", (8, 8), (48, 72, 96)).save(path)
        item["screenshot"] = str(path)
    return payload


def test_render_tab_specs_cover_matplotlib_saliency_views():
    assert [spec["tab"] for spec in RENDER_TAB_SPECS] == [
        "Saliency Map",
        "Spectrogram",
        "Topographic Map",
    ]


def test_blocked_tab_specs_cover_headless_3d_boundary():
    assert [spec["tab"] for spec in BLOCKED_TAB_SPECS] == ["3D Plot"]


def test_validate_visualization_payload_accepts_rendered_tabs(tmp_path):
    ok, reason = validate_visualization_render_payload(
        _payload_with_screenshots(tmp_path)
    )

    assert ok is True
    assert reason == ""


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


def test_validate_visualization_payload_requires_3d_blocked_reason(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["blocked_renders"] = []

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "3D Plot" in reason


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


def test_validate_visualization_payload_rejects_missing_screenshot_file(tmp_path):
    payload = _payload_with_screenshots(tmp_path)
    payload["renders"][0]["screenshot"] = str(tmp_path / "missing.png")

    ok, reason = validate_visualization_render_payload(payload)

    assert ok is False
    assert "Saliency Map screenshot file was not found" in reason


def test_render_markdown_records_render_claim_boundary():
    markdown = render_markdown(_base_payload())

    assert "# Visualization Render Walkthrough" in markdown
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
        FakeApp(),
        service,
        training_output_dir="/tmp/xbrainlab-viz-test",
        timeout_seconds=1,
        started_at=time.monotonic(),
        payload=payload,
    )

    assert ok is True
    assert isinstance(service.commands[-1], TrainCommand)
    assert service.commands[-1].confirmed is True
    assert service.commands[-1].interactive is False
