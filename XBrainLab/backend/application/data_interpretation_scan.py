"""Source scanning boundary for the Data Interpretation lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from .data_interpretation_formats import (
    LABEL_CARRIER_EXTENSIONS,
    SUPPORTED_EEG_EXTENSIONS,
)
from .data_interpretation_formats import (
    format_capabilities as _format_capabilities,
)
from .data_interpretation_metadata import (
    FileMetadataResolution,
)
from .data_interpretation_metadata import (
    bids_summary as _bids_summary,
)
from .data_interpretation_metadata import (
    metadata_for_file as _metadata_for_file,
)


@dataclass(frozen=True)
class ScanResult:
    """Files, label carriers, and metadata discovered from a source path."""

    scan_id: str
    source_path: str
    source_hint: str = "auto"
    source_kind: str = "unknown"
    eeg_files: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    bids: dict[str, Any] = dc_field(default_factory=dict)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


def scan_source_path(
    *,
    scan_id: str,
    source_path: str,
    source_hint: str = "auto",
) -> ScanResult:
    """Scan a file, folder, BIDS root, device export, or recipe path."""
    if not str(source_path).strip():
        raise ValueError("source_path is required.")

    path = Path(source_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")
    resolved = path.resolve()
    source_kind = _source_kind(resolved, source_hint)
    scan_root = resolved.parent if resolved.is_file() else resolved
    files = _candidate_files(resolved)
    eeg_files = sorted(
        str(item)
        for item in files
        if _has_supported_suffix(item, SUPPORTED_EEG_EXTENSIONS)
    )
    label_carriers = sorted(
        str(item)
        for item in files
        if _is_label_carrier(item) or _is_bids_events_file(item)
    )
    metadata = [
        _metadata_for_file(Path(file_path), scan_root, source_kind)
        for file_path in eeg_files
    ]
    bids = _bids_summary(scan_root, source_kind, eeg_files, label_carriers)
    format_capabilities = _format_capabilities(files)
    warnings = _scan_warnings(
        source_kind,
        eeg_files,
        label_carriers,
        bids,
        format_capabilities,
    )
    blocked_reasons = _scan_blocked_reasons(eeg_files, format_capabilities)

    return ScanResult(
        scan_id=scan_id,
        source_path=str(resolved),
        source_hint=source_hint,
        source_kind=source_kind,
        eeg_files=eeg_files,
        label_carriers=label_carriers,
        metadata=metadata,
        bids=bids,
        format_capabilities=format_capabilities,
        warnings=warnings,
        blocked_reasons=blocked_reasons,
    )


def _source_kind(path: Path, source_hint: str) -> str:
    hint = str(source_hint or "auto").strip().lower()
    if hint in {"file", "folder", "bids", "device_export", "recipe"}:
        return hint
    if path.is_file() and path.suffix.lower() == ".json":
        return "recipe"
    if path.is_file():
        return "file"
    if _looks_like_bids(path):
        return "bids"
    return "folder"


def _candidate_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return [item for item in path.rglob("*") if item.is_file()]


def _has_supported_suffix(path: Path, suffixes: tuple[str, ...]) -> bool:
    normalized = str(path).lower()
    return any(normalized.endswith(suffix) for suffix in suffixes)


def _is_label_carrier(path: Path) -> bool:
    return _has_supported_suffix(path, LABEL_CARRIER_EXTENSIONS)


def _is_bids_events_file(path: Path) -> bool:
    return path.name.endswith("_events.tsv") or path.name == "events.tsv"


def _looks_like_bids(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / "dataset_description.json").exists():
        return True
    return any(item.name.startswith("sub-") for item in path.iterdir())


def _scan_warnings(
    source_kind: str,
    eeg_files: list[str],
    label_carriers: list[str],
    bids: dict[str, Any],
    format_capabilities: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if len(eeg_files) > 1:
        warnings.append(
            "Multiple EEG files were discovered; subject/session/run mapping "
            "should be reviewed.",
        )
    if label_carriers:
        warnings.append("External label/event carriers require preview before apply.")
    if source_kind == "bids" and not bids.get("events_files"):
        warnings.append(
            "BIDS-like source has no events.tsv carrier; supervised labels "
            "may be limited.",
        )
    blocked_formats = [
        str(item.get("format"))
        for item in format_capabilities
        if item.get("status") == "blocked"
    ]
    if blocked_formats and eeg_files:
        warnings.append(
            "Some discovered sources are not applied by this wizard yet: "
            + ", ".join(blocked_formats)
            + ".",
        )
    return warnings


def _scan_blocked_reasons(
    eeg_files: list[str],
    format_capabilities: list[dict[str, Any]],
) -> list[str]:
    if eeg_files:
        return []
    blocked = [
        str(item.get("message"))
        for item in format_capabilities
        if item.get("status") == "blocked" and item.get("message")
    ]
    if blocked:
        return sorted(set(blocked))
    return ["No supported EEG data files were found."]


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value
