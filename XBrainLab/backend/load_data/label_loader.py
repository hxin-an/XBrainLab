"""Label loader for reading files in various formats (.txt, .mat, .csv, .tsv)."""

import contextlib
import os
from pathlib import Path
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
    duration_field: str | None = None,
    sequence_only: bool = False,
    resource_reader: Any | None = None,
) -> Any:
    """Load label data from a file.

    Supports ``.txt``, ``.csv``, ``.tsv``, and ``.mat`` formats.

    Args:
        filepath: Path to the label file.
        label_field: Optional reviewed label column or MAT variable.
        anchor: Optional reviewed time/sample/anchor column for CSV/TSV or MAT
            variable for sample-index event construction.
        sequence_only: Force CSV/TSV loading to return the reviewed label column
            as an ordered sequence even when timing columns are present.

    Returns:
        1D array of integer labels (Sequence Mode), or a list of dicts
        for Timestamp Mode (CSV/TSV with time columns).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is unsupported or loading fails.

    """
    if resource_reader is not None:
        with resource_reader.open_binary(
            filepath,
            purpose="external label payload materialization",
        ) as source:
            return _load_label_source(
                filepath,
                source,
                label_field=label_field,
                anchor=anchor,
                duration_field=duration_field,
                sequence_only=sequence_only,
            )

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    return _load_label_source(
        filepath,
        filepath,
        label_field=label_field,
        anchor=anchor,
        duration_field=duration_field,
        sequence_only=sequence_only,
    )


def _load_label_source(
    filepath: str,
    source: Any,
    *,
    label_field: str | None,
    anchor: str | None,
    duration_field: str | None,
    sequence_only: bool,
) -> Any:
    suffix = Path(filepath).suffix.lower()

    if suffix == ".txt":
        return _load_txt(source, display_path=filepath)
    if suffix in {".csv", ".tsv"}:
        return _load_csv_tsv(
            source,
            display_path=filepath,
            label_field=label_field,
            anchor=anchor,
            duration_field=duration_field,
            sequence_only=sequence_only,
        )
    if suffix == ".mat":
        return _load_mat(
            source,
            display_path=filepath,
            label_field=label_field,
            anchor=anchor,
            duration_field=duration_field,
        )
    if suffix == ".npy":
        return _load_npy(source, display_path=filepath)
    raise ValueError(f"Unsupported file format: {filepath}")


def _load_txt(source: Any, *, display_path: str) -> np.ndarray:
    """Load labels from a text file containing space-separated integers.

    Args:
        source: Path or admitted binary stream for the text file.

    Returns:
        1D array of integer labels.

    Raises:
        ValueError: If reading or parsing the file fails.

    """
    labels = []
    try:
        if isinstance(source, (str, os.PathLike)):
            with open(source, encoding="utf-8") as f:
                lines = list(f)
        else:
            lines = source.read().decode("utf-8").splitlines()
        for line in lines:
            parts = line.strip().split()
            for p in parts:
                with contextlib.suppress(ValueError):
                    labels.append(int(p))
        return np.array(labels)
    except Exception as e:
        logger.error("Failed to load txt file %s: %s", display_path, e)
        raise ValueError(f"Failed to load txt file: {e}") from e


def _load_mat(
    source: Any,
    *,
    display_path: str,
    label_field: str | None = None,
    anchor: str | None = None,
    duration_field: str | None = None,
) -> np.ndarray | list[dict[str, int]]:
    """Load labels from a MATLAB ``.mat`` file.

    Handles common shapes including ``(n,)``, ``(n, 1)``, ``(1, n)``,
    and MNE-format ``(n, 3)`` arrays.

    Args:
        source: Path or admitted binary stream for the ``.mat`` file.

    Returns:
        1D array of integer labels.

    Raises:
        ValueError: If the file contains no variables or loading fails.

    """
    try:
        mat = scipy.io.loadmat(source)
        # Filter out __header__, __version__, __globals__
        variables = [k for k in mat if not k.startswith("__")]

        if not variables:
            raise ValueError("No variables found in .mat file")  # noqa: TRY301

        # Pick the reviewed variable when provided, otherwise choose a label-like one.
        var_name = _resolve_mat_variable(mat, variables, label_field)
        data = mat[var_name]

        if anchor is not None and str(anchor).strip():
            anchor_name = _resolve_mat_variable(mat, variables, anchor)
            selected_duration = str(duration_field or "").strip()
            duration_name = (
                _resolve_mat_variable(mat, variables, selected_duration)
                if selected_duration
                else None
            )
            return _mat_sample_anchor_events(
                data,
                mat[anchor_name],
                duration_data=mat[duration_name] if duration_name else None,
                duration_field=duration_name,
            )

        return _mat_label_array(data)

    except Exception as e:
        logger.error("Failed to load mat file %s: %s", display_path, e)
        raise ValueError(f"Invalid .mat file: {e}") from e


def _load_npy(source: Any, *, display_path: str) -> np.ndarray:
    """Load a non-pickled NumPy label array from a path or admitted stream."""
    try:
        data = np.load(source, allow_pickle=False)
        return _mat_label_array(_require_npy_array(data))
    except Exception as exc:
        logger.error("Failed to load npy file %s: %s", display_path, exc)
        raise ValueError(f"Invalid .npy file: {exc}") from exc


def _require_npy_array(data: Any) -> np.ndarray:
    if not isinstance(data, np.ndarray):
        raise ValueError("NumPy label file did not contain one array.")
    return data


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


def _mat_label_array(data: Any) -> np.ndarray:
    """Convert a MAT label variable to the legacy 1D label array."""
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


def _mat_sample_anchor_events(
    label_data: Any,
    anchor_data: Any,
    *,
    duration_data: Any | None = None,
    duration_field: str | None = None,
) -> np.ndarray | list[dict[str, int]]:
    """Build MNE event rows from reviewed MAT label and sample-anchor variables."""
    labels = _mat_label_array(label_data).astype(np.int32).flatten()
    anchors = np.array(anchor_data).squeeze().flatten()
    if anchors.size != labels.size:
        raise ValueError(
            "MAT anchor variable length does not match selected label variable.",
        )
    try:
        anchor_values = anchors.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("MAT anchor variable must be numeric.") from exc
    if not np.all(np.isfinite(anchor_values)):
        raise ValueError("MAT anchor variable contains non-finite values.")
    if not np.all(np.equal(np.mod(anchor_values, 1), 0)):
        raise ValueError("MAT anchor variable must contain integer sample indexes.")
    samples = anchor_values.astype(np.int64)
    if duration_data is not None:
        durations = np.array(duration_data).squeeze().flatten()
        if durations.size != labels.size:
            raise ValueError(
                "MAT duration variable length does not match selected label variable.",
            )
        try:
            duration_values = durations.astype(float)
        except (TypeError, ValueError) as exc:
            raise ValueError("MAT duration variable must be numeric.") from exc
        if not np.all(np.isfinite(duration_values)):
            raise ValueError("MAT duration variable contains non-finite values.")
        if str(duration_field or "").strip().lower() in {
            "end",
            "end_time",
            "stop",
            "stop_time",
            "offset",
        }:
            duration_values = duration_values - anchor_values
        if np.any(duration_values < 0):
            raise ValueError("MAT duration variable contains a negative interval.")
        if not np.all(np.equal(np.mod(duration_values, 1), 0)):
            raise ValueError(
                "MAT sample-index duration variable must contain integer values.",
            )
        sample_durations = duration_values.astype(np.int64)
        return [
            {
                "onset": int(sample),
                "duration": int(duration),
                "label": int(label),
            }
            for sample, duration, label in zip(
                samples,
                sample_durations,
                labels,
                strict=True,
            )
        ]
    zeros = np.zeros(labels.size, dtype=np.int64)
    return np.column_stack([samples, zeros, labels.astype(np.int64)]).astype(np.int32)


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
    source: Any,
    *,
    display_path: str,
    label_field: str | None = None,
    anchor: str | None = None,
    duration_field: str | None = None,
    sequence_only: bool = False,
):
    """Load labels from a CSV or TSV file.

    Detects whether the file contains timestamp data (columns like ``onset``,
    ``time``, ``latency``) or sequence data (single column of labels).

    Args:
        source: Path or admitted binary stream for the CSV/TSV file.

    Returns:
        np.ndarray: 1D label array for Sequence Mode.
        list[dict]: List of ``{onset, label, duration}`` dicts for
            Timestamp Mode.

    Raises:
        ValueError: If reading or parsing the file fails.

    """
    try:
        sep = "\t" if Path(display_path).suffix.lower() == ".tsv" else ","
        preserve_label_lexemes = bool(str(label_field or "").strip())
        df = pd.read_csv(
            source,
            sep=sep,
            **(
                {"dtype": str, "keep_default_na": False}
                if preserve_label_lexemes
                else {}
            ),
        )

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
        found_duration = _resolve_column(df.columns, duration_field) or next(
            (c for c in duration_cols if c in df.columns),
            None,
        )

        if sequence_only:
            return _sequence_label_values(df, found_label)

        if found_time and found_label:
            # Timestamp Mode
            result = []
            for _, row in df.iterrows():
                item = {
                    "onset": _tabular_numeric_value(row[found_time]),
                    "label": row[found_label],
                    "duration": _duration_value(
                        row,
                        onset_field=found_time,
                        duration_field=found_duration,
                    ),
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
        logger.error("Failed to load csv/tsv file %s: %s", display_path, e)
        raise ValueError(f"Failed to load csv/tsv file: {e}") from e


def _resolve_column(columns: Any, requested: str | None) -> str | None:
    """Return a normalized DataFrame column selected by the wizard."""
    if requested is None or not str(requested).strip():
        return None
    normalized = str(requested).strip().lower()
    if normalized in columns:
        return normalized
    raise ValueError(f"Column not found: {requested}")


def _sequence_label_values(df: pd.DataFrame, found_label: str | None) -> Any:
    if found_label:
        return df[found_label].values
    if len(df.columns) == 1:
        return df.iloc[:, 0].values
    raise ValueError("Label column is required for event-order labels.")


def _duration_value(row: Any, *, onset_field: str, duration_field: str | None) -> Any:
    if not duration_field:
        return 0.0
    value = row[duration_field]
    if duration_field.lower() in {"end", "end_time", "stop", "stop_time", "offset"}:
        try:
            return round(float(value) - float(row[onset_field]), 10)
        except (TypeError, ValueError):
            return value
    return _tabular_numeric_value(value)


def _tabular_numeric_value(value: Any) -> Any:
    """Restore pandas-style numeric values after lexeme-preserving table parsing."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if not any(token in text.casefold() for token in (".", "e")):
        try:
            return int(text)
        except ValueError:
            pass
    try:
        numeric = float(text)
    except ValueError:
        return value
    return numeric
