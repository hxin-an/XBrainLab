from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QLabel

from scripts.dev import capture_chatpanel_ui_ux_walkthrough as walkthrough_module
from scripts.dev.capture_chatpanel_ui_ux_walkthrough import (
    ASSISTANT_SETTINGS_SCREEN_FILES,
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
    assert tuple(spec.filename for spec in SCENARIOS) == EXPECTED_SCREEN_FILES[:-4]
    assert EXPECTED_SCREEN_FILES[-4:] == (
        "main-window-dock-420-action-visible.png",
        "main-window-dock-420-action-click.png",
        "main-window-dock-420-stopping.png",
        "main-window-dock-420-command-running.png",
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
    multiline = next(
        spec for spec in SCENARIOS if spec.review_state == "multiline_composer"
    )
    assert multiline.logical_width == 320
    assert multiline.expected_send_enabled is True
    assert multiline.expected_composer_text.count("\n") == 2
    assert multiline.minimum_composer_height >= 68
    assert any(
        spec.logical_width == 320
        and spec.logical_height == 520
        and spec.review_state == "long_clarification_action"
        for spec in SCENARIOS
    )
    dpi_evidence = [spec for spec in SCENARIOS if spec.review_state == "dpi_evidence"]
    assert [spec.logical_width for spec in dpi_evidence] == [320, 420, 760]
    assert all(spec.render_pixel_ratio == 1.0 for spec in dpi_evidence)
    assert all(spec.required_kinds == ("user", "error") for spec in dpi_evidence)
    assert all(spec.confirmation_visible for spec in dpi_evidence)
    assert all(spec.expected_confirmation_values for spec in dpi_evidence)
    assert any(
        spec.logical_width == 320
        and spec.logical_height == 650
        and spec.review_state == "long_clarification_action"
        for spec in SCENARIOS
    )
    assert any(
        spec.logical_width == 320
        and spec.confirmation_visible
        and spec.scroll_to_bottom
        and spec.filename == "narrow-setting-change-confirmation-max-content.png"
        for spec in SCENARIOS
    )
    message_boundaries = next(
        spec for spec in SCENARIOS if spec.review_state == "message_content_boundaries"
    )
    assert message_boundaries.logical_width == 320
    assert message_boundaries.scroll_to_bottom is True
    assert message_boundaries.required_kinds == ("user", "assistant")
    assert DEFAULT_OUTPUT_DIR == (
        walkthrough_module.ROOT / "build" / "dev-artifacts" / "chatpanel-ui-ux"
    )
    assert ASSISTANT_SETTINGS_SCREEN_FILES == (
        "assistant-settings-collapsed.png",
        "assistant-settings-advanced.png",
    )


def test_source_fingerprint_manifest_covers_every_runtime_capture_owner() -> None:
    assert {
        "scripts/dev/capture_chatpanel_ui_ux_walkthrough.py",
        "scripts/dev/active_checkout.py",
        "scripts/dev/human_like_walkthrough/evidence.py",
        "pyproject.toml",
        "poetry.lock",
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
        "XBrainLab/ui/dialogs/model_settings_dialog.py",
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
    provenance = payload["runtime_import_provenance"]
    assert provenance["root_matches_capture"] is True
    assert provenance["all_sources_under_root"] is True
    assert all(record["under_root"] for record in provenance["modules"])
    assert payload["native_display_scaling_observed"] is False
    assert payload["render_scale_evidence"] == (
        "observed_widget_dpr_with_labeled_synthetic_pixmap_probe"
    )
    assert payload["render_readiness"] == {
        "required_consecutive_content_frames": 2,
        "normalized_png_color_mode": "RGB",
        "real_widget_capture_method": "QWidget.grab",
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
        for required_control in ("composer", "send"):
            assert geometry[required_control]["inside_panel_on_all_sides"] is True
            assert all(geometry[required_control]["sides"].values()), geometry[
                required_control
            ]
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
    assert dock["assistant_usable_width"] == 420
    assert dock["action_click"]["clicked"] is True
    assert dock["action_click"]["label"] == "Open Dataset"
    assert dock["action_click"]["history_source"] == "live_correlated_response"
    assert dock["action_click"]["restored_actions_inert"] is True
    assert dock["action_click"]["presentation_identity_from_ui"] is True
    assert dock["action_click"]["workflow_panel_opened"] is True
    assert dock["action_click"]["before_panel_index"] == 1
    assert dock["action_click"]["after_panel_index"] == 0
    assert dock["action_click"]["before_panel_materialized"] is True
    assert dock["action_click"]["after_panel_materialized"] is True
    assert dock["action_click"]["before_placeholder_visible"] is False
    assert dock["action_click"]["after_placeholder_visible"] is False
    assert dock["states"]["cancellable"]["button_text"] == "Stop"
    assert dock["states"]["cancellable"]["button_enabled"] is True
    assert dock["states"]["stopping"]["button_text"] == "Stopping"
    assert dock["states"]["stopping"]["button_enabled"] is False
    assert dock["states"]["stopping"]["late_activity_latched"] is True
    assert dock["states"]["application_command"]["button_text"] == "Working"
    assert dock["states"]["application_command"]["button_enabled"] is False

    assistant_settings = payload["assistant_settings"]
    assert assistant_settings["passed"] is True
    assert (
        tuple(screen["file"] for screen in assistant_settings["screens"])
        == ASSISTANT_SETTINGS_SCREEN_FILES
    )
    for screen in assistant_settings["screens"]:
        assert all(screen["checks"].values()), screen
        settings_path = tmp_path / screen["file"]
        assert settings_path.is_file()
        with Image.open(settings_path) as captured:
            assert list(captured.size) == screen["pixel_size"]
            assert captured.mode == screen["png_color_mode"] == "RGB"

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
        assert evidence["manual_mode_selector_present"] is False
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
    assert teardown["initial_close_call_duration_ms"] < 100
    assert teardown["gui_heartbeat"]["count_during_cleanup"] >= 2
    assert teardown["gui_heartbeat"]["max_gap_ms"] < 100
    assert teardown["gui_heartbeat"]["responsive"] is True
    assert (
        teardown["observation_method"]
        == "qt_signals_event_loop_heartbeat_and_close_latency"
    )
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
    assert "synthetic pixmap probe" in readme.lower()
    assert "does not demonstrate windows native dpi" in readme.lower()


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
        "manual_mode_selector_absent"
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

    broken_settings = copy.deepcopy(payload)
    broken_settings["assistant_settings"]["screens"][0]["checks"][
        "buttons_text_only"
    ] = False
    broken_settings["assistant_settings"]["passed"] = False
    settings_failures = validate_payload(broken_settings)
    assert "assistant settings" in "; ".join(settings_failures).lower()

    screenshot_path = tmp_path / payload["screens"][0]["file"]
    screenshot_path.write_bytes(b"tampered screenshot")
    screenshot_failures = validate_payload(payload)
    assert "screenshot hash does not match" in "; ".join(screenshot_failures).lower()


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


def test_image_content_gate_uses_font_tolerant_profile_only_for_text_regions(
    tmp_path,
) -> None:
    path = tmp_path / "painted-text-region.png"
    image = Image.new("RGB", (240, 180), "#202020")
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(
        ("#303030", "#404040", "#505050", "#606060", "#707070", "#808080", "#909090")
    ):
        draw.rectangle((index * 20, 80, index * 20 + 19, 179), fill=color)
    text_bounds = (20, 20, 180, 40)
    draw.rectangle((20, 20, 199, 59), fill="#202020")
    for left in range(28, 192, 24):
        draw.rectangle((left, 30, left + 11, 45), fill="#eeeeee")
    image.save(path)

    generic = image_content_evidence(
        path,
        required_regions={"empty_state": text_bounds},
    )
    text_profile = image_content_evidence(
        path,
        required_regions={"empty_state": text_bounds},
        text_region_names=("empty_state",),
    )

    assert generic["regions"]["empty_state"]["passed"] is False
    assert text_profile["passed"] is True
    assert text_profile["regions"]["empty_state"] == {
        **generic["regions"]["empty_state"],
        "passed": True,
    }


def test_image_content_gate_accepts_semantic_text_only_empty_state(tmp_path) -> None:
    path = tmp_path / "text-only-empty-state.png"
    image = Image.new("RGB", (240, 180), "#202020")
    ImageDraw.Draw(image).rectangle((40, 82, 199, 97), fill="#eeeeee")
    image.save(path)

    evidence = image_content_evidence(
        path,
        required_regions={"empty_state": (0, 0, 240, 180)},
        text_region_names=("empty_state",),
    )

    assert evidence["passed"] is True
    assert evidence["full_frame"]["color_count"] == 2
    assert evidence["regions"]["empty_state"]["passed"] is True


def test_scaled_child_regions_maps_logical_geometry_to_physical_pixels(
    qapp,
) -> None:
    root = ChatPanel()
    root.resize(320, 520)
    root.show()
    qapp.processEvents()

    child = root.input_field
    origin = child.mapTo(root, child.rect().topLeft())
    regions = walkthrough_module._scaled_child_regions(
        root,
        {"composer": child},
        pixel_width=400,
        pixel_height=650,
    )

    assert regions["composer"] == (
        round(origin.x() * 1.25),
        round(origin.y() * 1.25),
        round(child.width() * 1.25),
        round(child.height() * 1.25),
    )
    root.close()
    root.deleteLater()
    qapp.processEvents()


def test_real_widget_capture_records_observed_device_pixel_ratio(
    qapp,
    tmp_path,
) -> None:
    panel = ChatPanel()
    panel.resize(320, 520)
    panel.set_runtime_state("ready")
    panel.show()
    qapp.processEvents()

    evidence = walkthrough_module._capture_widget(
        panel,
        tmp_path / "observed-dpr.png",
        render_pixel_ratio=1.0,
    )

    observed_dpr = panel.devicePixelRatioF()
    assert evidence["capture_method"] == "widget_grab"
    assert evidence["capture_device_pixel_ratio"] == observed_dpr
    assert evidence["render_pixel_ratio"] == observed_dpr
    assert evidence["pixel_size"] == [
        int(panel.width() * observed_dpr + 0.5),
        int(panel.height() * observed_dpr + 0.5),
    ]
    panel.close()
    panel.deleteLater()
    qapp.processEvents()


def test_product_panel_does_not_expose_legacy_mode_selector(qapp) -> None:
    panel = ChatPanel()
    panel.resize(320, 520)
    panel.set_runtime_state("ready")
    panel.show()
    qapp.processEvents()
    overflow = human_evidence._assistant_text_overflow(panel)
    geometry = walkthrough_module._panel_relative_geometry(panel)

    assert "mode_description_label" not in overflow
    assert "mode_control" not in geometry
    assert "mode_description" not in geometry
    assert not hasattr(panel, "mode_selector_widget")
    panel.close()
    panel.deleteLater()
    qapp.processEvents()


def test_send_button_renders_its_visible_command_text(qapp) -> None:
    panel = ChatPanel()
    panel.resize(320, 520)
    panel.set_runtime_state("ready")
    panel.show()
    qapp.processEvents()

    assert panel.send_btn.text() == "Send"
    assert panel.send_btn.accessibleName() == "Send request"
    assert panel.send_btn.icon().isNull() is True
    assert human_evidence._button_renders_text(panel.send_btn) is True
    assert "send_btn" not in human_evidence._assistant_text_overflow(panel)
    send_record = next(
        record
        for record in walkthrough_module._button_evidence(panel)[0]
        if record["name"] == "AssistantSendButton"
    )
    assert send_record["text_rendered"] is True
    assert send_record["text_fits"] is True

    panel.close()
    panel.deleteLater()
    qapp.processEvents()


def test_confirmation_card_labels_participate_in_overflow_evidence(qapp) -> None:
    from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest

    panel = ChatPanel()
    panel.resize(320, 680)
    panel.set_runtime_state("ready")
    panel.show_confirmation_request(
        AgentConfirmationRequest.for_action(
            command_name="configure_training",
            params={"batch_size": 16},
            action_label="Apply change",
            description="Reduce GPU memory pressure before training.",
            destructive=False,
            publication_generation=7,
        ),
        current_values={"Batch size": "32"},
    )
    panel.show()
    qapp.processEvents()
    panel.confirmation_card_widget.reason_label.setFixedHeight(1)
    qapp.processEvents()

    overflow = human_evidence._assistant_text_overflow(panel)

    assert "confirmation_card/reason_label" in overflow
    panel.close()
    panel.deleteLater()
    qapp.processEvents()


def test_wordwrapped_label_reports_unbreakable_token_overflow(qapp) -> None:
    label = QLabel("W" * 160)
    label.setWordWrap(True)
    label.resize(230, 200)
    label.show()
    qapp.processEvents()

    assert human_evidence._label_text_exceeds_bounds(label) is True
    label.close()
    label.deleteLater()
    qapp.processEvents()


def test_product_assistant_teardown_owners_have_no_blocking_wait_call() -> None:
    root = Path(walkthrough_module.__file__).resolve().parents[2]
    source_paths = (
        root / "XBrainLab/ui/components/agent_manager.py",
        root / "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
        root / "XBrainLab/ui/components/assistant_command_dispatcher.py",
        root / "XBrainLab/ui/components/assistant_runtime_coordinator.py",
    )
    blocking_calls: list[str] = []
    for source_path in source_paths:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        blocking_calls.extend(
            f"{source_path.name}:{node.lineno}:{node.func.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"wait", "sleep", "msleep", "usleep"}
        )

    assert blocking_calls == []
