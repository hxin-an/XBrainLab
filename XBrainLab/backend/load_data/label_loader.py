import os
import numpy as np
import scipy.io
from XBrainLab.backend.utils.logger import logger

def load_label_file(filepath: str) -> np.ndarray:
    """
    Load label data from a file (.txt or .mat).
    
    Args:
        filepath: Path to the label file.
        
    Returns:
        np.ndarray: 1D array of labels.
        
    Raises:
        ValueError: If file format is not supported or loading fails.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    if filepath.endswith('.txt'):
        return _load_txt(filepath)
    elif filepath.endswith('.csv') or filepath.endswith('.tsv'):
        return _load_csv_tsv(filepath)
    elif filepath.endswith('.mat'):
        return _load_mat(filepath)
    else:
        raise ValueError(f"Unsupported file format: {filepath}")

def _load_txt(path: str) -> np.ndarray:
    """Load labels from a text file (space-separated integers)."""
    labels = []
    try:
        with open(path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                for p in parts:
                    try:
                        labels.append(int(p))
                    except ValueError:
                        pass
        return np.array(labels)
    except Exception as e:
        logger.error(f"Failed to load txt file {path}: {e}")
        raise ValueError(f"Failed to load txt file: {e}")

def _load_mat(path: str) -> np.ndarray:
    """Load labels from a .mat file."""
    try:
        mat = scipy.io.loadmat(path)
        # Filter out __header__, __version__, __globals__
        vars = [k for k in mat.keys() if not k.startswith('__')]
        
        if not vars:
            raise ValueError("No variables found in .mat file")
            
        # Pick the first valid variable
        var_name = vars[0]
        data = mat[var_name]
        
        # Robust shape handling (migrated from EventLoader)
        label_list = np.array(data).astype(np.int32)
        
        # Handle (n, 1) and (1, n)
        if len(label_list.shape) == 2:
            if label_list.shape[0] == 1:
                return label_list[0]
            elif label_list.shape[1] == 1:
                return label_list[:, 0]
            # Handle (n, 3) - MNE event format
            elif label_list.shape[1] == 3:
                # Return the last column (event id)
                return label_list[:, -1]
            else:
                 # Fallback for other 2D shapes: flatten? or error?
                 # For now, let's flatten to be safe, or raise error if strict.
                 # Original code raised ValueError for non-3 columns if not 1D.
                 # Let's try to flatten if it looks like a list
                 return label_list.flatten()
                 
        elif len(label_list.shape) == 1:
            return label_list
        else:
            return label_list.flatten()
        
    except Exception as e:
        logger.error(f"Failed to load mat file {path}: {e}")
        raise ValueError(f"Invalid .mat file: {e}")

def _load_csv_tsv(path: str):
    """Load labels from CSV/TSV file.
    Returns:
        np.ndarray: If sequence data (single column or no header).
        List[dict]: If timestamp data (headers 'time', 'latency', 'onset', 'duration', 'label', 'trial_type').
    """
    import pandas as pd
    try:
        sep = '\t' if path.endswith('.tsv') else ','
        df = pd.read_csv(path, sep=sep)
        
        # Normalize column names
        df.columns = [c.lower().strip() for c in df.columns]
        
        # Check for timestamp columns
        time_cols = ['time', 'latency', 'onset']
        label_cols = ['label', 'trial_type', 'type']
        duration_cols = ['duration']
        
        found_time = next((c for c in time_cols if c in df.columns), None)
        found_label = next((c for c in label_cols if c in df.columns), None)
        found_duration = next((c for c in duration_cols if c in df.columns), None)
        
        if found_time and found_label:
            # Timestamp Mode
            result = []
            for _, row in df.iterrows():
                item = {
                    'onset': row[found_time],
                    'label': row[found_label],
                    'duration': row[found_duration] if found_duration else 0.0
                }
                result.append(item)
            return result
        else:
            # Sequence Mode: Assume first column is labels if no specific label column found
            # Or if only one column exists
            if found_label:
                return df[found_label].values
            elif len(df.columns) == 1:
                return df.iloc[:, 0].values
            else:
                # Try to guess? Or raise error?
                # Let's assume first column
                return df.iloc[:, 0].values
                
    except Exception as e:
        logger.error(f"Failed to load csv/tsv file {path}: {e}")
        raise ValueError(f"Failed to load csv/tsv file: {e}")
