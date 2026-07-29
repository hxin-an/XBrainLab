"""Source scanning boundary for the Data Interpretation lifecycle."""

from __future__ import annotations

import contextlib
from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from .data_interpretation_formats import (
    LABEL_CARRIER_EXTENSIONS,
    SUPPORTED_EEG_EXTENSIONS,
    is_bids_metadata_table,
    is_edf_annotation_sidecar,
    is_text_context_sidecar,
)
from .data_interpretation_formats import (
    format_capabilities as _format_capabilities,
)
from .data_interpretation_metadata import (
    BIDS_METADATA_READ_BUDGET_BYTES as DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES,
)
from .data_interpretation_metadata import (
    FileMetadataResolution,
)
from .data_interpretation_metadata import (
    bids_metadata_resource_paths as _bids_metadata_resource_paths,
)
from .data_interpretation_metadata import (
    bids_summary as _bids_summary,
)
from .data_interpretation_metadata import (
    metadata_for_file as _metadata_for_file,
)
from .data_interpretation_pairing import label_mapping_key
from .data_interpretation_resource_reader import AdmittedResourceReader

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


@dataclass(frozen=True)
class ScanPreflightScope:
    """Bounded, metadata-free discovery used before full scan materialization."""

    source_path: str
    source_hint: str
    source_kind: str
    scan_root: str
    eeg_files: list[str] = dc_field(default_factory=list)
    label_sources: list[str] = dc_field(default_factory=list)
    label_carriers: list[str] = dc_field(default_factory=list)
    label_carrier_sources: dict[str, str] = dc_field(default_factory=dict)
    metadata_files: list[str] = dc_field(default_factory=list)
    all_files: list[str] = dc_field(default_factory=list)
    bids: dict[str, Any] = dc_field(default_factory=dict)
    skipped_nested_bids_roots: list[str] = dc_field(default_factory=list)
    discovery_warnings: list[str] = dc_field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        """Return every payload or scan-metadata path that may be materialized."""
        return _dedupe_strings(
            [*self.eeg_files, *self.label_carriers, *self.metadata_files],
        )

    def selection_scan_result(self, *, scan_id: str) -> ScanResult:
        """Return a metadata-free scan shape for candidate-scope selection."""
        return ScanResult(
            scan_id=scan_id,
            source_path=self.source_path,
            source_hint=self.source_hint,
            source_kind=self.source_kind,
            eeg_files=list(self.eeg_files),
            label_sources=list(self.label_sources),
            label_carriers=list(self.label_carriers),
            label_carrier_sources=dict(self.label_carrier_sources),
            bids=dict(self.bids),
        )


@dataclass
class _ScanBudget:
    """Shared limits for one bounded filesystem scan."""

    max_depth: int = _MAX_SCAN_DEPTH
    max_files: int = _MAX_SCAN_FILES
    max_entries: int = _MAX_SCAN_FILES
    files_collected: int = 0
    entries_visited: int = 0
    metadata_candidate_bytes: int = 0
    metadata_budget_exhausted: bool = False
    warnings: list[str] = dc_field(default_factory=list)
    _warning_keys: set[str] = dc_field(default_factory=set)
    _counted_files: set[str] = dc_field(default_factory=set)
    _counted_metadata_files: set[str] = dc_field(default_factory=set)
    _directory_cache: dict[str, tuple[Path, ...]] = dc_field(default_factory=dict)

    def warn_once(self, key: str, message: str) -> None:
        if key in self._warning_keys:
            return
        self._warning_keys.add(key)
        self.warnings.append(message)

    def claim_file(self, path: Path) -> bool:
        """Count one unique file against the shared discovery budget."""
        resolved = str(path.resolve(strict=False))
        if resolved in self._counted_files:
            return True
        if self.files_collected >= self.max_files:
            self.warn_once(
                "file-limit",
                (
                    "Shared source scan budget stopped after "
                    f"{self.max_files} files. Choose a narrower source or label "
                    "folder if expected files are missing."
                ),
            )
            return False
        self._counted_files.add(resolved)
        self.files_collected += 1
        return True

    def directory_entries(self, path: Path) -> list[Path]:
        """Return a sorted, bounded slice of one directory iterator."""
        cache_key = str(path.resolve(strict=False))
        cached = self._directory_cache.get(cache_key)
        if cached is not None:
            return list(cached)
        remaining = self.max_entries - self.entries_visited
        if remaining <= 0:
            self._warn_entry_limit()
            return []
        entries: list[Path] = []
        iterator: Any | None = None
        try:
            iterator = path.iterdir()
            while len(entries) < remaining:
                try:
                    entries.append(next(iterator))
                except StopIteration:
                    break
                self.entries_visited += 1
        except OSError as exc:
            self.warn_once(
                f"directory:{path}",
                f"Source scan could not inspect directory {path}: {exc}.",
            )
            self._directory_cache[cache_key] = ()
            return []
        finally:
            if iterator is not None:
                with contextlib.suppress(Exception):
                    close = getattr(iterator, "close", None)
                    if callable(close):
                        close()
        if self.entries_visited >= self.max_entries:
            self._warn_entry_limit()
        sorted_entries = tuple(sorted(entries, key=lambda value: value.name.lower()))
        self._directory_cache[cache_key] = sorted_entries
        return list(sorted_entries)

    def observe_metadata_file(self, path: Path) -> int:
        """Account metadata size by stat without opening its payload."""
        resolved = str(path.resolve(strict=False))
        if resolved in self._counted_metadata_files:
            try:
                return max(int(path.stat().st_size), 0)
            except OSError:
                return 0
        self._counted_metadata_files.add(resolved)
        try:
            file_bytes = max(int(path.stat().st_size), 0)
        except OSError:
            file_bytes = 0
        self.metadata_candidate_bytes += file_bytes
        if self.metadata_candidate_bytes > DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES:
            self.metadata_budget_exhausted = True
            self.warn_once(
                "metadata-byte-budget",
                (
                    "The shared BIDS metadata byte budget of "
                    f"{DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES} bytes was exceeded "
                    "while identifying dataset_description.json paths. Metadata "
                    "payloads were not read during discovery."
                ),
            )
        return file_bytes

    def metadata_discovery_diagnostics(self) -> dict[str, Any]:
        return {
            "budget_bytes": DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES,
            "candidate_bytes": self.metadata_candidate_bytes,
            "bytes_read": 0,
            "budget_exhausted": self.metadata_budget_exhausted,
        }

    def _warn_entry_limit(self) -> None:
        self.warn_once(
            "entry-limit",
            (
                "Shared source scan budget stopped after inspecting "
                f"{self.max_entries} directory entries. Choose a narrower source "
                "or label folder if expected files are missing."
            ),
        )


def scan_source_path(
    *,
    scan_id: str,
    source_path: str,
    source_hint: str = "auto",
    label_sources: list[str] | None = None,
    preflight_scope: ScanPreflightScope | None = None,
    materialize_metadata: bool = True,
    resource_reader: AdmittedResourceReader | None = None,
) -> ScanResult:
    """Scan a file, folder, BIDS root, device export, or recipe path."""
    scope = preflight_scope or discover_source_preflight_scope(
        source_path=source_path,
        source_hint=source_hint,
        label_sources=label_sources,
    )
    resolved = Path(scope.source_path)
    source_kind = scope.source_kind
    normalized_hint = str(scope.source_hint or source_hint or "auto").strip().lower()
    scan_root = Path(scope.scan_root)
    eeg_files = list(scope.eeg_files)
    if resource_reader is not None:
        eeg_files = [
            file_path
            for file_path in eeg_files
            if not is_edf_annotation_sidecar(
                Path(file_path),
                resource_reader=resource_reader,
            )
        ]
    label_carriers = list(scope.label_carriers)
    metadata_guard = (
        resource_reader.guard(
            scope.metadata_files,
            purpose="BIDS metadata materialization",
        )
        if materialize_metadata and resource_reader is not None and scope.metadata_files
        else contextlib.nullcontext()
    )
    with metadata_guard:
        bids = _bids_summary(
            scan_root,
            source_kind,
            eeg_files,
            label_carriers,
            layout=[
                dict(row)
                for row in scope.bids.get("layout", [])
                if isinstance(row, dict)
            ],
            materialize=materialize_metadata,
            admitted_metadata_files=(
                scope.metadata_files if materialize_metadata else ()
            ),
        )
    scope_issue = str(scope.bids.get("root_validation_issue") or "")
    materialized_issue = str(bids.get("root_validation_issue") or "")
    root_validation_issue = (
        materialized_issue or scope_issue if materialize_metadata else scope_issue
    )
    if (
        materialize_metadata
        and normalized_hint == "auto"
        and source_kind == "bids"
        and root_validation_issue
    ):
        source_kind = "folder"
    if materialize_metadata:
        looks_like_bids = bool(scope.bids.get("looks_like_bids")) and not bool(
            root_validation_issue,
        )
        is_bids = source_kind == "bids" and looks_like_bids
    else:
        looks_like_bids = bool(scope.bids.get("looks_like_bids"))
        is_bids = bool(scope.bids.get("is_bids"))
    bids["looks_like_bids"] = looks_like_bids
    bids["is_bids"] = is_bids
    bids["root_validation_issue"] = root_validation_issue
    bids["metadata_discovery"] = dict(
        scope.bids.get("metadata_discovery") or {},
    )
    metadata = [
        _metadata_for_file(Path(file_path), scan_root, source_kind)
        for file_path in eeg_files
    ]
    all_files = [Path(item) for item in scope.all_files]
    format_capabilities = _format_capabilities(
        all_files,
        resource_reader=resource_reader,
    )
    warnings = _scan_warnings(
        source_kind,
        eeg_files,
        label_carriers,
        bids,
        format_capabilities,
    )
    warnings.extend(
        _nested_bids_warnings(
            [Path(item) for item in scope.skipped_nested_bids_roots],
        ),
    )
    warnings.extend(scope.discovery_warnings)
    blocked_reasons = _scan_blocked_reasons(
        eeg_files,
        format_capabilities,
        source_kind=source_kind,
        bids=bids,
    )

    return ScanResult(
        scan_id=scan_id,
        source_path=str(resolved),
        source_hint=scope.source_hint,
        source_kind=source_kind,
        eeg_files=eeg_files,
        label_sources=list(scope.label_sources),
        label_carriers=label_carriers,
        label_carrier_sources=dict(scope.label_carrier_sources),
        metadata=metadata,
        bids=bids,
        format_capabilities=format_capabilities,
        warnings=warnings,
        blocked_reasons=blocked_reasons,
    )


def discover_source_preflight_scope(
    *,
    source_path: str,
    source_hint: str = "auto",
    label_sources: list[str] | None = None,
) -> ScanPreflightScope:
    """Discover an exact bounded scan scope without parsing BIDS TSV rows."""
    if not str(source_path).strip():
        raise ValueError("source_path is required.")

    path = Path(source_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")
    resolved = path.resolve()
    scan_root = resolved.parent if resolved.is_file() else resolved
    scan_budget = _ScanBudget()
    looks_like_bids, bids_root_issue = _provisional_bids_root(
        scan_root,
        scan_budget,
    )
    source_kind = _source_kind(
        resolved,
        source_hint,
        looks_like_bids=looks_like_bids,
    )
    skipped_nested_bids_roots: list[Path] = []
    files = _candidate_files(
        resolved,
        skip_nested_bids_roots=source_kind != "bids",
        skipped_bids_roots=skipped_nested_bids_roots,
        budget=scan_budget,
    )
    strict_bids_files = (
        [item for item in files if _is_raw_bids_eeg_scope_path(item, scan_root)]
        if source_kind == "bids" and looks_like_bids
        else files
    )
    eeg_files = sorted(
        str(item)
        for item in strict_bids_files
        if _has_supported_suffix(item, SUPPORTED_EEG_EXTENSIONS)
    )
    bids_structure_detected = _has_bids_subject_structure(scan_root, files)
    auto_label_carriers = (
        [item for item in strict_bids_files if _is_bids_events_file(item)]
        if source_kind == "bids" and looks_like_bids
        else _auto_label_carriers_for_source(
            resolved,
            files,
            scan_budget,
        )
    )
    normalized_label_sources, source_label_carriers, source_warnings = (
        _label_carriers_from_sources(label_sources or [], scan_budget)
    )
    label_carrier_sources: dict[str, str] = {}
    for carrier in auto_label_carriers:
        label_carrier_sources[str(carrier)] = "auto"
    for source, carriers in source_label_carriers:
        for carrier in carriers:
            label_carrier_sources.setdefault(str(carrier), str(source))
    label_carriers = sorted(label_carrier_sources)
    source_label_files = [
        carrier for _, carriers in source_label_carriers for carrier in carriers
    ]
    all_files = _dedupe_paths([*strict_bids_files, *source_label_files])
    bids = _bids_summary(
        scan_root,
        source_kind,
        eeg_files,
        label_carriers,
        materialize=False,
    )
    bids["looks_like_bids"] = looks_like_bids
    bids["is_bids"] = source_kind == "bids" and looks_like_bids
    bids["root_validation_issue"] = (
        bids_root_issue
        if source_kind == "bids"
        or bids_structure_detected
        or (scan_root / "dataset_description.json").exists()
        else ""
    )
    bids["metadata_discovery"] = scan_budget.metadata_discovery_diagnostics()
    return ScanPreflightScope(
        source_path=str(resolved),
        source_hint=source_hint,
        source_kind=source_kind,
        scan_root=str(scan_root),
        eeg_files=eeg_files,
        label_sources=[str(item) for item in normalized_label_sources],
        label_carriers=label_carriers,
        label_carrier_sources=label_carrier_sources,
        metadata_files=_bids_metadata_resource_paths(bids),
        all_files=[str(item) for item in all_files],
        bids=bids,
        skipped_nested_bids_roots=[str(item) for item in skipped_nested_bids_roots],
        discovery_warnings=[*scan_budget.warnings, *source_warnings],
    )


def discover_explicit_file_preflight_scope(
    *,
    source_path: str,
    selected_eeg_files: list[str],
    label_sources: list[str] | None = None,
) -> ScanPreflightScope:
    """Discover only explicitly selected EEG files and their nearby labels.

    A multi-file picker commonly returns several files from one directory. The
    directory remains useful as the displayed scan location, but it must not
    silently widen the EEG selection into a recursive folder import.
    """
    selected_paths = _dedupe_paths(
        [
            Path(item).expanduser().resolve(strict=False)
            for item in selected_eeg_files
            if str(item).strip()
        ],
    )
    if not selected_paths:
        return discover_source_preflight_scope(
            source_path=source_path,
            source_hint="file",
            label_sources=label_sources,
        )

    scan_budget = _ScanBudget()
    bounded_selected_paths: list[Path] = []
    for selected_path in selected_paths:
        if not selected_path.is_file():
            raise FileNotFoundError(
                f"Selected EEG file does not exist: {selected_path}",
            )
        if not scan_budget.claim_file(selected_path):
            break
        bounded_selected_paths.append(selected_path)
    selected_paths = bounded_selected_paths

    eeg_files = [
        str(path)
        for path in selected_paths
        if _has_supported_suffix(path, SUPPORTED_EEG_EXTENSIONS)
    ]
    auto_label_carriers = _dedupe_paths(
        [
            carrier
            for selected_path in selected_paths
            for carrier in _auto_label_carriers_for_source(
                selected_path,
                [selected_path],
                scan_budget,
            )
        ],
    )
    normalized_label_sources, source_label_carriers, source_warnings = (
        _label_carriers_from_sources(label_sources or [], scan_budget)
    )
    label_carrier_sources: dict[str, str] = {
        str(carrier): "auto" for carrier in auto_label_carriers
    }
    for label_source, carriers in source_label_carriers:
        for carrier in carriers:
            label_carrier_sources.setdefault(str(carrier), str(label_source))
    label_carriers = sorted(label_carrier_sources)
    source_label_files = [
        carrier for _, carriers in source_label_carriers for carrier in carriers
    ]

    requested_source = Path(source_path).expanduser().resolve(strict=False)
    scan_root = (
        requested_source.parent if requested_source.is_file() else requested_source
    )
    bids = _bids_summary(
        scan_root,
        "file",
        eeg_files,
        label_carriers,
        materialize=False,
    )
    bids.update(
        {
            "looks_like_bids": False,
            "is_bids": False,
            "root_validation_issue": "",
            "metadata_discovery": scan_budget.metadata_discovery_diagnostics(),
        },
    )
    return ScanPreflightScope(
        source_path=str(requested_source),
        source_hint="file",
        source_kind="file",
        scan_root=str(scan_root),
        eeg_files=eeg_files,
        label_sources=[str(item) for item in normalized_label_sources],
        label_carriers=label_carriers,
        label_carrier_sources=label_carrier_sources,
        metadata_files=[],
        all_files=[
            str(item)
            for item in _dedupe_paths(
                [*selected_paths, *auto_label_carriers, *source_label_files],
            )
        ],
        bids=bids,
        skipped_nested_bids_roots=[],
        discovery_warnings=[*scan_budget.warnings, *source_warnings],
    )


def _source_kind(
    path: Path,
    source_hint: str,
    *,
    looks_like_bids: bool,
) -> str:
    hint = str(source_hint or "auto").strip().lower()
    if hint in {"file", "folder", "bids", "device_export", "recipe"}:
        return hint
    if path.is_file() and path.suffix.lower() == ".json":
        return "recipe"
    if path.is_file():
        return "file"
    if looks_like_bids:
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
        if not budget.claim_file(path):
            return []
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
    for item in budget.directory_entries(path):
        if item.is_symlink():
            budget.warn_once(
                f"symlink:{item}",
                f"Skipped symbolic link during source scan: {item}.",
            )
            continue
        if item.is_file():
            if not budget.claim_file(item):
                break
            result.append(item.resolve())
            continue
        if not item.is_dir():
            continue
        if skip_nested_bids_roots and _provisional_bids_root(item, budget)[0]:
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


def _auto_label_carriers_for_source(
    source_path: Path,
    files: list[Path],
    budget: _ScanBudget,
) -> list[Path]:
    if not source_path.is_file():
        return [
            item
            for item in files
            if _is_label_carrier(item) or _is_bids_events_file(item)
        ]
    source_key = label_mapping_key(source_path)
    candidates: list[Path] = []
    for item in _nearby_label_candidates_for_file(source_path, budget):
        if not item.is_file():
            continue
        resolved = item.resolve()
        if not (_is_label_carrier(resolved) or _is_bids_events_file(resolved)):
            continue
        if _nearby_label_matches_source(source_key, resolved):
            candidates.append(resolved)
    return candidates


def _nearby_label_candidates_for_file(
    source_path: Path,
    budget: _ScanBudget,
) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def _append_file(path: Path) -> None:
        if path.is_symlink():
            budget.warn_once(
                f"symlink:{path}",
                f"Skipped symbolic link during source scan: {path}.",
            )
            return
        if not path.is_file() or not budget.claim_file(path):
            return
        resolved = path.resolve()
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            candidates.append(resolved)

    for item in budget.directory_entries(source_path.parent):
        if item.is_symlink():
            budget.warn_once(
                f"symlink:{item}",
                f"Skipped symbolic link during source scan: {item}.",
            )
            continue
        if item.is_file():
            _append_file(item)
            continue
        if not item.is_dir():
            continue
        if item.name.lower() not in {"label", "labels", "event", "events"}:
            continue
        for child in budget.directory_entries(item):
            _append_file(child)
    return candidates


def _nearby_label_matches_source(source_key: str, label_path: Path) -> bool:
    label_name = label_path.name.lower()
    if label_name == "events.tsv":
        return True
    return label_mapping_key(label_path) == source_key


def _label_carriers_from_sources(
    label_sources: list[str],
    budget: _ScanBudget,
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
        candidates = _candidate_files(resolved, budget=budget)
        if resolved.is_file():
            # An explicitly selected TXT file is user intent. Keep automatic
            # report-name filtering for folder scans, but do not silently
            # discard a file the user chose as a label source.
            carriers = [item for item in candidates if _is_explicit_label_carrier(item)]
        else:
            carriers = [
                item
                for item in candidates
                if _is_label_carrier(item) or _is_bids_events_file(item)
            ]
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


def _dedupe_strings(paths: list[str]) -> list[str]:
    result: list[str] = []
    for path in paths:
        if path and path not in result:
            result.append(path)
    return result


def _has_supported_suffix(path: Path, suffixes: tuple[str, ...]) -> bool:
    normalized = str(path).lower()
    return any(normalized.endswith(suffix) for suffix in suffixes)


def _is_raw_bids_eeg_scope_path(path: Path, bids_root: Path) -> bool:
    """Keep only raw subject-level EEG datatype files for strict BIDS import."""
    try:
        parts = path.resolve().relative_to(bids_root.resolve()).parts
    except ValueError:
        return False
    if not parts or not parts[0].startswith("sub-") or "derivatives" in parts:
        return False
    if len(parts) >= 2 and parts[1] == "eeg":
        return True
    return len(parts) >= 3 and parts[1].startswith("ses-") and parts[2] == "eeg"


def _is_label_carrier(path: Path) -> bool:
    if is_bids_metadata_table(path) or is_text_context_sidecar(path):
        return False
    return _has_supported_suffix(path, LABEL_CARRIER_EXTENSIONS)


def _is_explicit_label_carrier(path: Path) -> bool:
    if is_bids_metadata_table(path):
        return False
    return _has_supported_suffix(path, LABEL_CARRIER_EXTENSIONS)


def _is_bids_events_file(path: Path) -> bool:
    return path.name.endswith("_events.tsv") or path.name == "events.tsv"


def _provisional_bids_root(
    path: Path,
    budget: _ScanBudget,
) -> tuple[bool, str]:
    """Identify a possible BIDS root using stat and directory structure only."""
    if not path.is_dir():
        return False, "The selected BIDS source is not a folder."
    description_path = path / "dataset_description.json"
    if not description_path.is_file():
        return (
            False,
            "dataset_description.json is missing from the selected BIDS root.",
        )
    description_bytes = budget.observe_metadata_file(description_path)
    if description_bytes > DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES:
        return False, (
            "dataset_description.json exceeds the bounded discovery limit of "
            f"{DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES} bytes (the shared BIDS "
            "metadata byte budget)."
        )
    if not _has_bids_subject_structure_on_disk(path, budget):
        return (
            False,
            "No BIDS subject/datatype structure was found under the selected root.",
        )
    return True, ""


def _has_bids_subject_structure_on_disk(
    path: Path,
    budget: _ScanBudget,
) -> bool:
    bids_datatype_dirs = {"eeg", "ieeg", "meg", "beh"}
    for subject_dir in budget.directory_entries(path):
        if (
            subject_dir.is_symlink()
            or not subject_dir.is_dir()
            or not subject_dir.name.startswith("sub-")
        ):
            continue
        if any((subject_dir / datatype).is_dir() for datatype in bids_datatype_dirs):
            return True
        for session_dir in budget.directory_entries(subject_dir):
            if session_dir.is_symlink() or not session_dir.is_dir():
                continue
            if any(
                (session_dir / datatype).is_dir() for datatype in bids_datatype_dirs
            ):
                return True
    return False


def _has_bids_subject_structure(path: Path, files: list[Path]) -> bool:
    if not path.is_dir():
        return False
    bids_datatype_dirs = {"eeg", "ieeg", "meg", "beh"}
    root = path.resolve()
    for file_path in files:
        try:
            parts = file_path.relative_to(root).parts
        except ValueError:
            continue
        subject_indexes = [
            index for index, part in enumerate(parts) if part.startswith("sub-")
        ]
        if any(
            datatype in parts[subject_index + 1 :]
            for subject_index in subject_indexes
            for datatype in bids_datatype_dirs
        ):
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
    if source_kind == "folder" and bids.get("looks_like_bids"):
        warnings.append(
            "BIDS folder detected during regular folder import. Use Import BIDS "
            "folder for BIDS-guided labels, metadata, and epoch setup."
        )
    root_issue = str(bids.get("root_validation_issue") or "").strip()
    if source_kind != "bids" and root_issue:
        warnings.append(root_issue)
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
        root_issue = str(bids.get("root_validation_issue") or "").strip()
        detail = root_issue or "The selected folder is not a valid BIDS dataset root."
        return [f"{detail} Use Import folder for regular EEG files."]
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
