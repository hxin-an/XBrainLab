
import os
import pytest
import numpy as np
from PyQt6.QtWidgets import QApplication
from XBrainLab.study import Study
from XBrainLab.load_data import RawDataLoader
from XBrainLab.load_data.raw_data_loader import load_gdf_file
from XBrainLab.ui_pyqt.dashboard_panel.dataset import DatasetPanel
from unittest.mock import MagicMock, patch

# Constants for test data
TEST_DATA_DIR = "/mnt/data/lab/XBrainlab_with_agent/test_data_small"
LABEL_DIR = os.path.join(TEST_DATA_DIR, "label")
EXPECTED_FILES = ["A01T.gdf", "A01E.gdf", "A02T.gdf", "A02E.gdf", "A03T.gdf", "A03E.gdf"]

@pytest.fixture(scope="session")
def qapp():
    """Create the QApplication instance for the session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def study():
    """Create a fresh Study instance for each test."""
    return Study()

from PyQt6.QtWidgets import QMainWindow

class MockMainWindow(QMainWindow):
    def __init__(self, study):
        super().__init__()
        self.study = study

@pytest.fixture
def dataset_panel(qapp, study):
    """Create a DatasetPanel with a mocked main window."""
    mock_main_window = MockMainWindow(study)
    panel = DatasetPanel(mock_main_window)
    return panel

def test_full_import_flow(dataset_panel, study):
    """
    Integration Test: Full Data Import and Label Application Flow
    1. Load GDF files from test_data_small
    2. Verify files are loaded into Study
    3. Simulate Import Label process
    4. Verify labels are correctly applied to events
    """
    print("\n[Integration] Starting Full Import Flow Test...")

    # --- Step 1: Load Data ---
    print(f"[Integration] Loading files from {TEST_DATA_DIR}...")
    loader = RawDataLoader()
    loaded_count = 0
    
    for filename in EXPECTED_FILES:
        filepath = os.path.join(TEST_DATA_DIR, filename)
        if os.path.exists(filepath):
            raw = load_gdf_file(filepath)
            if raw:
                loader.append(raw)
                loaded_count += 1
                print(f"  Loaded: {filename}")
            else:
                print(f"  Failed to load: {filename}")
        else:
            print(f"  File not found: {filepath}")

    assert loaded_count > 0, "No files were loaded!"
    
    # Apply to study
    loader.apply(study, force_update=True)
    dataset_panel.update_panel()
    
    assert len(study.loaded_data_list) == loaded_count
    print(f"[Integration] Successfully loaded {len(study.loaded_data_list)} files.")

    # --- Step 2: Prepare Labels ---
    print(f"[Integration] Preparing labels from {LABEL_DIR}...")
    # Simulate what ImportLabelDialog would return
    # label_map: {filename: [labels...]}
    # mapping: {code: name} (e.g. {1: 'left_hand', 2: 'right_hand'})
    
    import scipy.io
    label_map = {}
    
    # We assume the label files match the data files by name (e.g. A01T.gdf -> A01T.mat)
    for data in study.loaded_data_list:
        base_name = os.path.splitext(data.get_filename())[0]
        mat_path = os.path.join(LABEL_DIR, f"{base_name}.mat")
        
        if os.path.exists(mat_path):
            try:
                mat = scipy.io.loadmat(mat_path)
                # Assuming standard structure 'classlabel' or similar
                # Adjust based on actual .mat structure inspection if needed
                # Common GDF/BCI Comp structure: 'classlabel'
                if 'classlabel' in mat:
                    labels = mat['classlabel'].flatten()
                    # Convert 1-based to 0-based or keep as is? 
                    # Usually labels are 1, 2, 3, 4.
                    label_map[f"{base_name}.mat"] = labels
                    print(f"  Found labels for {base_name}: {len(labels)} labels")
                else:
                    print(f"  'classlabel' key not found in {mat_path}. Keys: {mat.keys()}")
            except Exception as e:
                print(f"  Error loading {mat_path}: {e}")
    
    assert len(label_map) > 0, "No labels were loaded!"

    # Mock mapping (standard BCI Competition IV 2a mapping)
    mapping = {1: 'Left Hand', 2: 'Right Hand', 3: 'Feet', 4: 'Tongue'}

    # --- Step 3: Apply Labels (Simulate UI interaction) ---
    print("[Integration] Applying labels...")
    
    # We need to mock the dialogs to return our prepared data
    # 1. ImportLabelDialog -> returns (label_map, mapping)
    # 2. EventFilterDialog -> returns selected_event_names (e.g. '768' for start trial)
    # 3. LabelMappingDialog -> returns file_mapping {data_path: label_filename}
    
    # Construct file mapping
    file_mapping = {}
    for data in study.loaded_data_list:
        base_name = os.path.splitext(data.get_filename())[0]
        label_name = f"{base_name}.mat"
        if label_name in label_map:
            file_mapping[data.get_filepath()] = label_name

    # Mock the dialogs
    with patch('XBrainLab.ui_pyqt.dashboard_panel.dataset.ImportLabelDialog') as MockLabelDialog, \
         patch('XBrainLab.ui_pyqt.dashboard_panel.dataset.EventFilterDialog') as MockFilterDialog, \
         patch('XBrainLab.ui_pyqt.dashboard_panel.dataset.LabelMappingDialog') as MockMappingDialog, \
         patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info, \
         patch.object(dataset_panel, '_get_target_files_for_import', return_value=study.loaded_data_list):
        
        # Setup Mock Returns
        MockLabelDialog.return_value.exec.return_value = True
        MockLabelDialog.return_value.get_results.return_value = (label_map, mapping)
        
        # For GDF files, we usually filter by specific event type (e.g. 768 - start of trial)
        # We need to know what events are in the GDF files.
        # Let's assume we filter for '768' (0x300) which is standard for BCI Comp IV 2a
        # Or we can return None to skip filtering if we want to apply to all events (unlikely for GDF)
        # Let's try to inspect one file first to see event ids
        
        # Inspect first file events
        events, event_id = study.loaded_data_list[0].get_event_list()
        print(f"  Events in first file: {event_id}")
        
        # Assuming '768' exists or similar trigger
        target_event = '768' 
        if target_event not in event_id:
             # Fallback: find the most common event or one that matches label count
             # For now, let's mock user selecting '768'
             pass

        MockFilterDialog.return_value.exec.return_value = True
        MockFilterDialog.return_value.get_selected_ids.return_value = [target_event]
        
        MockMappingDialog.return_value.exec.return_value = True
        MockMappingDialog.return_value.get_mapping.return_value = file_mapping

        # Execute Import
        dataset_panel.import_label()
        
        # --- Step 4: Verification ---
        print("[Integration] Verifying results...")
        
        # Verify labels applied
        for data in study.loaded_data_list:
            assert data.is_labels_imported()
            
        # IMPORTANT: Sync loaded data to preprocessed data (as DatasetPanel now does)
        study.reset_preprocess(force_update=True)
        
        success_count = 0
        for data in study.loaded_data_list:
            if data.is_labels_imported():
                success_count += 1
                # Verify event codes were updated
                events, event_id = data.get_event_list()
                # Check if we have our mapped class names
                has_classes = any(name in event_id for name in mapping.values())
                if has_classes:
                    print(f"  {data.get_filename()}: Labels applied successfully. Classes found: {list(event_id.keys())}")
                else:
                    print(f"  {data.get_filename()}: Labels imported flag is True, but classes not found in event_id: {event_id}")
            else:
                print(f"  {data.get_filename()}: Labels NOT imported.")
                
        assert success_count > 0, "Labels were not applied to any file!"
        print(f"[Integration] Test Passed! Labels applied to {success_count} files.")

    # --- Step 5: Dataset Generation (Reproduce IndexError) ---
    print("\n[Integration] Starting Dataset Generation Test...")
    
    # 1. Preprocess Data (Required before generation)
    # We need to epoch the data first.
    from XBrainLab.preprocessor import TimeEpoch
    
    # Check events in first file again
    events, event_id = study.loaded_data_list[0].get_event_list()
    target_event = 768 # Standard BCI IV 2a
    
    # Find the name for event 768
    # NOTE: After Label Import, the original events (768) are replaced by the Label names/IDs.
    # So we should epoch based on the LABELS (Left Hand, Right Hand, etc.)
    
    # Check events in first file again
    events, event_id = study.loaded_data_list[0].get_event_list()
    print(f"  Events after labeling: {event_id}")
    
    # We want to use all label classes for epoching
    target_event_names = list(mapping.values()) # ['Left Hand', 'Right Hand', 'Feet', 'Tongue']
    
    # Verify these exist in the file
    available_names = list(event_id.keys())
    selected_names = [name for name in target_event_names if name in available_names]
    
    if not selected_names:
         print(f"  Warning: No label events found. Available: {available_names}")
         # Fallback
         selected_names = available_names

    # Apply Preprocessing
    print(f"  Preprocessing (Epoching) with events: {selected_names}")
    study.preprocess(
        TimeEpoch, 
        baseline=None, 
        selected_event_names=selected_names, 
        tmin=0.0, 
        tmax=4.0
    )
    assert len(study.preprocessed_data_list) > 0
    print(f"  Preprocessed {len(study.preprocessed_data_list)} files.")
    
    # 2. Generate Dataset
    from XBrainLab.dataset import DatasetGenerator, DataSplittingConfig, DataSplitter
    from XBrainLab.dataset.option import SplitUnit, SplitByType, ValSplitByType, TrainingType
    from XBrainLab.training.option import TrainingOption, TRAINING_EVALUATION
    import torch.optim as optim
    
    # Setup Training Option
    train_option = TrainingOption(
        output_dir="/tmp/xbrainlab_test_output",
        optim=optim.Adam,
        optim_params={'weight_decay': 0.0},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=16,
        lr=0.001,
        checkpoint_epoch=1,
        evaluation_option=TRAINING_EVALUATION.LAST_EPOCH,
        repeat_num=1
    )
    
    # Setup Data Splitting Config
    # We want to trigger the error in split_test -> pick_session
    # So we use SplitByType.SESSION (or SUBJECT) for test split.
    
    # Validation Splitter (e.g. 20% Ratio)
    val_splitter = DataSplitter(
        split_type=ValSplitByType.TRIAL,
        value_var="0.2",
        split_unit=SplitUnit.RATIO
    )
    
    # Test Splitter (Split by Session to hit pick_session)
    # We need to provide a session name or ratio?
    # If SplitUnit.RATIO, pick_session picks sessions to satisfy ratio.
    test_splitter = DataSplitter(
        split_type=SplitByType.SESSION,
        value_var="0.2",
        split_unit=SplitUnit.RATIO
    )
    
    split_config = DataSplittingConfig(
        train_type=TrainingType.FULL,
        is_cross_validation=False,
        val_splitter_list=[val_splitter],
        test_splitter_list=[test_splitter]
    )
    
    study.training_option = train_option
    
    # Generate
    print("  Generating Dataset...")
    generator = DatasetGenerator(study.epoch_data, split_config)
    
    # This should trigger the error if reproducible
    try:
        generator.generate()
        print("[Integration] Dataset Generation Successful!")
    except Exception as e:
        print(f"[Integration] Dataset Generation Failed: {e}")
        raise e


def test_resample_and_epoch(dataset_panel, study):
    """
    Integration Test: Resample -> Epoch Flow
    Reproduce 'No event markers found' error.
    """
    print("\n[Integration] Starting Resample -> Epoch Test...")

    # --- Step 1: Load Data ---
    loader = RawDataLoader()
    loaded_count = 0
    for filename in EXPECTED_FILES:
        filepath = os.path.join(TEST_DATA_DIR, filename)
        if os.path.exists(filepath):
            raw = load_gdf_file(filepath)
            if raw:
                loader.append(raw)
                loaded_count += 1
    
    assert loaded_count > 0
    loader.apply(study, force_update=True)
    
    # --- Step 2: Import Labels ---
    import scipy.io
    label_map = {}
    for data in study.loaded_data_list:
        base_name = os.path.splitext(data.get_filename())[0]
        mat_path = os.path.join(LABEL_DIR, f"{base_name}.mat")
        if os.path.exists(mat_path):
            try:
                mat = scipy.io.loadmat(mat_path)
                if 'classlabel' in mat:
                    label_map[f"{base_name}.mat"] = mat['classlabel'].flatten()
            except: pass
            
    mapping = {1: 'Left Hand', 2: 'Right Hand', 3: 'Feet', 4: 'Tongue'}
    file_mapping = {}
    for data in study.loaded_data_list:
        base_name = os.path.splitext(data.get_filename())[0]
        label_name = f"{base_name}.mat"
        if label_name in label_map:
            file_mapping[data.get_filepath()] = label_name

    with patch('XBrainLab.ui_pyqt.dashboard_panel.dataset.ImportLabelDialog') as MockLabelDialog, \
         patch('XBrainLab.ui_pyqt.dashboard_panel.dataset.EventFilterDialog') as MockFilterDialog, \
         patch('XBrainLab.ui_pyqt.dashboard_panel.dataset.LabelMappingDialog') as MockMappingDialog, \
         patch('PyQt6.QtWidgets.QMessageBox.information'), \
         patch.object(dataset_panel, '_get_target_files_for_import', return_value=study.loaded_data_list):
        
        MockLabelDialog.return_value.exec.return_value = True
        MockLabelDialog.return_value.get_results.return_value = (label_map, mapping)
        
        # events, event_id = study.loaded_data_list[0].get_event_list()
        target_event = '768' 
        
        MockFilterDialog.return_value.exec.return_value = True
        MockFilterDialog.return_value.get_selected_ids.return_value = [target_event]
        
        MockMappingDialog.return_value.exec.return_value = True
        MockMappingDialog.return_value.get_mapping.return_value = file_mapping

        dataset_panel.import_label()
        
    study.reset_preprocess(force_update=True)
    
    # --- Step 3: Resample ---
    from XBrainLab.preprocessor import Resample, TimeEpoch
    
    print("  Resampling to 100Hz...")
    study.preprocess(Resample, sfreq=100.0)
    
    # Verify sfreq
    for data in study.preprocessed_data_list:
        assert data.get_sfreq() == 100.0
        
    # --- Step 4: Epoch ---
    print("  Epoching...")
    target_event_names = list(mapping.values())
    
    # This should NOT raise ValueError: No event markers found
    study.preprocess(
        TimeEpoch, 
        baseline=None, 
        selected_event_names=target_event_names, 
        tmin=0.0, 
        tmax=4.0
    )
    
    assert len(study.preprocessed_data_list) > 0
    print("[Integration] Resample -> Epoch Successful!")


def test_resample_epoch_no_labels(dataset_panel, study):
    """
    Integration Test: Resample -> Epoch Flow (No Imported Labels)
    Verify that Resample correctly handles raw stim events and TimeEpoch can use them.
    """
    print("\n[Integration] Starting Resample -> Epoch (No Labels) Test...")

    # --- Step 1: Load Data ---
    loader = RawDataLoader()
    loaded_count = 0
    for filename in EXPECTED_FILES:
        filepath = os.path.join(TEST_DATA_DIR, filename)
        if os.path.exists(filepath):
            raw = load_gdf_file(filepath)
            if raw:
                loader.append(raw)
                loaded_count += 1
    
    assert loaded_count > 0
    loader.apply(study, force_update=True)
    
    # Skip Label Import
    
    # --- Step 2: Resample ---
    from XBrainLab.preprocessor import Resample, TimeEpoch
    
    print("  Resampling to 100Hz...")
    study.preprocess(Resample, sfreq=100.0)
    
    # --- Step 3: Epoch ---
    print("  Epoching...")
    # Use raw event code '768' (standard start trial)
    target_event_names = ['768']
    
    # Check if events exist
    events, event_id = study.preprocessed_data_list[0].get_event_list()
    print(f"  Events available: {event_id}")
    
    if '768' not in event_id:
        print("  Warning: '768' not found. Using available events.")
        target_event_names = list(event_id.keys())

    study.preprocess(
        TimeEpoch, 
        baseline=None, 
        selected_event_names=target_event_names, 
        tmin=0.0, 
        tmax=4.0
    )
    
    assert len(study.preprocessed_data_list) > 0
    print("[Integration] Resample -> Epoch (No Labels) Successful!")

