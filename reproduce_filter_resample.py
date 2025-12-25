
import mne
import numpy as np
from XBrainLab.load_data import Raw
from XBrainLab import preprocessor as Preprocessor

def create_dummy_raw():
    info = mne.create_info(ch_names=['Fz', 'Cz', 'Pz'], sfreq=1000, ch_types='eeg')
    data = np.random.randn(3, 10000)
    raw = mne.io.RawArray(data, info)
    return Raw("dummy.set", raw)

def test_filter_then_resample():
    print("Creating dummy data...")
    raw_data = create_dummy_raw()
    data_list = [raw_data]
    
    print("Applying Filter...")
    filter_proc = Preprocessor.Filtering(data_list)
    filtered_list = filter_proc.data_preprocess(1.0, 40.0)
    print(f"Filter returned: {type(filtered_list)}")
    
    print("Applying Resample...")
    # This is where the user says it fails
    resample_proc = Preprocessor.Resample(filtered_list)
    resampled_list = resample_proc.data_preprocess(250.0)
    print("Resample successful!")

if __name__ == "__main__":
    try:
        test_filter_then_resample()
    except Exception as e:
        print(f"Caught expected error: {e}")
        import traceback
        traceback.print_exc()
