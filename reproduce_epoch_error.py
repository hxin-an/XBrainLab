import sys
import os
import copy
import mne
import numpy as np
from XBrainLab.ui_pyqt.load_data.gdf import load_gdf_file
from XBrainLab.load_data.raw import Raw

# Add project root
sys.path.append(os.getcwd())

def reproduce_deepcopy_issue():
    print("=== Reproducing Deepcopy Issue ===")
    
    # 1. Load Data
    data_path = "/mnt/data/lab/XBrainlab_with_agent/test_data_small/A01T.gdf"
    if not os.path.exists(data_path):
        print(f"[FAIL] Data file not found: {data_path}")
        return

    raw_wrapper = load_gdf_file(data_path)
    if not raw_wrapper:
        print("[FAIL] Failed to load GDF")
        return
        
    print(f"[OK] Loaded data. Type of mne_data: {type(raw_wrapper.mne_data)}")
    print(f"Is instance of BaseRaw? {isinstance(raw_wrapper.mne_data, mne.io.BaseRaw)}")
    
    # 2. Simulate UI Flow: Filtering -> Epoching
    try:
        print("--- Simulating UI Flow ---")
        from XBrainLab.preprocessor.filtering import Filtering
        from XBrainLab.preprocessor.time_epoch import TimeEpoch
        
        # Create a list of data (as in Study)
        data_list = [raw_wrapper]
        
        # Step 1: Filtering
        print("1. Filtering...")
        filter_proc = Filtering(data_list)
        # Filtering returns a NEW list (because of deepcopy in PreprocessBase)
        filtered_list = filter_proc.data_preprocess(l_freq=1.0, h_freq=40.0)
        
        print(f"Filtered data type: {type(filtered_list[0].mne_data)}")
        print(f"Filtered Is instance of BaseRaw? {isinstance(filtered_list[0].mne_data, mne.io.BaseRaw)}")
        
        # Step 2: Epoching
        print("2. Epoching...")
        # Epoching takes the result of Filtering
        epoch_proc = TimeEpoch(filtered_list)
        
        events, event_id = filtered_list[0].get_event_list()
        # Pick one event
        event_val = list(event_id.values())[0]
        # Find event name for this value
        event_name = [k for k, v in event_id.items() if v == event_val][0]
        
        print(f"Epoching on event: {event_name}")
        
        epoched_list = epoch_proc.data_preprocess(
            baseline=(-0.2, 0),
            selected_event_names=[event_name],
            tmin=-0.2,
            tmax=0.5
        )
        
        print(f"[OK] Epoching successful. Result type: {type(epoched_list[0].mne_data)}")
        
        # Step 3: Try Epoching AGAIN on the SAME instance (Re-entrant test)
        print("3. Attempting Re-entrant Epoching (should fail with new error)...")
        try:
            # Reuse epoch_proc, which now holds epoched data in its internal list
            epoch_proc.data_preprocess(
                baseline=(-0.2, 0),
                selected_event_names=[event_name],
                tmin=-0.2,
                tmax=0.5
            )
            print("[FAIL] TimeEpoch re-ran without error!")
        except ValueError as e:
            print(f"[PASS] Caught expected ValueError: {e}")
            if "Data is already epoched" in str(e):
                print("[PASS] Error message matches my fix.")
            else:
                print(f"[WARN] Error message is different: {e}")
        except TypeError as e:
            print(f"[FAIL] Caught TypeError (User's bug!): {e}")
        except Exception as e:
            print(f"[FAIL] Caught unexpected exception: {type(e).__name__}: {e}")
        
    except Exception as e:
        print(f"[FAIL] Error during flow: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduce_deepcopy_issue()
