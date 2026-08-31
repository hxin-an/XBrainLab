import inspect
import threading
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import pytest
from PyQt6.QtWidgets import QGroupBox, QLabel, QMainWindow, QPushButton

from XBrainLab.backend.application import (
    ChangedState,
    CommandName,
    CommandResult,
    ConfigureTrainingCommand,
    ErrorType,
    QueryStateCommand,
)
from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.owned_work import OwnedWorkRegistry
from XBrainLab.backend.application.resource_guard import (
    RISK_BLOCKING,
    RISK_SAFE,
    RISK_UNKNOWN,
    RISK_WARNING,
    ResourcePreflightResult,
    TrainingResourcePreviewContext,
    TrainingResourcePreviewReceipt,
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
)
from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendation,
    TrainingRecommendationField,
    TrainingRecommendationValues,
    TrainingSettingProvenance,
)
from XBrainLab.backend.application.training_resource_preview_coordinator import (
    TrainingResourcePreviewCoordinator,
)
from XBrainLab.backend.application.training_submission import (
    training_submission_resource_preview_receipt,
)
from XBrainLab.backend.model_base.model_catalog import get_model_spec
from XBrainLab.backend.study import Study
from XBrainLab.backend.training.model_holder import ModelHolder
from XBrainLab.backend.training.option import class_map_fingerprint
from XBrainLab.ui.application_capabilities import CommandReviewContext
from XBrainLab.ui.panels.training.sidebar import TrainingSidebar
from XBrainLab.ui.refresh_coordinator import refresh_after_command
from XBrainLab.ui.styles.stylesheets import Stylesheets


@pytest.fixture
def sidebar(qtbot):
    panel_mock = MagicMock()
    panel_mock.controller = MagicMock()
    # Mock main_window on panel for AggregateInfoPanel access
    panel_mock.main_window = None

    widget = TrainingSidebar(panel_mock, parent=None)
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def real_study_sidebar(qtbot):
    study = Study()

    main_window = QMainWindow()
    cast(Any, main_window).study = study
    qtbot.addWidget(main_window)

    panel = MagicMock()
    panel.controller = MagicMock()
    panel.controller.get_resource_preflight_context.side_effect = AssertionError(
        "real product resource checks must not read the injected controller",
    )
    panel.main_window = main_window
    widget = TrainingSidebar(panel, parent=None)
    qtbot.addWidget(widget)
    return widget, study


def _training_preflight(
    *,
    ram_risk: str = RISK_SAFE,
    vram_risk: str = RISK_SAFE,
    confirmation_token: str | None = None,
) -> ResourcePreflightResult:
    ram_message = {
        RISK_SAFE: "Training RAM check: Safe",
        RISK_WARNING: "Training dataset is close to available RAM.",
        RISK_BLOCKING: "Training dataset is too large for available RAM.",
        RISK_UNKNOWN: "Unable to estimate available RAM.",
    }[ram_risk]
    vram_message = {
        RISK_SAFE: "GPU resource check: Safe",
        RISK_WARNING: "Training configuration is close to available GPU memory.",
        RISK_BLOCKING: "Training may exceed available GPU memory.",
        RISK_UNKNOWN: "Unable to estimate GPU memory.",
    }[vram_risk]
    messages = (ram_message, vram_message)
    risks = (ram_risk, vram_risk)
    diagnostics = {
        "dataset_ram_risk_level": ram_risk,
        "required_memory_bytes": 7 * 1024**3,
        "available_memory_bytes": 8 * 1024**3,
        "message": ram_message,
        "suggestions": ["use a smaller dataset split"],
        "vram_risk_level": vram_risk,
        "vram": {
            "risk_level": vram_risk,
            "required_memory_bytes": 7 * 1024**3,
            "available_memory_bytes": 8 * 1024**3,
            "message": vram_message,
            "suggestions": ["reduce batch size"],
            "batch_size": 256,
            "gpu_name": "NVIDIA Test GPU",
        },
    }
    if confirmation_token is not None:
        diagnostics.update(
            {
                "payload_type": "training_resource_preflight",
                "confirmation_token": confirmation_token,
                "confirmation_command": "start_training",
                "confirmation_ttl_seconds": 120.0,
                "configuration_fingerprint": "configuration-1",
                "preflight_fingerprint": "preflight-1",
                "scope_fingerprint": "scope-1",
            }
        )
    return ResourcePreflightResult(
        issues=tuple(
            message
            for risk, message in zip(risks, messages, strict=True)
            if risk == RISK_BLOCKING
        ),
        warnings=tuple(
            message
            for risk, message in zip(risks, messages, strict=True)
            if risk == RISK_WARNING
        ),
        diagnostics=diagnostics,
    )


def _resource_preview_request(
    request_generation: int,
) -> TrainingResourcePreviewRequest:
    return TrainingResourcePreviewRequest(
        request_generation=request_generation,
        publication_generation=41,
        model_name="EEGNet",
        model_params={},
        device="cuda:0",
        batch_size=32,
        optimizer="Adam",
    )


def _resource_preview_result(
    request: TrainingResourcePreviewRequest,
) -> TrainingResourcePreviewResult:
    return TrainingResourcePreviewResult(
        request_generation=request.request_generation,
        publication_generation=request.publication_generation,
        requested_batch_size=request.batch_size,
        suggested_batch_size=8,
        estimated_vram_bytes=128 * 1024**2,
        available_vram_bytes=512 * 1024**2,
        risk_level=RISK_WARNING,
        vram_known=True,
        warning="Batch size was reduced for available GPU memory.",
    )


def _resource_preview_context() -> TrainingResourcePreviewContext:
    return TrainingResourcePreviewContext(
        input_shape=(2, 64),
        sample_count=8,
        class_count=2,
        sampling_frequency=128.0,
    )


class _ResourcePreviewPort:
    def __init__(self, coordinator: TrainingResourcePreviewCoordinator) -> None:
        self.coordinator = coordinator

    def begin_training_resource_preview(
        self,
        request: TrainingResourcePreviewRequest,
    ):
        return self.coordinator.submit(request, _resource_preview_context())

    def training_resource_preview_background_work_snapshot(self):
        return self.coordinator.background_work_snapshot()

    def begin_training_resource_preview_shutdown(self) -> None:
        self.coordinator.begin_close()

    def cancel_training_resource_preview_shutdown(self) -> bool:
        return self.coordinator.cancel_close()


def test_training_resource_preview_is_single_flight_and_delivers_only_latest(
    sidebar,
    qtbot,
):
    first_started = threading.Event()
    release_first = threading.Event()
    requests: list[TrainingResourcePreviewRequest] = []

    def get_preview(
        request: TrainingResourcePreviewRequest,
    ) -> TrainingResourcePreviewResult:
        requests.append(request)
        if len(requests) == 1:
            first_started.set()
            assert release_first.wait(timeout=2.0)
        return _resource_preview_result(request)

    coordinator = TrainingResourcePreviewCoordinator(
        estimate=lambda request, _context: get_preview(request),
        generation_is_current=lambda _generation: True,
        registry=OwnedWorkRegistry(),
    )
    sidebar.panel._query_port = _ResourcePreviewPort(coordinator)
    delivered: list[list[TrainingResourcePreviewResult]] = [[], [], []]
    drafts = [_resource_preview_request(generation) for generation in (1, 2, 3)]

    try:
        assert sidebar._dispatch_training_resource_preview(
            drafts[0], delivered[0].append
        )
        qtbot.waitUntil(first_started.is_set, timeout=1000)
        assert sidebar._dispatch_training_resource_preview(
            drafts[1], delivered[1].append
        )
        assert sidebar._dispatch_training_resource_preview(
            drafts[2], delivered[2].append
        )
        assert [request.request_generation for request in requests] == [1]

        release_first.set()
        qtbot.waitUntil(lambda: len(delivered[2]) == 1, timeout=2000)

        assert [request.request_generation for request in requests] == [1, 3]
        assert delivered[0] == []
        assert delivered[1] == []
        assert delivered[2][0].request_generation == 3
    finally:
        release_first.set()
        assert coordinator.close(timeout=2.0)


def test_panel_close_abandons_preview_without_waiting_or_late_delivery(qtbot):
    panel = QMainWindow()
    cast(Any, panel).controller = MagicMock()
    cast(Any, panel).main_window = None
    qtbot.addWidget(panel)

    worker_started = threading.Event()
    release_worker = threading.Event()
    worker_finished = threading.Event()

    def get_preview(
        request: TrainingResourcePreviewRequest,
    ) -> TrainingResourcePreviewResult:
        worker_started.set()
        try:
            assert release_worker.wait(timeout=2.0)
            return _resource_preview_result(request)
        finally:
            worker_finished.set()

    coordinator = TrainingResourcePreviewCoordinator(
        estimate=lambda request, _context: get_preview(request),
        generation_is_current=lambda _generation: True,
        registry=OwnedWorkRegistry(),
    )
    cast(Any, panel)._query_port = _ResourcePreviewPort(coordinator)
    sidebar = TrainingSidebar(panel, parent=None)
    qtbot.addWidget(sidebar)
    delivered: list[TrainingResourcePreviewResult] = []

    assert sidebar._dispatch_training_resource_preview(
        _resource_preview_request(1),
        delivered.append,
    )
    qtbot.waitUntil(worker_started.is_set, timeout=1000)
    worker = coordinator.worker_thread
    assert worker is not None
    assert worker.daemon is False

    panel.show()
    assert panel.close() is True
    assert worker.is_alive() is True
    assert (
        sidebar._dispatch_training_resource_preview(
            _resource_preview_request(2),
            delivered.append,
        )
        is False
    )

    release_worker.set()
    qtbot.waitUntil(worker_finished.is_set, timeout=1000)
    qtbot.waitUntil(
        lambda: bool(coordinator.background_work_snapshot()["idle"]),
        timeout=1000,
    )

    assert coordinator.background_work_snapshot()["remaining_workers"] == 0
    assert delivered == []

    sidebar._cancel_training_resource_preview_shutdown()
    retried: list[TrainingResourcePreviewResult] = []
    assert sidebar._dispatch_training_resource_preview(
        _resource_preview_request(2),
        retried.append,
    )
    qtbot.waitUntil(lambda: len(retried) == 1, timeout=1000)
    assert retried[0].request_generation == 2
    assert coordinator.close(timeout=2.0)


def test_training_sidebar_does_not_spawn_or_abandon_preview_workers() -> None:
    source = inspect.getsource(TrainingSidebar)

    assert "PythonThreadWorker" not in source
    assert "daemon=True" not in source
    assert "begin_training_resource_preview" in source


def test_configure_training_command_preserves_catalog_model_id() -> None:
    spec = get_model_spec("braindecode.eegnet")
    holder = ModelHolder(
        spec.factory,
        {},
        model_id=spec.model_id,
        display_name=spec.display_name,
    )

    command = TrainingSidebar._configure_training_command(model_holder=holder)

    assert command.model_name == "braindecode.eegnet"


def test_configure_training_command_preserves_auto_and_exact_edited_fields() -> None:
    option = SimpleNamespace(
        epoch=50,
        bs=8,
        lr=0.001,
        repeat_num=1,
        optim=SimpleNamespace(__name__="Adam"),
        optim_params={"weight_decay": 0.01},
        checkpoint_epoch=0,
        output_dir="./output",
        evaluation_option=SimpleNamespace(value="Best validation loss"),
        use_cpu=True,
        gpu_idx=None,
    )

    command = TrainingSidebar._configure_training_command(
        training_option=option,
        device="auto",
        edited_recommendation_fields=frozenset(
            {
                TrainingRecommendationField.EPOCHS,
                TrainingRecommendationField.OPTIMIZER,
            }
        ),
    )

    assert command.device == "auto"
    assert command.optimizer_params == {"weight_decay": 0.01}
    assert command.edited_recommendation_fields == frozenset(
        {
            TrainingRecommendationField.EPOCHS,
            TrainingRecommendationField.OPTIMIZER,
        }
    )


def test_training_settings_snapshot_uses_the_current_reviewed_class_map(sidebar):
    publication = SimpleNamespace(
        state=SimpleNamespace(epoch=SimpleNamespace(event_ids={"right": 1, "left": 0}))
    )
    with (
        patch.object(
            sidebar,
            "_training_option_snapshot",
            return_value={
                "class_weight_mode": "custom",
                "custom_class_weights": {"left": 2.0, "right": 1.0},
                "class_map_fingerprint": "stale",
            },
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
    ):
        initial = sidebar._training_setting_initial_option(None)

    assert initial["class_map"] == {0: "left", 1: "right"}
    assert initial["class_map_fingerprint"] == class_map_fingerprint(
        {0: "left", 1: "right"}
    )


def test_training_settings_use_saved_preview_before_split_materializes(sidebar):
    publication = SimpleNamespace(
        state=SimpleNamespace(
            dataset=SimpleNamespace(
                split_spec_saved=True,
                split_materialized=False,
                split_preview_summary={"validation_count": 3},
                active_split_summary={"val_count": 0},
            ),
            epoch=SimpleNamespace(event_ids={}),
        )
    )
    with (
        patch.object(sidebar, "_training_option_snapshot", return_value={}),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
    ):
        initial = sidebar._training_setting_initial_option(None)

    assert initial["validation_samples_available"] is True
    assert initial["validation_sample_count"] == 3


def test_training_settings_fail_closed_for_an_unsaved_split_preview(sidebar):
    publication = SimpleNamespace(
        state=SimpleNamespace(
            dataset=SimpleNamespace(
                split_spec_saved=False,
                split_materialized=False,
                split_preview_summary={"validation_count": 3},
                active_split_summary={"val_count": 3},
            ),
            epoch=SimpleNamespace(event_ids={}),
        )
    )
    with (
        patch.object(sidebar, "_training_option_snapshot", return_value={}),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
    ):
        initial = sidebar._training_setting_initial_option(None)

    assert initial["validation_samples_available"] is False
    assert initial["validation_sample_count"] == 0


def test_configure_training_command_carries_exact_applied_preview_receipt() -> None:
    option = SimpleNamespace(
        epoch=50,
        bs=8,
        lr=0.001,
        repeat_num=1,
        optim=SimpleNamespace(__name__="Adam"),
        optim_params={},
        checkpoint_epoch=0,
        output_dir="./output",
        evaluation_option=SimpleNamespace(value="Best validation loss"),
        use_cpu=False,
        gpu_idx=0,
    )
    receipt = TrainingResourcePreviewReceipt(
        token="accepted-preview",  # noqa: S106 - opaque test receipt, not a secret
        request_generation=3,
        publication_generation=22,
        requested_batch_size=32,
        suggested_batch_size=8,
    )

    command = TrainingSidebar._configure_training_command(
        training_option=option,
        device="cuda:0",
        resource_preview_receipt=receipt,
    )

    assert training_submission_resource_preview_receipt(command) == receipt


def test_init_ui(sidebar):
    assert isinstance(sidebar.btn_split, QPushButton)
    assert isinstance(sidebar.btn_model, QPushButton)
    assert isinstance(sidebar.btn_setting, QPushButton)
    assert isinstance(sidebar.btn_start, QPushButton)
    assert sidebar.btn_start.styleSheet() == Stylesheets.BTN_PRIMARY
    assert sidebar.findChild(QLabel, "TrainingResourceCheck") is None
    assert sidebar.findChild(QGroupBox, "TrainingReadiness") is None
    assert sidebar.scroll_area.content_layout.itemAt(0).widget() is sidebar.info_panel


def test_model_selection_receives_typed_training_query_port(sidebar):
    query_port = MagicMock()
    sidebar.panel.__dict__["_query_port"] = query_port
    sidebar.panel._typed_port_mode = True

    with patch(
        "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog",
    ) as dialog:
        dialog.return_value.exec.return_value = False
        outcome = sidebar._collect_model_selection(None)

    assert outcome.status.value == "cancelled"
    dialog.assert_called_once_with(
        sidebar,
        sidebar.controller,
        initial_model_name=None,
        query_port=query_port,
    )


def test_execution_section_does_not_show_persistent_resource_status(sidebar):
    visible_text = " ".join(
        label.text() for label in sidebar.findChildren(QLabel) if label.isVisible()
    )

    assert "Resource check" not in visible_text
    assert "GPU memory unavailable" not in visible_text


def test_on_start_clicked(sidebar):
    # Mock readiness
    sidebar.controller.validate_ready.return_value = True

    # Test Start
    sidebar.controller.is_training.return_value = False
    with patch("XBrainLab.ui.panels.training.sidebar.show_warning") as warning:
        sidebar.start_training_ui_action()
    sidebar.controller.start_training.assert_not_called()
    warning.assert_called_once()
    assert warning.call_args.args[1] == "Start Training Blocked"

    # Test Stop is separate method: stop_training
    # But checking start_training_ui_action logic:
    # It calls start_training if not running.

    sidebar.controller.start_training.reset_mock()
    sidebar.controller.is_training.return_value = True
    sidebar.start_training_ui_action()
    sidebar.controller.start_training.assert_not_called()
    # It acts as idempotent or safe start?
    # Logic: if not self.controller.is_training(): start()


def _training_result(
    *,
    preflight: ResourcePreflightResult | None = None,
    error_type: ErrorType | None = None,
) -> CommandResult:
    if error_type is None:
        return CommandResult.success_result(
            command_name="train",
            message="Training started.",
            state=None,
            changed_state=ChangedState(training_changed=True),
            diagnostics={
                "resource_preflight": (
                    preflight.to_diagnostics() if preflight is not None else {}
                )
            },
        )
    return CommandResult.failure_result(
        command_name="train",
        message=(preflight.message if preflight is not None else "Training failed."),
        state=None,
        changed_state=ChangedState(),
        error_type=error_type,
        recoverable=True,
        diagnostics={
            "resource_preflight": (
                preflight.to_diagnostics() if preflight is not None else {}
            )
        },
    )


def _async_dispatch_recorder():
    calls: list[tuple[Any, Any]] = []
    callbacks: list[tuple[Any, Any]] = []

    def dispatch(context, command, *, on_result, on_error, **_kwargs):
        calls.append((context, command))
        callbacks.append((on_result, on_error))
        return True

    return dispatch, calls, callbacks


def test_train_result_before_publication_leaves_state_controls_unchanged(sidebar):
    dispatch, calls, callbacks = _async_dispatch_recorder()
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=SimpleNamespace(enabled=True, reasons=[]),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
            side_effect=dispatch,
        ),
    ):
        sidebar.start_training_ui_action()

    assert len(calls) == 1
    assert calls[0][1].resource_preflight_confirmed is False

    sidebar.btn_stop.setEnabled(False)
    with patch.object(
        sidebar.panel,
        "reconcile_training_terminal_outcome",
    ) as reconcile:
        callbacks[0][0](_training_result(preflight=_training_preflight()))

    reconcile.assert_not_called()
    assert sidebar.btn_stop.isEnabled() is False

    sidebar.on_training_started(refresh_ready=False)

    assert sidebar.btn_stop.isEnabled() is True


def test_start_training_busy_scope_does_not_disable_entire_panel(sidebar):
    dispatched: list[dict[str, Any]] = []

    def dispatch(_context, _command, **kwargs):
        dispatched.append(kwargs)
        return True

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=SimpleNamespace(enabled=True, reasons=[]),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
            side_effect=dispatch,
        ),
    ):
        sidebar.start_training_ui_action()

    assert len(dispatched) == 1
    assert dispatched[0]["busy_target"] is sidebar
    assert dispatched[0]["busy_target"] is not sidebar.panel


def test_training_start_publishes_preparing_data_split_before_dispatch(sidebar):
    with (
        patch.object(sidebar, "_execute_action_async", return_value=True),
        patch.object(sidebar, "_show_status") as show_status,
    ):
        assert sidebar._dispatch_start_training() is True

    assert show_status.call_args_list[0].args == ("Preparing data split",)


def test_train_result_after_running_publication_does_not_reapply_state(sidebar):
    sidebar.on_training_started(refresh_ready=False)

    with patch.object(
        sidebar.panel,
        "reconcile_training_terminal_outcome",
    ) as reconcile:
        sidebar._handle_start_training_result(
            _training_result(preflight=_training_preflight()),
            unknown_retried=False,
        )

    reconcile.assert_not_called()
    assert sidebar.btn_stop.isEnabled() is True


def test_duplicate_late_train_results_cannot_overwrite_terminal_publication(sidebar):
    sidebar.on_training_started(refresh_ready=False)
    sidebar.on_training_stopped(refresh_ready=False)

    with patch.object(
        sidebar.panel,
        "reconcile_training_terminal_outcome",
    ) as reconcile:
        for _ in range(2):
            sidebar._handle_start_training_result(
                _training_result(preflight=_training_preflight()),
                unknown_retried=False,
            )

    reconcile.assert_not_called()
    assert sidebar.btn_stop.isEnabled() is False


def test_late_train_ack_cannot_overwrite_terminal_publication_status(sidebar):
    terminal_publication = SimpleNamespace(
        usable=True,
        state=SimpleNamespace(
            training=SimpleNamespace(
                terminal_outcome=SimpleNamespace(is_terminal=True),
            ),
        ),
    )

    with (
        patch.object(
            sidebar,
            "_application_publication",
            return_value=terminal_publication,
        ),
        patch.object(sidebar, "_show_status") as show_status,
    ):
        sidebar._handle_start_training_result(
            _training_result(preflight=_training_preflight()),
            unknown_retried=False,
        )

    show_status.assert_not_called()


def test_current_train_ack_reports_started_from_nonterminal_publication(sidebar):
    running_publication = SimpleNamespace(
        usable=True,
        state=SimpleNamespace(
            training=SimpleNamespace(
                terminal_outcome=SimpleNamespace(is_terminal=False),
            ),
        ),
    )

    with (
        patch.object(
            sidebar,
            "_application_publication",
            return_value=running_publication,
        ),
        patch.object(sidebar, "_show_status") as show_status,
    ):
        sidebar._handle_start_training_result(
            _training_result(preflight=_training_preflight()),
            unknown_retried=False,
        )

    show_status.assert_called_once_with("Training started")


def test_completed_command_ack_leaves_readiness_to_publication(sidebar):
    with (
        patch.object(sidebar, "check_ready_to_train") as check_ready,
        patch.object(
            sidebar.panel,
            "reconcile_training_terminal_outcome",
        ) as reconcile,
    ):
        sidebar._handle_start_training_result(
            _training_result(preflight=_training_preflight()),
            unknown_retried=False,
        )

    check_ready.assert_not_called()
    reconcile.assert_not_called()


def test_start_training_warning_is_confirmed_on_gui_then_redispatched(sidebar):
    dispatch, calls, callbacks = _async_dispatch_recorder()
    receipt = "training-receipt-1"
    warning = _training_preflight(
        vram_risk=RISK_WARNING,
        confirmation_token=receipt,
    )
    warning = ResourcePreflightResult(
        issues=warning.issues,
        warnings=warning.warnings,
        diagnostics={
            **warning.diagnostics,
            "model_name": "EEGNet",
            "training_batch_size": 256,
        },
    )
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=SimpleNamespace(enabled=True, reasons=[]),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
            side_effect=dispatch,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.ask_confirmation",
            return_value=True,
        ) as question,
    ):
        sidebar.start_training_ui_action()
        callbacks[0][0](
            _training_result(
                preflight=warning,
                error_type=ErrorType.CONFIRMATION_REQUIRED,
            )
        )

    assert len(calls) == 2
    assert calls[1][1].resource_preflight_confirmed is True
    assert calls[1][1].resource_preflight_token == receipt
    message = question.call_args.kwargs["message"]
    assert "Model: EEGNet" in message
    assert "Batch size: 256" in message
    assert "Estimated VRAM required: 7.0 GB" in message
    assert "Available VRAM: 8.0 GB" in message


def test_start_training_confirmation_keeps_the_reviewed_publication_generation(
    sidebar,
):
    calls: list[dict[str, Any]] = []
    callbacks = []

    def _dispatch(_context, _command, *, on_result, **kwargs):
        calls.append(kwargs)
        callbacks.append(on_result)
        return True

    capability = CommandCapability(command_name="train", enabled=True)
    receipt = "training-receipt-2"
    warning = _training_preflight(
        vram_risk=RISK_WARNING,
        confirmation_token=receipt,
    )
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
            return_value=CommandReviewContext(
                capability=capability,
                publication_generation=61,
            ),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=capability,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
            side_effect=_dispatch,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.ask_confirmation",
            return_value=True,
        ),
    ):
        sidebar.start_training_ui_action()
        callbacks[0](
            _training_result(
                preflight=warning,
                error_type=ErrorType.CONFIRMATION_REQUIRED,
            )
        )

    assert [call["expected_publication_generation"] for call in calls] == [61, 61]


def test_training_settings_bind_snapshot_and_apply_to_one_reviewed_generation(
    sidebar,
):
    capability = CommandCapability(
        command_name="configure_training",
        enabled=True,
    )
    query_result = SimpleNamespace(
        failed=False,
        diagnostics={"state": {"training": {"training_option": {}}}},
    )
    save_result = SimpleNamespace(failed=False, message="saved")
    option = SimpleNamespace(
        epoch=10,
        bs=32,
        lr=0.001,
        repeat_num=1,
        use_cpu=True,
        gpu_idx=None,
        optim=None,
        optim_params={},
        checkpoint_epoch=0,
        output_dir="./output",
        evaluation_option=SimpleNamespace(value="last"),
    )
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
            return_value=CommandReviewContext(
                capability=capability,
                publication_generation=71,
            ),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=capability,
        ),
        patch("XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog") as dialog,
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command",
            side_effect=[query_result, save_result],
        ) as execute,
    ):
        dialog.return_value.exec.return_value = True
        dialog.return_value.get_result.return_value = option

        sidebar.training_setting()

    assert isinstance(execute.call_args_list[0].args[1], QueryStateCommand)
    assert isinstance(execute.call_args_list[1].args[1], ConfigureTrainingCommand)
    assert [
        call.kwargs["expected_publication_generation"]
        for call in execute.call_args_list
    ] == [71, 71]


def test_training_setting_prefills_backend_recommendation_then_explicit_proposal(
    sidebar,
):
    values = TrainingRecommendationValues(
        epochs=50,
        batch_size=8,
        learning_rate=0.001,
        optimizer="AdamW",
        evaluation_strategy="Best validation loss",
    )
    recommendation = TrainingRecommendation(
        context_fingerprint="sidebar-context",
        recommended_values=values,
        values=values,
        provenance={
            field.value: TrainingSettingProvenance.RECOMMENDED
            for field in TrainingRecommendationField
        },
        reasons=(),
        warnings=(),
    ).with_user_values({TrainingRecommendationField.BATCH_SIZE: 12})
    query_port = MagicMock()
    query_port.query_training_state.return_value = SimpleNamespace(
        failed=False,
        diagnostics={
            "state": {
                "training": {
                    "training_option": {
                        "epoch": 7,
                        "batch_size": 9,
                        "learning_rate": 0.9,
                        "optimizer": "Adam",
                        "evaluation_option": "Last Epoch",
                        "repeat": 3,
                        "device": "cpu",
                    }
                }
            }
        },
    )
    query_port.get_training_recommendation.return_value = recommendation
    sidebar.panel._typed_port_mode = True
    sidebar.panel._query_port = query_port
    sidebar.panel._publication_port = MagicMock()
    captured: dict[str, Any] = {}
    selected_option = SimpleNamespace()
    completed = SimpleNamespace(status="completed")

    def _capture_visible_fields(dialog):
        captured.update(
            epoch=dialog.epoch_entry.text(),
            batch_size=dialog.bs_entry.text(),
            learning_rate=dialog.lr_entry.text(),
            optimizer=dialog.optim.__name__,
            evaluation=dialog.evaluation_combo.currentData().value,
            repeat=dialog.repeat_entry.text(),
            use_cpu=dialog.use_cpu,
            manual_fields=dialog.get_recommendation().manual_fields,
        )
        return True

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
            return_value=CommandReviewContext(
                capability=CommandCapability(
                    command_name="configure_training",
                    enabled=True,
                ),
                publication_generation=71,
            ),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog.exec",
            new=_capture_visible_fields,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog.get_result",
            new=lambda _dialog: selected_option,
        ),
        patch.object(
            sidebar,
            "_apply_training_configuration",
            return_value=completed,
        ) as apply_configuration,
    ):
        outcome = sidebar.training_setting(
            suggested_values={"epoch": "61", "learning_rate": "0.002"}
        )

    assert outcome is completed
    query_port.get_training_recommendation.assert_called_once_with(
        expected_publication_generation=71
    )
    assert captured == {
        "epoch": "61",
        "batch_size": "12",
        "learning_rate": "0.002",
        "optimizer": "AdamW",
        "evaluation": "Best validation loss",
        "repeat": "3",
        "use_cpu": True,
        "manual_fields": (
            TrainingRecommendationField.EPOCHS,
            TrainingRecommendationField.BATCH_SIZE,
            TrainingRecommendationField.LEARNING_RATE,
        ),
    }
    submitted = apply_configuration.call_args.args[0]
    assert submitted.edited_recommendation_fields == frozenset(
        {
            TrainingRecommendationField.EPOCHS,
            TrainingRecommendationField.LEARNING_RATE,
        }
    )


def test_training_setting_recommendation_unavailable_still_opens_dialog(sidebar):
    query_port = MagicMock()
    query_port.query_training_state.return_value = SimpleNamespace(
        failed=False,
        diagnostics={"state": {"training": {"training_option": {}}}},
    )
    query_port.get_training_recommendation.side_effect = PreconditionError(
        "Recommendation context is changing."
    )
    sidebar.panel._typed_port_mode = True
    sidebar.panel._query_port = query_port
    sidebar.panel._publication_port = MagicMock()

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
            return_value=CommandReviewContext(
                capability=CommandCapability(
                    command_name="configure_training",
                    enabled=True,
                ),
                publication_generation=72,
            ),
        ),
        patch("XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog") as dialog,
    ):
        dialog.return_value.exec.return_value = False
        outcome = sidebar.training_setting()

    assert outcome.status.value == "cancelled"
    assert dialog.call_args.kwargs["recommendation"] is None


def test_device_recommendation_uses_same_detached_publication_context(sidebar):
    cpu_values = TrainingRecommendationValues(
        epochs=40,
        batch_size=32,
        learning_rate=0.0005,
        optimizer="AdamW",
        evaluation_strategy="Best validation loss",
    )
    gpu_values = replace(cpu_values, batch_size=8)
    cpu = TrainingRecommendation(
        context_fingerprint="cpu",
        recommended_values=cpu_values,
        values=cpu_values,
        provenance={},
        reasons=(),
        warnings=(),
    )
    gpu = replace(
        cpu,
        context_fingerprint="gpu",
        recommended_values=gpu_values,
        values=gpu_values,
    )
    query_port = MagicMock()
    query_port.get_training_recommendation.side_effect = [cpu, gpu]
    sidebar.panel._typed_port_mode = True
    sidebar.panel._query_port = query_port

    cpu_result = sidebar._training_device_recommendation(
        "cpu",
        expected_publication_generation=74,
    )
    gpu_result = sidebar._training_device_recommendation(
        "cuda:0",
        expected_publication_generation=74,
    )

    assert cpu_result is cpu
    assert gpu_result is gpu
    assert query_port.get_training_recommendation.call_args_list == [
        call(
            expected_publication_generation=74,
            prospective_device="cpu",
        ),
        call(
            expected_publication_generation=74,
            prospective_device="cuda:0",
        ),
    ]


def test_configure_training_previews_selected_model_recommendation_before_commit(
    sidebar,
):
    query_port = MagicMock()
    query_port.query_training_state.return_value = SimpleNamespace(
        failed=False,
        diagnostics={"state": {"training": {"training_option": {}}}},
    )
    attention_values = TrainingRecommendationValues(
        epochs=75,
        batch_size=16,
        learning_rate=0.0003,
        optimizer="AdamW",
        evaluation_strategy="Best validation loss",
    )
    attention_recommendation = TrainingRecommendation(
        context_fingerprint="prospective-attention",
        recommended_values=attention_values,
        values=attention_values,
        provenance={
            field.value: TrainingSettingProvenance.RECOMMENDED
            for field in TrainingRecommendationField
        },
        reasons=(),
        warnings=(),
    )
    query_port.get_training_recommendation.return_value = attention_recommendation
    sidebar.panel._typed_port_mode = True
    sidebar.panel._query_port = query_port
    sidebar.panel._publication_port = MagicMock()
    model_holder = MagicMock()
    model_holder.model_id = "braindecode.eegconformer"
    model_holder.model_params_map = {"n_filters_time": 40}
    model_holder.pretrained_weight_path = None
    model_holder.target_model.__name__ = "EEGConformer"
    selected_option = SimpleNamespace()
    completed = SimpleNamespace(status="completed")
    committed = False
    captured: dict[str, str] = {}

    def _capture_visible_fields(dialog):
        assert committed is False
        captured.update(
            epoch=dialog.epoch_entry.text(),
            batch_size=dialog.bs_entry.text(),
            learning_rate=dialog.lr_entry.text(),
            optimizer=dialog.optim.__name__,
        )
        return True

    def _commit(*_args, **_kwargs):
        nonlocal committed
        committed = True
        return completed

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
            return_value=CommandReviewContext(
                capability=CommandCapability(
                    command_name="configure_training",
                    enabled=True,
                ),
                publication_generation=73,
            ),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
        ) as model_dialog,
        patch(
            "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog.exec",
            new=_capture_visible_fields,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog.get_result",
            new=lambda _dialog: selected_option,
        ),
        patch.object(
            sidebar,
            "_apply_training_configuration",
            side_effect=_commit,
        ) as apply_configuration,
    ):
        model_dialog.return_value.exec.return_value = True
        model_dialog.return_value.get_result.return_value = model_holder
        outcome = sidebar.configure_training()

    assert outcome is completed
    query_port.get_training_recommendation.assert_called_once_with(
        expected_publication_generation=73,
        prospective_model_name="braindecode.eegconformer",
        prospective_model_params={"n_filters_time": 40},
    )
    assert captured == {
        "epoch": "75",
        "batch_size": "16",
        "learning_rate": "0.0003",
        "optimizer": "AdamW",
    }
    submitted = apply_configuration.call_args.args[0]
    assert submitted.model_name == "braindecode.eegconformer"
    assert submitted.edited_recommendation_fields == frozenset()


def test_start_training_blocking_result_opens_adjust_settings_without_retry(sidebar):
    dispatch, calls, callbacks = _async_dispatch_recorder()
    blocking_result = _training_preflight(ram_risk=RISK_BLOCKING)
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=SimpleNamespace(enabled=True, reasons=[]),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
            side_effect=dispatch,
        ),
        patch.object(sidebar, "_show_training_resource_blocking_dialog") as blocking,
    ):
        sidebar.start_training_ui_action()
        callbacks[0][0](
            _training_result(
                preflight=blocking_result,
                error_type=ErrorType.PRECONDITION,
            )
        )

    assert len(calls) == 1
    blocking.assert_called_once()


def test_start_training_warning_without_receipt_fails_closed(sidebar):
    dispatch, calls, callbacks = _async_dispatch_recorder()
    warning = _training_preflight(vram_risk=RISK_WARNING)
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=SimpleNamespace(enabled=True, reasons=[]),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
            side_effect=dispatch,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.ask_confirmation",
            return_value=True,
        ),
        patch("XBrainLab.ui.panels.training.sidebar.show_error") as critical,
    ):
        sidebar.start_training_ui_action()
        callbacks[0][0](
            _training_result(
                preflight=warning,
                error_type=ErrorType.CONFIRMATION_REQUIRED,
            )
        )

    assert len(calls) == 1
    critical.assert_called_once()
    assert "could not verify" in critical.call_args.args[2]


def test_start_training_unknown_retries_once_before_prompt(sidebar):
    dispatch, calls, callbacks = _async_dispatch_recorder()
    unknown = _training_preflight(vram_risk=RISK_UNKNOWN)
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=SimpleNamespace(enabled=True, reasons=[]),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
            side_effect=dispatch,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.ask_confirmation",
            return_value=False,
        ) as question,
    ):
        sidebar.start_training_ui_action()
        first_unknown = _training_result(
            preflight=unknown,
            error_type=ErrorType.CONFIRMATION_REQUIRED,
        )
        callbacks[0][0](first_unknown)
        callbacks[1][0](first_unknown)

    assert len(calls) == 2
    assert all(not command.resource_preflight_confirmed for _, command in calls)
    question.assert_called_once()


def test_start_training_async_failure_uses_existing_error_surface(sidebar):
    dispatch, calls, callbacks = _async_dispatch_recorder()
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=SimpleNamespace(enabled=True, reasons=[]),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command_async",
            side_effect=dispatch,
        ),
        patch("XBrainLab.ui.panels.training.sidebar.show_error") as critical,
    ):
        sidebar.start_training_ui_action()
        callbacks[0][0](_training_result(error_type=ErrorType.TRAINING))

    assert len(calls) == 1
    critical.assert_called_once()


def test_stop_training(sidebar):
    sidebar.controller.is_training.return_value = True
    with patch("XBrainLab.ui.panels.training.sidebar.show_warning") as warning:
        sidebar.stop_training()
    sidebar.controller.stop_training.assert_not_called()
    warning.assert_called_once()
    assert warning.call_args.args[1] == "Stop Training Blocked"


def test_stop_result_waits_for_stopped_publication_to_disable_control(sidebar):
    result = CommandResult.success_result(
        command_name="stop_training",
        message="Training stop requested.",
        state=None,
        changed_state=ChangedState(training_changed=True),
    )
    sidebar.btn_stop.setEnabled(True)

    with (
        patch.object(
            sidebar,
            "_command_capability",
            return_value=CommandCapability(
                command_name=CommandName.STOP_TRAINING.value,
                enabled=True,
            ),
        ),
        patch.object(sidebar, "_execute_action", return_value=result),
    ):
        sidebar.stop_training()

    assert sidebar.btn_stop.isEnabled() is True

    sidebar.on_training_stopped(refresh_ready=False)

    assert sidebar.btn_stop.isEnabled() is False


def test_check_ready_to_train(sidebar):
    # Ensure button starts enabled or disabled based on init.
    # Init calls check_ready_to_train. Mock default is True (MagicMock is truthy).
    # So initially enabled.

    sidebar.controller.validate_ready.return_value = False
    sidebar.check_ready_to_train()

    # Debug: verification
    sidebar.controller.validate_ready.assert_called()
    assert sidebar.btn_start.isEnabled() is False

    sidebar.controller.validate_ready.return_value = True
    sidebar.check_ready_to_train()
    assert sidebar.btn_start.isEnabled() is True


def test_training_capability_blocks_start_without_rendering_readiness(sidebar, qtbot):
    capability = CommandCapability(
        command_name="train",
        enabled=False,
        reasons=[
            "Generate datasets before training.",
            "Select a model before training.",
        ],
    )
    publication = SimpleNamespace(
        usable=True,
        state=SimpleNamespace(
            active_dataset=SimpleNamespace(
                has_raw_data=True,
                has_preprocessed_data=True,
                has_epoch_data=True,
                has_datasets=False,
            ),
            active_training=SimpleNamespace(
                has_model=False,
                has_training_option=False,
            ),
        ),
        effective_capabilities={CommandName.TRAIN: capability},
    )

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            side_effect=AssertionError(
                "readiness must use the capability from the same publication",
            ),
        ),
    ):
        sidebar.check_ready_to_train()
        qtbot.wait(0)
        assert not sidebar.btn_start.isEnabled()
        assert "Generate datasets before training." in sidebar.btn_start.toolTip()
        assert sidebar.findChild(QGroupBox, "TrainingReadiness") is None


@pytest.mark.parametrize(
    (
        "raw",
        "preprocessed",
        "epochs",
        "split",
        "model",
        "settings",
        "capability_enabled",
        "capability_reason",
        "expected_statuses",
        "expected_next",
    ),
    [
        pytest.param(
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            "Import EEG data before training.",
            ("Needed", "Needed", "Needed"),
            "Next: Import EEG data",
            id="import",
        ),
        pytest.param(
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            "Preprocess the imported EEG data before training.",
            ("Needed", "Needed", "Needed"),
            "Next: Preprocess EEG",
            id="preprocess",
        ),
        pytest.param(
            True,
            True,
            False,
            False,
            False,
            False,
            False,
            "Create EEG epochs before configuring training datasets.",
            ("Needed", "Needed", "Needed"),
            "Next: Create EEG epochs",
            id="epochs-before-split",
        ),
        pytest.param(
            True,
            True,
            True,
            False,
            False,
            False,
            False,
            "Generate datasets before training.",
            ("Needed", "Needed", "Needed"),
            "Next: Configure dataset split",
            id="split",
        ),
        pytest.param(
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            "Select a model before training.",
            ("Ready", "Needed", "Needed"),
            "Next: Select model",
            id="model",
        ),
        pytest.param(
            True,
            True,
            True,
            True,
            True,
            False,
            False,
            "Set training options before training.",
            ("Ready", "Ready", "Needed"),
            "Next: Set training options",
            id="settings",
        ),
        pytest.param(
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            "",
            ("Ready", "Ready", "Ready"),
            None,
            id="ready",
        ),
    ],
)
def test_training_start_availability_uses_one_application_publication(
    sidebar,
    raw,
    preprocessed,
    epochs,
    split,
    model,
    settings,
    capability_enabled,
    capability_reason,
    expected_statuses,
    expected_next,
):
    capability = CommandCapability(
        command_name="train",
        enabled=capability_enabled,
        reasons=[capability_reason] if capability_reason else [],
    )
    publication = SimpleNamespace(
        usable=True,
        state=SimpleNamespace(
            active_dataset=SimpleNamespace(
                has_raw_data=raw,
                has_preprocessed_data=preprocessed,
                has_epoch_data=epochs,
                has_datasets=split,
            ),
            active_training=SimpleNamespace(
                has_model=model,
                has_training_option=settings,
            ),
        ),
        effective_capabilities={CommandName.TRAIN: capability},
    )
    for method_name in (
        "validate_ready",
        "has_datasets",
        "has_model",
        "has_training_option",
    ):
        controller_method = getattr(sidebar.controller, method_name)
        controller_method.reset_mock()
        controller_method.side_effect = AssertionError(
            f"publication readiness must not call controller.{method_name}",
        )

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            side_effect=AssertionError(
                "readiness must use the capability from the same publication",
            ),
        ),
    ):
        sidebar.check_ready_to_train()

    assert sidebar.btn_start.isEnabled() is capability_enabled
    expected_tooltip = "Start Training" if capability_enabled else capability_reason
    assert expected_tooltip in sidebar.btn_start.toolTip()
    assert sidebar.findChild(QGroupBox, "TrainingReadiness") is None
    for method_name in (
        "validate_ready",
        "has_datasets",
        "has_model",
        "has_training_option",
    ):
        getattr(sidebar.controller, method_name).assert_not_called()


def test_training_start_fails_closed_when_product_publication_is_unavailable(
    sidebar,
):
    publication = SimpleNamespace(usable=False, state=None)
    capability = CommandCapability(
        command_name="train",
        enabled=False,
        reasons=["Training state is unavailable."],
    )

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.has_real_application_context",
            return_value=True,
        ),
        patch.object(
            sidebar,
            "_compatibility_controller_value",
            side_effect=AssertionError(
                "product readiness must not fall back to controller state",
            ),
        ),
    ):
        sidebar.check_ready_to_train()

    assert not sidebar.btn_start.isEnabled()
    assert sidebar.btn_start.toolTip() == "Training state is unavailable right now."
    assert sidebar.findChild(QGroupBox, "TrainingReadiness") is None


def test_clear_history_button_uses_same_publication_capability(sidebar):
    train_capability = CommandCapability(
        command_name=CommandName.TRAIN.value,
        enabled=False,
        reasons=["Training is running."],
    )
    clear_capability = CommandCapability(
        command_name=CommandName.CLEAR_TRAINING_HISTORY.value,
        enabled=False,
        reasons=["Stop training before clearing history."],
    )
    capabilities = {
        CommandName.TRAIN: train_capability,
        CommandName.CLEAR_TRAINING_HISTORY: clear_capability,
    }
    publication = SimpleNamespace(
        usable=True,
        state=SimpleNamespace(
            active_dataset=SimpleNamespace(
                has_raw_data=True,
                has_preprocessed_data=True,
                has_epoch_data=True,
                has_datasets=True,
            ),
            active_training=SimpleNamespace(
                has_model=True,
                has_training_option=True,
            ),
        ),
        effective_capabilities=capabilities,
    )

    sidebar.check_ready_to_train(publication=publication)

    assert sidebar.btn_clear.isEnabled() is False
    assert sidebar.btn_clear.toolTip() == "Stop training before clearing history."

    capabilities[CommandName.CLEAR_TRAINING_HISTORY] = CommandCapability(
        command_name=CommandName.CLEAR_TRAINING_HISTORY.value,
        enabled=True,
    )
    sidebar.check_ready_to_train(publication=publication)

    assert sidebar.btn_clear.isEnabled() is True
    assert sidebar.btn_clear.toolTip() == "Clear training history"


def test_real_study_controller_compatibility_stops_before_fallback_gateway(
    real_study_sidebar,
):
    sidebar, *_ = real_study_sidebar
    fallback = MagicMock()

    with patch(
        "XBrainLab.ui.panels.training.sidebar.run_controller_compatibility_call",
        side_effect=AssertionError(
            "real Study context must not enter controller compatibility",
        ),
    ):
        available, value = sidebar._compatibility_controller_value(fallback)

    assert available is False
    assert value is None
    fallback.assert_not_called()


def test_real_study_missing_publication_never_reads_controller(
    real_study_sidebar,
):
    sidebar, *_ = real_study_sidebar
    controller = sidebar.controller
    for method_name in (
        "validate_ready",
        "has_datasets",
        "has_model",
        "has_training_option",
    ):
        getattr(controller, method_name).side_effect = AssertionError(
            f"product readiness must not call controller.{method_name}",
        )

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.run_controller_compatibility_call",
            side_effect=AssertionError(
                "missing product publication must not enter controller compatibility",
            ),
        ),
    ):
        sidebar.check_ready_to_train()

    assert not sidebar.btn_start.isEnabled()
    assert sidebar.btn_start.toolTip() == "Training state is unavailable right now."
    assert sidebar.findChild(QGroupBox, "TrainingReadiness") is None


def test_product_action_result_waits_for_the_next_publication(
    real_study_sidebar,
):
    sidebar, *_ = real_study_sidebar
    controller = sidebar.controller
    for method_name in (
        "validate_ready",
        "has_datasets",
        "has_model",
        "has_training_option",
    ):
        getattr(controller, method_name).side_effect = AssertionError(
            f"product refresh must not call controller.{method_name}",
        )

    blocked_capability = CommandCapability(
        command_name="train",
        enabled=False,
        reasons=["Select a model before training."],
    )
    ready_capability = CommandCapability(command_name="train", enabled=True)
    dataset_state = SimpleNamespace(
        has_raw_data=True,
        has_preprocessed_data=True,
        has_epoch_data=True,
        has_datasets=True,
    )
    publications = (
        SimpleNamespace(
            usable=True,
            state=SimpleNamespace(
                active_dataset=dataset_state,
                active_training=SimpleNamespace(
                    has_model=False,
                    has_training_option=True,
                ),
            ),
            effective_capabilities={CommandName.TRAIN: blocked_capability},
        ),
        SimpleNamespace(
            usable=True,
            state=SimpleNamespace(
                active_dataset=dataset_state,
                active_training=SimpleNamespace(
                    has_model=True,
                    has_training_option=True,
                ),
            ),
            effective_capabilities={CommandName.TRAIN: ready_capability},
        ),
    )
    panel = sidebar.panel
    main_window = sidebar.main_window
    cast(Any, main_window).training_panel = panel
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            side_effect=publications,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.run_controller_compatibility_call",
            side_effect=AssertionError(
                "product refresh must not enter controller compatibility",
            ),
        ),
    ):
        sidebar.check_ready_to_train()
        assert not sidebar.btn_start.isEnabled()

        refreshed = refresh_after_command(
            sidebar,
            _training_result(preflight=_training_preflight()),
        )
        assert refreshed is False
        panel.update_panel.assert_not_called()
        assert not sidebar.btn_start.isEnabled()

        sidebar.check_ready_to_train()

    assert sidebar.btn_start.isEnabled()
    assert sidebar.btn_start.toolTip() == "Start Training"


def test_check_ready_to_train_never_reads_controller_when_product_truth_is_missing(
    sidebar,
):
    publication = SimpleNamespace(usable=False, state=None)

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.has_real_application_context",
            return_value=True,
        ),
        patch.object(
            sidebar,
            "_compatibility_controller_value",
            side_effect=AssertionError(
                "product readiness must not read controller compatibility state",
            ),
        ),
    ):
        sidebar.check_ready_to_train()

    assert not sidebar.btn_start.isEnabled()
    assert sidebar.btn_start.toolTip() == "Training state is unavailable right now."
    assert sidebar.findChild(QGroupBox, "TrainingReadiness") is None


def test_check_ready_to_train_rejects_enabled_capability_from_unusable_publication(
    sidebar,
):
    publication = SimpleNamespace(
        usable=False,
        state=None,
        effective_capabilities={
            CommandName.TRAIN: CommandCapability(
                command_name="train",
                enabled=True,
            )
        },
    )

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.has_real_application_context",
            return_value=True,
        ),
        patch.object(
            sidebar,
            "_compatibility_controller_value",
            side_effect=AssertionError(
                "unusable product publication must not enter compatibility",
            ),
        ),
    ):
        sidebar.check_ready_to_train()

    assert not sidebar.btn_start.isEnabled()
    assert sidebar.btn_start.toolTip() == "Training state is unavailable right now."
    assert sidebar.findChild(QGroupBox, "TrainingReadiness") is None


def test_check_ready_to_train_rejects_malformed_product_capability(sidebar):
    publication = SimpleNamespace(
        usable=True,
        state=SimpleNamespace(
            active_dataset=SimpleNamespace(
                has_raw_data=True,
                has_preprocessed_data=True,
                has_epoch_data=True,
                has_datasets=True,
            ),
            active_training=SimpleNamespace(
                has_model=True,
                has_training_option=True,
            ),
        ),
        effective_capabilities={CommandName.TRAIN: object()},
    )

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.has_real_application_context",
            return_value=True,
        ),
        patch.object(
            sidebar,
            "_compatibility_controller_value",
            side_effect=AssertionError(
                "malformed product publication must fail closed",
            ),
        ),
    ):
        sidebar.check_ready_to_train()

    assert not sidebar.btn_start.isEnabled()
    assert sidebar.btn_start.toolTip() == "Training state is unavailable right now."
    assert sidebar.findChild(QGroupBox, "TrainingReadiness") is None


@pytest.mark.parametrize(
    "action_name",
    ["select_model", "configure_training", "training_setting"],
)
@pytest.mark.parametrize(
    "review_context",
    [
        pytest.param(None, id="missing-review"),
        pytest.param(
            SimpleNamespace(capability=None, publication_generation=81),
            id="missing-capability",
        ),
    ],
)
def test_training_configuration_fails_before_dialog_without_product_review(
    real_study_sidebar,
    action_name,
    review_context,
):
    sidebar, _study = real_study_sidebar

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
            return_value=review_context,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog",
        ) as model_dialog,
        patch(
            "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog",
        ) as settings_dialog,
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command",
        ) as execute,
        patch("XBrainLab.ui.panels.training.sidebar.show_warning") as warning,
    ):
        outcome = getattr(sidebar, action_name)()

    assert outcome.status.value == "blocked"
    model_dialog.assert_not_called()
    settings_dialog.assert_not_called()
    execute.assert_not_called()
    warning.assert_called_once()


def test_start_training_fails_before_dispatch_when_product_review_disappears(
    real_study_sidebar,
):
    sidebar, _study = real_study_sidebar
    enabled = CommandCapability(command_name="train", enabled=True)

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_review_context",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=enabled,
        ),
        patch.object(sidebar, "_dispatch_start_training") as dispatch,
        patch("XBrainLab.ui.panels.training.sidebar.show_warning") as warning,
    ):
        sidebar.start_training_ui_action()

    dispatch.assert_not_called()
    warning.assert_called_once()


def test_clear_history_fails_before_confirmation_when_publication_disappears(
    real_study_sidebar,
):
    sidebar, _study = real_study_sidebar
    enabled = CommandCapability(
        command_name=CommandName.CLEAR_TRAINING_HISTORY.value,
        enabled=True,
    )

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=enabled,
        ),
        patch("XBrainLab.ui.panels.training.sidebar.ask_confirmation") as question,
        patch("XBrainLab.ui.panels.training.sidebar.show_warning") as warning,
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command",
        ) as execute,
    ):
        sidebar.clear_history()

    question.assert_not_called()
    execute.assert_not_called()
    warning.assert_called_once()


def test_dataset_split_dialog_binding_uses_typed_runtime_callbacks():
    from XBrainLab.backend.application.dataset_split_preview import (
        DatasetSplitContext,
        DatasetSplitContextPublication,
        DatasetSplitContextRequest,
        DatasetSplitPreviewPublication,
        DatasetSplitPreviewRequest,
        DatasetSplitPreviewRow,
        DatasetSplitSpecification,
    )
    from XBrainLab.ui.application_capabilities import (
        get_dataset_split_dialog_binding,
    )

    generation = 91
    context_request = DatasetSplitContextRequest(
        publication_generation=generation,
    )
    context_publication = DatasetSplitContextPublication(
        request=context_request,
        generation=generation,
        context=DatasetSplitContext(
            epoch_available=True,
            subject_count=2,
            session_count=1,
            label_count=2,
            trial_count=12,
        ),
    )
    preview_request = DatasetSplitPreviewRequest(
        request_id="preview-91",
        publication_generation=generation,
        specification=DatasetSplitSpecification(
            train_type="Individual",
            is_cross_validation=False,
        ),
    )
    preview_publication = DatasetSplitPreviewPublication(
        request=preview_request,
        generation=generation,
        epoch_token=1,
        rows=(
            DatasetSplitPreviewRow(
                name="Subject 1",
                train_count=8,
                validation_count=2,
                test_count=2,
            ),
        ),
    )

    class Runtime:
        def __init__(self):
            self.context_requests = []
            self.preview_requests = []
            self.cancelled_request_ids = []

        def get_dataset_split_context(self, request):
            self.context_requests.append(request)
            return context_publication

        def get_dataset_split_preview(self, request):
            self.preview_requests.append(request)
            return preview_publication

        def cancel_dataset_split_preview(self, request_id):
            self.cancelled_request_ids.append(request_id)
            return True

    runtime = Runtime()

    binding = get_dataset_split_dialog_binding(
        object(),
        publication_generation=generation,
        runtime=cast(Any, runtime),
    )

    assert binding is not None
    assert runtime.context_requests == [context_request]
    assert binding.split_context is context_publication.context
    assert binding.publication_generation == generation
    assert binding.preview_provider(preview_request) is preview_publication
    assert binding.preview_canceller("preview-91") is True
    assert runtime.preview_requests == [preview_request]
    assert runtime.cancelled_request_ids == ["preview-91"]


def test_split_data_passes_typed_detached_binding_to_dialog(
    sidebar,
):
    from PyQt6.QtWidgets import QDialog

    from XBrainLab.backend.application.dataset_split_preview import DatasetSplitContext
    from XBrainLab.ui.application_capabilities import DatasetSplitDialogBinding
    from XBrainLab.ui.interaction_outcome import InteractionStatus

    generation = 92
    capability = CommandCapability(
        command_name=CommandName.CONFIGURE_DATASET_SPLIT.value,
        enabled=True,
    )
    publication = SimpleNamespace(
        generation=generation,
        effective_capabilities={CommandName.CONFIGURE_DATASET_SPLIT: capability},
    )
    split_context = DatasetSplitContext(
        epoch_available=True,
        subject_count=2,
        session_count=1,
        label_count=2,
        trial_count=12,
    )
    preview_provider = MagicMock()
    preview_canceller = MagicMock()
    binding = DatasetSplitDialogBinding(
        split_context=split_context,
        publication_generation=generation,
        preview_provider=preview_provider,
        preview_canceller=preview_canceller,
    )
    initial_values = {
        "training_mode": "individual",
        "split_strategy": "subject",
    }

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_application_view_publication",
            return_value=publication,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_dataset_split_dialog_binding",
            return_value=binding,
        ) as get_binding,
        patch(
            "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog",
        ) as dialog,
    ):
        dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
        outcome = sidebar.split_data(suggested_values=initial_values)

    assert outcome.status is InteractionStatus.CANCELLED
    get_binding.assert_called_once_with(
        sidebar,
        publication_generation=generation,
    )
    dialog.assert_called_once_with(
        sidebar,
        split_context=split_context,
        publication_generation=generation,
        preview_provider=preview_provider,
        preview_canceller=preview_canceller,
        initial_values=initial_values,
    )


def test_split_confirmation_keeps_model_and_training_settings_responsive(sidebar):
    from PyQt6.QtWidgets import QDialog

    from XBrainLab.backend.application.dataset_split_preview import (
        DatasetSplitContext,
        DatasetSplitPreviewPublication,
        DatasetSplitPreviewRequest,
        DatasetSplitPreviewRow,
        DatasetSplitSpecification,
    )
    from XBrainLab.ui.application_capabilities import DatasetSplitDialogBinding

    generation = 93
    capability = CommandCapability(
        command_name=CommandName.CONFIGURE_DATASET_SPLIT.value,
        enabled=True,
    )
    publication = SimpleNamespace(
        generation=generation,
        effective_capabilities={CommandName.CONFIGURE_DATASET_SPLIT: capability},
    )
    specification = DatasetSplitSpecification.from_payload(
        {
            "train_type": "Individual",
            "is_cross_validation": False,
            "val_splitters": [],
            "test_splitters": [],
        }
    )
    preview_request = DatasetSplitPreviewRequest(
        request_id="preview-93",
        publication_generation=generation,
        specification=specification,
    )
    receipt = DatasetSplitPreviewPublication(
        request=preview_request,
        generation=generation,
        epoch_token=1,
        rows=(
            DatasetSplitPreviewRow(
                name="S01",
                train_count=8,
                validation_count=2,
                test_count=2,
            ),
        ),
    ).receipt
    binding = DatasetSplitDialogBinding(
        split_context=DatasetSplitContext(epoch_available=True, trial_count=12),
        publication_generation=generation,
        preview_provider=MagicMock(),
        preview_canceller=MagicMock(),
    )
    dispatched: list[tuple[Any, dict[str, Any]]] = []

    def dispatch(command, **kwargs):
        dispatched.append((command, kwargs))
        kwargs["busy_target"].set_busy(True)
        return True

    with (
        patch.object(sidebar, "_application_publication", return_value=publication),
        patch.object(sidebar, "_data_splitting_dialog_context", return_value=binding),
        patch("XBrainLab.ui.panels.training.sidebar.DataSplittingDialog") as dialog,
        patch.object(sidebar, "_execute_action_async", side_effect=dispatch),
    ):
        dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
        dialog.return_value.get_result.return_value = specification.to_payload()
        dialog.return_value.get_preview_receipt.return_value = receipt
        outcome = sidebar.split_data()

    assert len(dispatched) == 1
    assert outcome.message == "Data splitting settings will be saved."
    command, kwargs = dispatched[0]
    assert command.preview_receipt is receipt
    assert kwargs["busy_target"] is sidebar
    assert sidebar.btn_start.isEnabled() is False
    assert sidebar.btn_model.isEnabled() is True
    assert sidebar.btn_setting.isEnabled() is True


def test_data_splitting_context_fails_closed_when_product_binding_disappears(
    real_study_sidebar,
):
    sidebar, _study = real_study_sidebar

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_dataset_split_dialog_binding",
            return_value=None,
        ) as get_binding,
        patch("XBrainLab.ui.panels.training.sidebar.show_warning") as warning,
    ):
        context = sidebar._data_splitting_dialog_context(
            expected_publication_generation=91,
        )

    assert context is None
    get_binding.assert_called_once_with(
        sidebar,
        publication_generation=91,
    )
    warning.assert_called_once_with(
        sidebar,
        "Data Splitting Blocked",
        (
            "XBrainLab could not safely complete this action from the current "
            "window state. Refresh the workflow and try again."
        ),
    )


def test_data_splitting_context_stale_publication_requires_review(sidebar):
    from XBrainLab.backend.application import PreconditionError

    error = PreconditionError(
        "The application data changed before dataset splitting could begin.",
        diagnostics={
            "requested_generation": 92,
            "current_generation": 93,
        },
    )

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_dataset_split_dialog_binding",
            side_effect=error,
        ),
        patch("XBrainLab.ui.panels.training.sidebar.show_warning") as warning,
    ):
        binding = sidebar._data_splitting_dialog_context(
            expected_publication_generation=92,
        )

    assert binding is None
    warning.assert_called_once_with(
        sidebar,
        "Review Data Splitting Again",
        str(error),
    )


def test_data_splitting_launch_uses_typed_detached_binding():
    source = inspect.getsource(TrainingSidebar._data_splitting_dialog_context)

    assert "get_dataset_split_dialog_binding" in source
    assert "publication_generation" in source


def test_on_training_stopped(sidebar):
    sidebar.on_training_stopped()
    # Button should revert to "Start Training" (primary color)
    # Checking text might differ based on UI implementation details,
    # but we can check if it's enabled and set to primary/success style logic if verified.
    assert sidebar.btn_start.text() == "Start Training"
    assert sidebar.btn_start.isEnabled() is True
