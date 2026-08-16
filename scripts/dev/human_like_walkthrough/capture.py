"""Full-dock GUI-with-Agent walkthrough capture."""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

from scripts.dev.capture_chatpanel_local_walkthrough import collect_visible_messages
from scripts.dev.human_like_walkthrough.contract import (
    ASSISTANT_BLOCKED_REQUEST,
    ASSISTANT_CANCEL_CONFIRMATION_REQUEST,
    ASSISTANT_CLARIFICATION_REQUEST,
    ASSISTANT_CONFIRM_CONFIRMATION_REQUEST,
    ASSISTANT_ERROR_REQUEST,
    ASSISTANT_EXISTING_UI_REQUEST,
    ASSISTANT_NARROW_DOCK_WIDTH,
    ASSISTANT_NORMAL_REQUEST,
    ASSISTANT_PROCESSING_REQUEST,
    ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS,
    ASSISTANT_STANDARD_DOCK_WIDTH,
    ASSISTANT_SUCCESS_REQUEST,
)
from scripts.dev.human_like_walkthrough.driver import (
    WalkthroughAssistantController,
    append_chat_transcript,
    click_assistant_control,
    drive_assistant_request,
    install_walkthrough_assistant,
)
from scripts.dev.human_like_walkthrough.evidence import (
    assistant_dock_evidence,
    assistant_error_evidence,
    assistant_main_window_evidence,
    assistant_main_window_handoff_evidence,
    assistant_notice_evidence,
    assistant_processing_evidence,
    assistant_restored_state,
    assistant_runtime_evidence,
    assistant_signal_path_evidence,
    chat_panel_geometry,
    evaluation_plot_readability_evidence,
    workflow_handoff_product_copy_evidence,
)
from XBrainLab.backend.application import NewSessionCommand, QueryStateCommand
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import model_snapshot_path
from XBrainLab.ui.chat.action_card import AssistantConfirmationCard
from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog


@dataclass(frozen=True)
class AssistantCaptureDependencies:
    """Generic walkthrough operations supplied by the orchestration entry."""

    capture_named: Callable[[QWidget, Path, str], str]
    visible_text_snapshot: Callable[[QWidget], list[str]]
    button_state_snapshot: Callable[[QWidget], list[dict[str, Any]]]
    compact_state: Callable[[Any], dict[str, Any]]
    command_summary: Callable[[Any], dict[str, Any]]
    set_window_geometry: Callable[[QWidget, QSize], None]
    settle_widget_for_capture: Callable[..., None]
    standard_window_size: QSize
    narrow_window_size: QSize


@dataclass
class AssistantSettingsIsolation:
    """Temporary settings/cache paths and persisted recovery evidence."""

    settings_path: Path
    cache_root: Path
    evidence: dict[str, Any]


def _file_digest(path: Path) -> str:
    if not path.exists():
        return "<missing>"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_sequence_since_failure(
    controller: WalkthroughAssistantController,
) -> list[str]:
    phases = [
        event.removeprefix("runtime:")
        for event in controller.events
        if event.startswith("runtime:")
    ]
    failed_indices = [index for index, phase in enumerate(phases) if phase == "failed"]
    return phases[failed_indices[-1] :] if failed_indices else phases


@contextmanager
def isolated_assistant_settings():
    """Keep the real settings dialog away from the user's host configuration."""
    host_settings_path = Path(LLMConfig._default_settings_path())
    host_digest = _file_digest(host_settings_path)
    with tempfile.TemporaryDirectory(
        prefix="xbrainlab-assistant-settings-"
    ) as temp_dir:
        root = Path(temp_dir)
        settings_path = root / "settings.json"
        cache_root = root / "model-cache"
        selected_model = LLMConfig.default_local_model_id()
        selected_cache = model_snapshot_path(str(cache_root), selected_model)
        if selected_cache is None:
            raise RuntimeError(
                f"Walkthrough model has no pinned cache layout: {selected_model}."
            )
        selected_cache.mkdir(parents=True, exist_ok=True)
        for name in ("config.json", "tokenizer_config.json"):
            (selected_cache / name).write_text("{}", encoding="utf-8")
        # A sparse file keeps the isolated capture cheap while making the visible
        # cache usage consistent with the installed-model state.
        with (selected_cache / "model.safetensors").open("wb") as model_file:
            model_file.truncate(256 * 1024 * 1024)

        load_from_file = LLMConfig.load_from_file.__func__

        def load_isolated_config(
            cls,
            filepath: str | None = None,
        ) -> LLMConfig | None:
            config = load_from_file(cls, filepath)
            if config is not None:
                config.cache_dir = str(cache_root)
            return config

        isolation = AssistantSettingsIsolation(
            settings_path=settings_path,
            cache_root=cache_root,
            evidence={
                "open_settings_clicked": False,
                "dialog_opened": False,
                "activate_clicked": False,
                "save_observed": False,
                "isolated_config": True,
                "host_config_unchanged": False,
                "runtime_sequence": [],
                "settings_screenshot": "",
            },
        )
        with (
            patch.object(
                LLMConfig,
                "_default_settings_path",
                staticmethod(lambda: str(settings_path)),
            ),
            patch.object(
                LLMConfig,
                "_legacy_settings_path",
                staticmethod(lambda: str(root / "legacy-settings.json")),
            ),
            patch.object(
                LLMConfig,
                "load_from_file",
                classmethod(load_isolated_config),
            ),
        ):
            yield isolation
        isolation.evidence["host_config_unchanged"] = (
            _file_digest(host_settings_path) == host_digest
        )


def set_assistant_dock_width(
    app: QApplication,
    window: Any,
    dock: QWidget,
    width: int,
    *,
    settle_widget_for_capture: Callable[..., None],
) -> None:
    """Resize a docked assistant deterministically before full-dock capture."""
    dock.setMinimumWidth(ASSISTANT_NARROW_DOCK_WIDTH)
    window.resizeDocks([dock], [width], Qt.Orientation.Horizontal)
    app.processEvents()
    window.resizeDocks([dock], [width], Qt.Orientation.Horizontal)
    settle_widget_for_capture(app, dock, wait_ms=40)


def _chat_phase(
    phase: str,
    screenshot: str,
    panel: QWidget,
    service: Any,
    notes: dict[str, Any],
    *,
    dock: QWidget,
    controller: WalkthroughAssistantController,
    dependencies: AssistantCaptureDependencies,
) -> dict[str, Any]:
    """Build full-dock evidence from the manager/controller signal path."""
    phase_notes = dict(notes)
    phase_notes.setdefault(
        "evidence_scope",
        "agent_manager_qt_signal_product_evidence",
    )
    phase_notes["assistant_signal_path"] = assistant_signal_path_evidence(controller)
    phase_notes["assistant_notice"] = assistant_notice_evidence(panel)
    phase_notes["assistant_dock"] = assistant_dock_evidence(dock, panel)
    geometry = chat_panel_geometry(panel)
    if geometry:
        phase_notes["chat_geometry"] = geometry
    return {
        "phase": phase,
        "screenshot": screenshot,
        "visible_text": dependencies.visible_text_snapshot(dock),
        "button_state": dependencies.button_state_snapshot(dock),
        "workflow_state": dependencies.compact_state(service.get_state()),
        "notes": phase_notes,
    }


def run_assistant_walkthrough(
    app: QApplication,
    window: Any,
    service: Any,
    screenshots: dict[str, str],
    phases: list[dict[str, Any]],
    output_dir: Path,
    user_transcript: list[dict[str, str]],
    tool_transcript: list[dict[str, Any]],
    *,
    dependencies: AssistantCaptureDependencies,
) -> dict[str, Any]:
    """Drive loading, feedback, error, and dock-layout product states."""
    with isolated_assistant_settings() as settings_isolation:
        if window.agent_manager is None:
            window.init_agent()
            app.processEvents()
        manager = window.agent_manager
        if manager is None:
            raise RuntimeError("Agent manager was not initialized.")
        panel = manager.chat_panel
        dock = manager.chat_dock
        if panel is None or dock is None:
            raise RuntimeError("ChatPanel was not initialized.")

        controller = install_walkthrough_assistant(manager)
        open_close_states = _exercise_open_close(app, dock)
        set_assistant_dock_width(
            app,
            window,
            dock,
            ASSISTANT_STANDARD_DOCK_WIDTH,
            settle_widget_for_capture=dependencies.settle_widget_for_capture,
        )

        _capture_runtime_states(
            app,
            manager,
            controller,
            dock,
            panel,
            service,
            screenshots,
            phases,
            output_dir,
            open_close_states,
            settings_isolation,
            dependencies,
        )
    _capture_request_states(
        app,
        manager,
        controller,
        dock,
        panel,
        service,
        screenshots,
        phases,
        output_dir,
        tool_transcript,
        dependencies,
    )
    _capture_narrow_layout(
        app,
        window,
        controller,
        dock,
        panel,
        service,
        screenshots,
        phases,
        output_dir,
        dependencies,
    )

    visible_messages = [message.__dict__ for message in collect_visible_messages(panel)]
    result = {
        "open_close_states": open_close_states,
        "visible_messages": visible_messages,
        "send_button_text": panel.send_btn.text(),
        "send_button_enabled": panel.send_btn.isEnabled(),
        "input_enabled": panel.input_field.isEnabled(),
        "processing": manager.chat_controller.is_processing,
        "assistant_driver": "agent_manager_qt_signals",
        "controller_events": list(controller.events),
        "assistant_settings_recovery": dict(settings_isolation.evidence),
    }
    append_chat_transcript(user_transcript, manager.chat_controller.messages)
    manager.start_new_conversation()
    app.processEvents()
    return result


def _exercise_open_close(
    app: QApplication,
    dock: QWidget,
) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    dock.show()
    app.processEvents()
    for index in range(2):
        states.append({"step": f"open-{index + 1}", "visible": dock.isVisible()})
        dock.close()
        app.processEvents()
        states.append({"step": f"close-{index + 1}", "visible": dock.isVisible()})
        dock.show()
        app.processEvents()
    return states


def _capture_runtime_states(
    app: QApplication,
    manager: Any,
    controller: WalkthroughAssistantController,
    dock: QWidget,
    panel: QWidget,
    service: Any,
    screenshots: dict[str, str],
    phases: list[dict[str, Any]],
    output_dir: Path,
    open_close_states: list[dict[str, Any]],
    settings_isolation: AssistantSettingsIsolation,
    dependencies: AssistantCaptureDependencies,
) -> None:
    controller.publish_runtime("idle")
    app.processEvents()
    _capture_phase(
        "assistant_runtime_idle",
        "assistant_idle_setup",
        {"assistant_runtime": assistant_runtime_evidence(panel)},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    controller.publish_runtime("loading")
    app.processEvents()
    _capture_phase(
        "assistant_runtime_loading",
        "assistant_loading",
        {"assistant_runtime": assistant_runtime_evidence(panel)},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    controller.publish_runtime_failure()
    app.processEvents()
    _capture_phase(
        "assistant_runtime_failed",
        "assistant_failed",
        {"assistant_runtime": assistant_runtime_evidence(panel)},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    _drive_settings_recovery(
        app,
        manager,
        controller,
        dock,
        panel,
        service,
        screenshots,
        phases,
        output_dir,
        settings_isolation,
        dependencies,
    )
    controller.complete_model_switch()
    app.processEvents()
    if manager.assistant_runtime.current.phase.value != "ready":
        raise RuntimeError(
            "Assistant runtime did not become ready after settings save."
        )
    settings_isolation.evidence["runtime_sequence"] = _runtime_sequence_since_failure(
        controller
    )
    if settings_isolation.evidence["runtime_sequence"] != [
        "failed",
        "loading",
        "ready",
    ]:
        raise RuntimeError(
            "Settings recovery did not publish failed -> loading -> ready."
        )
    manager.start_new_conversation()
    app.processEvents()
    _capture_phase(
        "assistant_runtime_ready",
        "assistant_ready",
        {
            "assistant_runtime": assistant_runtime_evidence(panel),
            "assistant_settings_recovery": settings_isolation.evidence,
        },
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )
    empty_screenshot = _capture_phase(
        "assistant_empty_state",
        "assistant_empty",
        {"open_close": open_close_states},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )
    repeated_open_close_phase = _chat_phase(
        "assistant_repeated_open_close",
        empty_screenshot,
        panel,
        service,
        {"open_close": open_close_states},
        dock=dock,
        controller=controller,
        dependencies=dependencies,
    )
    repeated_open_close_phase["alias_of"] = "assistant_empty_state"
    phases.append(repeated_open_close_phase)


def _drive_settings_recovery(
    app: QApplication,
    manager: Any,
    controller: WalkthroughAssistantController,
    dock: QWidget,
    panel: Any,
    service: Any,
    screenshots: dict[str, str],
    phases: list[dict[str, Any]],
    output_dir: Path,
    isolation: AssistantSettingsIsolation,
    dependencies: AssistantCaptureDependencies,
) -> None:
    """Open, capture, and save the real Assistant Settings dialog."""
    evidence = isolation.evidence
    callback_error: list[str] = []

    def interact_with_dialog() -> None:
        dialogs = [
            widget
            for widget in app.topLevelWidgets()
            if isinstance(widget, ModelSettingsDialog) and widget.isVisible()
        ]
        if len(dialogs) != 1:
            callback_error.append(
                f"Expected one Assistant Settings dialog, found {len(dialogs)}."
            )
            for widget in dialogs:
                widget.reject()
            return
        dialog = dialogs[0]
        evidence["dialog_opened"] = True
        evidence["dialog_title"] = dialog.windowTitle()
        initial_deadline = time.monotonic() + 20.0
        while dialog._persisted_config_pending and time.monotonic() < initial_deadline:
            app.processEvents()
            time.sleep(0.005)
        if dialog._persisted_config_pending:
            callback_error.append(
                "Assistant Settings initial model check did not finish."
            )
            dialog.reject()
            return

        selected_model = LLMConfig.default_local_model_id()
        selected_index = dialog.local_model_combo.findData(selected_model)
        if selected_index < 0:
            callback_error.append(
                f"Primary local model is missing from Assistant Settings: "
                f"{selected_model}."
            )
            dialog.reject()
            return
        dialog.config.cache_dir = str(isolation.cache_root)
        dialog.local_model_combo.setCurrentIndex(selected_index)
        dialog.check_local_model_status()
        deadline = time.monotonic() + 20.0
        while (
            dialog._pending_inspection_request_id is not None
            and time.monotonic() < deadline
        ):
            app.processEvents()
            time.sleep(0.005)
        if dialog._pending_inspection_request_id is not None:
            callback_error.append("Assistant Settings model check did not finish.")
            dialog.reject()
            return
        dialog.response_style_control.set_selected("precise", emit=True)
        dialog.update_validation_state()
        evidence["selected_model"] = str(dialog.local_model_combo.currentData() or "")
        evidence["selected_model_label"] = dialog.local_model_combo.currentText()
        evidence["controlled_temperature"] = dialog.temperature_spin.value()
        screenshot = dependencies.capture_named(
            dialog,
            output_dir,
            "assistant_settings",
        )
        screenshots["assistant_settings"] = screenshot
        evidence["settings_screenshot"] = screenshot
        if not dialog.btn_activate.isEnabled():
            callback_error.append("Assistant Settings Activate button was not enabled.")
            dialog.reject()
            return
        evidence["activate_clicked"] = True
        click_assistant_control(cast(QWidget, dialog.btn_activate))

    QTimer.singleShot(0, interact_with_dialog)
    evidence["open_settings_clicked"] = True
    click_assistant_control(cast(QWidget, panel.setup_btn))
    app.processEvents()
    if callback_error:
        raise RuntimeError(callback_error[0])
    if not isolation.settings_path.exists():
        raise RuntimeError("Assistant Settings did not save the isolated config.")
    saved = json.loads(isolation.settings_path.read_text(encoding="utf-8"))
    saved_local = saved.get("local", {})
    evidence["save_observed"] = (
        saved.get("generation", {}).get("temperature") == 0.2
        and bool(saved_local.get("enabled"))
        and saved_local.get("model_name") == LLMConfig.default_local_model_id()
    )
    if not evidence["save_observed"]:
        raise RuntimeError("Assistant Settings save did not preserve the test setting.")

    evidence["runtime_sequence"] = _runtime_sequence_since_failure(controller)
    if evidence["runtime_sequence"] != ["failed", "loading"]:
        raise RuntimeError("Settings save did not trigger assistant loading.")
    _capture_phase(
        "assistant_runtime_recovery_loading",
        "assistant_recovery_loading",
        {
            "assistant_runtime": assistant_runtime_evidence(panel),
            "assistant_settings_recovery": evidence,
        },
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )


def _capture_request_states(
    app: QApplication,
    manager: Any,
    controller: WalkthroughAssistantController,
    dock: QWidget,
    panel: Any,
    service: Any,
    screenshots: dict[str, str],
    phases: list[dict[str, Any]],
    output_dir: Path,
    tool_transcript: list[dict[str, Any]],
    dependencies: AssistantCaptureDependencies,
) -> None:
    drive_assistant_request(app, manager, ASSISTANT_NORMAL_REQUEST)
    app.processEvents()
    _capture_phase(
        "assistant_normal_message",
        "assistant_normal",
        {"outcome": "normal_response"},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    drive_assistant_request(
        app,
        manager,
        ASSISTANT_PROCESSING_REQUEST,
        expect_processing=True,
    )
    app.processEvents()
    processing_screenshot = _capture_screenshot(
        dock,
        output_dir,
        "assistant_processing",
        screenshots,
        dependencies,
    )
    processing_phase = _chat_phase(
        "assistant_processing_state",
        processing_screenshot,
        panel,
        service,
        {
            "assistant_processing": assistant_processing_evidence(
                panel,
                controller_processing=manager.chat_controller.is_processing,
            )
        },
        dock=dock,
        controller=controller,
        dependencies=dependencies,
    )
    phases.append(processing_phase)

    stop_message_start = len(manager.chat_controller.messages)
    click_assistant_control(cast(QWidget, panel.send_btn))
    app.processEvents()
    processing_phase["notes"]["stopping_state"] = assistant_processing_evidence(
        panel,
        controller_processing=manager.chat_controller.is_processing,
    )
    controller.complete_stop()
    app.processEvents()
    stop_terminal_messages = [
        str(message.get("content") or "")
        for message in manager.chat_controller.messages[stop_message_start:]
        if message.get("role") == "assistant"
    ]
    restored = assistant_restored_state(
        panel,
        controller_processing=manager.chat_controller.is_processing,
    )
    processing_phase["notes"]["restored_state"] = restored
    _capture_phase(
        "assistant_idle_after_stop",
        "assistant_idle",
        {
            "assistant_idle": restored,
            "assistant_cancelled_turn": {
                "terminal_messages": stop_terminal_messages,
            },
        },
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    drive_assistant_request(app, manager, ASSISTANT_CLARIFICATION_REQUEST)
    app.processEvents()
    _capture_phase(
        "assistant_missing_input_clarification",
        "assistant_clarification",
        {"clarification": "ambiguous workflow request"},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    blocked_result = service.execute(NewSessionCommand())
    tool_transcript.append(dependencies.command_summary(blocked_result))
    drive_assistant_request(app, manager, ASSISTANT_BLOCKED_REQUEST)
    app.processEvents()
    _capture_phase(
        "assistant_blocked_command",
        "assistant_blocked",
        {
            "blocked_reason": "active workflow replacement boundary",
            "blocked_command": dependencies.command_summary(blocked_result),
        },
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    query_state = service.execute(QueryStateCommand())
    tool_transcript.append(dependencies.command_summary(query_state))
    state_response = controller.configure_state_response(
        query_state,
        dependencies.compact_state(service.get_state()),
    )
    drive_assistant_request(app, manager, ASSISTANT_SUCCESS_REQUEST)
    app.processEvents()
    _capture_phase(
        "assistant_successful_tool_result",
        "assistant_success",
        {
            "query_state": dependencies.command_summary(query_state),
            "assistant_claims": {
                "command_result": dependencies.command_summary(query_state),
                "claims": list(state_response.claims),
                "response_text": state_response.text,
            },
        },
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    drive_assistant_request(app, manager, ASSISTANT_ERROR_REQUEST)
    app.processEvents()
    _capture_phase(
        "assistant_sanitized_error",
        "assistant_error",
        {"assistant_error": assistant_error_evidence(panel)},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    _capture_confirmation_interactions(
        app,
        manager,
        controller,
        dock,
        panel,
        service,
        screenshots,
        phases,
        output_dir,
        dependencies,
    )


def _capture_narrow_layout(
    app: QApplication,
    window: Any,
    controller: WalkthroughAssistantController,
    dock: QWidget,
    panel: QWidget,
    service: Any,
    screenshots: dict[str, str],
    phases: list[dict[str, Any]],
    output_dir: Path,
    dependencies: AssistantCaptureDependencies,
) -> None:
    controller.publish_runtime("idle")
    app.processEvents()
    dependencies.set_window_geometry(window, dependencies.narrow_window_size)
    set_assistant_dock_width(
        app,
        window,
        dock,
        ASSISTANT_NARROW_DOCK_WIDTH,
        settle_widget_for_capture=dependencies.settle_widget_for_capture,
    )
    _capture_phase(
        "assistant_narrow_panel",
        "assistant_narrow",
        {
            "width": window.width(),
            "dock_width": dock.width(),
            "assistant_runtime": assistant_runtime_evidence(panel),
        },
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )
    controller.publish_runtime("ready")
    app.processEvents()
    dependencies.set_window_geometry(window, dependencies.standard_window_size)
    set_assistant_dock_width(
        app,
        window,
        dock,
        ASSISTANT_STANDARD_DOCK_WIDTH,
        settle_widget_for_capture=dependencies.settle_widget_for_capture,
    )
    app.processEvents()


def _capture_confirmation_interactions(
    app: QApplication,
    manager: Any,
    controller: WalkthroughAssistantController,
    dock: QWidget,
    panel: Any,
    service: Any,
    screenshots: dict[str, str],
    phases: list[dict[str, Any]],
    output_dir: Path,
    dependencies: AssistantCaptureDependencies,
) -> None:
    """Exercise production manager routing for cancel, confirm, and UI handoff."""

    def reset_scenario(name: str) -> int:
        manager.start_new_conversation()
        app.processEvents()
        start_count = len(manager.chat_controller.messages)
        if start_count != 0:
            raise RuntimeError(f"Assistant {name} scenario did not start empty.")
        controller.events.append(f"scenario:{name}:started")
        return start_count

    def terminal_messages(start_index: int) -> list[str]:
        return [
            str(message.get("content") or "")
            for message in manager.chat_controller.messages[start_index:]
            if message.get("role") == "assistant"
        ]

    def card_decision(
        request: str,
        *,
        approved: bool,
        decision: str,
        scenario_name: str,
    ) -> dict[str, Any]:
        scenario_start_count = reset_scenario(scenario_name)
        start_index = len(manager.chat_controller.messages)
        execution_before = controller.confirmed_execution_count
        panel.input_field.setText(request)
        click_assistant_control(cast(QWidget, panel.send_btn))

        card = cast(
            AssistantConfirmationCard,
            panel.confirmation_card_widget,
        )
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            app.processEvents()
            if card.isVisibleTo(dock) and card.request_id:
                break
            time.sleep(0.005)
        if not card.isVisibleTo(dock) or not card.request_id:
            raise RuntimeError("Expected one inline confirmation card.")

        controller_request = controller.last_confirmation_request
        request_correlated = bool(
            controller_request and controller_request.request_id == card.request_id
        )
        card_state = {
            "opened": True,
            "title": card.title_label.text(),
            "request_id": card.request_id,
            "request_correlated": request_correlated,
            "primary_action": card.primary_button.text(),
            "secondary_action": card.secondary_button.text(),
            "waiting_surface": assistant_processing_evidence(
                panel,
                controller_processing=manager.chat_controller.is_processing,
            ),
        }
        if scenario_name == "confirmed":
            screenshot = dependencies.capture_named(
                dock,
                output_dir,
                "assistant_confirmation_card",
            )
            screenshots["assistant_confirmation_card"] = screenshot
            card_state["screenshot"] = screenshot

        decision_button = card.primary_button if approved else card.secondary_button
        click_assistant_control(cast(QWidget, decision_button))

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            app.processEvents()
            if (
                len(manager.chat_controller.messages) > start_index
                and not manager.chat_controller.is_processing
                and not card.isVisible()
            ):
                break
            time.sleep(0.005)
        if manager.chat_controller.is_processing or card.isVisible():
            raise RuntimeError(
                "Assistant confirmation did not reach one terminal UI state."
            )
        terminal = terminal_messages(start_index)
        normalized = [" ".join(item.split()).lower() for item in terminal]
        return {
            "request_kind": "production_confirmation_card",
            "decision": decision,
            "destructive": bool(
                controller.last_confirmation_request
                and controller.last_confirmation_request.destructive
            ),
            "card_opened": card_state["opened"],
            "card_title": card_state["title"],
            "card_request_id": card_state["request_id"],
            "request_correlated": card_state["request_correlated"],
            "primary_action": card_state["primary_action"],
            "secondary_action": card_state["secondary_action"],
            "waiting_surface": card_state["waiting_surface"],
            "card_screenshot": card_state.get("screenshot", ""),
            "terminal_messages": terminal,
            "confirmed_execution_count": (
                controller.confirmed_execution_count - execution_before
            ),
            "duplicate_terminal_message": len(normalized) != len(set(normalized)),
            "scenario_start_message_count": scenario_start_count,
            "scenario_message_count": len(manager.chat_controller.messages),
            "scenario_isolated": scenario_start_count == 0,
        }

    cancelled = card_decision(
        ASSISTANT_CANCEL_CONFIRMATION_REQUEST,
        approved=False,
        decision="cancelled",
        scenario_name="cancelled",
    )
    _capture_phase(
        "assistant_confirmation_cancelled",
        "assistant_cancelled",
        {"assistant_interaction": cancelled},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    confirmed = card_decision(
        ASSISTANT_CONFIRM_CONFIRMATION_REQUEST,
        approved=True,
        decision="confirmed",
        scenario_name="confirmed",
    )
    _capture_phase(
        "assistant_confirmation_confirmed",
        "assistant_confirmed",
        {"assistant_interaction": confirmed},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
    )

    scenario_start_count = reset_scenario("handoff")
    start_index = len(manager.chat_controller.messages)
    execution_before = controller.confirmed_execution_count
    drive_assistant_request(app, manager, ASSISTANT_EXISTING_UI_REQUEST)
    app.processEvents()
    terminal = terminal_messages(start_index)
    normalized = [" ".join(item.split()).lower() for item in terminal]
    request = controller.last_workflow_handoff
    resolution = controller.last_workflow_resolution
    main_window = manager.main_window
    main_window_handoff = assistant_main_window_handoff_evidence(
        main_window,
        dock,
        panel,
        expected_panel="Evaluation",
    )
    if (
        main_window_handoff["active_panel"] != "Evaluation"
        or main_window_handoff["active_index"]
        != main_window_handoff["evaluation_index"]
        or not main_window_handoff["evaluation_nav_checked"]
    ):
        raise RuntimeError("Typed assistant handoff did not activate Evaluation.")
    handoff = {
        "request_kind": "typed_workflow_ui_handoff",
        "decision": "opened_in_main_window",
        "handoff_kind": request.kind.value if request is not None else "",
        "command_name": request.command_name if request is not None else "",
        "request_id": request.request_id if request is not None else "",
        "decision_fields": list(request.decision_fields) if request is not None else [],
        "resolution_request_id": (
            resolution.request_id if resolution is not None else ""
        ),
        "resolution_command_name": (
            resolution.command_name if resolution is not None else ""
        ),
        "resolution_status": (
            resolution.status.value if resolution is not None else ""
        ),
        "resolution_decision_fields": (
            list(resolution.decision_fields) if resolution is not None else []
        ),
        "resolution_message": resolution.message if resolution is not None else "",
        "request_resolution_correlated": bool(
            request is not None
            and resolution is not None
            and request.request_id == resolution.request_id
            and request.command is resolution.command
            and request.decision_fields == resolution.decision_fields
        ),
        "terminal_messages": terminal,
        "confirmed_execution_count": (
            controller.confirmed_execution_count - execution_before
        ),
        "duplicate_terminal_message": len(normalized) != len(set(normalized)),
        "typed_handoff_emitted": "handoff:typed_emitted:evaluate" in controller.events,
        "typed_resolution_accepted": bool(
            resolution is not None
            and any(
                event.startswith("handoff:resolution_accepted:")
                for event in controller.events
            )
        ),
        "scenario_start_message_count": scenario_start_count,
        "scenario_message_count": len(manager.chat_controller.messages),
        "scenario_isolated": scenario_start_count == 0,
        "main_window_handoff": main_window_handoff,
        "product_copy": workflow_handoff_product_copy_evidence(),
    }
    _capture_phase(
        "assistant_existing_ui_handoff",
        "assistant_handoff",
        {"assistant_interaction": handoff},
        dock=dock,
        panel=panel,
        service=service,
        controller=controller,
        screenshots=screenshots,
        phases=phases,
        output_dir=output_dir,
        dependencies=dependencies,
        capture_target=main_window,
    )


def _capture_phase(
    phase_name: str,
    screenshot_key: str,
    notes: dict[str, Any],
    *,
    dock: QWidget,
    panel: QWidget,
    service: Any,
    controller: WalkthroughAssistantController,
    screenshots: dict[str, str],
    phases: list[dict[str, Any]],
    output_dir: Path,
    dependencies: AssistantCaptureDependencies,
    capture_target: QWidget | None = None,
) -> str:
    phase_notes = dict(notes)
    screenshot = _capture_screenshot(
        capture_target if capture_target is not None else dock,
        output_dir,
        screenshot_key,
        screenshots,
        dependencies,
    )
    full_window_key = ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS.get(phase_name)
    if full_window_key is not None:
        main_window = dock.window()
        if not isinstance(main_window, QWidget) or main_window is dock:
            raise RuntimeError(
                f"{phase_name} cannot capture its owning full main window."
            )
        full_window_screenshot = (
            screenshot
            if capture_target is main_window and screenshot_key == full_window_key
            else _capture_screenshot(
                main_window,
                output_dir,
                full_window_key,
                screenshots,
                dependencies,
            )
        )
        workflow_status = _observed_full_window_status(phase_name, phase_notes)
        main_window_state = assistant_main_window_evidence(
            main_window,
            dock,
            panel,
            state=phase_name,
            workflow_status=workflow_status,
        )
        main_window_state.update(
            {
                "screenshot_key": full_window_key,
                "screenshot": full_window_screenshot,
            }
        )
        if phase_name == "assistant_narrow_panel":
            main_window_state["evaluation_plot_readability"] = (
                evaluation_plot_readability_evidence(main_window)
            )
        phase_notes["assistant_main_window"] = main_window_state
    phases.append(
        _chat_phase(
            phase_name,
            screenshot,
            panel,
            service,
            phase_notes,
            dock=dock,
            controller=controller,
            dependencies=dependencies,
        )
    )
    return screenshot


def _observed_full_window_status(
    phase_name: str,
    notes: dict[str, Any],
) -> str:
    """Derive the recorded state from observed evidence instead of phase naming."""
    runtime = notes.get("assistant_runtime", {})
    runtime = runtime if isinstance(runtime, dict) else {}
    runtime_phase = str(runtime.get("phase") or "")
    if phase_name in {
        "assistant_runtime_idle",
        "assistant_runtime_loading",
        "assistant_runtime_failed",
        "assistant_runtime_ready",
        "assistant_narrow_panel",
    }:
        return "unavailable" if runtime_phase == "idle" else runtime_phase
    if phase_name == "assistant_blocked_command":
        result = notes.get("blocked_command", {})
        result = result if isinstance(result, dict) else {}
        return "blocked" if not bool(result.get("ok")) else "unexpected_success"
    if phase_name == "assistant_existing_ui_handoff":
        interaction = notes.get("assistant_interaction", {})
        interaction = interaction if isinstance(interaction, dict) else {}
        handoff = interaction.get("main_window_handoff", {})
        handoff = handoff if isinstance(handoff, dict) else {}
        return str(handoff.get("workflow_status") or "not_opened")
    return "unknown"


def _capture_screenshot(
    target: QWidget,
    output_dir: Path,
    screenshot_key: str,
    screenshots: dict[str, str],
    dependencies: AssistantCaptureDependencies,
) -> str:
    screenshot = dependencies.capture_named(target, output_dir, screenshot_key)
    screenshots[screenshot_key] = screenshot
    return screenshot
