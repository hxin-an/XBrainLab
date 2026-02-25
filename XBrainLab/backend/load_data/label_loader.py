"""Label loader for reading files in various formats (.txt, .mat, .csv, .tsv)."""

import contextlib
import os

import numpy as np
import pandas as pd
import scipy.io

from XBrainLab.backend.utils.logger import logger


def load_label_file(filepath: str) -> np.ndarray:
    """Load label data from a file.

    Supports ``.txt``, ``.csv``, ``.tsv``, and ``.mat`` formats.

    Args:
        filepath: Path to the label file.

    Returns:
        1D array of integer labels (Sequence Mode), or a list of dicts
        for Timestamp Mode (CSV/TSV with time columns).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is unsupported or loading fails.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    if filepath.endswith(".txt"):
        return _load_txt(filepath)
    elif filepath.endswith((".csv", ".tsv")):
        return _load_csv_tsv(filepath)
    elif filepath.endswith(".mat"):
        return _load_mat(filepath)
    else:
        raise ValueError(f"Unsupported file format: {filepath}")


def _load_txt(path: str) -> np.ndarray:
    """Load labels from a text file containing space-separated integers.

    Args:
        path: Path to the text file.

    Returns:
        1D array of integer labels.

    Raises:
        ValueError: If reading or parsing the file fails.
    """
    labels = []
    try:
        with open(path) as f:
            for line in f:
                parts = line.strip().split()
                for p in parts:
                    with contextlib.suppress(ValueError):
                        labels.append(int(p))
        return np.array(labels)
    except Exception as e:
        logger.error("Failed to load txt file %s: %s", path, e)
        raise ValueError(f"Failed to load txt file: {e}") from e


def _load_mat(path: str) -> np.ndarray:
    """Load labels from a MATLAB ``.mat`` file.

    Handles common shapes including ``(n,)``, ``(n, 1)``, ``(1, n)``,
    and MNE-format ``(n, 3)`` arrays.

    Args:
        path: Path to the ``.mat`` file.

    Returns:
        1D array of integer labels.

    Raises:
        ValueError: If the file contains no variables or loading fails.
    """
    try:
        mat = scipy.io.loadmat(path)
        # Filter out __header__, __version__, __globals__
        variables = [k for k in mat if not k.startswith("__")]

        if not variables:
            raise ValueError("No variables found in .mat file")  # noqa: TRY301

        # Pick the first valid variable
        var_name = variables[0]
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
                # Fallback for non-standard 2D shapes: Flatten to 1D to attempt
                # heuristic matching. This accommodates loose formats where dimensions
                # might be ambiguous.
                return label_list.flatten()

        elif len(label_list.shape) == 1:
            return label_list
        else:
            return label_list.flatten()

    except Exception as e:
        logger.error("Failed to load mat file %s: %s", path, e)
        raise ValueError(f"Invalid .mat file: {e}") from e


def _load_csv_tsv(path: str):
    """Load labels from a CSV or TSV file.

    Detects whether the file contains timestamp data (columns like ``onset``,
    ``time``, ``latency``) or sequence data (single column of labels).

    Args:
        path: Path to the CSV/TSV file.

    Returns:
        np.ndarray: 1D label array for Sequence Mode.
        list[dict]: List of ``{onset, label, duration}`` dicts for
            Timestamp Mode.

    Raises:
        ValueError: If reading or parsing the file fails.
    """

    try:
        sep = "\t" if path.endswith(".tsv") else ","
        df = pd.read_csv(path, sep=sep)

        # Normalize column names
        df.columns = [c.lower().strip() for c in df.columns]

        # Check for timestamp columns
        time_cols = ["time", "latency", "onset"]
        label_cols = ["label", "trial_type", "type"]
        duration_cols = ["duration"]

        found_time = next((c for c in time_cols if c in df.columns), None)
        found_label = next((c for c in label_cols if c in df.columns), None)
        found_duration = next((c for c in duration_cols if c in df.columns), None)

        if found_time and found_label:
            # Timestamp Mode
            result = []
            for _, row in df.iterrows():
                item = {
                    "onset": row[found_time],
                    "label": row[found_label],
                    "duration": row[found_duration] if found_duration else 0.0,
                }
                result.append(item)
            return result
        # Sequence Mode: Assume first column is labels if no specific label column found
        # Or if only one column exists
        elif found_label:
            return df[found_label].values
        elif len(df.columns) == 1:
            return df.iloc[:, 0].values
        else:
            # Try to guess? Or raise error?
            # Let's assume first column
            return df.iloc[:, 0].values

    except Exception as e:
        logger.error("Failed to load csv/tsv file %s: %s", path, e)
        raise ValueError(f"Failed to load csv/tsv file: {e}") from e
