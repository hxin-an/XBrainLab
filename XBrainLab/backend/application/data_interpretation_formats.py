"""Format capability boundaries for Data Interpretation sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SUPPORTED_EEG_EXTENSIONS = (
    ".set",
    ".gdf",
    ".fif",
    ".fif.gz",
    ".edf",
    ".bdf",
    ".cnt",
    ".vhdr",
)
LABEL_CARRIER_EXTENSIONS = (".mat", ".txt", ".csv", ".tsv")


def format_capabilities(files: list[Path]) -> list[dict[str, Any]]:
    """Return user-facing import capability boundaries for discovered files."""
    capabilities: list[dict[str, Any]] = []
    for path in sorted(files, key=lambda item: item.name.lower()):
        capability = format_capability(path)
        if capability:
            capabilities.append(capability)
    return capabilities


def format_capability(path: Path) -> dict[str, Any]:
    """Return the import capability boundary for one path."""
    suffix = path.suffix.lower()
    if _is_bids_events_file(path):
        return _capability(
            path,
            "BIDS events",
            "external_labels",
            "needs_review",
            "BIDS events use onset and duration with label columns such as "
            "trial_type or value; review event column and sidecar semantics.",
        )
    if suffix == ".gdf":
        return _capability(
            path,
            "GDF",
            "eeg",
            "needs_review",
            "GDF event tables often mix trial starts, cues, artifacts, and "
            "class events; confirm trial anchor, class map, and external label "
            "alignment before supervised training.",
        )
    if suffix in {".edf", ".bdf"}:
        return _capability(
            path,
            "EDF",
            "eeg",
            "needs_review",
            "EDF / BDF annotations can describe events or intervals; review "
            "annotation roles, time units, and class map before supervised "
            "training.",
        )
    if suffix == ".set":
        return _capability(
            path,
            "EEGLAB",
            "eeg",
            "needs_review",
            "EEGLAB events, urevents, and boundary markers require review; "
            "boundary must not be treated as a class label.",
        )
    if suffix == ".vhdr":
        return _capability(
            path,
            "BrainVision",
            "eeg",
            "needs_review",
            "BrainVision marker sidecars can include stimulus, response, sync, "
            "and new segment markers; review event roles before apply.",
        )
    if suffix == ".vmrk":
        return _capability(
            path,
            "BrainVision markers",
            "sidecar",
            "context",
            "BrainVision marker sidecar detected; use the associated .vhdr "
            "source and review marker roles.",
        )
    if str(path).lower().endswith((".fif", ".fif.gz")):
        return _capability(
            path,
            "MNE FIF",
            "eeg",
            "supported",
            "FIF can be loaded as an EEG recording; review metadata and events "
            "before supervised training.",
        )
    if suffix == ".mat":
        return _capability(
            path,
            "MAT labels",
            "external_labels",
            "needs_review",
            "MAT labels require variable selection, anchor alignment, and class "
            "map confirmation.",
        )
    if suffix in {".csv", ".tsv"}:
        return _capability(
            path,
            "CSV / TSV labels",
            "external_labels",
            "needs_review",
            "CSV / TSV labels require label column, anchor, time model, and "
            "granularity confirmation.",
        )
    if suffix == ".txt":
        return _capability(
            path,
            "TXT labels",
            "external_labels",
            "needs_review",
            "Text label sequences require trial-order or anchor alignment "
            "confirmation.",
        )
    if suffix == ".xdf":
        return _capability(
            path,
            "XDF / LSL",
            "device_export",
            "blocked",
            "XDF / LSL stream selection is not available in this import wizard "
            "yet. Convert streams to a supported EEG format or provide a "
            "prepared recipe.",
        )
    if suffix in {".pkl", ".pickle"}:
        return _capability(
            path,
            "Pickle sidecar",
            "sidecar",
            "blocked",
            "Pickle label or metadata files are not loaded by this import "
            "wizard. Convert the labels to MAT, CSV, TSV, or TXT with one "
            "label column and one placement column.",
        )
    if suffix == ".log":
        return _capability(
            path,
            "Proprietary log",
            "sidecar",
            "limited",
            "Proprietary log sidecars are not interpreted by this wizard. "
            "Convert relevant labels or events to MAT, CSV, TSV, or TXT.",
        )
    if suffix and suffix not in {".json", ".md"}:
        return _capability(
            path,
            "Unknown sidecar",
            "sidecar",
            "limited",
            "This sidecar format is not interpreted by this wizard. Convert "
            "relevant labels or events to MAT, CSV, TSV, or TXT.",
        )
    return {}


def _capability(
    path: Path,
    format_name: str,
    role: str,
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "path": str(path),
        "name": path.name,
        "format": format_name,
        "role": role,
        "status": status,
        "message": message,
    }


def _is_bids_events_file(path: Path) -> bool:
    return path.name.lower() == "events.tsv" or path.name.lower().endswith(
        "_events.tsv"
    )
