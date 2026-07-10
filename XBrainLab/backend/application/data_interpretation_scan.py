"""Source scanning boundary for the Data Interpretation lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from .data_interpretation_formats import (
    LABEL_CARRIER_EXTENSIONS,
    SUPPORTED_EEG_EXTENSIONS,
    is_bids_metadata_table,
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
from .data_interpretation_pairing import label_mapping_key

_MAX_SCAN_DEPTH = 8
_MAX_SCAN_FILES = 5000


@dataclass(frozen=True)
class ScanResult:
    """Files, label carriers, and metadata discovered from a source path."""

    scan_id: str
    source_path: str
    source_hint: str = "auto"
    source_kind: str = "unknown"
    eeg_files: list[str] = dc_field(default_factory=list)
    label_sources: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    label_carrier_sources: dict[str, str] = dc_field(default_factory=dict)
    metadata: list[FileMetadataResolution] = dc_field(default_factory=list)
    bids: dict[str, Any] = dc_field(default_factory=dict)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass
class _ScanBudget:
    """Shared limits for one bounded filesystem scan."""

    max_depth: int = _MAX_SCAN_DEPTH
    max_files: int = _MAX_SCAN_FILES
    files_collected: int = 0
    warnings: list[str] = dc_field(default_factory=list)
    _warning_keys: set[str] = dc_field(default_factory=set)

    def warn_once(self, key: str, message: str) -> None:
        if key in self._warning_keys:
            return
        self._warning_keys.add(key)
        self.warnings.append(message)


def scan_source_path(
    *,
    scan_id: str,
    source_path: str,
    source_hint: str = "auto",
    label_sources: list[str] | None = None,
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
    looks_like_bids = _looks_like_bids(scan_root)
    skipped_nested_bids_roots: list[Path] = []
    scan_budget = _ScanBudget()
    files = _candidate_files(
        resolved,
        skip_nested_bids_roots=source_kind != "bids",
        skipped_bids_roots=skipped_nested_bids_roots,
        budget=scan_budget,
    )
    eeg_files = sorted(
        str(item)
        for item in files
        if _has_supported_suffix(item, SUPPORTED_EEG_EXTENSIONS)
    )
    auto_label_carriers = _auto_label_carriers_for_source(resolved, files)
    normalized_label_sources, source_label_carriers, source_warnings = (
        _label_carriers_from_sources(label_sources or [])
    )
    label_carrier_sources: dict[str, str] = {}
    for carrier in auto_label_carriers:
        label_carrier_sources[str(carrier)] = "auto"
    for source, carriers in source_label_carriers:
        for carrier in carriers:
            label_carrier_sources.setdefault(str(carrier), str(source))
    label_carriers = sorted(label_carrier_sources)
    metadata = [
        _metadata_for_file(Path(file_path), scan_root, source_kind)
        for file_path in eeg_files
    ]
    source_label_files = [
        carrier for _, carriers in source_label_carriers for carrier in carriers
    ]
    all_files = _dedupe_paths([*files, *source_label_files])
    bids = _bids_summary(scan_root, source_kind, eeg_files, label_carriers)
    bids["looks_like_bids"] = looks_like_bids
    bids["is_bids"] = source_kind == "bids" and looks_like_bids
    format_capabilities = _format_capabilities(all_files)
    warnings = _scan_warnings(
        source_kind,
        eeg_files,
        label_carriers,
        bids,
        format_capabilities,
    )
    warnings.extend(_nested_bids_warnings(skipped_nested_bids_roots))
    warnings.extend(scan_budget.warnings)
    warnings.extend(source_warnings)
    blocked_reasons = _scan_blocked_reasons(
        eeg_files,
        format_capabilities,
        source_kind=source_kind,
        bids=bids,
    )

    return ScanResult(
        scan_id=scan_id,
        source_path=str(resolved),
        source_hint=source_hint,
        source_kind=source_kind,
        eeg_files=eeg_files,
        label_sources=[str(item) for item in normalized_label_sources],
        label_carriers=label_carriers,
        label_carrier_sources=label_carrier_sources,
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


def _candidate_files(
    path: Path,
    *,
    skip_nested_bids_roots: bool = False,
    skipped_bids_roots: list[Path] | None = None,
    budget: _ScanBudget | None = None,
    depth: int = 0,
) -> list[Path]:
    budget = budget or _ScanBudget()
    if path.is_file():
        if path.is_symlink():
            budget.warn_once(
                f"symlink:{path}",
                f"Skipped symbolic link during source scan: {path}.",
            )
            return []
        if budget.files_collected >= budget.max_files:
            budget.warn_once(
                "file-limit",
                (
                    "Source scan stopped after "
                    f"{budget.max_files} files. Choose a narrower folder if "
                    "expected files are missing."
                ),
            )
            return []
        budget.files_collected += 1
        return [path.resolve()]
    if depth >= budget.max_depth:
        budget.warn_once(
            f"depth:{path}",
            (
                "Source scan skipped folders deeper than "
                f"{budget.max_depth} levels: {path}."
            ),
        )
        return []
    result: list[Path] = []
    for item in sorted(path.iterdir(), key=lambda value: value.name.lower()):
        if budget.files_collected >= budget.max_files:
            budget.warn_once(
                "file-limit",
                (
                    "Source scan stopped after "
                    f"{budget.max_files} files. Choose a narrower folder if "
                    "expected files are missing."
                ),
            )
            break
        if item.is_symlink():
            budget.warn_once(
                f"symlink:{item}",
                f"Skipped symbolic link during source scan: {item}.",
            )
            continue
        if item.is_file():
            result.append(item.resolve())
            budget.files_collected += 1
            continue
        if not item.is_dir():
            continue
        if skip_nested_bids_roots and _looks_like_bids(item):
            if skipped_bids_roots is not None:
                skipped_bids_roots.append(item.resolve())
            continue
        result.extend(
            _candidate_files(
                item,
                skip_nested_bids_roots=skip_nested_bids_roots,
                skipped_bids_roots=skipped_bids_roots,
                budget=budget,
                depth=depth + 1,
            )
        )
    return result


def _auto_label_carriers_for_source(source_path: Path, files: list[Path]) -> list[Path]:
    if not source_path.is_file():
        return [
            item
            for item in files
            if _is_label_carrier(item) or _is_bids_events_file(item)
        ]
    source_key = label_mapping_key(source_path)
    candidates: list[Path] = []
    for item in _nearby_label_candidates_for_file(source_path):
        if not item.is_file():
            continue
        resolved = item.resolve()
        if not (_is_label_carrier(resolved) or _is_bids_events_file(resolved)):
            continue
        if _nearby_label_matches_source(source_key, resolved):
            candidates.append(resolved)
    return candidates


def _nearby_label_candidates_for_file(source_path: Path) -> list[Path]:
    candidates: list[Path] = []
    for item in source_path.parent.iterdir():
        if item.is_file():
            candidates.append(item)
            continue
        if not item.is_dir():
            continue
        if item.name.lower() not in {"label", "labels", "event", "events"}:
            continue
        candidates.extend(child for child in item.iterdir() if child.is_file())
    return candidates


def _nearby_label_matches_source(source_key: str, label_path: Path) -> bool:
    label_name = label_path.name.lower()
    if label_name == "events.tsv":
        return True
    return label_mapping_key(label_path) == source_key


def _label_carriers_from_sources(
    label_sources: list[str],
) -> tuple[list[Path], list[tuple[Path, list[Path]]], list[str]]:
    normalized: list[Path] = []
    source_carriers: list[tuple[Path, list[Path]]] = []
    warnings: list[str] = []
    for source_text in label_sources:
        if not str(source_text).strip():
            continue
        source = Path(source_text).expanduser()
        if not source.exists():
            warnings.append(f"Label source was not found: {source_text}.")
            continue
        resolved = source.resolve()
        if resolved not in normalized:
            normalized.append(resolved)
        label_budget = _ScanBudget()
        carriers = [
            item
            for item in _candidate_files(resolved, budget=label_budget)
            if _is_label_carrier(item) or _is_bids_events_file(item)
        ]
        warnings.extend(label_budget.warnings)
        if not carriers:
            warnings.append(
                "Label source did not contain a supported label/event file: "
                f"{resolved}."
            )
        source_carriers.append((resolved, carriers))
    return normalized, source_carriers, warnings


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _has_supported_suffix(path: Path, suffixes: tuple[str, ...]) -> bool:
    normalized = str(path).lower()
    return any(normalized.endswith(suffix) for suffix in suffixes)


def _is_label_carrier(path: Path) -> bool:
    if is_bids_metadata_table(path):
        return False
    return _has_supported_suffix(path, LABEL_CARRIER_EXTENSIONS)


def _is_bids_events_file(path: Path) -> bool:
    return path.name.endswith("_events.tsv") or path.name == "events.tsv"


def _looks_like_bids(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / "dataset_description.json").exists():
        return True
    bids_datatype_dirs = {"eeg", "ieeg", "meg", "beh"}
    for item in path.iterdir():
        if item.is_symlink() or not item.is_dir() or not item.name.startswith("sub-"):
            continue
        if any((item / datatype).is_dir() for datatype in bids_datatype_dirs):
            return True
        for child in item.iterdir():
            if child.is_symlink() or not child.is_dir():
                continue
            if any((child / datatype).is_dir() for datatype in bids_datatype_dirs):
                return True
    return False


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
    if source_kind == "folder" and bids.get("looks_like_bids"):
        warnings.append(
            "BIDS folder detected during regular folder import. Use Import BIDS "
            "folder for BIDS-guided labels, metadata, and epoch setup."
        )
    if source_kind == "bids" and bids.get("is_bids") and not bids.get("events_files"):
        warnings.append(
            "BIDS folder has no events.tsv carrier for the selected scan scope.",
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


def _nested_bids_warnings(skipped_roots: list[Path]) -> list[str]:
    return [
        "Nested BIDS folder was skipped during regular folder import: "
        f"{root}. Use Import BIDS folder to import that dataset."
        for root in skipped_roots
    ]


def _scan_blocked_reasons(
    eeg_files: list[str],
    format_capabilities: list[dict[str, Any]],
    *,
    source_kind: str,
    bids: dict[str, Any],
) -> list[str]:
    if source_kind == "bids" and not bids.get("is_bids"):
        return [
            "Selected folder does not look like a BIDS EEG dataset. Use Import "
            "folder for regular EEG files."
        ]
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
