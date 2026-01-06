
import pytest
from unittest.mock import MagicMock, patch
from XBrainLab.ui.services.label_import_service import LabelImportService
import numpy as np

@pytest.fixture
def service():
    return LabelImportService()

@pytest.fixture
def mock_raw_data():
    data = MagicMock()
    data.get_filepath.return_value = "/path/to/data.gdf"
    data.get_filename.return_value = "data.gdf"
    data.is_raw.return_value = True
    
    # Mock events: 10 events, all type 1
    events = np.zeros((10, 3), dtype=int)
    events[:, 2] = 1
    event_id = {'Type1': 1}
    data.get_event_list.return_value = (events, event_id)
    
    return data

def test_apply_labels_batch_success(service, mock_raw_data):
    """Test successful batch application."""
    target_files = [mock_raw_data]
    label_map = {"labels.mat": [1, 2, 1, 2, 1, 2, 1, 2, 1, 2]} # 10 labels
    file_mapping = {"/path/to/data.gdf": "labels.mat"}
    mapping = {1: "Left", 2: "Right"}
    
    with patch('XBrainLab.ui.services.label_import_service.EventLoader') as MockLoader:
        count = service.apply_labels_batch(target_files, label_map, file_mapping, mapping)
        
        assert count == 1
        MockLoader.assert_called()
        mock_raw_data.set_labels_imported.assert_called_with(True)

def test_apply_labels_batch_no_match(service, mock_raw_data):
    """Test batch application with no matching file."""
    target_files = [mock_raw_data]
    label_map = {"labels.mat": [1]*10}
    file_mapping = {"/other/path.gdf": "labels.mat"} # Mismatch path
    mapping = {1: "Left"}
    
    count = service.apply_labels_batch(target_files, label_map, file_mapping, mapping)
    assert count == 0

def test_apply_labels_legacy_exact_match(service, mock_raw_data):
    """Test legacy application with exact count match."""
    target_files = [mock_raw_data]
    labels = [1] * 10 # Matches 10 events
    mapping = {1: "Left"}
    
    with patch('XBrainLab.ui.services.label_import_service.EventLoader') as MockLoader:
        count = service.apply_labels_legacy(target_files, labels, mapping)
        
        assert count == 1
        MockLoader.assert_called()

def test_apply_labels_legacy_mismatch(service, mock_raw_data):
    """Test legacy application with count mismatch."""
    target_files = [mock_raw_data]
    labels = [1] * 5 # Only 5 labels, but 10 events
    mapping = {1: "Left"}
    
    count = service.apply_labels_legacy(target_files, labels, mapping)
    assert count == 0 # Should fail without force

def test_apply_labels_legacy_force(service, mock_raw_data):
    """Test legacy application with force=True."""
    target_files = [mock_raw_data]
    labels = [1] * 5 # Mismatch
    mapping = {1: "Left"}
    
    # Mock get_epoch_count_for_file to return 5 for force logic simulation
    # Or rely on internal fallback. 
    # In force mode, it calls get_epoch_count_for_file(data, None) -> returns 10
    # So it will try to take 10 labels from a list of 5 -> Index Error?
    # Let's check logic:
    # if current_idx + n <= len(labels):
    # 0 + 10 <= 5 -> False.
    # So it won't apply.
    
    # Let's provide enough labels for force import
    labels = [1] * 20 
    
    with patch('XBrainLab.ui.services.label_import_service.EventLoader') as MockLoader:
        count = service.apply_labels_legacy(target_files, labels, mapping, force_import=True)
        assert count == 1
        MockLoader.assert_called()

def test_apply_labels_synced(service, mock_raw_data):
    """Test applying labels synced to specific events."""
    # Setup data with mixed events
    events = np.zeros((10, 3), dtype=int)
    events[:5, 2] = 768 # Target
    events[5:, 2] = 100 # Noise
    event_id = {'Target': 768, 'Noise': 100}
    mock_raw_data.get_event_list.return_value = (events, event_id)
    
    target_files = [mock_raw_data]
    labels = [1, 2, 1, 2, 1] # 5 labels for 5 targets
    mapping = {1: "Left", 2: "Right"}
    selected_event_names = {"Target"}
    
    # Verify get_epoch_count
    count = service.get_epoch_count_for_file(mock_raw_data, selected_event_names)
    assert count == 5
    
    # Apply
    with patch('XBrainLab.backend.load_data.event_loader.validate_type'):
        service.apply_labels_to_single_file(mock_raw_data, labels, mapping, selected_event_names)
    
    # Verify set_event called with new events
    mock_raw_data.set_event.assert_called()
    args = mock_raw_data.set_event.call_args[0]
    new_events = args[0]
    assert len(new_events) == 5
    assert np.array_equal(new_events[:, 2], labels)

def test_apply_labels_synced_mismatch(service, mock_raw_data):
    """Test synced application handles mismatch by truncation (Sequence Mode)."""
    events = np.zeros((10, 3), dtype=int)
    events[:, 2] = 768
    event_id = {'Target': 768}
    mock_raw_data.get_event_list.return_value = (events, event_id)
    
    labels = [1] * 5 # 5 labels vs 10 events
    mapping = {1: "Left"}
    selected_event_names = {"Target"}
    
    # Patch validate_type to allow MagicMock as raw data
    with patch('XBrainLab.backend.load_data.event_loader.validate_type'):
         service.apply_labels_to_single_file(mock_raw_data, labels, mapping, selected_event_names)
         
    # Verify set_event called with 5 events (truncated)
    mock_raw_data.set_event.assert_called()
    args = mock_raw_data.set_event.call_args[0]
    new_events = args[0]
    assert len(new_events) == 5
    assert np.array_equal(new_events[:, 2], labels)
