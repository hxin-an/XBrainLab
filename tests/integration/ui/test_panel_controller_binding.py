"""
Integration tests ensuring UI Panels correctly respond to Controller events.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.controller.training_controller import TrainingController
from XBrainLab.backend.study import Study
from XBrainLab.ui.panels.training.panel import TrainingPanel

# Mocking the TrainingPanel dependencies is tricky because it's complex.
# We'll rely on the existing codebase's structure where panels accept 'parent' which has 'study'.


class TestPanelControllerBinding:
    """Test UI <-> Controller wiring."""

    @pytest.fixture
    def mock_study(self):
        return MagicMock(spec=Study)

    @pytest.fixture
    def training_panel(self, qtbot, mock_study):
        parent = QWidget()
        parent.study = mock_study

        # Setup specific returns for get_controller
        training_ctrl = MagicMock(spec=TrainingController)
        dataset_ctrl = MagicMock()  # Spec not strictly needed for basic checks

        def get_ctrl_side_effect(name):
            if name == "training":
                return training_ctrl
            if name == "dataset":
                return dataset_ctrl
            return MagicMock()

        mock_study.get_controller.side_effect = get_ctrl_side_effect

        # Initialize
        panel = TrainingPanel(parent=parent)
        qtbot.addWidget(panel)
        return panel

    def test_training_start_event_updates_ui(self, training_panel, mock_study):
        """Test 'training_started' event updates sidebar."""
        controller = training_panel.controller

        # Spy on sidebar
        training_panel.sidebar = MagicMock()

        # Simulate 'training_started'
        # The bridge connects to _on_training_started
        # We manually trigger the callback to verify logic,
        # NOT the Qt signal capability (Qtbot handles that but mocking signal emission is complex)

        training_panel._on_training_started()

        # Verify sidebar was notified
        training_panel.sidebar.on_training_started.assert_called_once()
        assert "started" in training_panel.log_text.toPlainText()

    def test_training_update_event_refreshes_graph(self, training_panel):
        """Test 'training_updated' event failsafe."""
        # This test ensures that receiving the event doesn't crash the UI
        # even if data is empty.
        try:
            training_panel.update_loop()  # Correct method name
        except Exception as e:
            pytest.fail(f"UI crashed on training update: {e}")

    def test_controller_resolution(self, training_panel, mock_study):
        """Verify panel correctly resolved the controller from study."""
        assert training_panel.controller is not None
        mock_study.get_controller.assert_any_call("training")
