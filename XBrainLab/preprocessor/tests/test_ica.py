from unittest.mock import patch
import pytest
import numpy as np
import mne
from XBrainLab.load_data import Raw
from XBrainLab.preprocessor import ICA

@pytest.fixture
def mock_raw_data():
    # Create a dummy MNE Raw object
    info = mne.create_info(ch_names=['Fz', 'Cz', 'Pz'], sfreq=100, ch_types='eeg')
    data = np.random.randn(3, 1000)
    # Add a blink-like artifact to channel 0
    blink = np.zeros((1, 1000))
    blink[0, 400:500] = 5.0 # Large amplitude
    data[0] += blink[0]
    
    raw = mne.io.RawArray(data, info)
    
    # Wrap in our Raw class
    # We need to mock the Raw class behavior slightly or just use it if it's simple
    # Our Raw class wraps mne.io.Raw
    x_raw = Raw("dummy.gdf", raw)
    return x_raw

def test_ica_picard_missing_dependency(mock_raw_data):
    """Test that ICA raises ImportError when picard is selected but missing."""
    ica_processor = ICA([mock_raw_data])
    
    # Mock import failure
    with patch.dict('sys.modules', {'picard': None}):
        with pytest.raises(ImportError, match="The 'picard' package is required"):
            ica_processor.data_preprocess(n_components=5, method='picard')

def test_ica_fit_apply(mock_raw_data):
    # Test basic ICA initialization and application
    ica_proc = ICA([mock_raw_data])
    
    # Apply ICA with 3 components
    # Using 'fastica'
    ica_proc.data_preprocess(n_components=3, method='fastica', random_state=42)
    
    # Check if data changed (it should, even if slightly due to reconstruction)
    # Note: If no components are excluded, PCA -> ICA -> Inverse ICA should reconstruct signal
    # but with some numerical differences.
    # However, our implementation might not exclude anything by default unless EOG is found.
    # Since we didn't mark any channel as EOG, it shouldn't exclude anything automatically.
    
    # Let's verify it runs without error and returns the object
    assert len(ica_proc.get_preprocessed_data_list()) == 1
    processed = ica_proc.get_preprocessed_data_list()[0]
    assert isinstance(processed, Raw)
    
    # Check history
    assert "ICA" in processed.get_preprocess_history()[-1]

def test_ica_params(mock_raw_data):
    ica_proc = ICA([mock_raw_data])
    desc = ica_proc.get_preprocess_desc(n_components=2, method='picard')
    assert "n_components=2" in desc
    assert "method=picard" in desc
