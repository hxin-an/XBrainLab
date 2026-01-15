import os
import pytest
import numpy as np
import torch
from unittest.mock import patch

from XBrainLab.backend.load_data.raw_data_loader import load_gdf_file
from XBrainLab.backend.preprocessor import Filtering, Normalize
from XBrainLab.backend.dataset import DatasetGenerator, DataSplittingConfig, TrainingType
from XBrainLab.backend.training import ModelHolder, TrainingOption, Trainer, TrainingPlanHolder, TRAINING_EVALUATION
from XBrainLab.backend.model_base import EEGNet
from XBrainLab.backend.study import Study

# Path to real test data
TEST_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
GDF_FILE = os.path.join(TEST_DATA_DIR, 'A01T.gdf')
from XBrainLab.backend.dataset.data_splitter import DataSplitter
from XBrainLab.backend.dataset.option import SplitByType, ValSplitByType, SplitUnit
from XBrainLab.backend.preprocessor import Filtering, Normalize, TimeEpoch

@pytest.mark.skipif(not os.path.exists(GDF_FILE), reason="Real test data not found")
def test_real_data_pipeline():
    """
    Test the full pipeline with REAL data (A01T.gdf).
    This verifies that:
    1. Real GDF files can be loaded.
    2. Preprocessing works on real data.
    3. Dataset generation works with real epochs.
    4. Training loop runs successfully with real data shapes.
    """
    print(f"Testing with real data: {GDF_FILE}")
    
    # 1. Load Data
    study = Study()
    # loader = study.get_raw_data_loader() # Not needed if we load directly
    raw = load_gdf_file(GDF_FILE)
    assert raw is not None
    raw_list = [raw]
    study.set_loaded_data_list(raw_list)
    
    # 2. Preprocess
    # Filter: 4-38 Hz
    study.preprocess(Filtering, l_freq=4, h_freq=38)
    # Normalize: Z-Score
    study.preprocess(Normalize, norm='z score')
    
    # Epoching: TimeEpoch
    # Get the actual object being processed (since Study deepcopies input)
    processed_raw = study.preprocessed_data_list[0]
    
    # Get available events
    events, event_id = processed_raw.get_event_list()
    print(f"Original events shape: {events.shape}")
    
    # Deduplicate events based on time sample (column 0)
    # Keep the first occurrence
    _, unique_indices = np.unique(events[:, 0], return_index=True)
    # Sort indices to preserve order
    unique_indices = np.sort(unique_indices)
    events = events[unique_indices]
    print(f"Deduplicated events shape: {events.shape}")
    
    # Verify no duplicates
    if len(np.unique(events[:, 0])) != len(events):
        print("WARNING: Duplicates still exist!")
    
    event_names = list(event_id.keys())
    print(f"Events found: {event_names}")
    
    # Filter event_names to only include those present in the deduplicated events
    present_event_ids = np.unique(events[:, -1])
    filtered_event_names = [
        name for name, eid in event_id.items() 
        if eid in present_event_ids
    ]
    print(f"Filtered events: {filtered_event_names}")
    
    # Patch get_raw_event_list on the processed object
    with patch.object(processed_raw, 'get_raw_event_list', return_value=(events, event_id)):
        study.preprocess(
            TimeEpoch, 
            baseline=None, 
            selected_event_names=filtered_event_names,
            tmin=0, 
            tmax=4
        )
    
    # 3. Dataset Generation
    # Use Individual Training Type
    val_splitter = DataSplitter(ValSplitByType.TRIAL, "0.2", SplitUnit.RATIO)
    test_splitter = DataSplitter(SplitByType.TRIAL, "0.2", SplitUnit.RATIO)
    
    config = DataSplittingConfig(
        train_type=TrainingType.IND,
        is_cross_validation=False,
        val_splitter_list=[val_splitter], 
        test_splitter_list=[test_splitter] 
    )
    generator = study.get_datasets_generator(config)
    datasets = generator.generate()
    assert len(datasets) > 0
    study.set_datasets(datasets)
    
    # 4. Training Setup
    # Model: EEGNet
    # Note: EEGNet requires specific input shape. 
    # Real data might have different channels/samples.
    # We need to get these from the dataset.
    
    # Get one dataset to inspect shape
    dataset = datasets[0]
    # We can get shape from epoch_data inside dataset or study
    # study.epoch_data is the source
    # 4. Model Setup
    # Get input shape from data
    n_channels = len(study.epoch_data.get_channel_names())
    n_samples = study.epoch_data.get_data().shape[-1]
    n_classes = len(study.epoch_data.event_id)
    
    print(f"Data Shape: Channels={n_channels}, Samples={n_samples}, Classes={n_classes}")

    # Model params are provided by dataset automatically via ModelHolder.get_model(args)
    # args include n_classes, channels, samples, sfreq
    model_params = {}
    
    holder = ModelHolder(EEGNet, model_params, None)
    study.set_model_holder(holder)
    
    # Training Option
    option = TrainingOption(
        output_dir='test_real_output',
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True, # Force CPU for testing
        gpu_idx=None,
        epoch=1, # Run 1 epoch for speed
        bs=16,
        lr=0.001,
        checkpoint_epoch=1,
        evaluation_option=TRAINING_EVALUATION.TEST_ACC,
        repeat_num=1
    )
    study.set_training_option(option)
    
    # Saliency Params (Required by TrainingPlanHolder)
    saliency_params = {
        'SmoothGrad': {'nt_samples': 1, 'stdevs': 0.1},
        'SmoothGrad_Squared': {'nt_samples': 1, 'stdevs': 0.1},
        'VarGrad': {'nt_samples': 1, 'stdevs': 0.1}
    }
    study.set_saliency_params(saliency_params)
    
    # 5. Generate Plan and Train
    # Patch file writing to avoid clutter
    with patch('matplotlib.pyplot.savefig'), \
         patch('torch.save'), \
         patch('numpy.savetxt'), \
         patch('os.makedirs'):
         
        study.generate_plan()
        study.train(interact=False) # Run synchronously
        
    # 6. Verification
    # Check if trainer has results
    assert study.trainer is not None
    
    # Get the first plan
    plan_holders = study.trainer.get_training_plan_holders()
    assert len(plan_holders) > 0
    
    plan = plan_holders[0]
    # Check records
    assert len(plan.train_record_list) > 0
    record = plan.train_record_list[0]
    
    # Check metrics exist
    from XBrainLab.backend.training.record import RecordKey
    assert RecordKey.LOSS in record.train
    assert RecordKey.ACC in record.train
    
    print("Real data pipeline test passed!")
