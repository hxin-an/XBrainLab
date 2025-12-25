
import mne
import scipy.io
import os

# Define paths
gdf_path = r"d:/交接/test_data_small/A01E.gdf"
mat_path = r"d:/交接/test_data_small/A01E_data.mat"

def convert_gdf_to_mat():
    if not os.path.exists(gdf_path):
        print(f"Error: GDF file not found at {gdf_path}")
        return

    try:
        print(f"Loading {gdf_path}...")
        # Load GDF file
        raw = mne.io.read_raw_gdf(gdf_path, preload=True)
        
        # Extract data and info
        data = raw.get_data() # (n_channels, n_times)
        sfreq = raw.info['sfreq']
        ch_names = raw.ch_names
        
        # Extract events if available
        events, event_id = mne.events_from_annotations(raw)
        
        # Create dictionary to save
        mat_dict = {
            'data': data,
            'sfreq': sfreq,
            'ch_names': ch_names,
            'events': events,
            'event_id': event_id
        }
        
        print(f"Saving to {mat_path}...")
        scipy.io.savemat(mat_path, mat_dict)
        print("Done!")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    convert_gdf_to_mat()
