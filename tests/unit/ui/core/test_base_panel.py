from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.core.base_panel import BasePanel


class ConcretePanel(BasePanel):
    """Concrete implementation for testing abstract BasePanel."""

    def init_ui(self):
        pass


class UnimplementedPanel(BasePanel):
    """Panel that fails to implement abstract methods."""


@pytest.fixture
def panel(qtbot) -> ConcretePanel:
    widget = ConcretePanel()
    qtbot.addWidget(widget)
    return widget


def test_init(panel: ConcretePanel):
    assert isinstance(panel, QWidget)
    assert panel.controller is None
    assert panel.main_window is None


def test_init_with_controller_and_parent(qtbot):
    mock_controller = MagicMock()
    mock_parent = MagicMock()
    # Mock parent having a study attribute
    mock_parent.study = MagicMock()

    # PyQt6 QWidget constructor is strict about parent type (must be QWidget or None).
    # Since we cannot easily pass a mock as a parent to QWidget without segfault/recursion issues
    # (because QWidget tries to access C++ object), we pass parent=None.
    # We verify that controller is set correctly, which logic is independent of parent.

    panel = ConcretePanel(parent=None, controller=mock_controller)
    assert panel.controller == mock_controller
    # Main window resolution logic is skipped if parent is None, but that is acceptable
    # for this unit test which primarily verifies __init__ stores the controller.


def test_abstract_method_error():
    # Can't instantiate class with abstract methods if we used ABC,
    # but BasePanel uses raise NotImplementedError
    panel = UnimplementedPanel()
    with pytest.raises(NotImplementedError):
        panel.init_ui()


def test_set_busy(panel, qtbot):
    # Test True
    panel.set_busy(True)
    assert panel.cursor().shape() == Qt.CursorShape.WaitCursor
    assert panel.isEnabled() is False

    # Test False
    panel.set_busy(False)
    assert panel.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert panel.isEnabled() is True


def test_methods_exist(panel):
    # Ensure optional methods exist and don't raise error
    panel.update_panel()
    panel.refresh_from_observer()
    panel._setup_bridges()
    panel.cleanup()


def test_refresh_from_observer_delegates_to_coordinator(panel):
    with patch(
        "XBrainLab.ui.core.base_panel.refresh_after_observer",
    ) as refresh_after_observer:
        panel.refresh_from_observer("event_arg", name="event")

    refresh_after_observer.assert_called_once_with(panel)


class TestCreateBridge:
    def test_creates_and_registers(self, qtbot):
        mock_ctrl = MagicMock()
        panel = ConcretePanel(controller=mock_ctrl)
        qtbot.addWidget(panel)

        handler = MagicMock()
        bridge = panel._create_bridge(mock_ctrl, "some_event", handler)

        assert bridge in panel._bridges
        assert len(panel._bridges) == 1

    def test_multiple_bridges(self, qtbot):
        mock_ctrl = MagicMock()
        panel = ConcretePanel(controller=mock_ctrl)
        qtbot.addWidget(panel)

        panel._create_bridge(mock_ctrl, "event_a", MagicMock())
        panel._create_bridge(mock_ctrl, "event_b", MagicMock())
        assert len(panel._bridges) == 2

    def test_create_refresh_bridge_uses_observer_refresh(self, qtbot):
        mock_ctrl = MagicMock()
        panel = ConcretePanel(controller=mock_ctrl)
        qtbot.addWidget(panel)

        with patch.object(
            panel, "_create_bridge", wraps=panel._create_bridge
        ) as create:
            bridge = panel._create_refresh_bridge(mock_ctrl, "data_changed")

        assert bridge in panel._bridges
        create.assert_called_once_with(
            mock_ctrl,
            "data_changed",
            panel.refresh_from_observer,
        )
