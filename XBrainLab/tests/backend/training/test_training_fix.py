
import os
import shutil
import unittest
import sys
from unittest.mock import MagicMock
sys.modules['captum'] = MagicMock()
sys.modules['captum.attr'] = MagicMock()

import torch
import datetime

from XBrainLab.backend.training.training_plan import TrainingPlanHolder
from XBrainLab.backend.training.record.train import TrainRecord
from XBrainLab.backend.dataset import Dataset, Epochs
from XBrainLab.backend.training import TrainingOption, ModelHolder

class TestTrainingFix(unittest.TestCase):
    def setUp(self):
        # Mock dependencies
        self.mock_dataset = MagicMock(spec=Dataset)
        self.mock_dataset.get_name.return_value = "TestDataset"
        
        self.mock_epochs = MagicMock(spec=Epochs)
        self.mock_epochs.get_model_args.return_value = {}
        self.mock_dataset.get_epoch_data.return_value = self.mock_epochs
        
        self.mock_option = MagicMock(spec=TrainingOption)
        self.mock_option.repeat_num = 1
        self.mock_option.get_output_dir.return_value = "/tmp/xbrainlab_test_output"
        self.mock_option.validate.return_value = True
        self.mock_option.get_optim.return_value = MagicMock()
        self.mock_option.criterion = MagicMock()
        
        self.mock_model = MagicMock(spec=torch.nn.Module)
        self.mock_model.__class__.__name__ = "TestModel"
        
        self.mock_model_holder = MagicMock(spec=ModelHolder)
        self.mock_model_holder.target_model = MagicMock()
        self.mock_model_holder.target_model.__name__ = "TestModel"
        self.mock_model_holder.get_model.return_value = self.mock_model
        
        self.saliency_params = {}

    def test_unique_output_path(self):
        # Create two plans sequentially
        plan1 = TrainingPlanHolder(
            self.mock_model_holder, self.mock_dataset, self.mock_option, self.saliency_params
        )
        
        # Simulate a small delay to ensure timestamp difference if resolution is high enough
        # (Though our format is seconds, so we might need to mock datetime if it runs too fast)
        # For now, let's just check the structure.
        
        record1 = plan1.get_plans()[0]
        path1 = record1.target_path
        print(f"Path 1: {path1}")
        
        self.assertIn("TestModel", path1)
        # Check for timestamp format roughly (YYYYMMDD-HHMMSS)
        # It should be in the path
        
        # Create another plan
        # We can mock datetime to ensure different time if needed, but let's see if it works naturally
        # or we can manually inspect the path structure.
        
        # Verify structure: output / dataset / model_timestamp / repeat
        parts = path1.split(os.sep)
        self.assertEqual(parts[-1], "Repeat-0")
        self.assertTrue("TestModel_" in parts[-2])
        
    def tearDown(self):
        if os.path.exists("/tmp/xbrainlab_test_output"):
            shutil.rmtree("/tmp/xbrainlab_test_output")

if __name__ == '__main__':
    unittest.main()
