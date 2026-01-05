import pytest
import numpy as np
import torch
from unittest.mock import MagicMock, patch

from XBrainLab.backend.dataset import DatasetGenerator
from XBrainLab.backend.training import Trainer, TrainingPlanHolder, ModelHolder, TrainingOption
from XBrainLab.backend.model_base import EEGNet
from XBrainLab.backend.visualization import VisualizerType

def test_pipeline_integration():
    # 1. Setup Mock Data and Environment
    # Mock torch.cuda to avoid GPU requirement
    with patch('torch.cuda.is_available', return_value=False), \
         patch('torch.cuda.device_count', return_value=0):
        
        # 2. Create Dataset Generator (Mocking data loading)
        # We'll use synthetic data instead of loading from files
        n_subjects = 2
        n_sessions = 2
        n_trials = 10
        n_channels = 4
        n_samples = 512
        n_classes = 2
        
        # Mock DatasetGenerator's internal data structures if possible, 
        # or just mock the output of get_dataset
        
        # Let's mock the dataset object directly to avoid complex file I/O mocking
        dataset_mock = MagicMock()
        
        # Mock dataloaders
        train_loader = MagicMock()
        val_loader = MagicMock()
        test_loader = MagicMock()
        
        # Make dataloaders iterable yielding (data, label)
        # Batch size 2
        batch_data = torch.randn(2, 1, n_channels, n_samples)
        batch_label = torch.randint(0, n_classes, (2,))
        
        train_loader.__iter__.return_value = iter([(batch_data, batch_label)])
        val_loader.__iter__.return_value = iter([(batch_data, batch_label)])
        test_loader.__iter__.return_value = iter([(batch_data, batch_label)])
        
        # Mock len()
        train_loader.__len__.return_value = 1
        val_loader.__len__.return_value = 1
        test_loader.__len__.return_value = 1
        
        # Mock get_training_data, get_val_data, get_test_data to return (X, y)
        # X needs to be numpy array, y needs to be numpy array
        mock_X = np.random.randn(n_trials, n_channels, n_samples)
        mock_y = np.random.randint(0, n_classes, n_trials)
        
        dataset_mock.get_training_data.return_value = (mock_X, mock_y)
        dataset_mock.get_val_data.return_value = (mock_X, mock_y)
        dataset_mock.get_test_data.return_value = (mock_X, mock_y)
        
        # 3. Setup Model Holder
        # Use a real model class but small parameters
        model_params = {
            'n_classes': n_classes,
            'channels': n_channels,
            'samples': n_samples,
            'sfreq': 128
        }
        
        # Mock get_epoch_data().get_model_args() used in TrainingPlanHolder.__init__ loop
        epoch_data_mock = MagicMock()
        epoch_data_mock.get_model_args.return_value = model_params
        dataset_mock.get_epoch_data.return_value = epoch_data_mock
        
        # We need to mock torch.load if ModelHolder tries to load weights, 
        # but here we init from scratch.
        # ModelHolder expects a class, params map, and weight path (optional)
        # Pass empty dict for params map because get_model_args provides them
        holder = ModelHolder(EEGNet, {}, None)
        
        # 4. Setup Training Option
        option_args = {
            'output_dir': 'test_output',
            'optim': torch.optim.Adam,
            'optim_params': {}, # lr is handled by 'lr' argument
            'use_cpu': True,
            'gpu_idx': None,
            'epoch': 1, # Short training
            'bs': 2,
            'lr': 0.001,
            'checkpoint_epoch': 1,
            'evaluation_option': 'TRAINING_EVALUATION.VAL_LOSS', 
            'repeat_num': 1
        }
        from XBrainLab.backend.training import TRAINING_EVALUATION
        option_args['evaluation_option'] = TRAINING_EVALUATION.VAL_LOSS
        
        option = TrainingOption(**option_args)
        
        # 5. Setup Training Plan
        saliency_params = {
            'SmoothGrad': {'nt_samples': 1, 'stdevs': 0.1},
            'SmoothGrad_Squared': {'nt_samples': 1, 'stdevs': 0.1},
            'VarGrad': {'nt_samples': 1, 'stdevs': 0.1}
        }
        
        # 6. Run Training via Trainer
        
        # Mock threading to run synchronously or just call job() directly
        # Trainer.run() starts a thread. Trainer.job() runs the logic.
        # Let's call job() directly to avoid threading complexity in test
        
        # We need to patch 'plt.savefig' and 'torch.save' to avoid file writes
        # Also patch validate_type to skip type checking for mocks
        with patch('matplotlib.pyplot.savefig'), \
             patch('torch.save'), \
             patch('numpy.savetxt'), \
             patch('os.makedirs'), \
             patch('XBrainLab.training.training_plan.validate_type'):
            
            plan_holder = TrainingPlanHolder(holder, dataset_mock, option, saliency_params)
            trainer = Trainer([plan_holder])
            trainer.job()
            
        # 7. Verify Results
        # Check if training record exists
        assert len(plan_holder.train_record_list) == 1
        record = plan_holder.train_record_list[0]
        
        # Check if metrics are recorded
        # TrainRecord stores metrics in .train dictionary with keys from RecordKey
        # We need to import RecordKey or check string keys if they are strings
        from XBrainLab.backend.training.record import RecordKey
        assert RecordKey.LOSS in record.train
        assert RecordKey.ACC in record.train
        assert RecordKey.AUC in record.train
        
        # Check if evaluation record exists
        assert record.eval_record is not None
        
        # Check if model state dict is saved (mocked)
        # We can check if torch.save was called
        
        print("Pipeline integration test passed!")

if __name__ == "__main__":
    test_pipeline_integration()
