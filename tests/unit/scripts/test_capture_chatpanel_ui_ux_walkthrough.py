from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from PIL import Image

from scripts.dev import capture_chatpanel_ui_ux_walkthrough as walkthrough_module
from scripts.dev.capture_chatpanel_ui_ux_walkthrough import (
    DEFAULT_OUTPUT_DIR,
    EXPECTED_SCREEN_FILES,
    EXPECTED_STATE_LABELS,
    FINGERPRINT_RELATIVE_PATHS,
    README_ARTIFACT,
    SCENARIOS,
    capture_walkthrough,
    image_content_evidence,
    source_fingerprint,
    validate_payload,
)
from scripts.dev.human_like_walkthrough import evidence as human_evidence
from XBrainLab.ui.chat.panel import ChatPanel


def test_scenario_contract_covers_required_surfaces_once() -> None:
    assert tuple(spec.filename for spec in SCENARIOS) == EXPECTED_SCREEN_FILES[:-3]
    assert EXPECTED_SCREEN_FILES[-3:] == (
        "main-window-dock-320-action-click.png",
        "main-window-dock-320-stopping.png",
        "main-window-dock-320-command-running.png",
    )
    assert len({spec.name for spec in SCENARIOS}) == len(SCENARIOS)
    assert len({spec.filename for spec in SCENARIOS}) == len(SCENARIOS)
    scaled = next(spec for spec in SCENARIOS if spec.name == "pixmap_scaled_narrow")
    assert scaled.logical_width == 320
    assert scaled.render_pixel_ratio == 1.5
    responsive_states = {
        (spec.logical_width, spec.review_state)
        for spec in SCENARIOS
        if spec.review_state
    }
    assert {
        (width, state)
        for width in (320, 760, 1280)
        for state in (
            "idle",
            "long_clarification_action",
            "processing_stop",
            "runtime_unavailable",
        )
    }.issubset(responsive_states)
    assert any(
        spec.logical_width == 320
        and spec.logical_height == 520
        and spec.review_state == "long_clarification_action"
        for spec in SCENARIOS
    )
    assert any(
        spec.logical_width == 320
        and spec.logical_height == 650
        and spec.review_state == "long_clarification_action"
        for spec in SCENARIOS
    )
    assert DEFAULT_OUTPUT_DIR.as_posix().endswith(
        "artifacts/ui/chatpanel-ui-ux-current"
    )


def test_source_fingerprint_manifest_covers_every_runtime_capture_owner() -> None:
    assert {
        "scripts/dev/capture_chatpanel_ui_ux_walkthrough.py",
        "scripts/dev/human_like_walkthrough/evidence.py",
        "XBrainLab/chat_contract.py",
        "XBrainLab/backend/controller/chat_controller.py",
        "XBrainLab/llm/agent/assistant_activity.py",
        "XBrainLab/llm/agent/controller.py",
        "XBrainLab/llm/agent/execution_policy.py",
        "XBrainLab/llm/agent/response_presentation.py",
        "XBrainLab/llm/agent/turn.py",
        "XBrainLab/ui/chat/presentation.py",
        "XBrainLab/ui/chat/composer.py",
        "XBrainLab/ui/chat/message_bubble.py",
        "XBrainLab/ui/chat/panel.py",
        "XBrainLab/ui/chat/styles.py",
        "XBrainLab/ui/chat/turn_state.py",
        "XBrainLab/ui/components/agent_manager.py",
        "XBrainLab/ui/components/agent_presentation_service.py",
        "XBrainLab/ui/components/assistant_command_dispatcher.py",
        "XBrainLab/ui/components/assistant_runtime_coordinator.py",
        "XBrainLab/ui/components/assistant_status_projection.py",
        "XBrainLab/ui/main_window.py",
        "XBrainLab/ui/panels/training/components.py",
    }.issubset(set(FINGERPRINT_RELATIVE_PATHS))


def test_capture_walkthrough_replays_real_widget_and_writes_gate(
    qapp, tmp_path
) -> None:
    payload = capture_walkthrough(qapp, tmp_path)
    current_fingerprint = source_fingerprint()

    assert payload["status"] == "passed", payload["failures"]
    assert payload["failures"] == []
    assert payload["source_fingerprint"] == current_fingerprint
    assert payload["capture_source"] == {
        "fingerprint_at_start": current_fingerprint,
        "fingerprint_at_completion": current_fingerprint,
        "stable": True,
    }
    assert payload["native_display_scaling_observed"] is False
    assert payload["render_scale_evidence"] == "synthetic_pixmap_device_ratio"
    assert payload["render_readiness"] == {
        "required_consecutive_content_frames": 2,
        "normalized_png_color_mode": "RGB",
        "full_frame_content_check": True,
        "main_window_required_regions": [
            "main_shell",
            "assistant_transcript",
            "assistant_primary_action",
            "assistant_activity_when_visible",
        ],
        "restored_action_inert_check": True,
        "live_action_pre_click_region_check": True,
    }
    assert len(payload["source_files"]) == len(FINGERPRINT_RELATIVE_PATHS)
    assert tuple(screen["file"] for screen in payload["screens"]) == (
        EXPECTED_SCREEN_FILES
    )
    for screen in payload["screens"]:
        assert all(screen["checks"].values()), screen
        path = tmp_path / screen["file"]
        assert path.is_file()
        with Image.open(path) as captured:
            assert list(captured.size) == screen["pixel_size"]
            assert captured.mode == screen["png_color_mode"] == "RGB"
        geometry = screen["panel_relative_geometry"]
        for required_control in ("composer", "send", "mode_control"):
            assert geometry[required_control]["inside_panel_on_all_sides"] is True
            assert all(geometry[required_control]["sides"].values()), geometry[
                required_control
            ]
        mode_description = geometry["mode_description"]
        assert isinstance(mode_description["visible"], bool)
        if mode_description["visible"]:
            assert mode_description["inside_panel_on_all_sides"] is True
            assert all(mode_description["sides"].values()), mode_description
        if screen.get("visible_response_actions"):
            assert geometry["response_action"]["inside_panel_on_all_sides"] is True
            assert all(geometry["response_action"]["sides"].values()), geometry[
                "response_action"
            ]

    observed_labels = {
        kind: label
        for screen in payload["screens"]
        for kind, label in screen["state_labels"].items()
    }
    assert {
        kind: observed_labels[kind] for kind in EXPECTED_STATE_LABELS
    } == EXPECTED_STATE_LABELS
    dock = payload["main_window_dock_walkthrough"]
    assert dock["real_main_window"] is True
    assert dock["real_qdockwidget"] is True
    assert dock["assistant_usable_width"] == 320
    assert dock["action_click"]["clicked"] is True
    assert dock["action_click"]["history_source"] == "live_correlated_response"
    assert dock["action_click"]["restored_actions_inert"] is True
    assert dock["action_click"]["presentation_identity_from_ui"] is True
    assert dock["action_click"]["workflow_panel_opened"] is True
    assert dock["states"]["cancellable"]["button_text"] == "Stop"
    assert dock["states"]["cancellable"]["button_enabled"] is True
    assert dock["states"]["stopping"]["button_text"] == "Stopping"
    assert dock["states"]["stopping"]["button_enabled"] is False
    assert dock["states"]["stopping"]["late_activity_latched"] is True
    assert dock["states"]["application_command"]["button_text"] == "Working"
    assert dock["states"]["application_command"]["button_enabled"] is False

    first_paint = payload["first_paint_320_contract"]
    assert first_paint["target_width"] == 320
    assert first_paint["passed"] is True
    for surface in ("standalone", "real_dock"):
        evidence = first_paint[surface]
        assert evidence["observed_during_first_paint_event"] is True
        assert evidence["paint_event_index"] == 1
        assert evidence["paint_events_observed_before_capture"] == 1
        assert evidence["settle_layout_called_before_observation"] is False
        assert evidence["assistant_usable_width"] == 320
        assert evidence["runtime_phase"] == "idle"
        assert evidence["mode_selector_visible"] is True
        assert evidence["mode_controls_enabled"] is False
        assert evidence["composer_enabled"] is False
        assert evidence["send_enabled"] is False
        assert evidence["render_content"]["passed"] is True
        assert all(evidence["checks"].values()), evidence
        assert (tmp_path / evidence["file"]).is_file()

    teardown = payload["teardown"]
    assert teardown["manager_close_requested"] is True
    assert teardown["manager_close_finished"] is True
    assert teardown["runtime_cleanup_finished"]["observed"] is True
    assert teardown["runtime_cleanup_finished"]["ok"] is True
    assert teardown["dedicated_qthread"]["created"] is True
    assert teardown["dedicated_qthread"]["running_before_close"] is True
    assert teardown["dedicated_qthread"]["finished_signal_observed"] is True
    assert teardown["dedicated_qthread"]["running_after_cleanup"] is False
    assert teardown["gui_thread_blocking_wait_used"] is False
    assert teardown["observation_method"] == "qt_signals_and_event_loop"
    assert teardown["passed"] is True

    metric_transition = payload["metric_tab_transition"]
    assert metric_transition["passed"] is True
    assert metric_transition["pre_first_epoch"]["empty_state_visible"] is True
    assert metric_transition["pre_first_epoch"]["canvas_visible"] is False
    assert metric_transition["pre_first_epoch"]["epochs"] == []
    assert metric_transition["first_data"]["empty_state_visible"] is False
    assert metric_transition["first_data"]["canvas_visible"] is True
    assert metric_transition["first_data"]["epochs"] == [1]
    assert metric_transition["first_data"]["train_values"] == [72.0]
    assert metric_transition["first_data"]["validation_values"] == [68.0]
    assert metric_transition["first_data"]["plotted_series"] == 2
    assert metric_transition["transition_observed"] is True
    for state in ("pre_first_epoch", "first_data"):
        evidence = metric_transition[state]
        assert evidence["render_content"]["passed"] is True
        assert (tmp_path / evidence["file"]).is_file()

    stored = json.loads((tmp_path / "walkthrough.json").read_text(encoding="utf-8"))
    assert stored["source_fingerprint"] == payload["source_fingerprint"]
    assert stored["capture_source"] == payload["capture_source"]
    readme = (tmp_path / README_ARTIFACT).read_text(encoding="utf-8")
    assert "visual reviewer verdict: `not adjudicated by this script`" in readme
    assert "capture_chatpanel_ui_ux_walkthrough.py" in readme
    assert "synthetic pixmap scaling" in readme.lower()
    assert "does not demonstrate native display scaling" in readme.lower()


def test_validate_payload_rejects_one_failed_geometry_check(qapp, tmp_path) -> None:
    payload = capture_walkthrough(qapp, tmp_path)
    broken = copy.deepcopy(payload)
    broken["screens"][0]["checks"]["no_horizontal_scroll"] = False

    failures = validate_payload(broken)

    assert "desktop_conversation_states: no_horizontal_scroll" in failures

    blank = copy.deepcopy(payload)
    blank["screens"][0]["render_content"]["passed"] = False
    blank_failures = validate_payload(blank)
    assert (
        "desktop_conversation_states: rendered UI content is blank or incomplete"
        in blank_failures
    )

    drifted = copy.deepcopy(payload)
    drifted["capture_source"]["fingerprint_at_completion"] = "changed-during-capture"
    drifted["capture_source"]["stable"] = False
    drift_failures = validate_payload(drifted)
    assert "source changed during capture" in "; ".join(drift_failures).lower()

    stale = copy.deepcopy(payload)
    stale["source_fingerprint"] = "stale-artifact-source"
    stale_failures = validate_payload(stale)
    assert "stale for the current source" in "; ".join(stale_failures).lower()

    stale_manifest = copy.deepcopy(payload)
    stale_manifest["source_files"][0]["sha256"] = "0" * 64
    manifest_failures = validate_payload(stale_manifest)
    assert "source manifest is stale" in "; ".join(manifest_failures).lower()

    first_paint = copy.deepcopy(payload)
    first_paint["first_paint_320_contract"]["standalone"]["checks"][
        "mode_selector_visible"
    ] = False
    first_paint["first_paint_320_contract"]["standalone"]["passed"] = False
    first_paint["first_paint_320_contract"]["passed"] = False
    first_paint_failures = validate_payload(first_paint)
    assert "standalone first-paint" in "; ".join(first_paint_failures).lower()

    incomplete_teardown = copy.deepcopy(payload)
    incomplete_teardown["teardown"]["runtime_cleanup_finished"]["observed"] = False
    incomplete_teardown["teardown"]["passed"] = False
    teardown_failures = validate_payload(incomplete_teardown)
    assert "teardown" in "; ".join(teardown_failures).lower()

    stale_metric_transition = copy.deepcopy(payload)
    stale_metric_transition["metric_tab_transition"]["first_data"][
        "empty_state_visible"
    ] = True
    stale_metric_transition["metric_tab_transition"]["passed"] = False
    metric_failures = validate_payload(stale_metric_transition)
    assert "metric" in "; ".join(metric_failures).lower()


def test_image_content_gate_rejects_blank_canvas_and_required_regions(tmp_path) -> None:
    path = tmp_path / "blank-shell.png"
    Image.new("RGB", (240, 180), "#202020").save(path)

    evidence = image_content_evidence(
        path,
        required_regions={
            "shell": (0, 0, 240, 180),
            "transcript": (120, 0, 120, 130),
            "action": (120, 130, 120, 50),
        },
    )

    assert evidence["passed"] is False
    assert evidence["full_frame"]["passed"] is False
    assert all(region["passed"] is False for region in evidence["regions"].values())


def test_mode_description_participates_in_overflow_and_geometry_evidence(
    qapp,
) -> None:
    panel = ChatPanel()
    panel.resize(320, 520)
    panel.set_runtime_state("ready")
    panel.show()
    qapp.processEvents()
    panel.mode_description_label.setFixedHeight(1)
    panel.mode_description_label.show()
    qapp.processEvents()

    overflow = human_evidence._assistant_text_overflow(panel)
    geometry = walkthrough_module._panel_relative_geometry(panel)

    assert "mode_description_label" in overflow
    assert geometry["mode_description"]["visible"] is True
    assert "inside_panel_on_all_sides" in geometry["mode_description"]
    panel.close()
    panel.deleteLater()
    qapp.processEvents()


def test_teardown_capture_has_no_qthread_blocking_wait_call() -> None:
    source_path = Path(walkthrough_module.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    wait_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "wait"
    ]

    assert wait_calls == []
