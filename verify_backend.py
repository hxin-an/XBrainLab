import sys
import os
import numpy as np
import scipy.io

# Add project root
sys.path.append(os.getcwd())

from XBrainLab.study import Study
from XBrainLab.load_data import RawDataLoader, EventLoader
from XBrainLab.ui_pyqt.load_data.gdf import load_gdf_file
from XBrainLab.dataset import Epochs
from XBrainLab.utils.logger import logger

def verify():
    print("=== Starting Backend Verification ===")
    
    # 1. Initialize Study
    study = Study()
    print("[OK] Study initialized")
    
    # 2. Load Data
    data_path = "/mnt/data/lab/XBrainlab_with_agent/test_data_small/A01T.gdf"
    if not os.path.exists(data_path):
        print(f"[FAIL] Data file not found: {data_path}")
        return
        
    try:
        raw = load_gdf_file(data_path)
        if raw:
            loader = RawDataLoader()
            loader.append(raw)
            loader.apply(study)
            print(f"[OK] Loaded {data_path}")
        else:
            print("[FAIL] load_gdf_file returned None")
            return
    except Exception as e:
        print(f"[FAIL] Loading data failed: {e}")
        return

    # 3. Load Labels
    label_path = "/mnt/data/lab/XBrainlab_with_agent/test_data_small/label/A01T.mat"
    if os.path.exists(label_path):
        try:
            mat = scipy.io.loadmat(label_path)
            # Assuming 'classlabel' or similar key exists, standard BCI IV 2a format
            if 'classlabel' in mat:
                labels = mat['classlabel'].flatten()
            else:
                # Try to find any array that looks like labels
                for k, v in mat.items():
                    if isinstance(v, np.ndarray) and v.size > 0:
                        labels = v.flatten()
                        break
            
            # Mock mapping
            mapping = {1: 'Left', 2: 'Right', 3: 'Foot', 4: 'Tongue'}
            
            # Apply labels (Mocking the logic from ImportLabelDialog)
            # We need to match labels to events. 
            # For GDF, events are already there (768, 769 etc).
            # If we just want to verify EventLoader:
            event_loader = EventLoader(study.loaded_data_list[0])
            # Just check if we can create events
            print(f"[OK] Label file found. Found {len(labels)} labels.")
        except Exception as e:
            print(f"[WARN] Label loading issue: {e}")
    
    # 4. Preprocess (Mock)
    try:
        # Just check if we can access data
        data = study.loaded_data_list[0]
        print(f"[OK] Data shape: {data.get_data().shape}")
    except Exception as e:
        print(f"[FAIL] Accessing data failed: {e}")

    print("=== Verification Complete ===")

if __name__ == "__main__":
    verify()
