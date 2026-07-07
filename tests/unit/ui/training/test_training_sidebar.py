from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QLabel, QMessageBox, QPushButton

from XBrainLab.backend.application.resource_guard import (
    RISK_BLOCKING,
    RISK_SAFE,
    RISK_UNKNOWN,
    RISK_WARNING,
    ResourceCheckResult,
)
from XBrainLab.ui.panels.training.sidebar import TrainingSidebar


@pytest.fixture
def sidebar(qtbot):
    panel_mock = MagicMock()
    panel_mock.controller = MagicMock()
    # Mock main_window on panel for AggregateInfoPanel access
    panel_mock.main_window = None

    widget = TrainingSidebar(panel_mock, parent=None)
    qtbot.addWidget(widget)
    return widget


def test_init_ui(sidebar):
    assert isinstance(sidebar.btn_split, QPushButton)
    assert isinstance(sidebar.btn_model, QPushButton)
    assert isinstance(sidebar.btn_setting, QPushButton)
    assert isinstance(sidebar.btn_start, QPushButton)
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


def test_start_training_blocks_when_resource_check_is_too_large(sidebar):
    resource_result = ResourceCheckResult(
        required_memory_bytes=10 * 1024**3,
        available_memory_bytes=4 * 1024**3,
        total_memory_bytes=8 * 1024**3,
        used_memory_bytes=4 * 1024**3,
        risk_level=RISK_BLOCKING,
        message="Training configuration may exceed available GPU memory.",
        suggestions=("reduce batch size",),
        details={},
    )
    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=MagicMock(enabled=True),
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar."
            "ResourceChecker.check_training_config_safe",
            return_value=resource_result,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command",
        ) as execute,
        patch.object(sidebar, "_show_training_resource_blocking_dialog") as blocking,
    ):
        sidebar.start_training_ui_action()

    execute.assert_not_called()
    blocking.assert_called_once()
    assert "Estimated VRAM required: 10.0 GB" in blocking.call_args.args[0]


def test_start_training_rechecks_unknown_resource_once_before_prompt(sidebar):
    unknown_result = ResourceCheckResult(
        required_memory_bytes=8 * 1024**3,
        available_memory_bytes=None,
        total_memory_bytes=None,
        used_memory_bytes=None,
        risk_level=RISK_UNKNOWN,
        message="Unable to estimate GPU memory.",
        suggestions=("reduce batch size",),
        details={"reason": "cuda_unavailable"},
    )
    safe_result = ResourceCheckResult(
        required_memory_bytes=2 * 1024**3,
        available_memory_bytes=8 * 1024**3,
        total_memory_bytes=12 * 1024**3,
        used_memory_bytes=4 * 1024**3,
        risk_level=RISK_SAFE,
        message="Resource check: Safe",
        suggestions=(),
        details={"batch_size": 32},
    )
    capability = MagicMock(enabled=True)

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=capability,
        ),
        patch.object(
            sidebar,
            "_training_resource_check_result",
            side_effect=[unknown_result, safe_result],
        ) as check,
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command",
            return_value=MagicMock(failed=False, diagnostics={}),
        ) as execute,
        patch("XBrainLab.ui.panels.training.sidebar.QMessageBox.question") as question,
    ):
        sidebar.start_training_ui_action()

    assert check.call_count == 2
    question.assert_not_called()
    execute.assert_called_once()


def test_start_training_warning_dialog_includes_actionable_resource_details(sidebar):
    class EEGNet:
        pass

    warning_result = ResourceCheckResult(
        required_memory_bytes=7 * 1024**3,
        available_memory_bytes=8 * 1024**3,
        total_memory_bytes=12 * 1024**3,
        used_memory_bytes=4 * 1024**3,
        risk_level=RISK_WARNING,
        message="Training configuration is close to available GPU memory.",
        suggestions=("reduce batch size", "reduce input length or epoch window"),
        details={"batch_size": 256, "gpu_name": "NVIDIA Test GPU"},
    )

    with (
        patch(
            "XBrainLab.ui.panels.training.sidebar.get_command_capability",
            return_value=MagicMock(enabled=True),
        ),
        patch.object(
            sidebar,
            "_training_resource_context",
            return_value={
                "training_option": SimpleNamespace(bs=256),
                "model_holder": SimpleNamespace(target_model=EEGNet),
            },
        ),
        patch.object(
            sidebar,
            "_training_resource_check_result",
            return_value=warning_result,
        ),
        patch(
            "XBrainLab.ui.panels.training.sidebar.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question,
        patch(
            "XBrainLab.ui.panels.training.sidebar.execute_application_command",
        ) as execute,
    ):
        sidebar.start_training_ui_action()

    execute.assert_not_called()
    message = question.call_args.args[2]
    assert "Model: EEGNet" in message
    assert "Batch size: 256" in message
    assert "Estimated VRAM required: 7.0 GB" in message
    assert "Available VRAM: 8.0 GB" in message
    assert "Risk level: Warning" in message


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


def test_on_training_stopped(sidebar):
    sidebar.on_training_stopped()
    # Button should revert to "Start Training" (primary color)
    # Checking text might differ based on UI implementation details,
    # but we can check if it's enabled and set to primary/success style logic if verified.
    assert sidebar.btn_start.text() == "Start Training"
    assert sidebar.btn_start.isEnabled() is True
