import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication, QGroupBox, QWidget

from XBrainLab.ui.training.panel import TrainingPanel


class TestTrainingPanelLock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    # Patch modules referenced during Panel init
    @patch("XBrainLab.ui.training.panel.AggregateInfoPanel")
    def setUp(self, MockInfoPanel):
        # Info Panel Mock
        fake_panel = QGroupBox()
        MockInfoPanel.return_value = fake_panel

        # Controller Mock
        self.mock_controller = MagicMock()
        self.mock_controller.is_training.return_value = False

        # Default state: Not ready
        self.mock_controller.validate_ready.return_value = False
        self.mock_controller.get_missing_requirements.return_value = ["Data", "Model"]
        self.mock_controller.has_datasets.return_value = (
            False  # Keep for safety if referenced elsewhere
        )
        self.mock_controller.get_model_holder.return_value = None
        self.mock_controller.get_training_option.return_value = None
        self.mock_controller.get_formatted_history.return_value = []

        # Mock Window
        self.mock_window = QWidget()
        self.mock_window.study = MagicMock()
        self.mock_window.study.get_controller.return_value = self.mock_controller

        self.panel = TrainingPanel(self.mock_window)

    def test_start_button_locked_initially(self):
        # Initially, no config
        self.panel.check_ready_to_train()
        self.assertFalse(self.panel.btn_start.isEnabled())
        self.assertIn("Please configure", self.panel.btn_start.toolTip())

    def test_start_button_unlocks_when_ready(self):
        # Set configurations
        self.mock_controller.validate_ready.return_value = True
        self.mock_controller.get_missing_requirements.return_value = []

        # Trigger check
        self.panel.check_ready_to_train()

        self.assertTrue(self.panel.btn_start.isEnabled())
        self.assertEqual(self.panel.btn_start.toolTip(), "Start Training")

    def test_start_button_remains_locked_if_partial_config(self):
        # Partial
        self.mock_controller.validate_ready.return_value = False
        self.mock_controller.get_missing_requirements.return_value = ["Model"]

        self.panel.check_ready_to_train()
        self.assertFalse(self.panel.btn_start.isEnabled())

        # Check tooltips if needed, but enabled state is primary

        # Ready
        self.mock_controller.validate_ready.return_value = True
        self.mock_controller.get_missing_requirements.return_value = []

        self.panel.check_ready_to_train()
        self.assertTrue(self.panel.btn_start.isEnabled())

    def test_training_finished_reenables_button(self):
        # Setup ready state
        self.mock_controller.validate_ready.return_value = True
        self.mock_controller.get_missing_requirements.return_value = []

        self.panel.check_ready_to_train()
        self.assertTrue(self.panel.btn_start.isEnabled())

        # Simulate start (disable) calling manually or via logic
        self.panel.btn_start.setEnabled(False)
        self.assertFalse(self.panel.btn_start.isEnabled())

        # Simulate finish
        self.panel.training_finished()

        # Should be enabled again
        self.assertTrue(self.panel.btn_start.isEnabled())

    def test_start_button_remains_enabled_for_queueing(self):
        # Setup ready state
        self.mock_controller.validate_ready.return_value = True
        self.panel.check_ready_to_train()

        # Start training
        self.mock_controller.is_training.side_effect = [False, True]

        # Mock plan generation success using controller methods check?
        # start_training calls controller.start_training()

        # We need to mock QTimer for start_training
        self.panel.timer = MagicMock()

        self.panel.start_training()

        # Button should remain enabled (if queueing is allowed/logic dictates)
        # Original test said: "Button should remain enabled"
        # Let's check panel.py start_training logic:
        # It calls btn_stop.setEnabled(True)
        # It calls check_ready_to_train() at the end.
        # check_ready_to_train sets btn_start.setEnabled(True) if ready.

        self.assertTrue(self.panel.btn_start.isEnabled())

        # Simulate running
        self.mock_controller.is_training.return_value = True
        self.mock_controller.is_training.side_effect = None

        # Click again (queueing)
        self.panel.start_training()

        # Button should still be enabled
        self.assertTrue(self.panel.btn_start.isEnabled())


if __name__ == "__main__":
    unittest.main()
