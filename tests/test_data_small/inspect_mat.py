
import scipy.io
import os
import numpy as np

file_path = r"d:/交接/test_data_small/label/A01E.mat"

def inspect_mat(path):
    if not os.path.exists(path):
        print(f"Error: File not found at {path}")
        return

    try:
        print(f"Loading {path}...")
        mat = scipy.io.loadmat(path)
        
        print("\n=== Keys in MAT file ===")
        for key in mat.keys():
            if key.startswith('__'):
                continue
            val = mat[key]
            print(f"Key: {key}")
            print(f"  Type: {type(val)}")
            if isinstance(val, np.ndarray):
                print(f"  Shape: {val.shape}")
                print(f"  Dtype: {val.dtype}")
                # If it's small, print it
                if val.size < 10:
                    print(f"  Value: {val}")
            else:
                print(f"  Value: {val}")
            print("-" * 20)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    inspect_mat(file_path)
