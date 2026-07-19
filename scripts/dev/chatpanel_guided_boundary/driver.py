"""Qt driver for the real-model Guided Workflow UI handoff boundary."""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import QApplication, QDialog

from scripts.dev.chatpanel_guided_boundary.contracts import GuidedBoundaryHooks
from scripts.dev.chatpanel_guided_boundary.dialog import (
    capture_and_cancel_workflow_dialog,
)
from scripts.dev.chatpanel_guided_boundary.evidence import (
    GuidedBoundaryEvidenceAssembler,
)
from scripts.dev.chatpanel_guided_boundary.state import (
    GuidedBoundaryPhase,
    GuidedBoundaryState,
    GuidedTurnContext,
    reconcile_closed_event_loop,
)
from scripts.dev.chatpanel_guided_boundary.tool_trace import assemble_tool_attempts
from scripts.dev.chatpanel_guided_boundary.validation import (
    canonical_turn_calls,
    validate_auto_chain_boundary,
    validate_guided_boundary_payload,
)
from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def _application_result_succeeded(
    result: object,
    structured: object,
) -> bool:
    """Read success from the current command contract, with legacy fallback."""
    explicit_success = getattr(result, "success", None)
    if isinstance(explicit_success, bool):
        return explicit_success

    if isinstance(structured, Mapping):
        for key in ("ok", "success"):
            value = structured.get(key)
            if isinstance(value, bool):
                return value
        status = structured.get("status")
    else:
        status = getattr(result, "status", None)

    status_value = getattr(status, "value", status)
    return status_value == "ok"


def _validate_pre_shutdown_candidate(
    payload: Mapping[str, object],
) -> tuple[bool, str]:
    """Validate a completed candidate before its terminal status is committed."""
    candidate = dict(payload)
    candidate["status"] = "passed"
    candidate["failure_reason"] = ""
    return validate_guided_boundary_payload(
        candidate,
        require_shutdown=False,
    )


class GuidedBoundaryDriver:
    """Drive one real turn through a typed Data Import UI handoff."""

    def __init__(
        self,
        *,
        app: Any,
        window: Any,
        service: Any,
        output_dir: Path,
        timeout_seconds: int,
        state: GuidedBoundaryState,
        hooks: GuidedBoundaryHooks,
        poll_interval_ms: int = 250,
        shutdown_grace_seconds: float = 20.0,
    ) -> None:
        self._app = app
        self._window = window
        self._service = service
        self._output_dir = Path(output_dir)
        self._timeout_seconds = timeout_seconds
        self._state = state
        self._hooks = hooks
        self._poll_interval_ms = poll_interval_ms
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._initial_runtime: Mapping[str, object] = {}
        self._first_context: GuidedTurnContext | None = None

    def run(self, initial_runtime: Mapping[str, object]) -> dict[str, Any]:
        """Own the Qt event loop through bounded shutdown and return evidence."""
        self._initial_runtime = dict(initial_runtime)
        self._state.advance(GuidedBoundaryPhase.STARTING)
        previous_excepthook = sys.excepthook
        sys.excepthook = self._qt_exception_hook(previous_excepthook)
        try:
            self._hooks.schedule(0, self._poll_setup_dialogs)
            self._hooks.schedule(0, self._watchdog)
            self._hooks.schedule(self._poll_interval_ms, self._open_assistant)
            self._app.exec()
        finally:
            sys.excepthook = previous_excepthook
            self._hooks.detach_tool_trace()

        self._reconcile_shutdown_after_event_loop()
        if not self._state.terminal_started:
            self._state.status = "failed"
            self._state.failure_reason = (
                "Qt event loop exited before the Guided Workflow proof finalized."
            )
        payload = self._build_payload()
        if self._state.status == "passed":
            ok, reason = validate_guided_boundary_payload(payload)
            if not ok:
                self._state.status = "failed"
                self._state.failure_reason = reason
                if not self._state.screenshots["failure"]:
                    self._state.screenshots["failure"] = self._state.screenshots[
                        "post_cancel"
                    ]
                payload = self._build_payload()
        return payload

    def _manager(self) -> Any | None:
        return getattr(self._window, "agent_manager", None)

    def _connect_controller_observers(self) -> None:
        manager = self._manager()
        controller = getattr(manager, "agent_controller", None)
        if controller is None or self._state.observed_controller_id == id(controller):
            return
        self._hooks.attach_tool_trace(controller)
        controller.application_command_completed.connect(
            self._observe_application_result
        )
        controller.workflow_ui_handoff_requested.connect(
            self._observe_workflow_handoff_request
        )
        controller.confirmation_requested.connect(
            lambda payload: self._append_structured(
                self._state.confirmation_requests,
                payload,
            )
        )
        controller.interaction_resolved.connect(
            lambda payload: self._append_structured(
                self._state.interaction_events,
                payload,
            )
        )
        controller.turn_finished.connect(
            lambda payload: self._append_structured(
                self._state.turn_terminals,
                payload,
            )
        )
        self._state.observed_controller_id = id(controller)

    def _observe_workflow_handoff_request(self, payload: object) -> None:
        structured = self._hooks.structured_value(payload)
        if not isinstance(structured, dict):
            self._state.workflow_handoff_requests.append(structured)
            return
        request_id = str(structured.get("request_id") or "")
        if any(
            isinstance(item, dict) and item.get("request_id") == request_id
            for item in self._state.workflow_handoff_requests
        ):
            return
        self._state.workflow_handoff_requests.append(structured)

    def _append_structured(self, target: list[Any], payload: object) -> None:
        target.append(self._hooks.structured_value(payload))

    def _observe_application_result(self, result: object) -> None:
        structured = self._hooks.structured_value(result)
        self._state.application_results.append(structured)
        success = _application_result_succeeded(result, structured)
        command_name = str(
            getattr(result, "command_name", "")
            or (
                structured.get("command_name", "")
                if isinstance(structured, dict)
                else ""
            )
        )
        self._state.command_observations.append(
            {
                "command_name": command_name,
                "success": success,
                "result": structured,
                "publication": self._hooks.publication_evidence(self._service),
            }
        )

    def _poll_setup_dialogs(self) -> None:
        if self._state.terminal_started:
            return
        for widget in QApplication.topLevelWidgets():
            if (
                not isinstance(widget, QDialog)
                or not widget.isVisible()
                or widget.windowTitle().casefold() != "local assistant runtime"
                or id(widget) in self._state.handled_setup_dialog_ids
            ):
                continue
            event = self._hooks.handle_setup_dialog(widget)
            self._state.handled_setup_dialog_ids.add(id(widget))
            if event is None or not event.get("approved"):
                widget.reject()
                self._fail(
                    "Local Assistant Runtime offered no enabled offline model action."
                )
                return
            self._state.setup_dialogs.append(event)
        self._hooks.schedule(self._poll_interval_ms, self._poll_setup_dialogs)

    def _open_assistant(self) -> None:
        if self._state.terminal_started:
            return
        self._state.advance(GuidedBoundaryPhase.WAITING_FOR_READY)
        self._window.ai_btn.click()
        self._hooks.schedule(0, self._wait_for_ready)

    def _wait_for_ready(self) -> None:
        if self._state.terminal_started:
            return
        manager = self._manager()
        if manager is None:
            self._reschedule(self._wait_for_ready)
            return
        self._connect_controller_observers()
        ready, reason = self._hooks.assistant_surface_ready(manager)
        if not ready:
            snapshot = manager.assistant_runtime.current
            if snapshot.phase is AssistantRuntimePhase.FAILED:
                self._fail(
                    "Assistant runtime failed before it became ready: "
                    f"{snapshot.error or reason}"
                )
                return
            self._reschedule(self._wait_for_ready)
            return
        self._select_guided_mode(manager)

    def _select_guided_mode(self, manager: Any) -> None:
        self._state.advance(GuidedBoundaryPhase.SELECTING_GUIDED_MODE)
        panel = manager.chat_panel
        controller = manager.agent_controller
        button = panel.workflow_mode_btn
        clicked: list[bool] = []
        button.clicked.connect(lambda _checked=False: clicked.append(True))
        was_checked = button.isChecked()
        button.click()
        self._app.processEvents()
        self._state.mode_selection = {
            "selected_by_click": bool(clicked),
            "button_was_checked_before_click": was_checked,
            "button_checked": button.isChecked(),
            "panel": str(panel.current_execution_mode),
            "manager": str(getattr(manager, "_execution_mode", "")),
            "controller": str(getattr(controller, "execution_mode", "")),
        }
        if (
            not clicked
            or not button.isChecked()
            or any(
                self._state.mode_selection.get(owner) != "multi"
                for owner in ("panel", "manager", "controller")
            )
        ):
            self._fail("Guided Workflow mode did not reach every runtime owner.")
            return
        ready_path = self._output_dir / "chatpanel-guided-boundary-ready.png"
        if self._hooks.capture(self._window, ready_path) != 0:
            self._fail("Guided Workflow ready screenshot was blank or unavailable.")
            return
        self._state.screenshots["ready"] = str(ready_path)
        self._state.runtime_snapshot = self._snapshot_runtime(manager)
        self._state.initial_publication = self._hooks.publication_evidence(
            self._service
        )
        self._state.advance(GuidedBoundaryPhase.RUNNING_AUTO_CHAIN)
        self._first_context = self._turn_context(manager)
        self._send_prompt(manager, self._state.prompts[0])
        self._reschedule(self._wait_for_auto_chain)

    def _wait_for_auto_chain(self) -> None:
        if self._state.terminal_started:
            return
        manager = self._manager()
        context = self._first_context
        if manager is None or context is None:
            self._fail("Guided Workflow first-turn context disappeared.")
            return
        dialogs = [
            widget
            for widget in QApplication.topLevelWidgets()
            if isinstance(widget, DataInterpretationPreviewDialog)
            and widget.isVisible()
        ]
        if len(dialogs) > 1:
            self._fail("More than one Data Import wizard was visible.")
            return
        generic_confirmation = [
            widget
            for widget in QApplication.topLevelWidgets()
            if isinstance(widget, QDialog)
            and widget.isVisible()
            and widget.windowTitle().casefold() == "confirm action"
        ]
        if generic_confirmation:
            self._fail("Legacy Confirm action dialog opened instead of workflow UI.")
            return
        if not dialogs:
            assistant_texts = self._completed_assistant_texts(
                manager,
                context,
                self._state.prompts[0],
            )
            if assistant_texts is not None:
                self._fail("Safe chain completed without a Data Import UI handoff.")
                return
            self._reschedule(self._wait_for_auto_chain)
            return

        controller = manager.agent_controller
        controller_request = controller.pending_interactions.workflow_handoff
        host = getattr(manager, "_workflow_ui_handoff_host", None)
        host_request = getattr(host, "active_request", None)
        if controller_request is None or host_request is None:
            self._reschedule(self._wait_for_auto_chain)
            return
        self._observe_workflow_handoff_request(controller_request)
        messages = self._hooks.collect_visible_messages(manager.chat_panel)
        new_messages = messages[context.before_messages :]
        if not any(
            message.sender == "user" and message.text.strip() == self._state.prompts[0]
            for message in new_messages
        ):
            self._fail("Guided Workflow prompt was not visible before the handoff.")
            return
        assistant_texts = [
            message.text.strip()
            for message in new_messages
            if message.sender == "assistant" and message.text.strip()
        ]
        self._state.first_turn = self._first_turn_evidence(
            manager,
            context,
            assistant_texts,
        )
        self._state.boundary = self._atomic_boundary_evidence()
        ok, reason = validate_auto_chain_boundary(
            source_path=self._state.source_path,
            initial_publication=self._state.initial_publication,
            command_observations=self._state.command_observations,
            first_turn=self._state.first_turn,
            boundary=self._state.boundary,
            require_completed_turn=False,
        )
        if not ok:
            self._fail(reason)
            return
        if assistant_texts and self._transcript_has_problem(assistant_texts):
            self._fail(
                "Guided auto-chain transcript exposed debug or runtime error text."
            )
            return
        screenshot = self._output_dir / "chatpanel-guided-auto-chain-complete.png"
        if self._hooks.capture(self._window, screenshot) != 0:
            self._fail("Auto-chain-complete screenshot was blank or unavailable.")
            return
        self._state.screenshots["auto_chain_complete"] = str(screenshot)
        self._state.first_turn["screenshot"] = str(screenshot)
        self._state.advance(GuidedBoundaryPhase.WAITING_AT_BOUNDARY)
        self._state.advance(GuidedBoundaryPhase.WORKFLOW_HANDOFF_OPEN)
        request_payload = self._hooks.structured_value(controller_request)
        controller_payload = self._hooks.structured_value(controller_request)
        host_payload = self._hooks.structured_value(host_request)
        self._state.workflow_handoff = {
            "observed": True,
            "observed_while_dialog_visible": dialogs[0].isVisible(),
            "request": request_payload,
            "controller_pending_request": controller_payload,
            "host_active_request": host_payload,
        }
        screenshot = self._output_dir / "chatpanel-guided-workflow-dialog-open.png"
        try:
            self._state.wizard = capture_and_cancel_workflow_dialog(
                dialogs[0],
                request=controller_request,
                controller_request=controller_request,
                host_request=host_request,
                screenshot_path=screenshot,
                capture=self._hooks.capture,
            )
        except RuntimeError as exc:
            self._fail(str(exc))
            return
        self._state.screenshots["workflow_dialog_open"] = str(screenshot)
        self._state.advance(GuidedBoundaryPhase.WAITING_AFTER_CANCEL)
        self._reschedule(self._wait_after_cancel)

    def _wait_after_cancel(self) -> None:
        if self._state.terminal_started:
            return
        manager = self._manager()
        context = self._first_context
        if manager is None or context is None:
            self._fail("Assistant manager disappeared after cancellation.")
            return
        assistant_texts = self._completed_assistant_texts(
            manager,
            context,
            self._state.prompts[0],
        )
        if assistant_texts is None:
            self._reschedule(self._wait_after_cancel)
            return
        self._record_post_cancel(manager, context, assistant_texts)

    def _record_post_cancel(
        self,
        manager: Any,
        context: GuidedTurnContext,
        assistant_texts: list[str],
    ) -> None:
        controller = manager.agent_controller
        executed = self._hooks.collect_executed_tools(controller.metrics)
        screenshot = self._state.screenshots["auto_chain_complete"]
        self._state.first_turn = self._first_turn_evidence(
            manager,
            context,
            assistant_texts,
        )
        self._state.first_turn["screenshot"] = screenshot
        publication = self._hooks.publication_evidence(self._service)
        pending = controller.pending_interactions.workflow_handoff
        apply_completed = any(
            isinstance(item, dict)
            and item.get("command_name") == "apply_interpretation"
            for item in self._state.application_results[
                context.before_application_results :
            ]
        )
        self._state.post_cancel = {
            "publication": publication,
            "state": publication.get("state", {}),
            "pending_workflow_handoff": pending is not None,
            "workflow_dialog_visible": any(
                isinstance(widget, DataInterpretationPreviewDialog)
                and widget.isVisible()
                for widget in QApplication.topLevelWidgets()
            ),
            "apply_completion_observed": apply_completed,
            "executed_tools": executed,
        }
        screenshot = self._output_dir / "chatpanel-guided-post-cancel.png"
        if self._hooks.capture(self._window, screenshot) != 0:
            self._fail("Post-cancel screenshot was blank or unavailable.")
            return
        self._state.screenshots["post_cancel"] = str(screenshot)
        self._collect_terminal_surface(manager)
        if self._transcript_has_problem(assistant_texts):
            self._state.transcript_clean = False
        self._state.elapsed_seconds = round(
            self._hooks.now() - self._state.started_at,
            3,
        )
        candidate = self._build_payload()
        ok, reason = _validate_pre_shutdown_candidate(candidate)
        self._state.status = "passed" if ok else "failed"
        self._state.failure_reason = "" if ok else reason
        self._begin_shutdown()

    def _first_turn_evidence(
        self,
        manager: Any,
        context: GuidedTurnContext,
        assistant_texts: list[str],
    ) -> dict[str, Any]:
        controller = manager.agent_controller
        executed = self._hooks.collect_executed_tools(controller.metrics)
        proposals = self._hooks.collect_model_proposals(
            controller.history,
            self._state.prompts[0],
        )
        traces = self._hooks.collect_tool_attempt_traces()[
            context.before_tool_attempts :
        ]
        new_tools = executed[context.before_tools :]
        if not new_tools:
            new_tools = [
                {
                    "name": str(item.get("command_name") or ""),
                    "success": item.get("success") is True,
                }
                for item in self._state.command_observations[
                    context.before_command_observations :
                ]
            ]
        return {
            "prompt": self._state.prompts[0],
            "assistant_text": assistant_texts[-1] if assistant_texts else "",
            "assistant_messages": assistant_texts,
            "new_tools": new_tools,
            "tool_proposals": proposals,
            "tool_attempts": assemble_tool_attempts(
                proposals,
                traces,
                canonical_turn_calls(self._state.source_path, turn="first"),
            ),
            "metrics": self._hooks.turn_metrics_evidence(
                controller.metrics,
                context.before_metric_turns,
            ),
            "application_results": self._state.application_results[
                context.before_application_results :
            ],
            "turn_terminals": self._state.turn_terminals[
                context.before_turn_terminals :
            ],
            "elapsed_seconds": round(self._hooks.now() - context.started_at, 3),
            "screenshot": "",
        }

    def _turn_context(self, manager: Any) -> GuidedTurnContext:
        panel = manager.chat_panel
        controller = manager.agent_controller
        return GuidedTurnContext(
            before_messages=len(self._hooks.collect_visible_messages(panel)),
            before_tools=len(self._hooks.collect_executed_tools(controller.metrics)),
            before_metric_turns=len(
                list(getattr(controller.metrics, "_completed_turns", []) or [])
            ),
            before_application_results=len(self._state.application_results),
            before_command_observations=len(self._state.command_observations),
            before_turn_terminals=len(self._state.turn_terminals),
            before_tool_attempts=len(self._hooks.collect_tool_attempt_traces()),
            started_at=self._hooks.now(),
        )

    def _send_prompt(self, manager: Any, prompt: str) -> None:
        panel = manager.chat_panel
        panel.input_field.setText(prompt)
        panel.send_btn.click()

    def _completed_assistant_texts(
        self,
        manager: Any,
        context: GuidedTurnContext,
        prompt: str,
    ) -> list[str] | None:
        self._app.processEvents()
        messages = self._hooks.collect_visible_messages(manager.chat_panel)
        new_messages = messages[context.before_messages :]
        has_user = any(
            message.sender == "user" and message.text.strip() == prompt
            for message in new_messages
        )
        assistant_texts = [
            message.text.strip()
            for message in new_messages
            if message.sender == "assistant" and message.text.strip()
        ]
        ready, _reason = self._hooks.assistant_surface_ready(manager)
        if not (has_user and assistant_texts and ready):
            return None
        return assistant_texts

    def _atomic_boundary_evidence(self) -> dict[str, Any]:
        publication = self._service.get_view_publication()
        state = self._hooks.structured_value(publication.state.to_dict())
        capabilities = publication.effective_capabilities
        apply_capability = self._hooks.structured_value(
            capabilities.get("apply_interpretation")
        )
        publication_payload = {
            "available": True,
            "generation": int(publication.generation),
            "usable": bool(publication.usable),
            "verified": bool(publication.verified),
            "stale": bool(publication.stale),
            "refresh_error": publication.refresh_error,
            "pipeline_stage": (
                state.get("pipeline_stage", "") if isinstance(state, dict) else ""
            ),
            "state": state,
        }
        return {
            "publication": publication_payload,
            "state": state,
            "apply_capability": apply_capability,
        }

    def _collect_terminal_surface(self, manager: Any) -> None:
        panel = manager.chat_panel
        controller = manager.agent_controller
        messages = self._hooks.collect_visible_messages(panel)
        self._state.visible_messages = [message.__dict__ for message in messages]
        self._state.executed_tools = self._hooks.collect_executed_tools(
            controller.metrics
        )
        self._state.runtime_snapshot = self._snapshot_runtime(manager)
        self._state.ui_state = {
            "send_button_text": panel.send_btn.text(),
            "send_button_enabled": panel.send_btn.isEnabled(),
            "input_enabled": panel.input_field.isEnabled(),
            "chat_processing": bool(manager.chat_controller.is_processing),
            "controller_processing": bool(getattr(controller, "is_processing", False)),
            "runtime_turn_in_flight": bool(manager.assistant_runtime.turn_in_flight),
        }
        assistant_texts = [
            message.text
            for message in messages
            if message.sender == "assistant" and message.text.strip()
        ]
        self._state.transcript_clean = not self._transcript_has_problem(assistant_texts)

    def _snapshot_runtime(self, manager: Any) -> dict[str, Any]:
        value = self._hooks.structured_value(manager.assistant_runtime.current)
        return value if isinstance(value, dict) else {}

    def _transcript_has_problem(self, assistant_texts: list[str]) -> bool:
        return bool(
            self._hooks.has_raw_debug_text(assistant_texts)
            or self._hooks.has_runtime_error_text(assistant_texts)
        )

    def _fail(self, reason: str) -> None:
        if self._state.terminal_started:
            return
        self._state.status = "failed"
        self._state.failure_reason = reason
        manager = self._manager()
        if manager is not None:
            with suppress(Exception):
                self._collect_terminal_surface(manager)
        self._state.elapsed_seconds = round(
            self._hooks.now() - self._state.started_at,
            3,
        )
        failure_path = self._output_dir / "chatpanel-guided-boundary-failure.png"
        if self._hooks.capture(self._window, failure_path) == 0:
            self._state.screenshots["failure"] = str(failure_path)
        self._begin_shutdown()

    def _begin_shutdown(self) -> None:
        if self._state.terminal_started:
            return
        self._state.terminal_started = True
        self._state.advance(GuidedBoundaryPhase.FINALIZING)
        self._close_product_dialogs()
        self._state.shutdown = {"status": "closing", "detail": ""}
        self._state.shutdown_deadline = self._hooks.now() + self._shutdown_grace_seconds
        self._state.advance(GuidedBoundaryPhase.SHUTTING_DOWN)
        self._window.close()
        self._reschedule(self._wait_for_shutdown)

    def _reconcile_shutdown_after_event_loop(self) -> None:
        manager = self._manager()
        try:
            window_visible = self._window.isVisible()
            lifecycle_state = (
                manager.assistant_runtime.state.value
                if manager is not None
                else "closed"
            )
        except RuntimeError:
            window_visible = False
            lifecycle_state = "closed"
        if reconcile_closed_event_loop(
            self._state,
            window_visible=window_visible,
            lifecycle_state=lifecycle_state,
        ):
            return
        if self._state.shutdown.get("status") == "closing":
            detail = "Qt event loop exited before assistant shutdown was observable."
            self._state.shutdown = {"status": "interrupted", "detail": detail}
            self._state.status = "failed"
            self._state.failure_reason = (
                f"{self._state.failure_reason} {detail}".strip()
            )

    def _wait_for_shutdown(self) -> None:
        manager = self._manager()
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
            self._state.advance(GuidedBoundaryPhase.COMPLETED)
            self._app.quit()
            return
        if self._hooks.now() >= self._state.shutdown_deadline:
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
            self._state.advance(GuidedBoundaryPhase.COMPLETED)
            self._app.quit()
            return
        self._window.close()
        self._reschedule(self._wait_for_shutdown)

    def _close_product_dialogs(self) -> None:
        for widget in QApplication.topLevelWidgets():
            if widget is self._window or not isinstance(widget, QDialog):
                continue
            if widget.isVisible():
                widget.reject()

    def _watchdog(self) -> None:
        if self._state.terminal_started:
            return
        if self._hooks.now() - self._state.started_at >= self._timeout_seconds:
            self._fail(f"Timed out after {self._timeout_seconds} seconds.")
            return
        self._reschedule(self._watchdog)

    def _reschedule(self, callback: Callable[[], None]) -> None:
        self._hooks.schedule(self._poll_interval_ms, callback)

    def _build_payload(self) -> dict[str, Any]:
        return GuidedBoundaryEvidenceAssembler(
            state=self._state,
            initial_runtime=self._initial_runtime,
            runtime_evidence=self._hooks.runtime_evidence,
            structured_value=self._hooks.structured_value,
        ).build()

    def _qt_exception_hook(
        self,
        previous_excepthook: Callable[[type[BaseException], BaseException, Any], None],
    ) -> Callable[[type[BaseException], BaseException, Any], None]:
        def hook(
            exc_type: type[BaseException],
            exc_value: BaseException,
            exc_traceback: Any,
        ) -> None:
            self._state.exception = "".join(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            )
            previous_excepthook(exc_type, exc_value, exc_traceback)
            if not self._state.terminal_started:
                self._hooks.schedule(
                    0,
                    lambda: self._fail(
                        "Unhandled Qt callback error: "
                        f"{type(exc_value).__name__}: {exc_value}"
                    ),
                )

        return hook
