"""Real Qt lifecycle regressions for the in-app assistant runtime.

These tests keep the production ``AgentManager`` -> ``LLMController`` ->
``AgentWorker`` thread topology intact.  The model engine is replaced by an
event-controlled fake so loading and generation races are deterministic; the
unrelated workflow-surface router is isolated while its parallel slice changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event, Lock
from types import SimpleNamespace
from typing import Any, cast

from PyQt6 import sip
from PyQt6.QtCore import QEventLoop, QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QMainWindow,
    QToolButton,
    QWidget,
)

from XBrainLab.backend.application import (
    ApplicationService,
    ConfigureTrainingCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.assistant_activity import (
    AssistantDecisionOwner,
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest
from XBrainLab.llm.agent.interaction import (
    AgentInteractionOutcome,
    AgentInteractionStatus,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptDecision,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation
from XBrainLab.llm.agent.ui_handoff import WorkflowUiHandoffRequest
from XBrainLab.llm.agent.worker import (
    ACTIVE_GENERATION_THREADS,
    ACTIVE_RUNTIME_LOAD_THREADS,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.generation import GenerationProfile
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchResolution,
    AssistantRuntimeLaunchResolver,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
    AssistantRuntimeSettingsSnapshot,
)
from XBrainLab.ui.components.agent_manager import AgentManager
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
    RuntimeCommandAdmissionStatus,
)
from XBrainLab.ui.dialogs.training import (
    ModelSelectionDialog,
    TrainingSettingDialog,
)
from XBrainLab.ui.interaction_outcome import InteractionOutcome
from XBrainLab.ui.panels.training.sidebar import TrainingSidebar
from XBrainLab.ui.qt_runtime import drain_qt_runtime_after_event_loop

WATCHDOG_MS = 5_000
WATCHDOG_SECONDS = WATCHDOG_MS / 1_000
TEST_TARGET_MODEL_ID = "test/runtime-target"


class _TestLaunchResolver(AssistantRuntimeLaunchResolver):
    """Resolve fake model IDs for lifecycle races without changing product policy."""

    def resolve(
        self,
        config: LLMConfig,
        *,
        requested_backend_id: str | None = None,
        requested_model_id: str | None = None,
    ) -> AssistantRuntimeLaunchResolution:
        backend_id = str(
            config.inference_mode
            if requested_backend_id is None
            else requested_backend_id
        ).strip()
        model_id = str(
            config.model_name if requested_model_id is None else requested_model_id
        ).strip()
        return AssistantRuntimeLaunchResolution(
            launch_spec=AssistantRuntimeLaunchSpec(
                backend=AssistantRuntimeBackend.LOCAL,
                requested_backend_id=backend_id,
                requested_model_id=model_id,
                model_id=model_id,
                outcome=AssistantRuntimeSelectionOutcome.EXACT,
                selection_detail=config.local_backend_status_message(model_id),
                settings=AssistantRuntimeSettingsSnapshot.from_config(config),
            )
        )


class _ControlledEngine:
    """Minimal model backend with deterministic loading/generation barriers."""

    uses_owned_process = True

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.active_backend: object | None = object()
        self.load_started = Event()
        self.load_release = Event()
        self.switch_started = Event()
        self.switch_release = Event()
        self.generation_started = Event()
        self.generation_release = Event()
        self.cancel_requested = Event()
        self.close_called = Event()
        self._lock = Lock()
        self.load_calls = 0
        self.switch_calls = 0
        self.generation_calls = 0
        self.cancel_calls = 0
        self.active_generations = 0
        self.max_active_generations = 0
        self.cancel_releases_generation = True
        self.generated_messages: list[list[dict[str, Any]]] = []
        self.generated_profiles: list[GenerationProfile] = []
        self.generation_failure: Exception | None = None

    @staticmethod
    def _wait_for_release(release: Event, operation: str) -> None:
        if not release.wait(WATCHDOG_SECONDS):
            raise TimeoutError(f"Timed out waiting to release fake {operation}.")

    def load_model(self) -> None:
        with self._lock:
            self.load_calls += 1
        self.load_started.set()
        self._wait_for_release(self.load_release, "model load")

    def switch_backend(self, _backend_mode: str) -> None:
        with self._lock:
            self.switch_calls += 1
        self.switch_started.set()
        self._wait_for_release(self.switch_release, "model switch")
        self.active_backend = object()

    def generate_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        profile: GenerationProfile,
    ):
        with self._lock:
            self.generation_calls += 1
            self.active_generations += 1
            self.max_active_generations = max(
                self.max_active_generations,
                self.active_generations,
            )
            self.generated_messages.append([dict(message) for message in messages])
            self.generated_profiles.append(profile)
        try:
            self.generation_started.set()
            self._wait_for_release(self.generation_release, "generation")
            if self.cancel_requested.is_set():
                return
            if self.generation_failure is not None:
                raise self.generation_failure
            yield (
                "I inspected the requested EEG workflow. No application command "
                "was executed."
            )
        finally:
            with self._lock:
                self.active_generations -= 1

    def cancel_generation(self, *, wait_timeout: float = 0.0) -> bool:
        del wait_timeout
        with self._lock:
            self.cancel_calls += 1
        self.cancel_requested.set()
        if self.cancel_releases_generation:
            self.generation_release.set()
        return self.cancel_releases_generation

    def close(self, *, wait_timeout: float = 0.0) -> bool:
        del wait_timeout
        self.close_called.set()
        self.active_backend = None
        self.release_all()
        return True

    def release_all(self) -> None:
        """Release every barrier so teardown cannot strand a native thread."""
        self.load_release.set()
        self.switch_release.set()
        self.generation_release.set()


class _NoopRagRetriever:
    """Retriever diagnostic surface for the process-free lifecycle test double."""

    def initialize(self) -> None:
        return None

    def get_similar_examples(
        self,
        query: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        del query, allowed_tool_names
        return ""

    def close(self) -> None:
        return None


class _NoopRagLifecycle:
    """Keep runtime lifecycle tests deterministic without a child process."""

    def __init__(self) -> None:
        self.retriever = _NoopRagRetriever()

    def start(self) -> bool:
        return True

    def retrieve(
        self,
        turn_id: int,
        query: str,
        callback: Any,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> bool:
        del allowed_tool_names
        callback(turn_id, query, "", "")
        return True

    def cancel_retrieval(self, turn_id: int) -> bool:
        del turn_id
        return False

    def close(self) -> bool:
        return True


class _WorkerErrorProbe(QObject):
    """Publish an error from the real worker thread via a queued slot."""

    request_error = pyqtSignal(str)

    def __init__(self, worker: Any) -> None:
        super().__init__()
        self._worker = worker
        self.error_sent = Event()
        self.delivery_threads: list[QThread] = []
        self.request_error.connect(self._publish_error)

    @pyqtSlot(str)
    def _publish_error(self, error: str) -> None:
        current_thread = QThread.currentThread()
        assert current_thread is not None
        self.delivery_threads.append(current_thread)
        self._worker.error.emit(error)
        self.error_sent.set()


class _WorkerTimeoutProbe(QObject):
    """Trigger timeout handling on the real worker's owning thread."""

    request_timeout = pyqtSignal()

    def __init__(self, worker: Any) -> None:
        super().__init__()
        self._worker = worker
        self.timeout_handled = Event()
        self.request_timeout.connect(self._trigger_timeout)

    @pyqtSlot()
    def _trigger_timeout(self) -> None:
        self._worker._on_timeout()
        self.timeout_handled.set()


class _QueuedSnapshotPublisher(QObject):
    """Represent a superseded runtime that publishes from its own QThread."""

    request_snapshot = pyqtSignal(object)
    snapshot_ready = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.snapshot_sent = Event()
        self.delivery_threads: list[QThread] = []
        self.request_snapshot.connect(self._publish_snapshot)

    @pyqtSlot(object)
    def _publish_snapshot(self, snapshot: object) -> None:
        current_thread = QThread.currentThread()
        assert current_thread is not None
        self.delivery_threads.append(current_thread)
        self.snapshot_ready.emit(snapshot)
        self.snapshot_sent.set()


class _UnusedWorkflowUiHandoffHost:
    """Keep unrelated in-flight workflow routing out of lifecycle evidence."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def open(self, _request: object, *, on_terminal: Any = None) -> Any:
        raise AssertionError("Runtime lifecycle tests must not open workflow surfaces.")

    def abandon_active(self) -> None:
        pass


@dataclass
class _RuntimeHarness:
    manager: AgentManager
    main_window: QMainWindow
    study: Study
    engine: _ControlledEngine
    config: LLMConfig

    @property
    def controller(self) -> Any:
        controller = self.manager.agent_controller
        assert controller is not None
        return controller

    @property
    def panel(self) -> Any:
        panel = self.manager.chat_panel
        assert panel is not None
        return panel

    @property
    def runtime(self) -> AssistantRuntimeLifecycle:
        """Return the manager-composed owner through its public contract."""
        return self.manager.assistant_runtime


def _wait_for_event(qtbot: Any, event: Event) -> None:
    qtbot.waitUntil(event.is_set, timeout=WATCHDOG_MS)


def _wait_for_phase(
    qtbot: Any,
    harness: _RuntimeHarness,
    phase: AssistantRuntimePhase,
) -> None:
    qtbot.waitUntil(
        lambda: harness.runtime.current.phase is phase,
        timeout=WATCHDOG_MS,
    )


def _drain_gui_turn(qtbot: Any) -> None:
    """Run a posted-event fence without relying on timing sleeps."""
    completed = Event()
    QTimer.singleShot(0, completed.set)
    _wait_for_event(qtbot, completed)


def _thread_has_stopped(thread: QThread) -> bool:
    try:
        return not thread.isRunning()
    except RuntimeError:
        return True


def _make_worker_probe(harness: _RuntimeHarness) -> _WorkerErrorProbe:
    worker = harness.controller.worker
    assert worker is not None
    probe = _WorkerErrorProbe(worker)
    probe.moveToThread(harness.controller.worker_thread)
    harness.controller.worker_thread.finished.connect(probe.deleteLater)
    return probe


def _make_timeout_probe(harness: _RuntimeHarness) -> _WorkerTimeoutProbe:
    worker = harness.controller.worker
    assert worker is not None
    probe = _WorkerTimeoutProbe(worker)
    probe.moveToThread(harness.controller.worker_thread)
    harness.controller.worker_thread.finished.connect(probe.deleteLater)
    return probe


@contextmanager
def _stale_snapshot_publisher(
    controller: Any,
) -> Iterator[tuple[_QueuedSnapshotPublisher, QThread]]:
    publisher = _QueuedSnapshotPublisher()
    stale_thread = QThread()
    stale_thread.setObjectName("SupersededAssistantRuntimeThread")
    publisher.moveToThread(stale_thread)
    publisher.snapshot_ready.connect(controller._on_runtime_snapshot_changed)
    stale_thread.finished.connect(publisher.deleteLater)
    stale_thread.start()
    try:
        yield publisher, stale_thread
    finally:
        stale_thread.quit()
        assert stale_thread.wait(WATCHDOG_MS)


@contextmanager
def _runtime_harness(
    qtbot: Any,
    monkeypatch: Any,
    *,
    use_real_workflow_router: bool = False,
    resolver: AssistantRuntimeLaunchResolver | None = None,
) -> Iterator[_RuntimeHarness]:
    """Build the real Qt runtime while replacing only external model work."""
    from XBrainLab.llm.agent import controller as controller_module
    from XBrainLab.llm.agent import worker as worker_module
    from XBrainLab.ui.components import agent_manager as agent_manager_module

    config = LLMConfig()
    config.timeout = 30
    engine = _ControlledEngine(config)

    config.local_model_enabled = True
    config.local_runtime_notice_acknowledged = True

    def _engine_factory(runtime_config: LLMConfig) -> _ControlledEngine:
        engine.config = runtime_config
        return engine

    monkeypatch.setattr(worker_module, "LLMEngine", _engine_factory)
    monkeypatch.setattr(
        LLMConfig,
        "load_from_file",
        classmethod(lambda cls, filepath=None: config),
    )
    monkeypatch.setattr(
        LLMConfig,
        "local_backend_ready",
        lambda self, model_id=None: True,
    )
    monkeypatch.setattr(
        LLMConfig,
        "local_backend_status_message",
        lambda self, model_id=None: "Local runtime ready.",
    )
    monkeypatch.setattr(
        LLMConfig,
        "local_backend_cpu_fallback_reason",
        lambda self: None,
    )
    monkeypatch.setattr(LLMConfig, "save_to_file", lambda self, filepath=None: None)
    monkeypatch.setattr(
        controller_module,
        "ProcessRAGRetrieverLifecycle",
        _NoopRagLifecycle,
    )
    if not use_real_workflow_router:
        monkeypatch.setattr(
            agent_manager_module,
            "WorkflowUiHandoffHost",
            _UnusedWorkflowUiHandoffHost,
        )

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = QToolButton(main_window)
    main_window.setCentralWidget(QWidget(main_window))
    main_window.resize(900, 640)

    study = Study()
    main_window.study = study
    manager = AgentManager(main_window, study)
    if resolver is not None:
        cast(Any, manager.assistant_runtime)._resolver = resolver
    manager.init_ui()
    main_window.show()
    assert manager.chat_dock is not None
    manager.chat_dock.show()

    harness = _RuntimeHarness(manager, main_window, study, engine, config)
    try:
        manager.start_system()
        yield harness
    finally:
        engine.release_all()
        _close_runtime_harness(qtbot, harness)
        _dispose_runtime_harness(harness)


def _close_runtime_harness(qtbot: Any, harness: _RuntimeHarness) -> None:
    """Wait for the real signal-driven runtime ownership to become terminal."""
    from XBrainLab.ui.components.assistant_runtime_lifecycle import (
        AssistantRuntimeLifecycleState,
    )

    harness.manager.close()
    qtbot.waitUntil(
        lambda: harness.runtime.state is AssistantRuntimeLifecycleState.CLOSED,
        timeout=WATCHDOG_MS,
    )
    assert harness.manager.close() is True


def _dispose_runtime_harness(harness: _RuntimeHarness) -> None:
    """Destroy top-level Qt ownership while the application can drain deletes."""
    app = QApplication.instance()
    assert app is not None
    harness.main_window.close()
    harness.main_window.deleteLater()
    drain_qt_runtime_after_event_loop(app)


def _release_initial_load(qtbot: Any, harness: _RuntimeHarness) -> None:
    _wait_for_event(qtbot, harness.engine.load_started)
    harness.engine.load_release.set()
    _wait_for_phase(qtbot, harness, AssistantRuntimePhase.READY)
    assert harness.panel.input_field.isEnabled()
    assert harness.panel.send_btn.isEnabled() is False


def _send_request(harness: _RuntimeHarness, text: str) -> None:
    harness.panel.input_field.setText(text)
    harness.panel.send_btn.click()


def _install_host_turn_lease(harness: _RuntimeHarness) -> AssistantTurnCorrelation:
    """Install one exact lease for tests that inject a post-admission callback."""
    submission = harness.manager._assistant_turn_state.begin_submission()
    correlation = AssistantTurnCorrelation(
        generation=submission.generation,
        turn_id=10_000 + submission.generation,
    )
    assert harness.manager._assistant_turn_state.accept_admission(
        submission,
        correlation,
    )
    harness.runtime._active_turn = correlation
    harness.controller._turn_orchestrator.host_turn_generation = correlation.generation
    harness.controller._turn_orchestrator.host_turn_id = correlation.turn_id
    return correlation


def _install_real_training_surface(
    qtbot: Any,
    harness: _RuntimeHarness,
) -> TrainingSidebar:
    """Attach the real training sidebar used by the product handoff host."""
    panel = SimpleNamespace(
        controller=harness.study.get_controller("training"),
        dataset_controller=harness.study.get_controller("dataset"),
        preprocess_controller=harness.study.get_controller("preprocess"),
        main_window=harness.main_window,
        update_panel=lambda: None,
    )
    sidebar = TrainingSidebar(panel)
    qtbot.addWidget(sidebar)
    panel.sidebar = sidebar
    main_window = cast(Any, harness.main_window)
    main_window.training_panel = panel
    main_window.switch_page = lambda _index: None
    return sidebar


def _run_scripted_dialog(
    dialog: QDialog,
    action: Any,
) -> QDialog.DialogCode:
    """Drive real dialog controls through a nested Qt event loop."""
    loop = QEventLoop()
    dialog.finished.connect(loop.quit)
    dialog.show()
    QTimer.singleShot(0, lambda: action(dialog))
    loop.exec()
    return QDialog.DialogCode(dialog.result())


def _model_dialog_accepts_eegnet(dialog: QDialog) -> None:
    assert isinstance(dialog, ModelSelectionDialog)
    assert dialog.model_combo is not None
    assert dialog.confirm_btn is not None
    dialog.model_combo.setCurrentText("EEGNet")
    dialog.confirm_btn.click()


def _training_dialog_cancel(dialog: QDialog) -> None:
    assert isinstance(dialog, TrainingSettingDialog)
    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    cancel = button_box.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel is not None
    cancel.click()


def _training_dialog_accepts_suggestions(dialog: QDialog) -> None:
    assert isinstance(dialog, TrainingSettingDialog)
    assert dialog.epoch_entry is not None
    assert dialog.bs_entry is not None
    assert dialog.lr_entry is not None
    assert dialog.bs_entry.text() == "32"
    assert dialog.lr_entry.text() == "0.001"
    dialog.epoch_entry.setText("12")
    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    ok = button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert ok is not None
    ok.click()


def test_loading_composer_blocks_dispatch_then_ready_dispatches_once(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _wait_for_event(qtbot, harness.engine.load_started)
        _wait_for_phase(qtbot, harness, AssistantRuntimePhase.LOADING)
        assert harness.engine.load_calls == 1
        send_spy = QSignalSpy(harness.panel.send_message)
        request = "Load EEG data from /tmp/runtime-lifecycle.edf"

        assert not harness.panel.input_field.isEnabled()
        assert not harness.panel.send_btn.isEnabled()
        harness.panel.input_field.setText(request)
        harness.panel.send_btn.click()
        harness.panel._on_send()
        harness.manager.handle_user_input(request)
        _drain_gui_turn(qtbot)

        assert len(send_spy) == 0
        assert harness.engine.generation_calls == 0
        assert not any(
            message["role"] == "user"
            for message in harness.manager.chat_controller.messages
        )

        harness.engine.load_release.set()
        _wait_for_phase(qtbot, harness, AssistantRuntimePhase.READY)
        assert harness.panel.input_field.isEnabled()
        assert harness.panel.send_btn.isEnabled()

        _send_request(harness, request)
        _wait_for_event(qtbot, harness.engine.generation_started)

        assert len(send_spy) == 1
        assert harness.engine.generation_calls == 1


def test_runtime_unavailable_presentation_preserves_activation_identity(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _wait_for_event(qtbot, harness.engine.load_started)
        _wait_for_phase(qtbot, harness, AssistantRuntimePhase.LOADING)
        activation_id = harness.runtime.expected_activation_id
        snapshot = harness.runtime.current
        assert activation_id is not None

        harness.manager._show_runtime_unavailable("Presentation-only notice")

        assert harness.runtime.expected_activation_id == activation_id
        assert harness.runtime.current == snapshot


def test_rapid_product_submissions_admit_only_first_turn(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _release_initial_load(qtbot, harness)

        harness.manager.handle_user_input("first queued request")
        harness.manager.handle_user_input("second queued request")

        user_messages = [
            message["content"]
            for message in harness.manager.chat_controller.messages
            if message["role"] == "user"
        ]
        assert user_messages == ["first queued request"]
        assert "previous request" in harness.panel.notice_label.text().lower()

        _wait_for_event(qtbot, harness.engine.generation_started)
        assert harness.engine.generation_calls == 1
        harness.engine.generation_release.set()
        qtbot.waitUntil(
            lambda: not harness.runtime.turn_in_flight,
            timeout=WATCHDOG_MS,
        )


def test_generation_timeout_retains_turn_until_thread_exit_then_retry_succeeds(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    timeout_response = (
        "The assistant could not complete the request. Try again. Technical "
        "details were written to the application log."
    )
    first_request = "Explain EEG epochs until the timeout"
    blocked_request = "This request must be rejected while generation is alive"
    retry_request = "Explain EEG epochs after the timeout"

    with _runtime_harness(qtbot, monkeypatch) as harness:
        _release_initial_load(qtbot, harness)
        harness.engine.cancel_releases_generation = False
        controller = harness.controller
        worker = controller.worker
        assert worker is not None
        terminal_spy = QSignalSpy(controller.turn_finished)
        error_spy = QSignalSpy(controller.error_occurred)
        timeout_probe = _make_timeout_probe(harness)

        _send_request(harness, first_request)
        _wait_for_event(qtbot, harness.engine.generation_started)
        generation_thread = worker.generation_thread
        assert generation_thread is not None
        assert generation_thread in ACTIVE_GENERATION_THREADS

        timeout_probe.request_timeout.emit()
        _wait_for_event(qtbot, timeout_probe.timeout_handled)
        _drain_gui_turn(qtbot)

        assert generation_thread.isRunning()
        assert worker.generation_thread is generation_thread
        assert harness.runtime.turn_in_flight is True
        assert controller.is_processing is True
        assert len(error_spy) == 0
        assert len(terminal_spy) == 0
        assert harness.engine.generation_calls == 1
        assert harness.engine.active_generations == 1
        assert harness.engine.max_active_generations == 1

        admissions = []
        submit = harness.runtime.submit

        def recording_submit(text: str, *, generation: int | None = None):
            admission = submit(text, generation=generation)
            admissions.append(admission)
            return admission

        monkeypatch.setattr(harness.runtime, "submit", recording_submit)
        harness.manager.handle_user_input(blocked_request)

        assert len(admissions) == 1
        assert admissions[0].status is RuntimeCommandAdmissionStatus.BUSY
        assert [
            message["content"]
            for message in harness.manager.chat_controller.messages
            if message["role"] == "user"
        ] == [first_request]
        assert harness.engine.generation_calls == 1
        assert harness.engine.max_active_generations == 1

        harness.engine.generation_release.set()
        qtbot.waitUntil(
            lambda: _thread_has_stopped(generation_thread),
            timeout=WATCHDOG_MS,
        )
        qtbot.waitUntil(lambda: not harness.runtime.turn_in_flight, timeout=WATCHDOG_MS)
        _drain_gui_turn(qtbot)

        assert len(error_spy) == 1
        assert "timed out" in error_spy[0][0].lower()
        assert len(terminal_spy) == 1
        assert terminal_spy[0][0].outcome == "generation_error"
        assert [
            message["content"]
            for message in harness.manager.chat_controller.messages
            if message["role"] == "assistant"
        ] == [timeout_response]
        assert generation_thread not in ACTIVE_GENERATION_THREADS
        assert harness.engine.active_generations == 0
        assert harness.engine.max_active_generations == 1

        harness.engine.cancel_requested.clear()
        harness.engine.generation_started.clear()
        harness.engine.generation_release.clear()
        harness.manager.handle_user_input(retry_request)
        _wait_for_event(qtbot, harness.engine.generation_started)
        assert harness.engine.generation_calls == 2
        assert harness.engine.max_active_generations == 1

        harness.engine.generation_release.set()
        qtbot.waitUntil(lambda: len(terminal_spy) == 2, timeout=WATCHDOG_MS)
        qtbot.waitUntil(lambda: not harness.runtime.turn_in_flight, timeout=WATCHDOG_MS)

        assert terminal_spy[1][0].outcome == "completed"
        assert [
            message["content"]
            for message in harness.manager.chat_controller.messages
            if message["role"] == "user"
        ] == [first_request, retry_request]
        assert [
            message["content"]
            for message in harness.manager.chat_controller.messages
            if message["role"] == "assistant"
        ] == [
            timeout_response,
            (
                "I inspected the requested EEG workflow. No application command "
                "was executed."
            ),
        ]
        assert harness.engine.active_generations == 0
        assert harness.engine.max_active_generations == 1

    assert not ACTIVE_GENERATION_THREADS


def test_real_product_submission_uses_backend_admission_before_model_generation(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _release_initial_load(qtbot, harness)

        _send_request(harness, "Train now.")
        qtbot.waitUntil(
            lambda: len(harness.manager.chat_controller.messages) >= 2,
            timeout=WATCHDOG_MS,
        )
        qtbot.waitUntil(
            lambda: not harness.manager.chat_controller.is_processing,
            timeout=WATCHDOG_MS,
        )

        messages = harness.manager.chat_controller.messages
        assert messages[0] == {"role": "user", "content": "Train now."}
        assert messages[1]["role"] == "assistant"
        assert "not available yet" in messages[1]["content"].lower()
        assert harness.engine.generation_calls == 0


def test_real_product_stop_has_one_terminal_response_and_no_late_model_text(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _release_initial_load(qtbot, harness)
        request = "Load EEG data from /tmp/cancel-this-request.edf"

        _send_request(harness, request)
        _wait_for_event(qtbot, harness.engine.generation_started)
        qtbot.waitUntil(
            lambda: harness.panel.send_btn.text() == "Stop",
            timeout=WATCHDOG_MS,
        )
        harness.panel.send_btn.click()
        qtbot.waitUntil(
            lambda: not harness.manager.chat_controller.is_processing,
            timeout=WATCHDOG_MS,
        )
        _drain_gui_turn(qtbot)

        messages = harness.manager.chat_controller.messages
        assert messages[0] == {"role": "user", "content": request}
        assistant_messages = [
            message["content"] for message in messages if message["role"] == "assistant"
        ]
        assert len(assistant_messages) == 1
        assert assistant_messages == [
            "Request cancelled. You can revise it or ask something else."
        ]
        assert "inspected the requested EEG workflow" not in " ".join(
            message["content"] for message in messages
        )
        assert harness.engine.cancel_calls == 1
        assert harness.runtime.turn_in_flight is False
        assert [
            message["content"]
            for message in harness.manager.chat_controller.messages
            if message["role"] == "user"
        ] == [request]

        harness.engine.generation_release.set()
        qtbot.waitUntil(
            lambda: not harness.manager.chat_controller.is_processing,
            timeout=WATCHDOG_MS,
        )
        assert harness.engine.generation_calls == 1


def test_worker_error_releases_runtime_turn_and_allows_next_submission(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    retry_request = "Explain EEG epochs after the worker error"
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _release_initial_load(qtbot, harness)
        harness.engine.generation_failure = RuntimeError("deterministic failure")

        _send_request(harness, "request that fails in the worker")
        _wait_for_event(qtbot, harness.engine.generation_started)
        assert harness.runtime.turn_in_flight is True
        harness.engine.generation_release.set()

        qtbot.waitUntil(
            lambda: not harness.runtime.turn_in_flight,
            timeout=WATCHDOG_MS,
        )
        qtbot.waitUntil(
            lambda: not harness.manager.chat_controller.is_processing,
            timeout=WATCHDOG_MS,
        )
        assert harness.engine.generation_calls == 1

        harness.engine.generation_failure = None
        harness.manager.handle_user_input(retry_request)
        qtbot.waitUntil(
            lambda: harness.engine.generation_calls == 2,
            timeout=WATCHDOG_MS,
        )
        qtbot.waitUntil(
            lambda: not harness.runtime.turn_in_flight,
            timeout=WATCHDOG_MS,
        )
        assert [
            message["content"]
            for message in harness.manager.chat_controller.messages
            if message["role"] == "user"
        ] == [
            "request that fails in the worker",
            retry_request,
        ]


def test_incomplete_training_handoff_cancel_preserves_backend_state(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(
        qtbot,
        monkeypatch,
        use_real_workflow_router=True,
    ) as harness:
        _release_initial_load(qtbot, harness)
        _install_real_training_surface(qtbot, harness)
        before = get_application_service(harness.study).get_state().training
        recorded_commands: list[object] = []
        original_execute = ApplicationService.execute

        def recording_execute(
            service: ApplicationService,
            command: object,
            **kwargs: object,
        ):
            recorded_commands.append(command)
            return original_execute(service, command, **kwargs)

        monkeypatch.setattr(ApplicationService, "execute", recording_execute)
        monkeypatch.setattr(
            ModelSelectionDialog,
            "exec",
            lambda dialog: _run_scripted_dialog(
                dialog,
                _model_dialog_accepts_eegnet,
            ),
        )
        monkeypatch.setattr(
            TrainingSettingDialog,
            "exec",
            lambda dialog: _run_scripted_dialog(dialog, _training_dialog_cancel),
        )
        request_spy = QSignalSpy(harness.controller.workflow_ui_handoff_requested)
        outcome_spy = QSignalSpy(harness.controller.interaction_resolved)
        request = "Configure training with batch size 32 and learning rate 0.001."

        _send_request(harness, request)
        qtbot.waitUntil(
            lambda: len(outcome_spy) == 1,
            timeout=WATCHDOG_MS,
        )
        qtbot.waitUntil(
            lambda: not harness.manager.chat_controller.is_processing,
            timeout=WATCHDOG_MS,
        )

        assert len(request_spy) == 1
        handoff = request_spy[0][0]
        assert isinstance(handoff, WorkflowUiHandoffRequest)
        assert handoff.command_name == "configure_training"
        assert handoff.decision_fields == ("model", "training_options")
        assert len(outcome_spy) == 1
        outcome = outcome_spy[0][0]
        assert outcome == AgentInteractionOutcome(
            status=AgentInteractionStatus.CANCELLED,
            command_name="configure_training",
            request_id=handoff.request_id,
            decision_fields=("model", "training_options"),
            message="Training settings were cancelled.",
        )
        assert not any(
            isinstance(command, ConfigureTrainingCommand)
            for command in recorded_commands
        )
        after = get_application_service(harness.study).get_state().training
        assert after == before
        assert harness.study.training_manager.model_holder is None
        assert harness.study.training_manager.training_option is None
        assert harness.engine.generation_calls == 0
        assert harness.manager.chat_controller.messages == [
            {"role": "user", "content": request},
            {
                "role": "assistant",
                "content": (
                    "Configure training was cancelled. "
                    "Your current workflow is unchanged."
                ),
            },
        ]


def test_incomplete_training_handoff_commits_one_backend_command(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(
        qtbot,
        monkeypatch,
        use_real_workflow_router=True,
    ) as harness:
        _release_initial_load(qtbot, harness)
        _install_real_training_surface(qtbot, harness)
        recorded_commands: list[object] = []
        original_execute = ApplicationService.execute

        def recording_execute(
            service: ApplicationService,
            command: object,
            **kwargs: object,
        ):
            recorded_commands.append(command)
            return original_execute(service, command, **kwargs)

        monkeypatch.setattr(ApplicationService, "execute", recording_execute)
        monkeypatch.setattr(
            ModelSelectionDialog,
            "exec",
            lambda dialog: _run_scripted_dialog(
                dialog,
                _model_dialog_accepts_eegnet,
            ),
        )
        monkeypatch.setattr(
            TrainingSettingDialog,
            "exec",
            lambda dialog: _run_scripted_dialog(
                dialog,
                _training_dialog_accepts_suggestions,
            ),
        )
        request_spy = QSignalSpy(harness.controller.workflow_ui_handoff_requested)
        outcome_spy = QSignalSpy(harness.controller.interaction_resolved)
        request = "Configure training with batch size 32 and learning rate 0.001."

        _send_request(harness, request)
        qtbot.waitUntil(
            lambda: len(outcome_spy) == 1,
            timeout=WATCHDOG_MS,
        )
        qtbot.waitUntil(
            lambda: not harness.manager.chat_controller.is_processing,
            timeout=WATCHDOG_MS,
        )

        assert len(request_spy) == 1
        handoff = request_spy[0][0]
        assert isinstance(handoff, WorkflowUiHandoffRequest)
        assert len(outcome_spy) == 1
        outcome = outcome_spy[0][0]
        assert outcome.status is AgentInteractionStatus.COMPLETED_IN_UI
        assert outcome.request_id == handoff.request_id
        configure_commands = [
            command
            for command in recorded_commands
            if isinstance(command, ConfigureTrainingCommand)
        ]
        assert len(configure_commands) == 1
        command = cast(ConfigureTrainingCommand, configure_commands[0])
        assert command.model_name == "braindecode.eegnet"
        assert command.epoch == 12
        assert command.batch_size == 32
        assert command.learning_rate == 0.001
        state = get_application_service(harness.study).get_state().training
        assert state.has_model is True
        assert state.model_name == "EEGNet (Braindecode)"
        assert state.has_training_option is True
        assert harness.engine.generation_calls == 0
        assert harness.manager.chat_controller.messages == [
            {"role": "user", "content": request},
            {
                "role": "assistant",
                "content": "Configure training was completed in XBrainLab.",
            },
        ]


def test_pending_agent_decision_resolves_through_real_ui_handoff_signal(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(
        qtbot,
        monkeypatch,
        use_real_workflow_router=True,
    ) as harness:
        _release_initial_load(qtbot, harness)
        opened = Event()
        switched_pages: list[int] = []

        def open_epoching() -> InteractionOutcome:
            opened.set()
            return InteractionOutcome.completed("Epoch settings were saved.")

        main_window = cast(Any, harness.main_window)
        main_window.preprocess_panel = SimpleNamespace(
            sidebar=SimpleNamespace(open_epoching=open_epoching)
        )
        main_window.switch_page = switched_pages.append
        request = WorkflowUiHandoffRequest.for_decision(
            "create_epoch",
            decision_fields=("target_event", "epoch_window"),
        )
        controller = harness.controller
        correlation = _install_host_turn_lease(harness)
        controller.pending_interactions.begin_workflow_handoff(request)
        controller._tool_attempt_session.visible_response_sent = True
        controller.is_processing = True
        outcome_spy = QSignalSpy(controller.interaction_resolved)
        harness.manager.on_assistant_activity_changed(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.WAITING_FOR_DECISION,
                command_name=request.command_name,
                request_id=request.request_id,
                turn_id=correlation.turn_id,
                generation=correlation.generation,
                decision_owner=AssistantDecisionOwner.PANEL_HANDOFF,
            )
        )

        controller.workflow_ui_handoff_requested.emit(request)

        _wait_for_event(qtbot, opened)
        qtbot.waitUntil(
            lambda: controller.pending_interactions.workflow_handoff is None,
            timeout=WATCHDOG_MS,
        )
        assert switched_pages == [1]
        assert len(outcome_spy) == 1
        assert outcome_spy[0][0] == AgentInteractionOutcome(
            status=AgentInteractionStatus.COMPLETED_IN_UI,
            command_name="create_epoch",
            request_id=request.request_id,
            decision_fields=("target_event", "epoch_window"),
            message="Epoch settings were saved.",
        )
        assert controller.is_processing is False
        qtbot.waitUntil(
            lambda: bool(harness.manager.chat_controller.messages),
            timeout=WATCHDOG_MS,
        )
        assert harness.manager.chat_controller.messages == [
            {
                "role": "assistant",
                "content": "Create EEG epochs was completed in XBrainLab.",
            }
        ]


def test_cancelled_confirmation_has_one_terminal_manager_presentation(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _release_initial_load(qtbot, harness)
        controller = harness.controller
        correlation = _install_host_turn_lease(harness)
        decision = ToolAttemptDecision(
            action=ToolAttemptAction.CONFIRMATION_REQUIRED,
            command_name="reset_preprocess",
            params={},
        )
        request = AgentConfirmationRequest.for_action(
            command_name="reset_preprocess",
            params={},
            action_label="Reset preprocessing",
            description="Restore the loaded EEG data to its raw state.",
            destructive=True,
            publication_generation=None,
        )
        controller.pending_interactions.begin_confirmation(decision, request)
        controller._tool_attempt_session.last_tool_summary = (
            "The assistant completed a background action."
        )
        outcome_spy = QSignalSpy(controller.interaction_resolved)
        harness.manager.on_assistant_activity_changed(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.WAITING_FOR_DECISION,
                command_name=request.command_name,
                request_id=request.request_id,
                turn_id=correlation.turn_id,
                generation=correlation.generation,
                decision_owner=AssistantDecisionOwner.CONFIRMATION_CARD,
            )
        )
        harness.manager._show_action_confirmation(request)
        assert harness.panel.confirmation_card_widget.isVisibleTo(harness.panel)
        harness.panel.confirmation_card_widget.secondary_button.click()

        qtbot.waitUntil(
            lambda: controller.pending_interactions.confirmation_decision is None,
            timeout=WATCHDOG_MS,
        )
        qtbot.waitUntil(
            lambda: len(harness.manager.chat_controller.messages) == 1,
            timeout=WATCHDOG_MS,
        )
        assert len(outcome_spy) == 1
        assert outcome_spy[0][0] == AgentInteractionOutcome(
            status=AgentInteractionStatus.CANCELLED,
            command_name="reset_preprocess",
            request_id=request.request_id,
        )
        visible = harness.manager.chat_controller.messages[0]["content"]
        assert visible == (
            "Preprocessing reset cancelled. Your current workflow is unchanged."
        )
        assert "workflow is unchanged" in visible
        assert "background action completed" not in visible.lower()
        assert controller._tool_attempt_session.execution_count == 0


def test_model_switch_ignores_stale_ready_until_target_is_ready(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(
        qtbot,
        monkeypatch,
        resolver=_TestLaunchResolver(),
    ) as harness:
        _release_initial_load(qtbot, harness)
        controller = harness.controller
        runtime_spy = QSignalSpy(controller.runtime_state_changed)
        old_model = LLMConfig.default_local_model_id()
        target_model = TEST_TARGET_MODEL_ID
        assert old_model != target_model

        with _stale_snapshot_publisher(controller) as (publisher, stale_thread):
            model_request_spy = QSignalSpy(harness.runtime.dispatcher.model_requested)
            harness.manager.set_model(target_model)
            requested_spec = model_request_spy[-1][0]
            assert requested_spec.requested_model_id == target_model
            assert requested_spec.model_id == target_model
            _wait_for_event(qtbot, harness.engine.switch_started)
            _wait_for_phase(qtbot, harness, AssistantRuntimePhase.LOADING)
            assert harness.engine.switch_calls == 1
            baseline = len(runtime_spy)

            stale_ready = AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.READY,
                initialized=True,
                backend_mode="local",
                model_id=old_model,
            )
            publisher.request_snapshot.emit(stale_ready)
            _wait_for_event(qtbot, publisher.snapshot_sent)
            qtbot.waitUntil(lambda: len(runtime_spy) > baseline, timeout=WATCHDOG_MS)
            _drain_gui_turn(qtbot)

            assert publisher.delivery_threads == [stale_thread]
            assert runtime_spy[-1][0] == stale_ready
            assert harness.runtime.current.phase is AssistantRuntimePhase.LOADING
            assert not harness.panel.input_field.isEnabled()

            harness.engine.switch_release.set()
            _wait_for_phase(qtbot, harness, AssistantRuntimePhase.READY)
            assert harness.runtime.current.model_id == target_model
            assert harness.panel.input_field.isEnabled()


def test_retry_loading_replaces_only_stale_runtime_failure_presentation(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    """FAILED -> LOADING must replace only runtime-owned presentation."""
    with _runtime_harness(
        qtbot,
        monkeypatch,
        resolver=_TestLaunchResolver(),
    ) as harness:
        _release_initial_load(qtbot, harness)
        original_controller = harness.controller
        original_worker_thread = original_controller.worker_thread
        original_command_thread = harness.runtime.dispatcher.command_thread
        harness.manager.chat_controller.add_user_message("Keep this question")
        harness.manager.chat_controller.add_agent_message("Keep this answer")

        harness.controller.runtime_state_changed.emit(
            AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.FAILED,
                initialized=False,
                backend_mode="local",
                error="Model Load Error: deterministic failure",
            ),
        )
        _wait_for_phase(qtbot, harness, AssistantRuntimePhase.FAILED)
        harness.controller.error_occurred.emit(
            "Model Load Error: deterministic failure",
        )
        _drain_gui_turn(qtbot)

        assert harness.panel.runtime_state_widget.isVisible()
        assert harness.panel.runtime_state_title.text() == "Assistant unavailable"
        assert [
            message["content"] for message in harness.manager.chat_controller.messages
        ] == ["Keep this question", "Keep this answer"]

        target_model = TEST_TARGET_MODEL_ID
        harness.manager.set_model(target_model)
        _wait_for_event(qtbot, harness.engine.switch_started)
        _wait_for_phase(qtbot, harness, AssistantRuntimePhase.LOADING)

        assert harness.panel.runtime_state_widget.isVisible()
        assert harness.panel.runtime_state_title.text() == ("Retrying local assistant")
        assert [
            message["content"] for message in harness.manager.chat_controller.messages
        ] == ["Keep this question", "Keep this answer"]

        harness.engine.switch_release.set()
        _wait_for_phase(qtbot, harness, AssistantRuntimePhase.READY)
        assert harness.controller is original_controller
        assert harness.controller.worker_thread is original_worker_thread
        assert harness.runtime.dispatcher.command_thread is original_command_thread


def test_model_switch_is_rejected_without_disturbing_active_generation(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(
        qtbot,
        monkeypatch,
        resolver=_TestLaunchResolver(),
    ) as harness:
        _release_initial_load(qtbot, harness)
        _send_request(harness, "Explain how EEG artifacts are reviewed")
        _wait_for_event(qtbot, harness.engine.generation_started)

        target_model = TEST_TARGET_MODEL_ID
        harness.manager.set_model(target_model)

        assert harness.engine.switch_started.is_set() is False
        assert harness.runtime.current.phase is AssistantRuntimePhase.READY
        assert harness.runtime.current.initialized is True
        assert harness.runtime.current.model_id == LLMConfig.default_local_model_id()
        assert harness.runtime.active_local_runtime_blocks_model_deletion() is True
        assert harness.runtime.expected_activation_id is None
        assert harness.runtime.turn_in_flight is True

        harness.engine.generation_release.set()
        qtbot.waitUntil(lambda: not harness.runtime.turn_in_flight, timeout=WATCHDOG_MS)


def test_close_during_model_load_stops_both_runtime_threads(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _wait_for_event(qtbot, harness.engine.load_started)
        controller = harness.controller
        worker_thread = controller.worker_thread
        command_thread = harness.runtime.dispatcher.command_thread
        assert isinstance(command_thread, QThread)

        harness.runtime.dispatcher.shutdown_requested.connect(
            harness.engine.load_release.set
        )
        _close_runtime_harness(qtbot, harness)

        assert harness.engine.close_called.is_set()
        assert _thread_has_stopped(worker_thread)
        assert _thread_has_stopped(command_thread)
        assert controller.worker is None


def test_close_during_generation_cancels_job_and_stops_threads(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _release_initial_load(qtbot, harness)
        _send_request(harness, "Load EEG data from /tmp/close-during-generation.edf")
        _wait_for_event(qtbot, harness.engine.generation_started)

        controller = harness.controller
        worker = controller.worker
        assert worker is not None
        generation_thread = worker.generation_thread
        assert generation_thread is not None
        worker_thread = controller.worker_thread
        command_thread = harness.runtime.dispatcher.command_thread
        assert isinstance(command_thread, QThread)
        assert generation_thread.isRunning()

        _close_runtime_harness(qtbot, harness)

        assert harness.engine.cancel_requested.is_set()
        assert harness.engine.cancel_calls == 1
        assert harness.runtime.turn_in_flight is False
        assert harness.engine.close_called.is_set()
        assert _thread_has_stopped(generation_thread)
        assert generation_thread not in ACTIVE_GENERATION_THREADS
        assert _thread_has_stopped(worker_thread)
        assert _thread_has_stopped(command_thread)


def test_teardown_drains_owned_threads_before_recreating_runtime_in_process(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    assert not ACTIVE_GENERATION_THREADS
    assert not ACTIVE_RUNTIME_LOAD_THREADS

    for cycle in range(2):
        with _runtime_harness(qtbot, monkeypatch) as harness:
            _wait_for_event(qtbot, harness.engine.load_started)
            worker = harness.controller.worker
            assert worker is not None
            runtime_load_thread = worker.runtime_load_thread
            assert runtime_load_thread is not None
            assert runtime_load_thread in ACTIVE_RUNTIME_LOAD_THREADS

            harness.engine.load_release.set()
            _wait_for_phase(qtbot, harness, AssistantRuntimePhase.READY)
            _send_request(harness, f"Inspect lifecycle cycle {cycle + 1}")
            _wait_for_event(qtbot, harness.engine.generation_started)

            generation_thread = worker.generation_thread
            assert generation_thread is not None
            assert generation_thread in ACTIVE_GENERATION_THREADS
            worker_thread = harness.controller.worker_thread
            command_thread = harness.runtime.dispatcher.command_thread
            assert isinstance(command_thread, QThread)
            window = harness.main_window

        assert _thread_has_stopped(runtime_load_thread)
        assert _thread_has_stopped(generation_thread)
        assert _thread_has_stopped(worker_thread)
        assert _thread_has_stopped(command_thread)
        assert not ACTIVE_GENERATION_THREADS
        assert not ACTIVE_RUNTIME_LOAD_THREADS
        assert sip.isdeleted(runtime_load_thread)
        assert sip.isdeleted(generation_thread)
        assert sip.isdeleted(window)


def test_worker_traceback_is_sanitized_before_visible_bubble(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    with _runtime_harness(qtbot, monkeypatch) as harness:
        _release_initial_load(qtbot, harness)
        controller = harness.controller
        error_spy = QSignalSpy(controller.error_occurred)
        probe = _make_worker_probe(harness)
        raw_traceback = (
            "Traceback (most recent call last):\n"
            '  File "/private/project/agent_runtime.py", line 42, in generate\n'
            "    raise RuntimeError('secret-token-123')\n"
            "RuntimeError: secret-token-123"
        )

        _install_host_turn_lease(harness)
        controller.is_processing = True
        harness.manager.chat_controller.set_processing(True)
        probe.request_error.emit(raw_traceback)
        _wait_for_event(qtbot, probe.error_sent)
        qtbot.waitUntil(lambda: len(error_spy) == 1, timeout=WATCHDOG_MS)
        qtbot.waitUntil(
            lambda: any(
                message["role"] == "assistant"
                for message in harness.manager.chat_controller.messages
            ),
            timeout=WATCHDOG_MS,
        )

        assert probe.delivery_threads == [controller.worker_thread]
        assert error_spy[0][0] == raw_traceback
        visible_message = next(
            message["content"]
            for message in reversed(harness.manager.chat_controller.messages)
            if message["role"] == "assistant"
        )
        assert visible_message.startswith(
            "The assistant could not complete the request."
        )
        assert "application log" in visible_message
        assert "Traceback" not in visible_message
        assert "/private/project" not in visible_message
        assert "secret-token-123" not in visible_message
        qtbot.waitUntil(
            lambda: (
                (bubble := harness.panel._latest_message_bubble()) is not None
                and bubble.get_text() == visible_message
            ),
            timeout=WATCHDOG_MS,
        )
        bubble = harness.panel._latest_message_bubble()
        assert bubble is not None
        assert bubble.get_text() == visible_message
