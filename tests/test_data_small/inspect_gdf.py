
import mne
import os

# Define the file path
file_path = r"d:/交接/test_data_small/A01E.gdf"

def inspect_gdf(path):
    if not os.path.exists(path):
        print(f"Error: File not found at {path}")
        return

    try:
        # Load the data
        # preload=False to avoid loading the entire file into memory if it's large, 
        # though for metadata inspection it doesn't strictly matter.
        raw = mne.io.read_raw_gdf(path, preload=False, verbose=False)
        
        print("=== Basic Information ===")
        print(raw.info)
        
        print("\n=== Channel Names ===")
        print(raw.ch_names)
        
        print("\n=== Sampling Frequency ===")
        print(f"{raw.info['sfreq']} Hz")
        
        print("\n=== Events / Annotations ===")
        # GDF files usually store events as annotations
        if raw.annotations:
            print(f"Number of annotations: {len(raw.annotations)}")
            # Show unique descriptions to understand the event types
            unique_descs = set(raw.annotations.description)
            print(f"Unique event descriptions: {unique_descs}")
            # Show first few annotations as sample
            for i in range(min(5, len(raw.annotations))):
                print(f"  {i}: onset={raw.annotations.onset[i]:.2f}, duration={raw.annotations.duration[i]}, desc={raw.annotations.description[i]}")
        else:
            print("No annotations found.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    inspect_gdf(file_path)
