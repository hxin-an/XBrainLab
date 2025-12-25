
import mne
import numpy as np
from XBrainLab.load_data import Raw
from XBrainLab.preprocessor import Resample

def test_resample():
    # Create dummy data
    sfreq = 1000
    info = mne.create_info(ch_names=['Fz', 'Cz', 'Pz'], sfreq=sfreq, ch_types='eeg')
    data = np.random.randn(3, 10000) # 10 seconds
    raw = mne.io.RawArray(data, info)
    
    # Add events
    events = np.array([[1000, 0, 1], [5000, 0, 2]])
    event_id = {'Event1': 1, 'Event2': 2}
    
    # Wrap in XBrainLab Raw
    xb_raw = Raw("dummy.gdf", raw)
    xb_raw.set_event(events, event_id)
    
    print(f"Original sfreq: {xb_raw.get_sfreq()}")
    print(f"Original events: {xb_raw.get_event_list()[0]}")
    
    # Resample
    target_sfreq = 250
    resampler = Resample([xb_raw])
    result = resampler.data_preprocess(target_sfreq)
    
    resampled_raw = result[0]
    print(f"New sfreq: {resampled_raw.get_sfreq()}")
    print(f"New events: {resampled_raw.get_event_list()[0]}")
    
    assert resampled_raw.get_sfreq() == target_sfreq
    # Events should be scaled: 1000 -> 250, 5000 -> 1250
    new_events = resampled_raw.get_event_list()[0]
    assert new_events[0, 0] == 250
    assert new_events[1, 0] == 1250
    
    print("Resample test passed!")

if __name__ == "__main__":
    test_resample()
