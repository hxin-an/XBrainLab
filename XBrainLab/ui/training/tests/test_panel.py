
import pytest
from PyQt6.QtWidgets import QMainWindow
from unittest.mock import MagicMock, patch
from XBrainLab.ui.training.panel import TrainingPanel
from XBrainLab.backend.study import Study

class TestTrainingPanel:
    @pytest.fixture
    def panel(self, qtbot):
        # Mock MainWindow and Study
        main_window = MagicMock(spec=QMainWindow)
        main_window.study = MagicMock(spec=Study)
        
        # We need to patch the imports in panel.py because they might be instantiated
        # But for now let's just instantiate the panel
        panel = TrainingPanel(main_window)
        qtbot.addWidget(panel)
        return panel

    def test_select_model_success(self, panel):
        # Mock ModelSelectionWindow to return a dummy result
        mock_result = MagicMock()
        mock_result.target_model.__name__ = "DummyModel"
        
        # Configure study mock to have model_holder
        panel.study.model_holder = mock_result
        
        with patch('XBrainLab.ui.training.panel.ModelSelectionWindow') as MockWindow:
            instance = MockWindow.return_value
            instance.exec.return_value = True
            instance.get_result.return_value = mock_result
            
            # Mock QMessageBox to avoid blocking
            with patch('PyQt6.QtWidgets.QMessageBox.information'):
                panel.select_model()
            
            # Verify study update
            panel.study.set_model_holder.assert_called_once_with(mock_result)

    def test_training_setting_success(self, panel):
        mock_result = MagicMock()
        
        with patch('XBrainLab.ui.training.panel.TrainingSettingWindow') as MockWindow:
            instance = MockWindow.return_value
            instance.exec.return_value = True
            instance.get_result.return_value = mock_result
            
            with patch('PyQt6.QtWidgets.QMessageBox.information'):
                panel.training_setting()
                
            panel.study.set_training_option.assert_called_once_with(mock_result)

    def test_test_only_setting_success(self, panel):
        mock_result = MagicMock()
        
        with patch('XBrainLab.ui.training.panel.TestOnlySettingWindow') as MockWindow:
            instance = MockWindow.return_value
            instance.exec.return_value = True
            instance.get_result.return_value = mock_result
            
            with patch('PyQt6.QtWidgets.QMessageBox.information'):
                panel.test_only_setting()
                
            panel.study.set_training_option.assert_called_once_with(mock_result)

    def test_start_training_success(self, panel):
        # Mock trainer and plan holders
        mock_trainer = MagicMock()
        mock_trainer.get_training_plan_holders.return_value = [MagicMock()]
        mock_trainer.is_running.return_value = False
        panel.study.trainer = mock_trainer
        
        # Mock model holder for UI update
        panel.study.model_holder = MagicMock()
        mock_model = MagicMock()
        mock_model.__name__ = "TestModel"
        panel.study.model_holder.target_model = mock_model
        
        # Mock QTimer
        panel.timer = MagicMock()
        
        # Call start_training
        panel.start_training()
        
        # Verify trainer.run called
        mock_trainer.run.assert_called_once_with(interact=True)
        panel.timer.start.assert_called_once()

    def test_generate_plan(self, panel):
        with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            panel.generate_plan()
            
            # Verify Study.generate_plan is called (NOT create_training_plan)
            panel.study.generate_plan.assert_called_once()
            mock_info.assert_called_once()

    def test_split_data(self, panel):
        # Mock epoch_data
        panel.study.epoch_data = MagicMock()
        panel.study.loaded_data_list = [MagicMock()] # Ensure loaded data exists
        
        # Mock DataSplittingSettingWindow
        mock_generator = MagicMock()
        
        with patch('XBrainLab.ui.training.panel.DataSplittingSettingWindow') as MockWindow:
            instance = MockWindow.return_value
            instance.exec.return_value = True
            instance.get_result.return_value = mock_generator
            
            with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
                panel.split_data()
                
                # Verify generator.apply is called
                mock_generator.apply.assert_called_once_with(panel.study)
                mock_info.assert_called_once()
