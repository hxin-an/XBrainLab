"""Format capability boundaries for Data Interpretation sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .data_interpretation_resource_reader import AdmittedResourceReader

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
BIDS_METADATA_TABLE_NAMES = (
    "participants.tsv",
    "scans.tsv",
    "sessions.tsv",
    "channels.tsv",
    "electrodes.tsv",
)
BIDS_METADATA_TABLE_SUFFIXES = (
    "_scans.tsv",
    "_sessions.tsv",
    "_channels.tsv",
    "_electrodes.tsv",
)
_EDF_FIXED_HEADER_BYTES = 256
_EDF_SIGNAL_LABEL_BYTES = 16
_EDF_SIGNAL_HEADER_BYTES = 256
_EDF_SAMPLES_PER_RECORD_OFFSET_BYTES = 216
_EDF_SAMPLES_PER_RECORD_BYTES = 8
_EDF_SAMPLE_BYTES = 2
_EDF_MAX_SIGNAL_COUNT = 512


def is_edf_annotation_sidecar(
    path: Path,
    *,
    resource_reader: AdmittedResourceReader | None = None,
) -> bool:
    """Return whether an EDF file contains annotation signals only.

    EDF stores the signal count in its fixed header followed by one 16-byte
    label per signal. Reading only that admitted, bounded header distinguishes
    an EDF+ annotation sidecar from a physiological recording without loading
    samples.
    """
    if (
        path.suffix.casefold() != ".edf"
        or not path.is_file()
        or resource_reader is None
    ):
        return False
    with resource_reader.guard([path], purpose="EDF annotation-sidecar review"):
        try:
            with path.open("rb") as handle:
                fixed_header = handle.read(_EDF_FIXED_HEADER_BYTES)
                if len(fixed_header) != _EDF_FIXED_HEADER_BYTES:
                    return False
                signal_count = int(fixed_header[252:256].decode("ascii").strip())
                declared_header_bytes = int(
                    fixed_header[184:192].decode("ascii").strip()
                )
                data_record_count = int(fixed_header[236:244].decode("ascii").strip())
                file_size_bytes = path.stat().st_size
                if signal_count <= 0 or signal_count > _EDF_MAX_SIGNAL_COUNT:
                    return False
                if data_record_count == 0 or data_record_count < -1:
                    return False
                expected_header_bytes = (
                    _EDF_FIXED_HEADER_BYTES + signal_count * _EDF_SIGNAL_HEADER_BYTES
                )
                if (
                    declared_header_bytes != expected_header_bytes
                    or file_size_bytes < expected_header_bytes
                ):
                    return False
                label_bytes = handle.read(signal_count * _EDF_SIGNAL_LABEL_BYTES)
                handle.seek(
                    _EDF_FIXED_HEADER_BYTES
                    + signal_count * _EDF_SAMPLES_PER_RECORD_OFFSET_BYTES
                )
                samples_per_record_bytes = handle.read(
                    signal_count * _EDF_SAMPLES_PER_RECORD_BYTES
                )
        except (OSError, UnicodeDecodeError, ValueError):
            return False
        if len(label_bytes) != signal_count * _EDF_SIGNAL_LABEL_BYTES:
            return False
        if (
            len(samples_per_record_bytes)
            != signal_count * _EDF_SAMPLES_PER_RECORD_BYTES
        ):
            return False
        try:
            samples_per_record = [
                int(
                    samples_per_record_bytes[
                        index * _EDF_SAMPLES_PER_RECORD_BYTES : (index + 1)
                        * _EDF_SAMPLES_PER_RECORD_BYTES
                    ]
                    .decode("ascii")
                    .strip()
                )
                for index in range(signal_count)
            ]
        except (UnicodeDecodeError, ValueError):
            return False
        if any(sample_count <= 0 for sample_count in samples_per_record):
            return False
        minimum_record_count = data_record_count if data_record_count > 0 else 1
        minimum_file_bytes = expected_header_bytes + (
            minimum_record_count * sum(samples_per_record) * _EDF_SAMPLE_BYTES
        )
        if file_size_bytes < minimum_file_bytes:
            return False
        labels = [
            label_bytes[
                index * _EDF_SIGNAL_LABEL_BYTES : (index + 1) * _EDF_SIGNAL_LABEL_BYTES
            ]
            .decode("ascii", errors="ignore")
            .strip()
            .casefold()
            for index in range(signal_count)
        ]
        if not labels:
            return False
        return all(label == "edf annotations" for label in labels)


def is_text_context_sidecar(path: Path) -> bool:
    """Return whether a TXT file is a human-readable report, not row labels."""
    if path.suffix.casefold() != ".txt":
        return False
    stem = path.stem.casefold()
    return stem in {"readme", "summary", "notes", "report"} or stem.endswith(
        ("-summary", "_summary", "-readme", "_readme", "-report", "_report")
    )


def format_capabilities(
    files: list[Path],
    *,
    resource_reader: AdmittedResourceReader | None = None,
) -> list[dict[str, Any]]:
    """Return user-facing import capability boundaries for discovered files."""
    capabilities: list[dict[str, Any]] = []
    for path in sorted(files, key=lambda item: item.name.lower()):
        capability = format_capability(path, resource_reader=resource_reader)
        if capability:
            capabilities.append(capability)
    return capabilities


def format_capability(
    path: Path,
    *,
    resource_reader: AdmittedResourceReader | None = None,
) -> dict[str, Any]:
    """Return the import capability boundary for one path."""
    suffix = path.suffix.lower()
    if path.name.casefold().endswith(".edf.seizures"):
        return _capability(
            path,
            "Seizure annotation sidecar",
            "sidecar",
            "unsupported",
            "CHB-MIT seizure annotations are detected but are not interpreted "
            "as supervised labels. The recording remains importable as raw EEG.",
        )
    if is_edf_annotation_sidecar(path, resource_reader=resource_reader):
        return _capability(
            path,
            "EDF+ annotations",
            "sidecar",
            "limited",
            "Annotation-only EDF+ sidecar detected. XBrainLab will not load it "
            "as an EEG recording; convert its reviewed intervals to CSV or TSV "
            "before attaching them as labels.",
        )
    if is_text_context_sidecar(path):
        return _capability(
            path,
            "Text metadata / report",
            "sidecar",
            "limited",
            "Human-readable text summary detected. XBrainLab keeps it as context "
            "instead of interpreting every line as a label sequence.",
        )
    if _is_bids_events_file(path):
        return _capability(
            path,
            "BIDS events",
            "external_labels",
            "needs_review",
            "BIDS events use onset and duration with label columns such as "
            "trial_type or value; review event column and sidecar semantics.",
        )
    if is_bids_metadata_table(path):
        return _capability(
            path,
            "BIDS metadata",
            "metadata",
            "context",
            "BIDS metadata table detected; use it for dataset context, not as "
            "a label/event carrier.",
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


def is_bids_metadata_table(path: Path) -> bool:
    """Return whether a TSV file is BIDS metadata rather than labels/events."""
    name = path.name.lower()
    return name in BIDS_METADATA_TABLE_NAMES or any(
        name.endswith(suffix) for suffix in BIDS_METADATA_TABLE_SUFFIXES
    )
