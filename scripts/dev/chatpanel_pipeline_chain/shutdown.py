"""Terminal evidence capture and bounded shutdown ownership."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import QApplication, QDialog

from scripts.dev.chatpanel_pipeline_chain.state import (
    PipelinePhase,
    PipelineWalkthroughState,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)


class PipelineShutdownCoordinator:
    """Own terminal evidence, screenshot capture, and process shutdown."""

    def __init__(
        self,
        *,
        app: Any,
        window: Any,
        service: Any,
        output_dir: Path,
        state: PipelineWalkthroughState,
        manager_provider: Callable[[], Any | None],
        capture_window: Callable[[Any, Path], int],
        collect_visible_messages: Callable[[Any], list[Any]],
        collect_executed_tools: Callable[[Any], list[dict[str, Any]]],
        publication_evidence: Callable[[Any], dict[str, Any]],
        structured_value: Callable[[Any], Any],
        validate_payload: Callable[[dict[str, Any]], tuple[bool, str]],
        schedule: Callable[[int, Callable[[], None]], None],
        now: Callable[[], float],
        poll_interval_ms: int = 250,
        shutdown_grace_seconds: float = 20.0,
        terminal_screenshot_name: str = "chatpanel-pipeline-chain-terminal.png",
        failure_screenshot_name: str = "chatpanel-pipeline-chain-failure.png",
    ) -> None:
        self._app = app
        self._window = window
        self._service = service
        self._output_dir = output_dir
        self._state = state
        self._manager_provider = manager_provider
        self._capture_window = capture_window
        self._collect_visible_messages = collect_visible_messages
        self._collect_executed_tools = collect_executed_tools
        self._publication_evidence = publication_evidence
        self._structured_value = structured_value
        self._validate_payload = validate_payload
        self._schedule = schedule
        self._now = now
        self._poll_interval_ms = poll_interval_ms
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._terminal_screenshot_name = terminal_screenshot_name
        self._failure_screenshot_name = failure_screenshot_name

    def fail(self, reason: str) -> None:
        if self._state.terminal_started:
            return
        self._state.status = "failed"
        self._state.failure_reason = reason
        self.finish()

    def finish(self) -> None:
        if self._state.terminal_started:
            return
        self._state.terminal_started = True
        self._state.advance(PipelinePhase.FINALIZING)
        self._state.elapsed_seconds = round(
            self._now() - self._state.started_at,
            3,
        )
        self._collect_terminal_evidence()
        self._validate_running_result()
        self._capture_terminal_screenshot()
        self._close_product_dialogs()
        self._state.shutdown = {"status": "closing", "detail": ""}
        self._state.shutdown_deadline = self._now() + self._shutdown_grace_seconds
        self._state.advance(PipelinePhase.SHUTTING_DOWN)
        self._window.close()
        self._schedule(self._poll_interval_ms, self.wait_for_shutdown)

    def _collect_terminal_evidence(self) -> None:
        manager = self._manager_provider()
        panel = manager.chat_panel if manager is not None else None
        controller = manager.agent_controller if manager is not None else None
        if panel is not None:
            self._state.visible_messages = [
                message.__dict__ for message in self._collect_visible_messages(panel)
            ]
            self._state.send_button_text = panel.send_btn.text()
            self._state.send_button_enabled = panel.send_btn.isEnabled()
            self._state.input_enabled = panel.input_field.isEnabled()
        if controller is not None:
            self._state.executed_tools = self._collect_executed_tools(
                controller.metrics
            )
            self._state.controller_history = self._structured_value(controller.history)
        runtime_snapshot = (
            manager.assistant_runtime.current
            if manager is not None
            else AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.IDLE,
                initialized=False,
            )
        )
        snapshot = self._structured_value(runtime_snapshot)
        self._state.runtime_snapshot = snapshot if isinstance(snapshot, dict) else {}
        try:
            self._state.final_state = self._service.get_state().to_dict()
        except Exception:
            self._state.final_state = {}
        self._state.final_publication = self._publication_evidence(self._service)
        self._state.chat_processing = bool(
            manager is not None and manager.chat_controller.is_processing
        )
        self._state.controller_processing = bool(
            controller is not None and getattr(controller, "is_processing", False)
        )

    def _validate_running_result(self) -> None:
        if self._state.status != "running":
            return
        ok, reason = self._validate_payload(self._state.validation_payload())
        self._state.status = "passed" if ok else "failed"
        self._state.failure_reason = "" if ok else reason

    def _capture_terminal_screenshot(self) -> None:
        screenshot_name = (
            self._terminal_screenshot_name
            if self._state.status == "passed"
            else self._failure_screenshot_name
        )
        screenshot_path = self._output_dir / screenshot_name
        if self._capture_window(self._window, screenshot_path) == 0:
            self._state.terminal_screenshot = str(screenshot_path)
            if self._state.status != "passed":
                self._state.failure_screenshot = str(screenshot_path)
            return
        if self._state.status == "passed":
            self._state.status = "failed"
            self._state.failure_reason = "Terminal screenshot could not be captured."

    def _close_product_dialogs(self) -> None:
        for widget in QApplication.topLevelWidgets():
            if widget is self._window or not isinstance(widget, QDialog):
                continue
            if widget.isVisible():
                widget.reject()

    def wait_for_shutdown(self) -> None:
        manager = self._manager_provider()
        try:
            visible = self._window.isVisible()
            lifecycle_state = (
                manager.assistant_runtime.state.value
                if manager is not None
                else "closed"
            )
        except RuntimeError:
            visible = False
            lifecycle_state = "closed"

        if not visible and lifecycle_state == "closed":
            self._state.shutdown = {"status": "completed", "detail": ""}
            self._state.advance(PipelinePhase.COMPLETED)
            self._app.quit()
            return
        if self._now() >= self._state.shutdown_deadline:
            detail = (
                "Assistant or window shutdown exceeded "
                f"{self._shutdown_grace_seconds:.0f} seconds."
            )
            self._state.shutdown = {"status": "timed_out", "detail": detail}
            self._state.status = "failed"
            self._state.failure_reason = (
                f"{self._state.failure_reason} {detail}".strip()
            )
            if manager is not None:
                with suppress(RuntimeError):
                    manager.close()
            self._state.advance(PipelinePhase.COMPLETED)
            self._app.quit()
            return
        self._window.close()
        self._schedule(self._poll_interval_ms, self.wait_for_shutdown)
