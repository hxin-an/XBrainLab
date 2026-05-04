"""Label loader for reading files in various formats (.txt, .mat, .csv, .tsv)."""

import contextlib
import os
from typing import Any

import numpy as np
import pandas as pd
import scipy.io

from XBrainLab.backend.utils.logger import logger

_MAT_LABEL_HINTS = (
    "classlabel",
    "labels",
    "label",
    "target",
    "targets",
    "trial",
    "trials",
    "event",
    "events",
    "y",
)


def load_label_file(
    filepath: str,
    *,
    label_field: str | None = None,
    anchor: str | None = None,
) -> Any:
    """Load label data from a file.

    Supports ``.txt``, ``.csv``, ``.tsv``, and ``.mat`` formats.

    Args:
        filepath: Path to the label file.
        label_field: Optional reviewed label column or MAT variable.
        anchor: Optional reviewed time/sample/anchor column for CSV/TSV.

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
    if filepath.endswith((".csv", ".tsv")):
        return _load_csv_tsv(filepath, label_field=label_field, anchor=anchor)
    if filepath.endswith(".mat"):
        return _load_mat(filepath, label_field=label_field)
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


def _load_mat(path: str, *, label_field: str | None = None) -> np.ndarray:
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

        # Pick the reviewed variable when provided, otherwise choose a label-like one.
        var_name = _resolve_mat_variable(mat, variables, label_field)
        data = mat[var_name]

        # Robust shape handling (migrated from EventLoader)
        label_list = np.array(data).astype(np.int32)

        # Handle (n, 1) and (1, n)
        if len(label_list.shape) == 2:
            if label_list.shape[0] == 1:
                return label_list[0]
            if label_list.shape[1] == 1:
                return label_list[:, 0]
            # Handle (n, 3) - MNE event format
            if label_list.shape[1] == 3:
                # Return the last column (event id)
                return label_list[:, -1]
            # Fallback for non-standard 2D shapes: Flatten to 1D to attempt
            # heuristic matching. This accommodates loose formats where dimensions
            # might be ambiguous.
            return label_list.flatten()

        if len(label_list.shape) == 1:
            return label_list
        return label_list.flatten()

    except Exception as e:
        logger.error("Failed to load mat file %s: %s", path, e)
        raise ValueError(f"Invalid .mat file: {e}") from e


def _resolve_mat_variable(
    mat: dict[str, Any],
    variables: list[str],
    label_field: str | None,
) -> str:
    """Resolve a reviewed MAT variable or fall back to heuristic selection."""
    if label_field is None or not str(label_field).strip():
        return _select_mat_variable(mat, variables)

    requested = str(label_field).strip()
    for variable in variables:
        if variable == requested:
            return variable
    normalized = requested.lower()
    for variable in variables:
        if variable.lower() == normalized:
            return variable
    raise ValueError(f"MAT variable not found: {requested}")


def _select_mat_variable(mat: dict[str, Any], variables: list[str]) -> str:
    """Select the most likely label variable from a loaded MATLAB file."""

    def score(name: str, data: Any) -> int:
        if not isinstance(data, np.ndarray):
            return -10_000

        # Strongly prefer numeric arrays over structs / cells / object arrays.
        if data.dtype.names is not None or data.dtype == object:
            return -5_000

        score_value = 0
        lower_name = name.lower()

        if any(hint in lower_name for hint in _MAT_LABEL_HINTS):
            score_value += 1_000

        if np.issubdtype(data.dtype, np.number):
            score_value += 100

        if data.size > 1:
            score_value += 20

        # Prefer common label/event layouts.
        if data.ndim == 1:
            score_value += 40
        elif data.ndim == 2:
            if 1 in data.shape:
                score_value += 50
            elif data.shape[1] == 3:
                score_value += 45
            else:
                score_value += 10

        return score_value

    return max(variables, key=lambda name: score(name, mat[name]))


def _load_csv_tsv(
    path: str,
    *,
    label_field: str | None = None,
    anchor: str | None = None,
):
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

        found_time = _resolve_column(df.columns, anchor) or next(
            (c for c in time_cols if c in df.columns),
            None,
        )
        found_label = _resolve_column(df.columns, label_field) or next(
            (c for c in label_cols if c in df.columns),
            None,
        )
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
        if found_label:
            return df[found_label].values
        if len(df.columns) == 1:
            return df.iloc[:, 0].values
        # Try to guess? Or raise error?
        # Let's assume first column
        return df.iloc[:, 0].values

    except Exception as e:
        logger.error("Failed to load csv/tsv file %s: %s", path, e)
        raise ValueError(f"Failed to load csv/tsv file: {e}") from e


def _resolve_column(columns: Any, requested: str | None) -> str | None:
    """Return a normalized DataFrame column selected by the wizard."""
    if requested is None or not str(requested).strip():
        return None
    normalized = str(requested).strip().lower()
    if normalized in columns:
        return normalized
    raise ValueError(f"Column not found: {requested}")
