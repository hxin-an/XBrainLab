import os
import pytest
import numpy as np
from XBrainLab.backend.load_data.raw_data_loader import load_gdf_file
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.utils.filename_parser import FilenameParser
from XBrainLab.backend.load_data.label_loader import load_label_file
from XBrainLab.backend.load_data.event_loader import EventLoader

# Path to the small test data provided in the repo
TEST_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
GDF_FILE = os.path.join(TEST_DATA_DIR, 'A01T.gdf')

class TestMetadataIntegration:
    """
    Integration tests for metadata processing pipeline:
    Load Raw -> Parse Filename -> Load Labels -> Create Events -> Update Raw
    """

    def test_full_metadata_pipeline(self, tmp_path):
        """
        Simulate the full workflow of loading data and applying metadata.
        """
        # 1. Load Raw Data
        if not os.path.exists(GDF_FILE):
            pytest.skip(f"Test data not found at {GDF_FILE}")
            
        raw = load_gdf_file(GDF_FILE)
        assert raw is not None
        
        # 2. Parse Filename (Simulate Smart Parser)
        # A01T.gdf -> Subject: A01, Session: T
        # Using Fixed Position strategy for this specific filename format
        sub, sess = FilenameParser.parse_by_fixed_position(
            os.path.basename(GDF_FILE), 
            1, 3, # Subject: start 1, len 3 -> A01
            4, 1  # Session: start 4, len 1 -> T
        )
        
        assert sub == "A01"
        assert sess == "T"
        
        raw.set_subject_name(sub)
        raw.set_session_name(sess)
        
        assert raw.get_subject_name() == "A01"
        assert raw.get_session_name() == "T"
        
        # 3. Load Labels (Simulate Import Label)
        # Create a dummy label file matching the number of trials/events
        # Note: A01T.gdf has events. We need to know how many to match.
        # For this test, we'll just create a dummy label list and verify EventLoader logic
        # assuming we are replacing or augmenting existing events.
        
        # Let's see how many events are in the raw file first
        original_events, _ = raw.get_raw_event_list()
        n_events = len(original_events)
        
        # Create dummy labels
        dummy_labels = np.random.randint(1, 4, size=n_events)
        label_file = tmp_path / "labels.txt"
        np.savetxt(label_file, dummy_labels, fmt='%d')
        
        loaded_labels = load_label_file(str(label_file))
        assert len(loaded_labels) == n_events
        
        # 4. Create Events (Simulate EventLoader)
        # We map label 1->Left, 2->Right, 3->Feet
        mapping = {1: 'Left', 2: 'Right', 3: 'Feet'}
        
        # EventLoader needs raw data to know WHERE to put events (timing)
        # If raw data already has events, it might replace them or align with them.
        event_loader = EventLoader(raw)
        # Manually set the label list since we loaded it via label_loader
        event_loader.label_list = loaded_labels.tolist()
        
        # Note: create_event implementation details might vary.
        # If it replaces existing events based on index:
        new_events, new_event_id = event_loader.create_event(mapping)
        
        # 5. Update Raw
        raw.set_event(new_events, new_event_id)
        
        # Verify
        assert raw.has_event()
        current_events, current_id = raw.get_event_list()
        assert len(current_events) == n_events
        assert 'Left' in current_id or 'Right' in current_id or 'Feet' in current_id
