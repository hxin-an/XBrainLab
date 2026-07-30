from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QLabel, QMainWindow, QMessageBox, QPushButton

from XBrainLab.backend.application import (
    ChangedState,
    CommandName,
    CommandResult,
    ConfigureTrainingCommand,
    ErrorType,
    QueryStateCommand,
)
from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.application.resource_guard import (
    RISK_BLOCKING,
    RISK_SAFE,
    RISK_UNKNOWN,
    RISK_WARNING,
    ResourcePreflightResult,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import CommandReviewContext
from XBrainLab.ui.panels.training.sidebar import TrainingSidebar
from XBrainLab.ui.refresh_coordinator import refresh_after_command
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme


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


def test_init_ui(sidebar):
    assert isinstance(sidebar.btn_split, QPushButton)
    assert isinstance(sidebar.btn_model, QPushButton)
    assert isinstance(sidebar.btn_setting, QPushButton)
    assert isinstance(sidebar.btn_start, QPushButton)
    assert sidebar.btn_start.styleSheet() == Stylesheets.BTN_PRIMARY
    assert sidebar.findChild(QLabel, "TrainingResourceCheck") is None


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
    with patch("XBrainLab.ui.panels.training.sidebar.QMessageBox.warning") as warning:
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


def test_start_training_dispatches_one_async_command_without_sync_preflight(sidebar):
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

    callbacks[0][0](_training_result(preflight=_training_preflight()))
    assert sidebar.btn_stop.isEnabled() is True


def test_completed_command_result_leaves_readiness_to_refresh_coordinator(sidebar):
    with patch.object(sidebar, "check_ready_to_train") as check_ready:
        sidebar._check_ready_after_command_result(
            _training_result(preflight=_training_preflight())
        )

    check_ready.assert_not_called()


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
        patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
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
    message = question.call_args.args[2]
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
        patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
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
        patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch.object(QMessageBox, "critical") as critical,
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
        patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.No,
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
        patch.object(QMessageBox, "critical") as critical,
    ):
        sidebar.start_training_ui_action()
        callbacks[0][0](_training_result(error_type=ErrorType.TRAINING))

    assert len(calls) == 1
    critical.assert_called_once()


def test_stop_training(sidebar):
    sidebar.controller.is_training.return_value = True
    with patch("XBrainLab.ui.panels.training.sidebar.QMessageBox.warning") as warning:
        sidebar.stop_training()
    sidebar.controller.stop_training.assert_not_called()
    warning.assert_called_once()
    assert warning.call_args.args[1] == "Stop Training Blocked"


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


def test_training_readiness_shows_only_first_blocking_next_action(sidebar, qtbot):
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
        patch.object(sidebar, "split_data") as split_data,
    ):
        sidebar.check_ready_to_train()
        qtbot.wait(0)
        visible_actions = [
            button
            for button in sidebar.readiness_group.findChildren(QPushButton)
            if not button.isHidden()
        ]
        assert visible_actions == [sidebar.readiness_next_button]
        assert sidebar.readiness_next_button.text() == "Next: Configure dataset split"
        assert "Generate datasets before training." in sidebar.readiness_blocker.text()
        assert sidebar.readiness_status_labels["EEG epochs"].text() == "Ready"
        assert sidebar.readiness_status_labels["Training datasets"].text() == "Needed"
        assert (
            f"color: {Theme.LOG_INFO};"
            in sidebar.readiness_status_labels["EEG epochs"].styleSheet()
        )
        assert (
            f"color: {Theme.LOG_WARNING};"
            in sidebar.readiness_status_labels["Training datasets"].styleSheet()
        )

        sidebar.readiness_next_button.click()

    split_data.assert_called_once_with()


def test_training_readiness_fails_closed_when_product_publication_is_unavailable(
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
            "XBrainLab.ui.panels.training.sidebar.has_real_application_context",
            return_value=True,
        ),
        patch.object(
            sidebar,
            "_compatibility_readiness",
            side_effect=AssertionError(
                "product readiness must not fall back to controller state",
            ),
        ),
    ):
        sidebar._update_readiness_presentation(publication, capability)

    assert all(
        label.text() == "Needed" for label in sidebar.readiness_status_labels.values()
    )
    assert (
        sidebar.readiness_blocker.text()
        == "Training state is unavailable. Reopen Training or reload the workflow."
    )
    assert sidebar.readiness_next_button.isHidden()
    assert sidebar._readiness_next_action is None


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
    assert (
        sidebar.readiness_blocker.text()
        == "Training state is unavailable. Reopen Training or reload the workflow."
    )
    assert sidebar.readiness_next_button.isHidden()


def test_product_action_result_refresh_reads_the_next_publication(
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
    panel.update_panel.side_effect = sidebar.check_ready_to_train

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

    assert refreshed is True
    panel.update_panel.assert_called_once_with()
    assert sidebar.btn_start.isEnabled()
    assert sidebar.readiness_blocker.text() == "Ready to start training."
    assert sidebar.readiness_next_button.isHidden()


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
    assert (
        sidebar.readiness_blocker.text()
        == "Training state is unavailable. Reopen Training or reload the workflow."
    )
    assert sidebar.readiness_next_button.isHidden()


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
    assert "state is unavailable" in sidebar.readiness_blocker.text()


def test_on_training_stopped(sidebar):
    sidebar.on_training_stopped()
    # Button should revert to "Start Training" (primary color)
    # Checking text might differ based on UI implementation details,
    # but we can check if it's enabled and set to primary/success style logic if verified.
    assert sidebar.btn_start.text() == "Start Training"
    assert sidebar.btn_start.isEnabled() is True
