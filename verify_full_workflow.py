import sys
import os
import numpy as np
import scipy.io

# Add project root
sys.path.append(os.getcwd())

from XBrainLab.study import Study
from XBrainLab.load_data import RawDataLoader
from XBrainLab.ui_pyqt.load_data.gdf import load_gdf_file
from XBrainLab.preprocessor.time_epoch import TimeEpoch
from XBrainLab.preprocessor.filtering import Filtering
from XBrainLab.dataset.data_splitter import DataSplittingConfig
from XBrainLab.training.trainer import Trainer
from XBrainLab.training.model_holder import ModelHolder

def verify_full_workflow():
    print("=== Starting Full Workflow Verification ===")
    
    # 1. Initialize Study
    study = Study()
    print("[OK] Study initialized")
    
    # 2. Load Data
    data_path = "/mnt/data/lab/XBrainlab_with_agent/test_data_small/A01T.gdf"
    if not os.path.exists(data_path):
        print(f"[FAIL] Data file not found: {data_path}")
        return
        
    raw = load_gdf_file(data_path)
    if not raw:
        print("[FAIL] Failed to load GDF")
        return
    
    loader = RawDataLoader()
    loader.append(raw)
    loader.apply(study)
    print(f"[OK] Loaded data. Events: {len(raw.get_event_list()[0])}")

    # 3. Preprocess: Filter
    print("--- Preprocessing: Filtering ---")
    try:
        # Use backend directly
        filter_proc = Filtering(study.preprocessed_data_list)
        study.preprocessed_data_list = filter_proc.data_preprocess(1.0, 40.0)
        print("[OK] Filtering done")
    except Exception as e:
        print(f"[FAIL] Filtering failed: {e}")
        return

    # 4. Preprocess: Epoching
    print("--- Preprocessing: Epoching ---")
    try:
        # Epoch on Left (769) and Right (770)
        target_events = ['769', '770']
        epoch_proc = TimeEpoch(study.preprocessed_data_list)
        study.preprocessed_data_list = epoch_proc.data_preprocess(
            baseline=(-0.2, 0),
            selected_event_names=target_events,
            tmin=-0.2,
            tmax=0.8
        )
        
        n_epochs = len(study.preprocessed_data_list[0].get_mne())
        print(f"[OK] Epoching done. Epochs: {n_epochs}")
        
        if n_epochs <= 1:
            print("[FAIL] Epoching resulted in <= 1 epoch!")
            return
            
    except Exception as e:
        print(f"[FAIL] Epoching failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 5. Dataset Splitting
    print("--- Dataset Splitting ---")
    try:
        from XBrainLab.dataset import Dataset
        from XBrainLab.dataset.epochs import Epochs
        from XBrainLab.dataset.data_splitter import DataSplitter
        from XBrainLab.dataset.option import TrainingType, SplitByType, SplitUnit, ValSplitByType
        
        # Clear existing
        study.dataset_list = []
        
        # Create config (e.g., 80/20 split)
        # Test Splitter: 20% by Trial
        test_splitter = DataSplitter(
            split_type=SplitByType.TRIAL,
            value_var="0.2",
            split_unit=SplitUnit.RATIO
        )
        
        config = DataSplittingConfig(
            train_type=TrainingType.IND,
            is_cross_validation=False,
            val_splitter_list=[], # No validation set
            test_splitter_list=[test_splitter]
        )
        
        # Wrap Raw objects (which contain MNE Epochs) into XBrainLab Epochs object
        epochs_obj = Epochs(study.preprocessed_data_list)
        
        ds = Dataset(epochs_obj, config)
            
        # Apply split manually for verification
        n_total = epochs_obj.get_data_length()
        indices = np.arange(n_total)
        np.random.shuffle(indices)
        n_train = int(n_total * 0.8)
        
        train_idx = indices[:n_train]
        test_idx = indices[n_train:]
        
        train_mask = np.zeros(n_total, dtype=bool)
        train_mask[train_idx] = True
        
        test_mask = np.zeros(n_total, dtype=bool)
        test_mask[test_idx] = True
        
        ds.train_mask = train_mask
        ds.test_mask = test_mask
        ds.remaining_mask = np.zeros(n_total, dtype=bool) # All used
        
        study.dataset_list.append(ds)
            
        print(f"[OK] Split done. Train: {study.dataset_list[0].get_train_len()}, Test: {study.dataset_list[0].get_test_len()}")
        
    except Exception as e:
        print(f"[FAIL] Splitting failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 6. Model Selection & Training
    print("--- Training ---")
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
        from XBrainLab.training.trainer import Trainer
        from XBrainLab.training.model_holder import ModelHolder
        from XBrainLab.training.training_plan import TrainingPlanHolder
        from XBrainLab.training.option import TrainingOption, TRAINING_EVALUATION
        
        # Define Dummy Model
        class DummyModel(nn.Module):
            def __init__(self, n_classes, channels, samples, sfreq):
                super().__init__()
                self.fc = nn.Linear(channels * samples, n_classes)
            def forward(self, x):
                x = x.view(x.size(0), -1)
                return self.fc(x)
        
        # Create ModelHolder
        # Model args are passed dynamically by TrainingPlanHolder based on dataset
        model_holder = ModelHolder(
            target_model=DummyModel,
            model_params_map={}
        )
        
        # Create TrainingOption
        train_option = TrainingOption(
            output_dir="/tmp/xbrainlab_test",
            optim=optim.Adam,
            optim_params={'weight_decay': 0.01},
            use_cpu=True,
            gpu_idx=None,
            epoch=1,
            bs=16,
            lr=0.001,
            checkpoint_epoch=0,
            evaluation_option=TRAINING_EVALUATION.LAST_EPOCH,
            repeat_num=1
        )
        
        # Create TrainingPlanHolder
        # We need a list of datasets (usually one per plan)
        # Here we use the first dataset
        dataset = study.dataset_list[0]
        
        plan_holder = TrainingPlanHolder(
            model_holder=model_holder,
            dataset=dataset,
            option=train_option,
            saliency_params={}
        )
        
        # Create Trainer
        trainer = Trainer([plan_holder])
        print("[OK] Trainer initialized with plan")
        
        # Run one step of training (optional, but good for verification)
        print("Running 1 epoch of training...")
        trainer.run(interact=False)
        print("[OK] Training run complete")

    except Exception as e:
        print(f"[FAIL] Training failed: {e}")
        import traceback
        traceback.print_exc()
        return

    print("=== Verification Complete: SUCCESS ===")

if __name__ == "__main__":
    verify_full_workflow()
