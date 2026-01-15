import sys
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QWidget
from XBrainLab.ui.training.panel import TrainingPanel

# Mock Study
class MockStudy:
    def __init__(self):
        self.datasets = []
        self.model_holder = None
        self.training_option = None
        self.trainer = MagicMock()
        self.trainer.is_running.return_value = False
        self.loaded_data_list = []
        self.preprocessed_data_list = []
        self.epoch_data = None
        self.is_training = lambda: False

class TestTrainingPanelLock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    @patch('XBrainLab.ui.training.panel.AggregateInfoPanel')
    def setUp(self, MockInfoPanel):
        # Make the mock return a real QWidget so addWidget accepts it
        fake_panel = QWidget()
        fake_panel.update_info = MagicMock()
        MockInfoPanel.return_value = fake_panel
        
        self.mock_window = QWidget() # Use real widget for parent
        self.mock_window.study = MockStudy()
        self.panel = TrainingPanel(self.mock_window)

    def test_start_button_locked_initially(self):
        # Initially, no config, so button should be disabled
        self.assertFalse(self.panel.btn_start.isEnabled())
        self.assertIn("Please configure", self.panel.btn_start.toolTip())

    def test_start_button_unlocks_when_ready(self):
        # Set configurations
        self.panel.study.datasets = ["dataset1"]
        self.panel.study.model_holder = "model"
        self.panel.study.training_option = "option"
        
        # Trigger check
        self.panel.check_ready_to_train()
        
        self.assertTrue(self.panel.btn_start.isEnabled())
        self.assertEqual(self.panel.btn_start.toolTip(), "Start Training")

    def test_start_button_remains_locked_if_partial_config(self):
        # Only datasets
        self.panel.study.datasets = ["dataset1"]
        self.panel.check_ready_to_train()
        self.assertFalse(self.panel.btn_start.isEnabled())
        
        # Add model
        self.panel.study.model_holder = "model"
        self.panel.check_ready_to_train()
        self.assertFalse(self.panel.btn_start.isEnabled())
        
        # Add option -> Ready
        self.panel.study.training_option = "option"
        self.panel.check_ready_to_train()
        self.assertTrue(self.panel.btn_start.isEnabled())

    def test_training_finished_reenables_button(self):
        # Setup ready state
        self.panel.study.datasets = ["dataset1"]
        self.panel.study.model_holder = "model"
        self.panel.study.training_option = "option"
        self.panel.check_ready_to_train()
        self.assertTrue(self.panel.btn_start.isEnabled())
        
        # Simulate start (disable)
        self.panel.btn_start.setEnabled(False)
        self.assertFalse(self.panel.btn_start.isEnabled())
        
        # Simulate finish
        self.panel.training_finished()
        
        # Should be enabled again
        self.assertTrue(self.panel.btn_start.isEnabled())

    def test_start_button_remains_enabled_for_queueing(self):
        # Setup ready state
        self.panel.study.datasets = ["dataset1"]
        self.panel.study.model_holder = "model"
        self.panel.study.training_option = "option"
        self.panel.check_ready_to_train()
        
        # Start training
        # We need to mock generate_plan to avoid errors
        self.panel.study.generate_plan = MagicMock()
        self.panel.study.trainer.get_training_plan_holders.return_value = [MagicMock()] # Mock valid plan
        
        # Mock dataset len check
        mock_holder = self.panel.study.trainer.get_training_plan_holders.return_value[0]
        mock_holder.get_dataset.return_value.get_train_len.return_value = 100
        
        self.panel.start_training()
        
        # Button should remain enabled
        self.assertTrue(self.panel.btn_start.isEnabled())
        
        # Simulate running
        self.panel.study.trainer.is_running.return_value = True
        
        # Click again (queueing)
        self.panel.start_training()
        
        # Button should still be enabled
        self.assertTrue(self.panel.btn_start.isEnabled())

if __name__ == '__main__':
    unittest.main()
