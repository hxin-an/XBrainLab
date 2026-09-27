"""Thread-affinity coverage for Assistant command dispatch."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event
from time import monotonic
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QMainWindow

from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
    AssistantResponsePresentation,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantDebugToolRequest,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)


class _ThreadedAgentController(QObject):
    response_presentation_ready = pyqtSignal(object)
    generation_started = pyqtSignal()
    processing_finished = pyqtSignal()
    turn_finished = pyqtSignal(object)
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    panel_navigation_requested = pyqtSignal(object)
    runtime_state_changed = pyqtSignal(object)
    confirmation_requested = pyqtSignal(object)
    workflow_ui_handoff_requested = pyqtSignal(object)
    application_command_completed = pyqtSignal(object)
    application_command_started = pyqtSignal()
    activity_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.worker_thread = QThread()
        self.worker_thread.start()
        self.input_thread: QThread | None = None
        self.handoff_resolution_thread: QThread | None = None
        self.handoff_resolution: WorkflowUiHandoffResolution | None = None
        self.confirmation_resolution_thread: QThread | None = None
        self.confirmation_resolution: AgentConfirmationResolution | None = None
        self.is_processing = False
        self._runtime_phase = "idle"
        self._launch_spec = None
        self._active_correlation: AssistantTurnCorrelation | None = None

    def initialize(self, launch_spec):
        self._launch_spec = launch_spec
        self._runtime_phase = "ready"
        self.runtime_state_changed.emit(self.runtime_snapshot())
        self.status_update.emit("Ready")

    def runtime_snapshot(self):
        launch_spec = self._launch_spec
        phase = AssistantRuntimePhase(self._runtime_phase)
        return AssistantRuntimeSnapshot(
            phase=phase,
            initialized=phase is AssistantRuntimePhase.READY,
            backend_mode=(
                launch_spec.backend_mode
                if phase is AssistantRuntimePhase.READY and launch_spec is not None
                else ""
            ),
            model_id=(
                launch_spec.model_id
                if phase is AssistantRuntimePhase.READY and launch_spec is not None
                else ""
            ),
            activation_id=(launch_spec.activation_id if launch_spec is not None else 0),
        )

    def handle_user_input(self, text: str):
        correlation = self._active_correlation
        if correlation is None:
            raise RuntimeError("Threaded controller requires an admitted host turn.")
        self.input_thread = QThread.currentThread()
        self.is_processing = True
        self.generation_started.emit()
        self.response_presentation_ready.emit(
            AssistantResponsePresentation(
                correlation=correlation,
                text=f"Checked: {text}",
            )
        )
        self.is_processing = False
        self.processing_finished.emit()

    def handle_user_turn(self, request: AssistantTurnRequest):
        self._active_correlation = request.correlation
        try:
            self.handle_user_input(request.text)
            self.turn_finished.emit(
                AssistantTurnTerminal(correlation=request.correlation)
            )
        finally:
            self._active_correlation = None

    def execute_debug_tool(self, _request: object):
        return None

    def set_model(self, _model: str):
        return None

    def stop_generation(self):
        self.is_processing = False
        self.processing_finished.emit()

    def reset_conversation(self):
        return None

    def on_user_confirmation_resolved(self, resolution):
        self.confirmation_resolution_thread = QThread.currentThread()
        self.confirmation_resolution = resolution

    def on_workflow_ui_handoff_resolved(self, resolution):
        self.handoff_resolution_thread = QThread.currentThread()
        self.handoff_resolution = resolution

    def on_panel_navigation_resolved(self, _request, _success):
        return None

    def close(self):
        self.worker_thread.quit()
        self.worker_thread.wait(1000)


class _ImmediateOutcomeController(_ThreadedAgentController):
    """Finish on the real command thread before the GUI consumes any event."""

    def __init__(self):
        super().__init__()
        self.outcome_emitted = Event()

    def handle_user_turn(self, request: AssistantTurnRequest):
        self._publish_outcome(request.correlation)

    def execute_debug_tool(self, request: AssistantDebugToolRequest):
        self._publish_outcome(request.correlation)

    def _publish_outcome(self, correlation: AssistantTurnCorrelation):
        self.input_thread = QThread.currentThread()
        self.activity_changed.emit(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.PREPARING,
                turn_id=correlation.turn_id,
                generation=correlation.generation,
            )
        )
        self.response_presentation_ready.emit(
            AssistantResponsePresentation(correlation=correlation, text="Checked.")
        )
        self.turn_finished.emit(AssistantTurnTerminal(correlation=correlation))
        self.outcome_emitted.set()


class _GuiAdmissionEvents(QObject):
    """Observe the actual Qt delivery, independently of Manager's event buffer."""

    def __init__(self):
        super().__init__()
        self.events: list[object] = []

    @pyqtSlot(object)
    def receive(self, payload: object):
        self.events.append(payload)


class _RetryShutdownController(_ThreadedAgentController):
    def __init__(self):
        super().__init__()
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        if self.close_calls == 1:
            return False
        super().close()
        return True


class _TerminalCloseController(_ThreadedAgentController):
    """Controller whose own resources close before dispatcher thread cleanup."""

    def __init__(self):
        super().__init__()
        self.received_inputs: list[str] = []
        self.terminal_closed = False

    def handle_user_input(self, text: str):
        self.received_inputs.append(text)

    def close(self):
        self.terminal_closed = True
        self.worker_thread.quit()
        return True


class _BlockingCloseController(_ThreadedAgentController):
    """Controller cleanup barrier used to prove GUI close remains responsive."""

    def __init__(self):
        super().__init__()
        self.close_started = Event()
        self.close_release = Event()

    def close(self):
        self.close_started.set()
        if not self.close_release.wait(timeout=0.4):
            return False
        return super().close()


class _BlockingApplicationCommandController(_ThreadedAgentController):
    """Keep one application command busy while the GUI handles Stop."""

    def __init__(self):
        super().__init__()
        self.command_started = Event()
        self.command_release = Event()
        self.stop_calls = 0

    def handle_user_turn(self, request: AssistantTurnRequest):
        self.input_thread = QThread.currentThread()
        self.is_processing = True
        self.application_command_started.emit()
        self.command_started.set()
        self.command_release.wait(timeout=2.0)
        self.application_command_completed.emit(MagicMock(changed_state=None))
        self.is_processing = False
        self.turn_finished.emit(AssistantTurnTerminal(correlation=request.correlation))

    def stop_generation(self):
        self.stop_calls += 1
        super().stop_generation()


def _ready_local_config():
    """Return deterministic local-runtime readiness without reading user settings."""
    from XBrainLab.llm.core.config import LLMConfig

    model_id = LLMConfig.default_local_model_id()
    config = LLMConfig(model_name=model_id)
    config.local_model_enabled = True
    config.local_runtime_notice_acknowledged = True
    config.local_backend_ready = (  # type: ignore[method-assign]
        lambda candidate=None: (candidate or model_id) == model_id
    )
    config.local_backend_status_message = (  # type: ignore[method-assign]
        lambda candidate=None: (
            "Local runtime ready."
            if (candidate or model_id) == model_id
            else f"Model cache not found for {candidate}."
        )
    )
    return config


@contextmanager
def _ready_manager_runtime(controller: QObject) -> Iterator[None]:
    """Isolate manager threading tests from the machine's model-cache state."""
    with (
        patch(
            "XBrainLab.ui.components.agent_manager.LLMController",
            return_value=controller,
        ),
        patch(
            "XBrainLab.ui.components.assistant_runtime_lifecycle."
            "LLMConfig.load_from_file",
            return_value=_ready_local_config(),
        ),
    ):
        yield


def _finish_dispatcher_close(qtbot, dispatcher, *, timeout: int = 5_000) -> None:
    """Drive one asynchronous dispatcher cleanup to its terminal contract."""
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcherState,
    )

    dispatcher.close()
    qtbot.waitUntil(
        lambda: dispatcher.state is AssistantCommandDispatcherState.CLOSED,
        timeout=timeout,
    )
    assert dispatcher.close() is True


def _finish_manager_close(qtbot, manager, *, timeout: int = 5_000) -> None:
    """Finish lifecycle cleanup after its dispatcher reaches terminal state."""
    from XBrainLab.ui.components.assistant_runtime_lifecycle import (
        AssistantRuntimeLifecycleState,
    )

    manager.close()
    qtbot.waitUntil(
        lambda: manager.assistant_runtime.dispatcher.state.value == "closed",
        timeout=timeout,
    )
    assert manager.close() is True
    assert manager.assistant_runtime.state is AssistantRuntimeLifecycleState.CLOSED


def test_controller_commands_run_off_gui_thread(qtbot):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    controller = _ThreadedAgentController()

    with _ready_manager_runtime(controller):
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        manager.toggle()
        command_thread = manager.assistant_runtime.dispatcher.command_thread
        assert isinstance(command_thread, QThread)
        qtbot.waitUntil(
            lambda: manager.assistant_runtime.current.phase
            is AssistantRuntimePhase.READY,
            timeout=2000,
        )
        manager.handle_user_input("inspect the dataset")

    qtbot.waitUntil(lambda: controller.input_thread is not None, timeout=2000)
    assert controller.input_thread is command_thread
    assert controller.input_thread is not controller.worker_thread
    assert controller.input_thread is not app.thread()
    _finish_manager_close(qtbot, manager)
    assert command_thread.isRunning() is False
    assert controller.worker_thread.isRunning() is False
    assert controller.thread() is app.thread()


@pytest.mark.parametrize("command", ["submit", "debug"])
def test_real_admission_returns_before_queued_outcome_delivery(qtbot, command):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    controller = _ImmediateOutcomeController()
    observed = _GuiAdmissionEvents()
    for signal in (
        controller.activity_changed,
        controller.response_presentation_ready,
        controller.turn_finished,
    ):
        signal.connect(observed.receive)

    with _ready_manager_runtime(controller):
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        manager.toggle()
        qtbot.waitUntil(lambda: manager.assistant_runtime.accepts_commands)
        dispatcher = manager.assistant_runtime.dispatcher
        dispatch = getattr(dispatcher, command)

        def dispatch_until_outcome(request):
            accepted = dispatch(request)
            # Force the command thread to finish before submit/debug returns,
            # without pumping GUI events or replacing the real transport.
            assert controller.outcome_emitted.wait(timeout=2.0)
            assert observed.events == []
            return accepted

        try:
            with patch.object(dispatcher, command, side_effect=dispatch_until_outcome):
                if command == "submit":
                    assert manager.handle_user_input("check data").accepted
                else:
                    manager._handle_debug_tool_requested("get_pipeline_state", {})
            assert observed.events == []
            expected = [("user", "check data")] if command == "submit" else []
            assert [
                (message["role"], message["content"])
                for message in manager.chat_controller.messages
            ] == expected
            assert manager.assistant_runtime.turn_in_flight

            qtbot.waitUntil(lambda: not manager.assistant_runtime.turn_in_flight)
            qtbot.waitUntil(lambda: len(observed.events) == 3)
            assert controller.input_thread is dispatcher.command_thread
            assert [
                (message["role"], message["content"])
                for message in manager.chat_controller.messages
            ] == [*expected, ("assistant", "Checked.")]
            assert isinstance(observed.events[0], AssistantTurnActivity)
            assert isinstance(observed.events[1], AssistantResponsePresentation)
            assert isinstance(observed.events[2], AssistantTurnTerminal)
        finally:
            _finish_manager_close(qtbot, manager)


@pytest.mark.parametrize("command", ["submit", "debug"])
def test_rejected_real_transport_does_not_admit_transcript(qtbot, command):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    controller = _ImmediateOutcomeController()
    with _ready_manager_runtime(controller):
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        manager.toggle()
        qtbot.waitUntil(lambda: manager.assistant_runtime.accepts_commands)
        dispatcher = manager.assistant_runtime.dispatcher
        signal = (
            dispatcher.input_requested
            if command == "submit"
            else dispatcher.debug_requested
        )
        signal.disconnect()
        try:
            if command == "submit":
                assert not manager.handle_user_input("check data").accepted
            else:
                manager._handle_debug_tool_requested("get_pipeline_state", {})
            assert not manager.assistant_runtime.turn_in_flight
            assert not controller.outcome_emitted.is_set()
            assert manager.chat_controller.messages == []
            assert manager._assistant_turn_state.lease is None
        finally:
            _finish_manager_close(qtbot, manager)


def test_stop_is_not_queued_behind_an_uncancellable_application_command(qtbot):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    controller = _BlockingApplicationCommandController()

    with _ready_manager_runtime(controller):
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        manager.toggle()
        qtbot.waitUntil(
            lambda: manager.assistant_runtime.current.phase
            is AssistantRuntimePhase.READY,
            timeout=2000,
        )
        manager.handle_user_input("run a blocking application action")
        qtbot.waitUntil(controller.command_started.is_set, timeout=2000)
        qtbot.waitUntil(
            lambda: manager._application_command_in_flight,
            timeout=2000,
        )

        assert manager.chat_panel.send_btn.text() == "Working"
        assert manager.chat_panel.send_btn.isEnabled() is False
        assert manager.chat_panel.turn_activity_title.text() == (
            "XBrainLab action in progress"
        )
        manager.chat_panel.send_btn.click()
        assert controller.stop_calls == 0

        manager.stop_generation()
        assert controller.stop_calls == 0

        controller.command_release.set()
        qtbot.waitUntil(
            lambda: not manager._application_command_in_flight,
            timeout=2000,
        )
        qtbot.wait(50)
        assert controller.stop_calls == 0

    _finish_manager_close(qtbot, manager)


def test_typed_response_signal_reaches_chat_without_raw_text_classification(qtbot):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    controller = _ThreadedAgentController()
    correlation = AssistantTurnCorrelation(generation=1, turn_id=1)
    presentation = AssistantResponsePresentation(
        correlation=correlation,
        text='Request: {"status": "ready"}',
    )

    with _ready_manager_runtime(controller):
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        manager.toggle()
        submission = manager._assistant_turn_state.begin_submission()
        assert (
            manager._assistant_turn_state.complete_admission(
                submission,
                correlation,
            )
            is True
        )
        manager.assistant_runtime._active_turn = correlation
        controller.response_presentation_ready.emit(presentation)

    qtbot.waitUntil(
        lambda: any(
            message["content"] == presentation.text
            for message in manager.chat_controller.messages
        ),
        timeout=2000,
    )
    assert [
        message["content"]
        for message in manager.chat_controller.messages
        if message["role"] == "assistant"
    ] == [presentation.text]
    _finish_manager_close(qtbot, manager)


def test_typed_panel_navigation_signal_reaches_existing_main_window(qtbot):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    main_window.switch_page = MagicMock()
    qtbot.addWidget(main_window)
    controller = _ThreadedAgentController()

    with _ready_manager_runtime(controller):
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        manager.toggle()
        controller.panel_navigation_requested.emit(
            AssistantPanelNavigationRequest(AssistantPanelTarget.TRAINING)
        )

    qtbot.waitUntil(lambda: main_window.switch_page.call_count == 1, timeout=2000)
    main_window.switch_page.assert_called_once_with(2)
    _finish_manager_close(qtbot, manager)


def test_typed_ui_handoff_resolution_runs_on_controller_command_thread(qtbot):
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
    )

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    controller = _ThreadedAgentController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    command_thread = dispatcher.command_thread
    assert isinstance(command_thread, QThread)

    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.COMPLETED,
    )
    dispatcher.resolve_ui_handoff(resolution)

    qtbot.waitUntil(
        lambda: controller.handoff_resolution_thread is not None,
        timeout=2000,
    )
    assert controller.handoff_resolution_thread is command_thread
    assert controller.handoff_resolution_thread is not app.thread()
    assert controller.handoff_resolution is resolution
    _finish_dispatcher_close(qtbot, dispatcher)


def test_typed_confirmation_resolution_runs_on_controller_command_thread(qtbot):
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
    )

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    controller = _ThreadedAgentController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    command_thread = dispatcher.command_thread
    assert isinstance(command_thread, QThread)
    request = AgentConfirmationRequest.for_action(
        command_name="reset_preprocess",
        params={},
        action_label="Clear dataset",
        description="Clear the current dataset",
        destructive=True,
        publication_generation=7,
    )
    resolution = AgentConfirmationResolution.for_request(
        request,
        status=AgentConfirmationResolutionStatus.APPROVED,
    )

    dispatcher.confirm(resolution)

    qtbot.waitUntil(
        lambda: controller.confirmation_resolution_thread is not None,
        timeout=2000,
    )
    assert controller.confirmation_resolution_thread is command_thread
    assert controller.confirmation_resolution_thread is not app.thread()
    assert controller.confirmation_resolution is resolution
    _finish_dispatcher_close(qtbot, dispatcher)


def test_close_is_idempotent_after_queued_shutdown(qtbot):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    controller = _ThreadedAgentController()
    with _ready_manager_runtime(controller):
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        manager.toggle()

    _finish_manager_close(qtbot, manager)
    assert manager.close() is True
    assert controller.worker_thread.isRunning() is False


def test_dispatcher_close_does_not_block_the_gui_event_loop(qtbot):
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
        AssistantCommandDispatcherState,
    )

    controller = _BlockingCloseController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    timer_fired: list[bool] = []
    QTimer.singleShot(0, lambda: timer_fired.append(True))

    started = monotonic()
    closed_immediately = dispatcher.close()
    elapsed = monotonic() - started

    assert closed_immediately is False
    assert elapsed < 0.1
    qtbot.waitUntil(controller.close_started.is_set, timeout=1_000)
    qtbot.waitUntil(lambda: timer_fired == [True], timeout=1_000)

    controller.close_release.set()
    qtbot.waitUntil(
        lambda: dispatcher.state is AssistantCommandDispatcherState.CLOSED,
        timeout=2_000,
    )
    assert dispatcher.close() is True


def test_dispatcher_rejects_invalid_contract_before_starting_command_thread(qtbot):
    del qtbot
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
    )

    class InvalidController(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.worker_thread = QThread()

        def initialize(self, _launch_spec: object) -> None:
            return None

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    controller = InvalidController()
    dispatcher = AssistantCommandDispatcher()

    with pytest.raises(TypeError, match="handle_user_turn"):
        dispatcher.bind(controller)

    leaked_threads = dispatcher.findChildren(QThread)
    try:
        assert leaked_threads == []
        assert controller.thread() is app.thread()
        assert dispatcher.command_thread is None
    finally:
        for thread in leaked_threads:
            thread.quit()
            thread.wait(1_000)


def test_dispatcher_source_forbids_nested_event_loops_and_thread_waits():
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
    )

    tree = ast.parse(inspect.getsource(AssistantCommandDispatcher))
    forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "QEventLoop":
            forbidden.append("QEventLoop")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "wait"
        ):
            forbidden.append("wait")

    assert forbidden == []


def test_real_controller_worker_shutdown_runs_through_qt_owner_thread(qtbot):
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
    )

    controller = LLMController(Study())
    worker = controller.worker
    assert worker is not None
    worker_thread = controller.worker_thread
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    command_thread = dispatcher.command_thread

    assert isinstance(command_thread, QThread)
    controller.shutdown_finished.connect(dispatcher.close)
    _finish_dispatcher_close(qtbot, dispatcher)
    qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2000)
    assert controller.worker is None
    assert worker_thread.isRunning() is False
    assert command_thread.isRunning() is False


def test_real_controller_can_be_created_and_disposed_repeatedly(qtbot):
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
    )

    for _index in range(2):
        controller = LLMController(Study())
        worker = controller.worker
        assert worker is not None
        dispatcher = AssistantCommandDispatcher()
        dispatcher.bind(controller)
        controller.shutdown_finished.connect(dispatcher.close)

        _finish_dispatcher_close(qtbot, dispatcher)
        qtbot.waitUntil(lambda target=worker: sip.isdeleted(target), timeout=2000)


def test_failed_shutdown_retains_thread_ownership_for_retry(qtbot):
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
        AssistantCommandDispatcherState,
    )

    controller = _RetryShutdownController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    command_thread = dispatcher.command_thread

    assert isinstance(command_thread, QThread)
    assert dispatcher.close() is False
    assert dispatcher.command_thread is command_thread
    assert command_thread.isRunning() is True
    assert dispatcher.state is AssistantCommandDispatcherState.CLOSING
    assert dispatcher.accepts_commands is False

    dispatcher.submit(
        AssistantTurnRequest(
            correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
            text="after-close-started",
        )
    )
    qtbot.wait(20)
    assert controller.input_thread is None

    qtbot.waitUntil(lambda: controller.close_calls == 1, timeout=1_000)
    assert dispatcher.state is AssistantCommandDispatcherState.CLOSING
    assert dispatcher.close() is False
    qtbot.waitUntil(
        lambda: dispatcher.state is AssistantCommandDispatcherState.CLOSED,
        timeout=2_000,
    )
    assert dispatcher.close() is True
    assert command_thread.isRunning() is False
    assert controller.worker_thread.isRunning() is False


def test_terminal_controller_close_rejects_commands_while_thread_cleanup_retries(
    qtbot,
    monkeypatch,
):
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
        AssistantCommandDispatcherState,
    )

    controller = _TerminalCloseController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    command_thread = dispatcher.command_thread
    assert isinstance(command_thread, QThread)

    def _forbid_gui_wait(_timeout):
        raise AssertionError("dispatcher shutdown must not call QThread.wait")

    monkeypatch.setattr(
        command_thread,
        "wait",
        _forbid_gui_wait,
    )

    assert dispatcher.close() is False
    assert dispatcher.command_thread is command_thread
    assert dispatcher.accepts_commands is False

    dispatcher.submit(
        AssistantTurnRequest(
            correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
            text="after-close",
        )
    )
    qtbot.waitUntil(lambda: controller.terminal_closed, timeout=1_000)
    qtbot.waitUntil(
        lambda: dispatcher.state is AssistantCommandDispatcherState.CLOSED,
        timeout=2_000,
    )

    assert controller.received_inputs == []
    assert dispatcher.close() is True
    assert dispatcher.command_thread is None
    assert dispatcher.state is AssistantCommandDispatcherState.CLOSED
    controller.worker_thread.quit()
    assert controller.worker_thread.wait(1_000)


def test_close_treats_an_already_deleted_command_thread_as_released(qtbot):
    from XBrainLab.ui.components.assistant_command_dispatcher import (
        AssistantCommandDispatcher,
    )

    controller = _ThreadedAgentController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    command_thread = dispatcher.command_thread
    assert isinstance(command_thread, QThread)

    controller.worker_thread.quit()
    assert controller.worker_thread.wait(1_000)
    command_thread.quit()
    assert command_thread.wait(1_000)
    command_thread.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(command_thread), timeout=2_000)

    assert dispatcher.close() is True
    assert dispatcher.command_thread is None
