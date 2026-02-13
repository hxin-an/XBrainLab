from unittest.mock import MagicMock

import pytest

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
    assert sidebar.btn_split is not None
    assert sidebar.btn_model is not None
    assert sidebar.btn_setting is not None
    assert sidebar.btn_start is not None


def test_on_start_clicked(sidebar):
    # Mock readiness
    sidebar.controller.validate_ready.return_value = True

    # Test Start
    sidebar.controller.is_training.return_value = False
    sidebar.start_training_ui_action()
    sidebar.controller.start_training.assert_called_once()

    # Test Stop is separate method: stop_training
    # But checking start_training_ui_action logic:
    # It calls start_training if not running.

    sidebar.controller.start_training.reset_mock()
    sidebar.controller.is_training.return_value = True
    sidebar.start_training_ui_action()
    sidebar.controller.start_training.assert_not_called()
    # It acts as idempotent or safe start?
    # Logic: if not self.controller.is_training(): start()


def test_stop_training(sidebar):
    sidebar.controller.is_training.return_value = True
    sidebar.stop_training()
    sidebar.controller.stop_training.assert_called_once()


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
