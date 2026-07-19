"""Qt phase driver for the local ChatPanel pipeline-chain walkthrough."""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import QApplication

from scripts.dev.chatpanel_pipeline_chain.contracts import (
    EventBucket,
    PipelineDriverHooks,
)
from scripts.dev.chatpanel_pipeline_chain.evidence import (
    PipelineEvidenceAssembler,
    PipelineTurnEvidenceBuilder,
)
from scripts.dev.chatpanel_pipeline_chain.shutdown import PipelineShutdownCoordinator
from scripts.dev.chatpanel_pipeline_chain.state import (
    PipelinePhase,
    PipelineTurnContext,
    PipelineWalkthroughState,
)
from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
from XBrainLab.llm.agent.turn import (
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
)


class PipelineChainDriver:
    """Drive startup, readiness, and one deterministic tool turn at a time."""

    def __init__(
        self,
        *,
        app: Any,
        window: Any,
        service: Any,
        output_dir: Path,
        prompts: list[str],
        timeout_seconds: int,
        state: PipelineWalkthroughState,
        hooks: PipelineDriverHooks,
        poll_interval_ms: int = 250,
        shutdown_grace_seconds: float = 20.0,
        ready_screenshot_name: str = "chatpanel-pipeline-chain-ready.png",
        terminal_screenshot_name: str = "chatpanel-pipeline-chain-terminal.png",
        failure_screenshot_name: str = "chatpanel-pipeline-chain-failure.png",
    ) -> None:
        if len(prompts) != len(state.expected_tools):
            raise ValueError(
                "Pipeline prompts and expected tools must have equal length."
            )
        self._app = app
        self._window = window
        self._service = service
        self._output_dir = output_dir
        self._prompts = prompts
        self._timeout_seconds = timeout_seconds
        self._state = state
        self._hooks = hooks
        self._poll_interval_ms = poll_interval_ms
        self._ready_screenshot_name = ready_screenshot_name
        self._turn_evidence = PipelineTurnEvidenceBuilder(
            state=state,
            service=service,
            hooks=hooks,
        )
        self._shutdown = PipelineShutdownCoordinator(
            app=app,
            window=window,
            service=service,
            output_dir=output_dir,
            state=state,
            manager_provider=self._current_agent_manager,
            capture_window=hooks.capture_window,
            collect_visible_messages=hooks.collect_visible_messages,
            collect_executed_tools=hooks.collect_executed_tools,
            publication_evidence=hooks.publication_evidence,
            structured_value=hooks.structured_value,
            validate_payload=hooks.validate_payload,
            schedule=hooks.schedule,
            now=hooks.now,
            poll_interval_ms=poll_interval_ms,
            shutdown_grace_seconds=shutdown_grace_seconds,
            terminal_screenshot_name=terminal_screenshot_name,
            failure_screenshot_name=failure_screenshot_name,
        )

    def run(self, initial_runtime: Mapping[str, object]) -> dict[str, Any]:
        self._state.advance(PipelinePhase.STARTING)
        previous_excepthook = sys.excepthook
        sys.excepthook = self._qt_exception_hook(previous_excepthook)
        try:
            self._hooks.schedule(0, self._handle_product_dialogs)
            self._hooks.schedule(0, self._watchdog)
            self._hooks.schedule(self._poll_interval_ms, self._open_assistant)
            self._app.exec()
        finally:
            sys.excepthook = previous_excepthook

        if self._state.status == "running":
            self._state.status = "failed"
            self._state.failure_reason = (
                "Qt event loop exited before a terminal result."
            )
        if self._state.shutdown["status"] == "closing":
            self._state.shutdown = {"status": "completed", "detail": ""}
            if self._state.phase is PipelinePhase.SHUTTING_DOWN:
                self._state.advance(PipelinePhase.COMPLETED)

        return PipelineEvidenceAssembler(
            state=self._state,
            prompts=self._prompts,
            initial_runtime=initial_runtime,
            runtime_evidence=self._hooks.runtime_evidence,
            structured_value=self._hooks.structured_value,
        ).build()

    def _current_agent_manager(self) -> Any | None:
        return self._window.agent_manager

    def _observe_signal(self, bucket: EventBucket, payload: object) -> None:
        self._state.append_event(
            bucket,
            payload,
            structured_value=self._hooks.structured_value,
        )

    def _observe_generation_event(
        self,
        controller: Any,
        event: object,
    ) -> None:
        """Record one typed controller publication without worker access."""
        if not self._is_current_controller(controller) or not isinstance(
            event,
            AssistantGenerationEvent,
        ):
            return
        if event.phase is AssistantGenerationEventPhase.STARTED:
            self._state.begin_model_generation(event.generation_id)
        elif event.phase is AssistantGenerationEventPhase.CHUNK:
            self._state.append_model_chunk(event.generation_id, event.text)
        elif event.phase in {
            AssistantGenerationEventPhase.FINISHED,
            AssistantGenerationEventPhase.CANCELLED,
            AssistantGenerationEventPhase.ERROR,
        }:
            self._state.end_model_generation(event.generation_id)

    def _is_current_controller(self, controller: Any) -> bool:
        manager = self._current_agent_manager()
        return manager is not None and manager.agent_controller is controller

    def _connect_controller_observers(self) -> None:
        manager = self._current_agent_manager()
        if manager is None:
            return
        controller = manager.agent_controller
        if controller is None or self._state.observed_controller_id == id(controller):
            return
        controller.confirmation_requested.connect(
            lambda payload: self._observe_signal("confirmation_requests", payload)
        )
        controller.interaction_resolved.connect(
            lambda payload: self._observe_signal("interaction_events", payload)
        )
        controller.workflow_ui_handoff_requested.connect(
            lambda payload: self._observe_signal("workflow_handoffs", payload)
        )
        controller.application_command_completed.connect(
            lambda payload: self._observe_signal("application_results", payload)
        )
        controller.turn_finished.connect(
            lambda payload: self._observe_signal("turn_terminals", payload)
        )
        controller.generation_event.connect(
            lambda event, current=controller: self._observe_generation_event(
                current,
                event,
            )
        )
        self._state.observed_controller_id = id(controller)

    def _handle_product_dialogs(self) -> None:
        if self._state.terminal_started:
            return
        for widget in QApplication.topLevelWidgets():
            if not widget.isVisible() or id(widget) in self._state.handled_dialog_ids:
                continue
            event = self._hooks.approve_product_dialog(widget)
            if event is None:
                continue
            self._state.handled_dialog_ids.add(id(widget))
            if event["kind"] == "first_run":
                self._state.setup_dialogs.append(event)
                if not event["approved"]:
                    widget.close()
                    self._hooks.schedule(
                        0,
                        lambda: self._shutdown.fail(
                            "Local Assistant Runtime offered no enabled offline "
                            "model action."
                        ),
                    )
                    return
            else:
                self._state.confirmation_dialogs.append(event)
                if not event["approved"]:
                    widget.close()
                    self._hooks.schedule(
                        0,
                        lambda: self._shutdown.fail(
                            "Product confirmation dialog had no enabled AcceptRole "
                            "button."
                        ),
                    )
                    return
        self._hooks.schedule(self._poll_interval_ms, self._handle_product_dialogs)

    def _open_assistant(self) -> None:
        if self._state.terminal_started:
            return
        self._state.advance(PipelinePhase.WAITING_FOR_READY)
        self._window.ai_btn.click()
        self._hooks.schedule(0, self._wait_for_ready)

    def _wait_for_ready(self) -> None:
        if self._state.terminal_started:
            return
        manager = self._current_agent_manager()
        if manager is None:
            self._hooks.schedule(self._poll_interval_ms, self._wait_for_ready)
            return
        self._connect_controller_observers()
        ready, reason = self._hooks.assistant_surface_ready(manager)
        if not ready:
            snapshot = manager.assistant_runtime.current
            if snapshot.phase is AssistantRuntimePhase.FAILED:
                self._shutdown.fail(
                    "Assistant runtime failed before it became ready: "
                    f"{snapshot.error or reason}"
                )
                return
            self._hooks.schedule(self._poll_interval_ms, self._wait_for_ready)
            return
        ready_path = self._output_dir / self._ready_screenshot_name
        if self._hooks.capture_window(self._window, ready_path) != 0:
            self._shutdown.fail("Ready screenshot was blank or could not be saved.")
            return
        self._state.ready_screenshot = str(ready_path)
        self._state.advance(PipelinePhase.RUNNING_TURNS)
        self._send_prompt(0)

    def _send_prompt(self, index: int) -> None:
        if self._state.terminal_started:
            return
        manager = self._current_agent_manager()
        if manager is None:
            self._hooks.schedule(
                self._poll_interval_ms,
                lambda: self._send_prompt(index),
            )
            return
        panel = manager.chat_panel
        ready, _reason = self._hooks.assistant_surface_ready(manager)
        if not ready:
            self._hooks.schedule(
                self._poll_interval_ms,
                lambda: self._send_prompt(index),
            )
            return
        controller = manager.agent_controller
        if panel is None or controller is None:
            self._shutdown.fail(
                "ChatPanel or controller disappeared during the walkthrough."
            )
            return
        self._connect_controller_observers()
        context = PipelineTurnContext(
            before_messages=len(self._hooks.collect_visible_messages(panel)),
            before_tools=len(self._hooks.collect_executed_tools(controller.metrics)),
            before_metric_turns=len(
                list(getattr(controller.metrics, "_completed_turns", []) or [])
            ),
            publication_before=self._hooks.publication_evidence(self._service),
            event_counts=self._state.event_counts(),
            started_at=self._hooks.now(),
        )
        prompt = self._prompts[index]
        panel.input_field.setText(prompt)
        panel.send_btn.click()
        self._hooks.schedule(
            self._poll_interval_ms,
            lambda: self._wait_for_turn(index, prompt, context),
        )

    def _wait_for_turn(
        self,
        index: int,
        prompt: str,
        context: PipelineTurnContext,
    ) -> None:
        if self._state.terminal_started:
            return
        manager = self._current_agent_manager()
        if manager is None:
            self._shutdown.fail("Assistant manager disappeared during the walkthrough.")
            return
        panel = manager.chat_panel
        controller = manager.agent_controller
        if panel is None or controller is None:
            self._shutdown.fail(
                "ChatPanel or controller disappeared during the walkthrough."
            )
            return

        self._app.processEvents()
        messages = self._hooks.collect_visible_messages(panel)
        new_messages = messages[context.before_messages :]
        assistant_texts = [
            message.text.strip()
            for message in new_messages
            if message.sender == "assistant" and message.text.strip()
        ]
        has_user = any(
            message.sender == "user" and message.text.strip() == prompt
            for message in new_messages
        )
        still_processing = (
            manager.chat_controller.is_processing
            or bool(getattr(controller, "is_processing", False))
            or bool(manager.assistant_runtime.turn_in_flight)
        )
        if not (has_user and assistant_texts and not still_processing):
            self._hooks.schedule(
                self._poll_interval_ms,
                lambda: self._wait_for_turn(index, prompt, context),
            )
            return

        self._record_completed_turn(index, prompt, context, assistant_texts, controller)

    def _record_completed_turn(
        self,
        index: int,
        prompt: str,
        context: PipelineTurnContext,
        assistant_texts: list[str],
        controller: Any,
    ) -> None:
        screenshot_path = self._output_dir / (
            f"chatpanel-pipeline-chain-turn-{index + 1}.png"
        )
        if self._hooks.capture_window(self._window, screenshot_path) != 0:
            self._shutdown.fail("Turn screenshot was blank or could not be saved.")
            return
        evidence = self._turn_evidence.build(
            index=index,
            prompt=prompt,
            context=context,
            assistant_text=assistant_texts[-1],
            controller=controller,
            screenshot_path=screenshot_path,
        )
        self._state.turns.append(evidence.payload)
        if self._hooks.has_raw_debug_text(assistant_texts):
            self._shutdown.fail("Visible assistant text exposed debug syntax.")
            return
        if self._hooks.has_runtime_error_text(assistant_texts):
            self._shutdown.fail(
                "Visible assistant text reported a local runtime error."
            )
            return
        if not self._hooks.turn_has_expected_tool(
            evidence.new_tools, evidence.expected_tool
        ):
            names = [tool.get("name") for tool in evidence.new_tools]
            self._shutdown.fail(
                f"Turn {index + 1} did not execute expected tool "
                f"{evidence.expected_tool}; new tools: {names}."
            )
            return
        if not any(
            proposal.get("tool_name") == evidence.expected_tool
            and isinstance(proposal.get("parameters"), dict)
            for proposal in evidence.proposals
        ):
            self._shutdown.fail(
                f"Turn {index + 1} did not preserve full proposed parameters "
                f"for {evidence.expected_tool}."
            )
            return
        if index + 1 < len(self._prompts):
            self._hooks.schedule(
                self._poll_interval_ms,
                lambda: self._send_prompt(index + 1),
            )
            return
        self._shutdown.finish()

    def _watchdog(self) -> None:
        if self._state.terminal_started:
            return
        if self._hooks.now() - self._state.started_at >= self._timeout_seconds:
            self._shutdown.fail(f"Timed out after {self._timeout_seconds} seconds.")
            return
        self._hooks.schedule(self._poll_interval_ms, self._watchdog)

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
                    lambda: self._shutdown.fail(
                        "Unhandled Qt callback error: "
                        f"{type(exc_value).__name__}: {exc_value}"
                    ),
                )

        return hook
