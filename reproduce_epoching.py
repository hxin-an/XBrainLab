import sys
import os
import numpy as np

# Add project root
sys.path.append(os.getcwd())

from XBrainLab.ui_pyqt.load_data.gdf import load_gdf_file
from XBrainLab.preprocessor.time_epoch import TimeEpoch
from XBrainLab.dataset import Dataset

def reproduce():
    print("=== Reproducing Epoching Bug ===")
    
    # 1. Load Data
    data_path = "/mnt/data/lab/XBrainlab_with_agent/test_data_small/A01T.gdf"
    if not os.path.exists(data_path):
        print(f"[FAIL] Data file not found: {data_path}")
        return

    raw_data = load_gdf_file(data_path)
    if not raw_data:
        print("[FAIL] Failed to load GDF")
        return
        
    print(f"[OK] Loaded data. Events: {raw_data.get_event_list()}")

    # 2. Setup Epoching
    # Events in A01T are typically 768 (start trial), 769 (left), 770 (right), etc.
    # Let's try to epoch on 769 and 770 (Left/Right)
    target_events = ['769', '770'] 
    
    # Check if these events exist
    evs, ev_ids = raw_data.get_event_list()
    # In GDF loader, events might be strings or ints. Let's check.
    print(f"Available events: {ev_ids.keys()}")
    
    # Create a list of datasets (TimeEpoch expects a list)
    data_list = [raw_data]
    
    epocher = TimeEpoch(data_list)
    
    # 3. Run Epoching
    tmin, tmax = -0.2, 0.8
    baseline = (-0.2, 0)
    
    print(f"Epoching on {target_events} with tmin={tmin}, tmax={tmax}...")
    
    try:
        epoched_list = epocher.data_preprocess(baseline, target_events, tmin, tmax)
        
        if not epoched_list:
            print("[FAIL] Epoching returned empty list")
            return
            
        epoched_data = epoched_list[0]
        n_epochs = len(epoched_data.get_mne())
        print(f"Resulting epochs: {n_epochs}")
        
        if n_epochs <= 1:
            print("[FAIL] Only 1 or 0 epochs found! Bug reproduced.")
        else:
            print(f"[PASS] Found {n_epochs} epochs.")
            
    except Exception as e:
        print(f"[FAIL] Epoching crashed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduce()
