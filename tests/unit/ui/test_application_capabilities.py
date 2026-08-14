"""Tests for UI reads of ApplicationService command capabilities."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock
from weakref import ref

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QThread, QTimer
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import (
    ApplicationViewPublication,
    ChangedState,
    Command,
    CommandName,
    CommandResult,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    ResetSessionCommand,
    TrainCommand,
    get_application_service,
)
from XBrainLab.backend.application.epoch_context import EpochDialogContext
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui import (
    application_capabilities,
    async_command_runner,
    refresh_coordinator,
)
from XBrainLab.ui.application_capabilities import (
    application_background_tasks_idle,
    cancel_application_operation,
    execute_application_command,
    execute_application_command_async,
    get_command_capability,
    get_command_review_context,
    get_epoch_dialog_context,
    get_interpretation_review,
    release_application_shutdown_fence,
    request_application_shutdown_fence,
    run_controller_compatibility_call,
)
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.interaction_outcome import (
    InteractionCompletionSession,
    InteractionCompletionStatus,
    bind_interaction_completion,
)
from XBrainLab.ui.refresh_coordinator import refresh_after_observer


class _ApplicationRuntimeFake:
    def __init__(
        self,
        *,
        publication: ApplicationViewPublication | None = None,
        execute: Callable[[Command], CommandResult] | None = None,
        epoch_dialog_context: EpochDialogContext | None = None,
    ) -> None:
        self._publication = publication
        self._execute = execute
        self._epoch_dialog_context = epoch_dialog_context
        self.commands: list[Command] = []
        self.publication_reads = 0
        self.epoch_dialog_context_reads = 0
        self.shutdown_requests = 0
        self.shutdown_releases = 0
        self.shutdown_release_succeeds = True
        self.background_waits: list[float | None] = []
        self.background_idle = True
        self.interpretation_review: dict[str, Any] = {}
        self.expected_publication_generations: list[int | None] = []
        self.operation_ids: list[str | None] = []
        self.begun_operations: list[tuple[str, Command]] = []
        self.cancelled_operations: list[str] = []
        self.failed_operations: list[tuple[str, str]] = []

    def get_view_publication(self) -> ApplicationViewPublication:
        self.publication_reads += 1
        if self._publication is None:
            raise AssertionError("publication was not configured for this fake")
        return self._publication

    def execute(
        self,
        command: Command,
        *,
        expected_publication_generation: int | None = None,
        operation_id: str | None = None,
    ) -> CommandResult:
        self.commands.append(command)
        self.expected_publication_generations.append(
            expected_publication_generation,
        )
        self.operation_ids.append(operation_id)
        if self._execute is None:
            raise AssertionError("command execution was not configured for this fake")
        return self._execute(command)

    def begin_owned_operation(self, command: Command) -> Any:
        operation_id = f"operation-{len(self.begun_operations) + 1}"
        self.begun_operations.append((operation_id, command))
        return SimpleNamespace(operation_id=operation_id)

    def cancel_owned_operation(self, operation_id: str) -> bool:
        self.cancelled_operations.append(operation_id)
        return True

    def fail_owned_operation(self, operation_id: str, *, message: str) -> Any:
        self.failed_operations.append((operation_id, message))
        return SimpleNamespace(operation_id=operation_id)

    def get_interpretation_review(
        self,
        *,
        expected_identity=None,
    ) -> dict[str, Any]:
        return dict(self.interpretation_review)

    def get_epoch_dialog_context(self) -> EpochDialogContext:
        self.epoch_dialog_context_reads += 1
        if self._epoch_dialog_context is None:
            raise AssertionError(
                "epoch dialog context was not configured for this fake"
            )
        return self._epoch_dialog_context

    def get_saliency_render(self, request: Any) -> Any:
        raise AssertionError(
            f"saliency render was not configured for this fake: {request!r}",
        )

    def request_shutdown_fence(self) -> None:
        self.shutdown_requests += 1

    def release_shutdown_fence(self) -> bool:
        self.shutdown_releases += 1
        return self.shutdown_release_succeeds

    def wait_for_background_tasks(self, timeout: float | None = None) -> bool:
        self.background_waits.append(timeout)
        return self.background_idle


def _unexpected_execution(message: str) -> Callable[[Command], CommandResult]:
    def fail(_command: Command) -> CommandResult:
        raise AssertionError(message)

    return fail


def test_ui_capability_helper_returns_application_policy(qtbot):
    study = Study()
    widget = QWidget()
    main_window = MagicMock()
    main_window.study = study
    cast(Any, widget).main_window = main_window
    qtbot.addWidget(widget)

    ui_capability = get_command_capability(widget, CommandName.TRAIN)
    backend_capability = (
        get_application_service(study)
        .get_capabilities()
        .get(
            CommandName.TRAIN,
        )
    )

    assert ui_capability is not None
    assert ui_capability.enabled == backend_capability.enabled
    assert ui_capability.reasons == backend_capability.reasons


def test_application_runtime_does_not_follow_dynamic_mock_parent_chain():
    context = MagicMock()
    context.study = Study()

    runtime = application_capabilities.application_ui_runtime(context)

    assert runtime is not None
    context.parent.assert_not_called()


def test_application_runtime_unsubscribe_is_safe_after_shutdown_owner_is_gone(
    monkeypatch,
) -> None:
    class _DesktopHost:
        _closing_in_progress = True

    study = Study()
    host = _DesktopHost()
    runtime = application_capabilities._StudyApplicationUiRuntime(study, ref(host))

    def callback() -> None:
        return None

    monkeypatch.setattr(
        "XBrainLab.backend.application.runtime.get_initialized_application_service",
        lambda _study: None,
    )

    runtime.unsubscribe(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, callback)


def test_application_runtime_unsubscribe_uses_existing_service_during_shutdown(
    monkeypatch,
) -> None:
    class _DesktopHost:
        _closing_in_progress = True

    study = Study()
    host = _DesktopHost()
    service = MagicMock()
    runtime = application_capabilities._StudyApplicationUiRuntime(study, ref(host))

    def callback() -> None:
        return None

    monkeypatch.setattr(
        "XBrainLab.backend.application.runtime.get_initialized_application_service",
        lambda _study: service,
    )

    runtime.unsubscribe(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, callback)

    service.unsubscribe.assert_called_once_with(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        callback,
    )


def test_ui_publication_helper_returns_one_full_application_publication(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    publication = get_application_service(Study()).get_view_publication()
    runtime = _ApplicationRuntimeFake(publication=publication)

    observed = application_capabilities.get_application_view_publication(
        widget,
        runtime=runtime,
    )

    assert observed is publication
    assert runtime.publication_reads == 1


def test_command_review_context_binds_capability_to_one_publication(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    publication = get_application_service(Study()).get_view_publication()
    runtime = _ApplicationRuntimeFake(publication=publication)

    context = get_command_review_context(
        widget,
        CommandName.REMOVE_FILES,
        runtime=runtime,
    )

    assert context is not None
    assert context.publication_generation == publication.generation
    assert context.capability == publication.effective_capabilities.get(
        CommandName.REMOVE_FILES,
    )
    assert runtime.publication_reads == 1


def test_interpretation_review_helper_reads_application_runtime(qtbot) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    runtime = _ApplicationRuntimeFake()
    runtime.interpretation_review = {
        "candidate": {"candidate_id": "candidate-1"},
        "validation_decision": {"decision": "needs_confirmation"},
    }

    assert get_interpretation_review(widget, runtime=runtime) == (
        runtime.interpretation_review
    )


def test_background_task_idle_helper_uses_runtime_lifecycle_boundary(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    runtime = _ApplicationRuntimeFake()
    runtime.background_idle = False

    assert (
        application_background_tasks_idle(widget, runtime=runtime, timeout=0.0) is False
    )
    assert runtime.background_waits == [0.0]


def test_ui_capability_helper_fails_closed_for_stale_publication(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    publication = get_application_service(study).get_view_publication()
    stale_publication = replace(
        publication,
        stale=True,
        refresh_error="backend refresh failed",
    )
    runtime = _ApplicationRuntimeFake(publication=stale_publication)

    capability = get_command_capability(
        widget,
        CommandName.TRAIN,
        runtime=runtime,
    )

    assert capability is not None
    assert capability.enabled is False
    assert capability.can_auto_execute is False
    assert capability.reasons == [PUBLIC_VIEW_UNAVAILABLE_MESSAGE]
    assert "backend refresh failed" not in capability.reasons


def test_ui_capability_helper_ignores_non_product_study(qtbot):
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=object())
    qtbot.addWidget(widget)

    assert get_command_capability(widget, CommandName.TRAIN) is None


def test_application_publication_read_failure_fails_closed(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    runtime = _ApplicationRuntimeFake()
    runtime.get_view_publication = MagicMock(
        side_effect=RuntimeError("authoritative publication unavailable")
    )

    publication = application_capabilities.get_application_view_publication(
        widget,
        runtime=runtime,
    )
    capability = get_command_capability(
        widget,
        CommandName.TRAIN,
        runtime=runtime,
    )

    assert publication is None
    assert capability is None


def test_invalid_application_publication_shape_fails_closed(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    runtime = _ApplicationRuntimeFake()
    runtime.get_view_publication = MagicMock(return_value={"verified": True})

    publication = application_capabilities.get_application_view_publication(
        widget,
        runtime=runtime,
    )

    assert publication is None


def test_epoch_dialog_context_delegates_one_typed_runtime_read(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    expected = EpochDialogContext(
        capability=MagicMock(),
        epoch_handoff={"ready": True},
        epoch_setup={"available_events": [{"name": "Left hand", "count": 2}]},
        publication_generation=7,
        usable=True,
        unavailable_reason=None,
    )
    runtime = _ApplicationRuntimeFake(epoch_dialog_context=expected)

    context = get_epoch_dialog_context(widget, runtime=runtime)

    assert context is expected
    assert runtime.epoch_dialog_context_reads == 1
    assert runtime.publication_reads == 0
    assert runtime.commands == []


def test_epoch_dialog_context_returns_typed_unavailable_on_runtime_error(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    runtime = _ApplicationRuntimeFake()
    runtime.get_epoch_dialog_context = MagicMock(
        side_effect=RuntimeError("authoritative context read failed")
    )

    context = get_epoch_dialog_context(widget, runtime=runtime)

    assert isinstance(context, EpochDialogContext)
    assert context.usable is False
    assert context.epoch_handoff is None
    assert context.epoch_setup is None
    assert context.publication_generation is None
    assert context.unavailable_reason == PUBLIC_VIEW_UNAVAILABLE_MESSAGE
    with pytest.raises(PreconditionError, match=PUBLIC_VIEW_UNAVAILABLE_MESSAGE):
        context.require_usable()
    runtime.get_epoch_dialog_context.assert_called_once_with()


def test_epoch_dialog_context_rejects_invalid_runtime_value(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    runtime = _ApplicationRuntimeFake()
    runtime.get_epoch_dialog_context = MagicMock(return_value={"usable": True})

    context = get_epoch_dialog_context(widget, runtime=runtime)

    assert context.usable is False
    runtime.get_epoch_dialog_context.assert_called_once_with()


def test_epoch_dialog_context_resolves_runtime_before_service_is_cached(
    qtbot,
    monkeypatch,
):
    from XBrainLab.backend.application import runtime as application_runtime

    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    expected = EpochDialogContext(
        capability=MagicMock(),
        epoch_handoff={"ready": True, "label_source": "bids_events"},
        epoch_setup={"available_events": []},
        publication_generation=9,
        usable=True,
        unavailable_reason=None,
    )
    service = SimpleNamespace(
        get_epoch_dialog_context=MagicMock(return_value=expected),
    )
    locate_service = MagicMock(return_value=service)
    monkeypatch.setattr(application_runtime, "get_application_service", locate_service)

    context = get_epoch_dialog_context(widget)

    assert context is expected
    locate_service.assert_called_once_with(study)
    service.get_epoch_dialog_context.assert_called_once_with()


def test_execute_application_command_leaves_refresh_to_publication(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            return result

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)
    command_result = execute_application_command(
        widget,
        QueryStateCommand(),
        runtime=runtime,
    )

    assert command_result is result


def test_execute_application_command_forwards_expected_publication_generation(
    qtbot,
    monkeypatch,
):
    from XBrainLab.backend.application import runtime as application_runtime

    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    command = QueryStateCommand()
    result = CommandResult.success_result(
        command_name=command.name.value,
        message="ok",
        state=None,
        changed_state=ChangedState(),
    )
    service = SimpleNamespace(execute=MagicMock(return_value=result))
    monkeypatch.setattr(
        application_runtime,
        "get_application_service",
        MagicMock(return_value=service),
    )

    observed = execute_application_command(
        widget,
        command,
        expected_publication_generation=37,
        refresh=False,
    )

    assert observed is result
    service.execute.assert_called_once_with(
        command,
        expected_publication_generation=37,
    )


def test_ui_stale_publication_rejection_does_not_execute_handler(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    service = get_application_service(study)
    reviewed_publication = service.get_view_publication()
    changed_state = replace(
        reviewed_publication.state,
        pipeline_stage="raw_loaded",
        raw=replace(reviewed_publication.state.raw, loaded=True, count=1),
        active_dataset=replace(
            reviewed_publication.state.active_dataset,
            has_raw_data=True,
        ),
    )
    cast(Any, service).state_snapshot.build = MagicMock(
        return_value=changed_state,
    )
    handler = MagicMock(return_value="Session reset.")
    cast(Any, service)._command_handlers[CommandName.RESET_SESSION] = handler
    service.get_state()
    current_publication = service.get_view_publication()

    result = execute_application_command(
        widget,
        ResetSessionCommand(confirmed=True),
        expected_publication_generation=reviewed_publication.generation,
        refresh=False,
    )

    assert result is not None
    assert result.failed is True
    assert result.diagnostics["stale_publication"] is True
    assert result.diagnostics["expected_publication_generation"] == (
        reviewed_publication.generation
    )
    assert result.diagnostics["current_publication_generation"] == (
        current_publication.generation
    )
    handler.assert_not_called()


def test_execute_application_command_does_not_echo_publication_refresh(qtbot):
    study = Study()
    widget = QWidget()
    qtbot.addWidget(widget)

    class _PanelSpy:
        def __init__(self) -> None:
            self.update_calls = 0

        def update_panel(self) -> None:
            self.update_calls += 1

    class _AgentSpy:
        def __init__(self) -> None:
            self.refresh_calls = 0

        def refresh_backend_status(self) -> None:
            self.refresh_calls += 1

    main_window = SimpleNamespace(
        study=study,
        dataset_panel=_PanelSpy(),
        preprocess_panel=_PanelSpy(),
        training_panel=_PanelSpy(),
        evaluation_panel=_PanelSpy(),
        visualization_panel=_PanelSpy(),
        agent_manager=_AgentSpy(),
        update_info_calls=0,
    )

    def update_info_panel() -> None:
        main_window.update_info_calls += 1

    main_window.update_info_panel = update_info_panel
    cast(Any, widget).main_window = main_window

    result = CommandResult.success_result(
        command_name="load_data",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            assert refresh_after_observer(widget, event_name="data_changed") is False
            return result

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)

    command_result = execute_application_command(
        widget,
        QueryStateCommand(),
        runtime=runtime,
    )

    assert command_result is result
    assert main_window.dataset_panel.update_calls == 0
    assert main_window.preprocess_panel.update_calls == 0
    assert main_window.training_panel.update_calls == 0
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert main_window.update_info_calls == 0
    # AgentManager subscribes to revisioned ApplicationService publications.
    # A second pull here would reintroduce ordering-dependent refresh truth.
    assert main_window.agent_manager.refresh_calls == 0


def test_sync_product_command_does_not_coalesce_controller_terminal_refresh(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)

    class _TrainingPanelSpy:
        def __init__(self) -> None:
            self.main_window: Any | None = None
            self.terminal_render_calls = 0
            self.generic_update_calls = 0
            self.dirty_mark_calls = 0

        def refresh_terminal_publication(self) -> None:
            self.terminal_render_calls += 1

        def update_panel(self) -> None:
            self.generic_update_calls += 1

        def mark_refresh_dirty(self) -> None:
            self.dirty_mark_calls += 1

    training_panel = _TrainingPanelSpy()
    main_window = SimpleNamespace(
        study=Study(),
        training_panel=training_panel,
        shared_status_refresh_calls=0,
    )

    def update_info_panel() -> None:
        main_window.shared_status_refresh_calls += 1

    main_window.update_info_panel = update_info_panel
    training_panel.main_window = main_window
    cast(Any, widget).main_window = main_window
    result = CommandResult.success_result(
        command_name="query_state",
        message="training complete",
        state=None,
        changed_state=ChangedState(training_changed=True),
    )

    def execute(command: Command) -> CommandResult:
        assert isinstance(command, QueryStateCommand)
        assert (
            refresh_after_observer(
                training_panel,
                event_name="training_terminal_published",
            )
            is False
        )
        return result

    observed = execute_application_command(
        widget,
        QueryStateCommand(),
        runtime=_ApplicationRuntimeFake(execute=execute),
    )

    assert observed is result
    assert training_panel.terminal_render_calls == 0
    assert training_panel.generic_update_calls == 0
    assert training_panel.dirty_mark_calls == 0
    assert main_window.shared_status_refresh_calls == 0


def test_execute_application_command_accepts_legacy_refresh_false_parameter(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            return result

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)
    command_result = execute_application_command(
        widget,
        QueryStateCommand(),
        refresh=False,
        runtime=runtime,
    )

    assert command_result is result


def test_ui_state_query_uses_unified_application_command_surface(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    result = CommandResult.success_result(
        command_name="query_state",
        message="published",
        state=None,
        changed_state=ChangedState(),
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            assert command.query == "state"
            return result

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)

    command_result = execute_application_command(
        widget,
        QueryStateCommand(query="state"),
        refresh=False,
        runtime=runtime,
    )

    assert command_result is result


def test_execute_application_command_async_runs_service_off_gui_call_stack(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )
    executed: list[QueryStateCommand] = []
    callbacks: list[CommandResult] = []
    refresh_calls: list[tuple[Any, CommandResult]] = []
    started_workers = []

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            executed.append(command)
            return result

    class _ThreadPool:
        def start(self, worker):
            started_workers.append(worker)

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)
    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )
    monkeypatch.setattr(
        async_command_runner,
        "refresh_after_command",
        lambda context, command_result: refresh_calls.append(
            (context, command_result),
        ),
    )

    started = execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=callbacks.append,
        runtime=runtime,
    )

    assert started is True
    assert busy_states == [True]
    assert executed == []
    assert len(started_workers) == 1
    assert application_command_registry().active_count(widget) == 1
    assert runtime.begun_operations == [("operation-1", QueryStateCommand())]

    started_workers[0].run()

    assert len(executed) == 1
    assert callbacks == [result]
    assert refresh_calls == []
    assert busy_states == [True, False]
    assert application_command_registry().active_count(widget) == 0
    assert runtime.operation_ids == ["operation-1"]


def test_async_operation_identity_is_visible_and_cancel_uses_runtime(
    qtbot, monkeypatch
):
    widget = QWidget()
    qtbot.addWidget(widget)
    command = QueryStateCommand()
    result = CommandResult.success_result(
        command_name=command.name.value,
        message="ok",
        state=None,
        changed_state=ChangedState(),
    )
    runtime = _ApplicationRuntimeFake(execute=lambda _command: result)
    workers = []
    started_operations: list[str] = []

    class _ThreadPool:
        def start(self, worker) -> None:
            workers.append(worker)

    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )

    assert execute_application_command_async(
        widget,
        command,
        on_result=lambda _result: None,
        on_operation_started=started_operations.append,
        runtime=runtime,
    )
    assert started_operations == ["operation-1"]
    assert cancel_application_operation(
        widget,
        "operation-1",
        runtime=runtime,
    )
    assert runtime.cancelled_operations == ["operation-1"]

    workers[0].run()
    assert runtime.operation_ids == ["operation-1"]


def test_async_preprocess_uses_python_owned_worker_instead_of_qt_pool(
    qtbot,
    monkeypatch,
):
    widget = QWidget()
    qtbot.addWidget(widget)
    cast(Any, widget).set_busy = lambda _busy: None
    command = PreprocessCommand(
        operation=PreprocessOperation.BANDPASS,
        low_freq=1.0,
        high_freq=40.0,
    )
    result = CommandResult.success_result(
        command_name=command.name.value,
        message="filtered",
        state=None,
        changed_state=ChangedState(preprocessed_changed=True),
    )
    execution_threads: list[threading.Thread] = []
    callbacks: list[CommandResult] = []

    def execute(received_command: Command) -> CommandResult:
        assert received_command is command
        execution_threads.append(threading.current_thread())
        return result

    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        MagicMock(side_effect=AssertionError("preprocess used the Qt thread pool")),
    )

    started = execute_application_command_async(
        widget,
        command,
        on_result=callbacks.append,
        runtime=_ApplicationRuntimeFake(execute=execute),
    )

    assert started is True
    qtbot.waitUntil(lambda: callbacks == [result], timeout=2_000)
    assert len(execution_threads) == 1
    assert execution_threads[0] is not threading.main_thread()
    assert execution_threads[0].name == "XBrainLab-preprocess"
    assert application_command_registry().active_count(widget) == 0


def test_async_training_uses_python_owned_worker_and_keeps_gui_responsive(
    qtbot,
    monkeypatch,
):
    widget = QWidget()
    qtbot.addWidget(widget)
    cast(Any, widget).set_busy = lambda _busy: None
    command = TrainCommand(confirmed=True, append=False)
    result = CommandResult.success_result(
        command_name=command.name.value,
        message="Training started.",
        state=None,
        changed_state=ChangedState(training_changed=True),
    )
    release_execution = threading.Event()
    execution_threads: list[threading.Thread] = []
    callbacks: list[CommandResult] = []
    heartbeat: list[bool] = []

    def execute(received_command: Command) -> CommandResult:
        assert received_command is command
        execution_threads.append(threading.current_thread())
        if not release_execution.wait(timeout=1.0):
            raise TimeoutError("training admission was not released")
        return result

    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        MagicMock(side_effect=AssertionError("training used the Qt thread pool")),
    )

    started = execute_application_command_async(
        widget,
        command,
        on_result=callbacks.append,
        runtime=_ApplicationRuntimeFake(execute=execute),
    )

    assert started is True
    qtbot.waitUntil(lambda: len(execution_threads) == 1, timeout=1_000)
    QCoreApplication.instance().processEvents()
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: heartbeat == [True], timeout=1_000)
    release_execution.set()
    qtbot.waitUntil(lambda: callbacks == [result], timeout=2_000)
    assert execution_threads[0] is not threading.main_thread()
    assert execution_threads[0].name == "XBrainLab-training-start"
    assert application_command_registry().active_count(widget) == 0


def test_execute_application_command_async_forwards_expected_publication_generation(
    qtbot,
    monkeypatch,
):
    widget = QWidget()
    qtbot.addWidget(widget)
    command = QueryStateCommand()
    result = CommandResult.success_result(
        command_name=command.name.value,
        message="ok",
        state=None,
        changed_state=ChangedState(),
    )
    received_generations: list[int | None] = []
    started_workers = []

    class _Runtime:
        def execute(
            self,
            received_command: Command,
            *,
            expected_publication_generation: int | None = None,
        ) -> CommandResult:
            assert received_command is command
            received_generations.append(expected_publication_generation)
            return result

    class _ThreadPool:
        def start(self, worker) -> None:
            started_workers.append(worker)

    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )

    started = execute_application_command_async(
        widget,
        command,
        expected_publication_generation=41,
        on_result=lambda _result: None,
        runtime=cast(Any, _Runtime()),
    )

    assert started is True
    assert received_generations == []
    started_workers[0].run()
    assert received_generations == [41]


def test_async_application_command_reports_correlated_handoff_terminal_callback(
    qtbot,
    monkeypatch,
):
    widget = QWidget()
    qtbot.addWidget(widget)
    workers = []
    terminal = []
    result = CommandResult.success_result(
        command_name="query_state",
        message="State read completed.",
        state={},
        changed_state=ChangedState(),
    )
    runtime = _ApplicationRuntimeFake(execute=lambda _command: result)

    class _ThreadPool:
        def start(self, worker):
            workers.append(worker)

    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )
    completion = InteractionCompletionSession(
        request_id="handoff-1",
        command_name="query_state",
        on_terminal=terminal.append,
    )

    with bind_interaction_completion(completion):
        started = execute_application_command_async(
            widget,
            QueryStateCommand(),
            on_result=lambda _result: None,
            runtime=runtime,
        )

    assert started is True
    assert completion.has_scheduled_command is True
    assert terminal == []

    workers[0].run()

    assert len(terminal) == 1
    assert terminal[0].request_id == "handoff-1"
    assert terminal[0].status is InteractionCompletionStatus.COMPLETED


def test_async_application_command_finished_without_outcome_fails_handoff(
    qtbot,
    monkeypatch,
):
    widget = QWidget()
    qtbot.addWidget(widget)
    workers = []
    terminal = []
    runtime = _ApplicationRuntimeFake(
        execute=_unexpected_execution(
            "runtime execution is not needed for a finished-only signal",
        ),
    )

    class _ThreadPool:
        def start(self, worker):
            workers.append(worker)

    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )
    completion = InteractionCompletionSession(
        request_id="handoff-finished-only",
        command_name="query_state",
        on_terminal=terminal.append,
    )

    with bind_interaction_completion(completion):
        started = execute_application_command_async(
            widget,
            QueryStateCommand(),
            on_result=lambda _result: None,
            runtime=runtime,
        )

    assert started is True
    assert terminal == []

    workers[0].signals.finished.emit()

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert terminal[0].message == (
        "The asynchronous UI command finished without returning a result."
    )


def test_real_worker_command_mismatch_fails_handoff_once(qtbot) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    terminal = []
    screen_callback = MagicMock()
    mismatched = CommandResult.success_result(
        command_name="configure_dataset_split",
        message="Unexpected dataset result.",
        state={},
        changed_state=ChangedState(datasets_changed=True),
    )
    runtime = _ApplicationRuntimeFake(execute=lambda _command: mismatched)
    completion = InteractionCompletionSession(
        request_id="handoff-mismatch",
        command_name="query_state",
        on_terminal=terminal.append,
    )

    with bind_interaction_completion(completion):
        started = execute_application_command_async(
            widget,
            QueryStateCommand(),
            on_result=screen_callback,
            refresh=False,
            runtime=runtime,
        )

    assert started is True
    qtbot.waitUntil(lambda: bool(terminal), timeout=2_000)
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(widget) == 0,
        timeout=2_000,
    )

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    screen_callback.assert_not_called()


def test_async_worker_ownership_is_released_only_after_finished(qtbot, monkeypatch):
    study = Study()
    widget = QWidget()
    main_window = SimpleNamespace(study=study)
    cast(Any, widget).main_window = main_window
    qtbot.addWidget(widget)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))
    callbacks: list[CommandResult] = []
    workers = []
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(),
    )

    class _Service:
        def execute(self, _command):
            return result

    class _ThreadPool:
        def start(self, worker):
            workers.append(worker)

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)
    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )

    assert execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=callbacks.append,
        runtime=runtime,
    )
    worker = workers[0]
    owner_id = id(main_window)

    worker.signals.result.emit(result)

    assert callbacks == [result]
    assert application_command_registry().active_count(widget) == 1
    assert busy_states == [True]
    assert owner_id not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS

    worker.signals.finished.emit()

    assert application_command_registry().active_count(widget) == 0
    assert busy_states == [True, False]
    assert owner_id not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS


def test_async_command_refuses_non_gui_thread_without_side_effects(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))
    results: list[bool] = []
    runtime = _ApplicationRuntimeFake(
        execute=_unexpected_execution(
            "runtime must not execute off the GUI thread",
        ),
    )
    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: None,
    )

    caller = threading.Thread(
        target=lambda: results.append(
            execute_application_command_async(
                widget,
                QueryStateCommand(),
                on_result=lambda _result: None,
                runtime=runtime,
            )
        )
    )
    caller.start()
    caller.join(timeout=1.0)

    assert not caller.is_alive()
    assert results == [False]
    assert busy_states == []
    assert runtime.commands == []
    assert application_command_registry().active_count(widget) == 0


def test_async_terminal_cleanup_survives_busy_callback_failure(qtbot, monkeypatch):
    study = Study()
    widget = QWidget()
    main_window = SimpleNamespace(study=study)
    cast(Any, widget).main_window = main_window
    qtbot.addWidget(widget)
    workers = []
    busy_states: list[bool] = []

    def set_busy(busy: bool) -> None:
        busy_states.append(bool(busy))
        if not busy:
            raise RuntimeError("busy target was already torn down")

    cast(Any, widget).set_busy = set_busy

    class _Service:
        def execute(self, _command):
            raise AssertionError("worker execution is not needed for this test")

    class _ThreadPool:
        def start(self, worker):
            workers.append(worker)

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)
    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )

    assert execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=lambda _result: None,
        runtime=runtime,
    )
    worker = workers[0]

    worker.signals.finished.emit()

    assert application_command_registry().active_count(widget) == 0
    assert busy_states == [True, False]
    assert id(main_window) not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS


def test_async_pool_lookup_failure_releases_all_ui_ownership(qtbot, monkeypatch):
    study = Study()
    widget = QWidget()
    main_window = SimpleNamespace(study=study)
    cast(Any, widget).main_window = main_window
    qtbot.addWidget(widget)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))
    runtime = _ApplicationRuntimeFake(
        execute=_unexpected_execution(
            "runtime must not execute when pool lookup fails",
        ),
    )

    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        MagicMock(side_effect=RuntimeError("Qt pool is unavailable")),
    )

    started = execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=lambda _result: None,
        runtime=runtime,
    )

    assert started is False
    assert busy_states == [True, False]
    assert application_command_registry().active_count(widget) == 0
    assert runtime.failed_operations == [
        ("operation-1", "The interface worker could not be scheduled."),
    ]
    assert id(main_window) not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS


def test_execute_application_command_async_ignores_result_after_widget_deleted(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )
    callbacks: list[CommandResult] = []
    refresh_calls: list[tuple[Any, CommandResult]] = []
    started_workers = []

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            return result

    class _ThreadPool:
        def start(self, worker):
            started_workers.append(worker)

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)
    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )
    monkeypatch.setattr(
        async_command_runner,
        "refresh_after_command",
        lambda context, command_result: refresh_calls.append(
            (context, command_result),
        ),
    )

    started = execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=callbacks.append,
        runtime=runtime,
    )
    assert started is True

    widget.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(widget), timeout=1_000)
    started_workers[0].run()

    assert busy_states == [True]
    assert callbacks == []
    assert refresh_calls == []
    assert application_command_registry().active_count(widget) == 0


def test_real_threadpool_cleanup_does_not_dereference_deleted_widget(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    main_window = SimpleNamespace(study=study)
    cast(Any, widget).main_window = main_window
    worker_started = threading.Event()
    worker_release = threading.Event()
    callbacks = []
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )

    class _Service:
        def execute(self, _command):
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return result

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)

    assert execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=callbacks.append,
        runtime=runtime,
    )
    assert worker_started.wait(timeout=1.0)
    owner_id = id(main_window)
    assert application_command_registry().active_count(widget) == 1
    assert owner_id not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS

    widget.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(widget), timeout=1_000)
    worker_release.set()
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(widget) == 0,
        timeout=1_000,
    )

    assert callbacks == []
    assert owner_id not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS


@pytest.mark.parametrize("outcome", ["success", "error"])
def test_real_threadpool_delivers_terminal_callback_on_gui_thread(
    qtbot,
    monkeypatch,
    outcome,
):
    study = Study()
    widget = QWidget()
    main_window = SimpleNamespace(study=study)
    cast(Any, widget).main_window = main_window
    qtbot.addWidget(widget)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))
    worker_started = threading.Event()
    worker_release = threading.Event()
    callback_threads: list[bool] = []
    results: list[CommandResult] = []
    errors: list[tuple] = []
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(),
    )

    class _Service:
        def execute(self, _command):
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            if outcome == "error":
                raise RuntimeError("worker failed")
            return result

    def on_result(value: CommandResult) -> None:
        application = QCoreApplication.instance()
        callback_threads.append(
            application is not None and QThread.currentThread() == application.thread()
        )
        results.append(value)

    def on_error(value: tuple) -> None:
        application = QCoreApplication.instance()
        callback_threads.append(
            application is not None and QThread.currentThread() == application.thread()
        )
        errors.append(value)

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)

    assert execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=on_result,
        on_error=on_error,
        refresh=False,
        runtime=runtime,
    )
    assert worker_started.wait(timeout=1.0)
    assert application_command_registry().active_count(widget) == 1

    worker_release.set()
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(widget) == 0,
        timeout=2_000,
    )

    assert callback_threads == [True]
    assert (results == [result]) is (outcome == "success")
    assert (len(errors) == 1) is (outcome == "error")
    assert busy_states == [True, False]
    assert id(main_window) not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS


def test_async_result_is_suppressed_after_main_window_starts_closing(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    main_window = SimpleNamespace(study=study, _closing_in_progress=False)
    cast(Any, widget).main_window = main_window
    qtbot.addWidget(widget)
    worker_started = threading.Event()
    worker_release = threading.Event()
    callbacks = []
    refreshes = []
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )

    class _Service:
        def execute(self, _command):
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return result

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)
    monkeypatch.setattr(
        async_command_runner,
        "refresh_after_command",
        lambda *_args: refreshes.append(True),
    )

    assert execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=callbacks.append,
        runtime=runtime,
    )
    assert worker_started.wait(timeout=1.0)
    assert application_command_registry().active_count(widget) == 1

    main_window._closing_in_progress = True
    worker_release.set()
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(widget) == 0,
        timeout=1_000,
    )

    assert callbacks == []
    assert refreshes == []


def test_execute_application_command_async_returns_false_for_non_product_study(
    qtbot,
    monkeypatch,
):
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=object())
    qtbot.addWidget(widget)
    started_workers = []

    class _ThreadPool:
        def start(self, worker):
            started_workers.append(worker)

    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )

    started = execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=lambda _result: None,
    )

    assert started is False
    assert started_workers == []


def test_shutdown_fence_request_uses_immediate_service_admission(qtbot, monkeypatch):
    study = Study()
    widget = QWidget()
    cast(Any, widget).study = study
    qtbot.addWidget(widget)
    runtime = _ApplicationRuntimeFake()

    installed = request_application_shutdown_fence(widget, runtime=runtime)

    assert installed is True
    assert runtime.shutdown_requests == 1

    released = release_application_shutdown_fence(widget, runtime=runtime)

    assert released is True
    assert runtime.shutdown_releases == 1


def test_shutdown_fence_release_propagates_runtime_retry_state(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    runtime = _ApplicationRuntimeFake()
    runtime.shutdown_release_succeeds = False

    released = release_application_shutdown_fence(widget, runtime=runtime)

    assert released is False
    assert runtime.shutdown_releases == 1


def test_execute_application_command_async_returns_false_without_thread_pool(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))

    class _Service:
        def execute(self, command):
            raise AssertionError("service should not run without a thread pool")

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)
    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: None,
    )

    started = execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=lambda _result: None,
        runtime=runtime,
    )

    assert started is False
    assert busy_states == [True, False]
    assert application_command_registry().active_count(widget) == 0
    assert runtime.failed_operations == [
        ("operation-1", "The interface worker could not be scheduled."),
    ]


def test_execute_application_command_async_returns_false_when_worker_start_fails(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))

    class _Service:
        def execute(self, command):
            raise AssertionError("worker should not run when start fails")

    class _ThreadPool:
        def start(self, worker):
            raise RuntimeError("thread pool rejected worker")

    runtime = _ApplicationRuntimeFake(execute=_Service().execute)
    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )

    started = execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=lambda _result: None,
        runtime=runtime,
    )

    assert started is False
    assert busy_states == [True, False]
    assert application_command_registry().active_count(widget) == 0


def test_legacy_controller_fallback_refuses_real_study(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    fallback = MagicMock()

    with pytest.raises(RuntimeError, match="could not safely complete"):
        run_controller_compatibility_call(widget, fallback)

    fallback.assert_not_called()


def test_legacy_controller_fallback_refuses_real_controller_study(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).controller = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    fallback = MagicMock()

    with pytest.raises(RuntimeError, match="could not safely complete"):
        run_controller_compatibility_call(widget, fallback)

    fallback.assert_not_called()


def test_named_controller_context_uses_application_service(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).preprocess_controller = SimpleNamespace(study=study)
    qtbot.addWidget(widget)

    ui_capability = get_command_capability(widget, CommandName.TRAIN)

    assert ui_capability is not None


def test_legacy_controller_fallback_refuses_named_real_controller(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).preprocess_controller = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    fallback = MagicMock()

    with pytest.raises(RuntimeError, match="could not safely complete"):
        run_controller_compatibility_call(widget, fallback)

    fallback.assert_not_called()


def test_legacy_controller_fallback_allows_plain_non_study_context():
    fallback = MagicMock(return_value="legacy-ok")

    result = run_controller_compatibility_call(object(), fallback)

    assert result == "legacy-ok"
    fallback.assert_called_once_with()
