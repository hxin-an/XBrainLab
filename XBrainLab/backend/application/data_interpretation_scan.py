"""Source scanning boundary for the Data Interpretation lifecycle."""

from __future__ import annotations

import contextlib
import os
import stat
from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from . import bids_dataset_index as bids_index_module
from .bids_dataset_index import BidsDatasetIndex
from .data_interpretation_bids_resources import (
    bids_events_json_resources_by_carrier,
)
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
from .owned_work import owned_work_checkpoint

_MAX_SCAN_DEPTH = 8
_MAX_SCAN_FILES = 5000
BIDS_REVIEW_METADATA_STAGE = "Materializing BIDS review metadata"
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = getattr(
    stat,
    "FILE_ATTRIBUTE_REPARSE_POINT",
    0x0400,
)


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
    bids_events_json_by_carrier: dict[str, tuple[str, ...]] = dc_field(
        default_factory=dict
    )
    all_files: list[str] = dc_field(default_factory=list)
    bids: dict[str, Any] = dc_field(default_factory=dict)
    skipped_nested_bids_roots: list[str] = dc_field(default_factory=list)
    discovery_warnings: list[str] = dc_field(default_factory=list)
    bids_index: BidsDatasetIndex | None = dc_field(
        default=None,
        repr=False,
        compare=False,
    )

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
    _directory_identities: dict[str, tuple[int, ...]] = dc_field(default_factory=dict)

    @property
    def traversed_directories(self) -> tuple[str, ...]:
        """Return directory identities already visited by this bounded walk."""
        return tuple(sorted(self._directory_cache))

    @property
    def traversal_complete(self) -> bool:
        """Return whether file, entry, and depth bounds retained the full tree."""
        return not any(
            key in {"file-limit", "entry-limit"} or key.startswith("depth:")
            for key in self._warning_keys
        )

    def warn_once(self, key: str, message: str) -> None:
        if key in self._warning_keys:
            return
        self._warning_keys.add(key)
        self.warnings.append(message)

    def claim_file(self, path: Path) -> bool:
        """Count one unique file against the shared discovery budget."""
        resolved = os.path.normcase(os.path.abspath(os.fspath(path.expanduser())))
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
        cache_key = os.path.normcase(os.path.abspath(os.fspath(path.expanduser())))
        if not self.retains_directory_identity(path):
            return []
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

    def retains_directory_identity(self, path: Path) -> bool:
        """Retain one directory identity so children need no repeated realpath."""
        key = os.path.normcase(os.path.abspath(os.fspath(path.expanduser())))
        try:
            status = path.lstat()
        except OSError:
            status = None
        if status is None or not stat.S_ISDIR(status.st_mode):
            self.warn_once(
                f"directory-identity:{path}",
                f"Source scan could not retain directory identity: {path}.",
            )
            return False
        observed = _filesystem_entry_identity(status)
        retained = self._directory_identities.setdefault(key, observed)
        if retained == observed:
            return True
        self.warn_once(
            f"directory-identity-changed:{path}",
            f"Source scan stopped because directory identity changed: {path}.",
        )
        return False

    def retained_directory_identity_is_current(self, path: Path) -> bool:
        """Recheck a retained directory without silently retaining a new one."""
        key = os.path.normcase(os.path.abspath(os.fspath(path.expanduser())))
        retained = self._directory_identities.get(key)
        if retained is None:
            return False
        try:
            status = path.lstat()
        except OSError:
            return False
        return retained == _filesystem_entry_identity(status)

    def revalidate_traversed_directories(self) -> tuple[str, ...]:
        """Return every enumerated directory whose retained contents changed."""
        changed: list[str] = []
        for path_text in self.traversed_directories:
            path = Path(path_text)
            if self.retained_directory_identity_is_current(path):
                continue
            changed.append(path_text)
            self.warn_once(
                f"directory-identity-changed:{path_text}",
                (
                    "Source scan stopped because directory contents changed while "
                    f"the BIDS index was being built: {path_text}."
                ),
            )
        return tuple(changed)

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
    label_carriers = list(scope.label_carriers)
    metadata_files = list(scope.metadata_files)
    all_files = [Path(item) for item in scope.all_files]
    if resource_reader is not None:
        eeg_files = [
            file_path
            for file_path in eeg_files
            if resource_reader.admits(file_path)
            if not is_edf_annotation_sidecar(
                Path(file_path),
                resource_reader=resource_reader,
            )
        ]
        label_carriers = [
            file_path
            for file_path in label_carriers
            if resource_reader.admits(file_path)
        ]
        metadata_files = [
            file_path
            for file_path in metadata_files
            if resource_reader.admits(file_path)
        ]
        if materialize_metadata:
            all_files = [
                file_path
                for file_path in all_files
                if resource_reader.admits(file_path)
            ]
    bids_layout = [
        dict(row) for row in scope.bids.get("layout", []) if isinstance(row, dict)
    ]
    admitted_metadata = set(metadata_files)
    admitted_channel_files = _dedupe_strings(
        [
            str(row.get("channels_file") or "")
            for row in bids_layout
            if str(row.get("channels_file") or "") in admitted_metadata
        ]
    )
    bids_review_metadata_total = (
        # Each materialization unit owns a cancellable begin and end boundary.
        # The fixed units are BIDS summary preparation, participants, and the
        # dataset description, followed by every channel file and EEG row.
        2 * (len(eeg_files) + len(admitted_channel_files) + 3)
        if materialize_metadata and source_kind == "bids"
        else None
    )
    bids_review_metadata_completed = 0

    def _publish_bids_metadata_unit() -> None:
        nonlocal bids_review_metadata_completed
        if bids_review_metadata_total is None:
            return
        bids_review_metadata_completed += 1
        owned_work_checkpoint(
            BIDS_REVIEW_METADATA_STAGE,
            completed=bids_review_metadata_completed,
            total=bids_review_metadata_total,
        )

    def _metadata_file_guard(path: Path):
        return (
            resource_reader.guard(
                [path],
                purpose="BIDS metadata materialization",
            )
            if resource_reader is not None
            else contextlib.nullcontext()
        )

    if bids_review_metadata_total is not None:
        owned_work_checkpoint(
            BIDS_REVIEW_METADATA_STAGE,
            completed=0,
            total=bids_review_metadata_total,
        )
    bids = _bids_summary(
        scan_root,
        source_kind,
        eeg_files,
        label_carriers,
        layout=bids_layout,
        materialize=materialize_metadata,
        admitted_metadata_files=metadata_files,
        on_metadata_checkpoint=(
            _publish_bids_metadata_unit
            if bids_review_metadata_total is not None
            else None
        ),
        metadata_file_guard=(
            _metadata_file_guard
            if materialize_metadata and resource_reader is not None
            else None
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
    for key in ("electrodes_files", "coordsystem_files", "json_sidecar_files"):
        bids[key] = [
            str(path)
            for path in list(scope.bids.get(key) or [])
            if str(path) in admitted_metadata
        ]
    for key in (
        "selected_subjects",
        "index_completeness",
        "skipped_nested_bids_roots",
        "nested_bids_candidates",
    ):
        if key in scope.bids:
            value = scope.bids[key]
            bids[key] = dict(value) if isinstance(value, dict) else list(value)
    if "selection_root" in scope.bids:
        bids["selection_root"] = str(scope.bids["selection_root"])
    metadata: list[FileMetadataResolution] = []
    for file_path in eeg_files:
        _publish_bids_metadata_unit()
        metadata.append(_metadata_for_file(Path(file_path), scan_root, source_kind))
        _publish_bids_metadata_unit()

    format_classification_completed = 0

    def _publish_format_classification() -> None:
        nonlocal format_classification_completed
        format_classification_completed += 1
        owned_work_checkpoint(
            "Classifying import formats",
            completed=format_classification_completed,
            total=len(all_files),
        )

    if all_files:
        owned_work_checkpoint(
            "Classifying import formats",
            completed=0,
            total=len(all_files),
        )
    format_capabilities = _format_capabilities(
        all_files,
        resource_reader=resource_reader,
        on_file_classified=_publish_format_classification if all_files else None,
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
    index_completeness = bids.get("index_completeness")
    if bids.get("is_bids") and isinstance(index_completeness, dict):
        blocked_reasons = _dedupe_strings(
            [
                *blocked_reasons,
                *(
                    str(reason)
                    for reason in index_completeness.get("blocked_reasons", [])
                    if str(reason).strip()
                ),
            ]
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
    selected_bids_subjects: list[str] | tuple[str, ...] | None = None,
    bids_index: BidsDatasetIndex | None = None,
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
    normalized_hint = str(source_hint or "auto").strip().casefold()
    active_bids_index = bids_index
    if active_bids_index is not None and (
        not active_bids_index.matches_root(scan_root)
        or not active_bids_index.is_current()
    ):
        active_bids_index = None
    if active_bids_index is not None:
        looks_like_bids = active_bids_index.looks_like_bids
        bids_root_issue = active_bids_index.root_validation_issue
    elif normalized_hint == "bids":
        active_bids_index = bids_index_module.build_bids_dataset_index(scan_root)
        looks_like_bids = active_bids_index.looks_like_bids
        bids_root_issue = active_bids_index.root_validation_issue
    else:
        looks_like_bids, bids_root_issue = _provisional_bids_root(
            scan_root,
            scan_budget,
            scan_root=scan_root,
        )
    source_kind = _source_kind(
        resolved,
        source_hint,
        looks_like_bids=looks_like_bids,
    )
    skipped_nested_bids_roots: list[Path] = []
    bids_projection = None
    if source_kind == "bids":
        active_bids_index = active_bids_index or (
            bids_index_module.build_bids_dataset_index(
                scan_root,
                _scan_budget=scan_budget,
            )
        )
        bids_projection = active_bids_index.project(selected_bids_subjects)
        # A user may select a download/container folder only when the index can
        # prove it contains one formal BIDS root. All downstream source identity
        # and inheritance semantics then use that resolved dataset root.
        resolved = Path(active_bids_index.root)
        scan_root = resolved
        files = [Path(item) for item in bids_projection.all_files]
    else:
        files = _candidate_files(
            resolved,
            skip_nested_bids_roots=source_kind != "bids",
            skipped_bids_roots=skipped_nested_bids_roots,
            budget=scan_budget,
        )
    if bids_projection is not None and looks_like_bids:
        strict_bids_files = [Path(item) for item in bids_projection.all_files]
        eeg_files = list(bids_projection.eeg_files)
        auto_label_carriers = [Path(item) for item in bids_projection.events_files]
    else:
        strict_bids_files = files
        eeg_files = sorted(
            str(item)
            for item in strict_bids_files
            if _has_supported_suffix(item, SUPPORTED_EEG_EXTENSIONS)
        )
        auto_label_carriers = _auto_label_carriers_for_source(
            resolved,
            files,
            scan_budget,
        )
    bids_structure_detected = (
        bool(active_bids_index and active_bids_index.subjects)
        if source_kind == "bids"
        else _has_bids_subject_structure(scan_root, files)
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
    indexed_events_json = (
        bids_projection.events_json_catalog if bids_projection is not None else {}
    )
    external_events_json = bids_events_json_resources_by_carrier(
        str(carrier) for _, carriers in source_label_carriers for carrier in carriers
    )
    bids_events_json_by_carrier = {
        carrier: indexed_events_json.get(
            carrier,
            external_events_json.get(carrier, ()),
        )
        for carrier in label_carriers
        if _is_bids_events_file(Path(carrier))
    }
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
        layout=(
            [dict(row) for row in bids_projection.layout]
            if bids_projection is not None
            else None
        ),
        discovered_files=files,
    )
    bids["looks_like_bids"] = looks_like_bids
    bids["is_bids"] = source_kind == "bids" and looks_like_bids
    bids["root_validation_issue"] = (
        bids_root_issue
        if source_kind == "bids"
        or bids_structure_detected
        or _path_entry_exists(scan_root / "dataset_description.json")
        else ""
    )
    bids["metadata_discovery"] = (
        active_bids_index.metadata_discovery_diagnostics
        if active_bids_index is not None
        else scan_budget.metadata_discovery_diagnostics()
    )
    if bids_projection is not None and active_bids_index is not None:
        bids.update(
            {
                "selected_subjects": list(bids_projection.selected_subjects),
                "selection_root": active_bids_index.selection_root,
                "nested_bids_candidates": list(
                    active_bids_index.nested_bids_candidates
                ),
                "electrodes_files": list(bids_projection.electrodes_files),
                "coordsystem_files": list(bids_projection.coordsystem_files),
                "json_sidecar_files": list(bids_projection.json_sidecar_files),
                "index_completeness": active_bids_index.completeness.to_dict(),
                "skipped_nested_bids_roots": list(
                    active_bids_index.skipped_nested_bids_roots
                ),
            }
        )
    indexed_metadata_files = (
        list(bids_projection.metadata_files) if bids_projection is not None else []
    )
    return ScanPreflightScope(
        source_path=str(resolved),
        source_hint=source_hint,
        source_kind=source_kind,
        scan_root=str(scan_root),
        eeg_files=eeg_files,
        label_sources=[str(item) for item in normalized_label_sources],
        label_carriers=label_carriers,
        label_carrier_sources=label_carrier_sources,
        metadata_files=_dedupe_strings(
            [
                *indexed_metadata_files,
                *(
                    []
                    if indexed_metadata_files
                    else _bids_metadata_resource_paths(bids)
                ),
                *(
                    path
                    for paths in bids_events_json_by_carrier.values()
                    for path in paths
                ),
            ]
        ),
        bids_events_json_by_carrier=bids_events_json_by_carrier,
        all_files=[str(item) for item in all_files],
        bids=bids,
        skipped_nested_bids_roots=[str(item) for item in skipped_nested_bids_roots],
        discovery_warnings=[
            *(
                active_bids_index.warnings
                if active_bids_index is not None
                else scan_budget.warnings
            ),
            *source_warnings,
        ],
        bids_index=active_bids_index,
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
        discovered_files=[
            *selected_paths,
            *auto_label_carriers,
            *source_label_files,
        ],
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
        bids_events_json_by_carrier={},
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


def _path_substitution_kind(
    path: Path,
    *,
    status: os.stat_result | None = None,
) -> str | None:
    """Return the unsafe link-like kind without requiring Python 3.12 APIs."""
    if status is None:
        try:
            status = path.lstat()
        except OSError:
            return "uninspectable filesystem entry"
    if stat.S_ISLNK(status.st_mode):
        return "symbolic link"
    file_attributes = int(getattr(status, "st_file_attributes", 0) or 0)
    if (
        stat.S_ISDIR(status.st_mode)
        and file_attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
    ):
        return "directory junction or reparse point"
    return None


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except OSError:
        return False
    return True


def _warn_skipped_substitution(
    path: Path,
    kind: str,
    budget: _ScanBudget,
) -> None:
    if kind == "symbolic link":
        message = f"Skipped symbolic link during source scan: {path}."
    elif kind == "directory junction or reparse point":
        message = (
            f"Skipped directory junction or reparse point during source scan: {path}."
        )
    else:
        message = (
            "Skipped path that could not be safely inspected for filesystem "
            f"substitutions during source scan: {path}."
        )
    budget.warn_once(f"substitution:{path}", message)


def _admit_discovered_child(
    path: Path,
    *,
    scan_root: Path,
    budget: _ScanBudget,
) -> Path | None:
    """Resolve one enumerated child only when it remains inside the scan root."""
    try:
        path.relative_to(scan_root)
    except ValueError:
        budget.warn_once(
            f"enumerated-outside-root:{path}",
            (
                "Skipped path outside the selected source root after directory "
                f"enumeration: {path}."
            ),
        )
        return None

    if not budget.retains_directory_identity(path.parent):
        return None

    try:
        initial_status = path.lstat()
    except OSError:
        initial_status = None
    substitution_kind = _path_substitution_kind(path, status=initial_status)
    if substitution_kind is not None:
        _warn_skipped_substitution(path, substitution_kind, budget)
        return None

    resolved = Path(os.path.abspath(os.fspath(path)))
    try:
        resolved.relative_to(scan_root)
    except ValueError:
        budget.warn_once(
            f"resolved-outside-root:{path}",
            (f"Skipped path that resolved outside the selected source root: {path}."),
        )
        return None

    try:
        retained_status = path.lstat()
    except OSError:
        retained_status = None
    if (
        not budget.retained_directory_identity_is_current(path.parent)
        or initial_status is None
        or retained_status is None
        or (
            initial_status.st_dev,
            initial_status.st_ino,
            initial_status.st_mode,
            int(getattr(initial_status, "st_file_attributes", 0) or 0),
        )
        != (
            retained_status.st_dev,
            retained_status.st_ino,
            retained_status.st_mode,
            int(getattr(retained_status, "st_file_attributes", 0) or 0),
        )
    ):
        substitution_kind = "uninspectable filesystem entry"
    else:
        substitution_kind = _path_substitution_kind(path, status=retained_status)
    if substitution_kind is not None:
        _warn_skipped_substitution(path, substitution_kind, budget)
        return None
    return resolved


def _filesystem_entry_identity(status: os.stat_result) -> tuple[int, ...]:
    """Capture substitution and entry-set signals before directory enumeration."""
    return (
        int(status.st_dev),
        int(status.st_ino),
        int(status.st_mode),
        int(getattr(status, "st_file_attributes", 0) or 0),
        int(status.st_size),
        _stat_time_ns(status, nanoseconds="st_mtime_ns", seconds="st_mtime"),
        _stat_time_ns(status, nanoseconds="st_ctime_ns", seconds="st_ctime"),
    )


def _stat_time_ns(
    status: os.stat_result,
    *,
    nanoseconds: str,
    seconds: str,
) -> int:
    value = getattr(status, nanoseconds, None)
    if value is not None:
        return int(value)
    return int(float(getattr(status, seconds)) * 1_000_000_000)


def _candidate_files(
    path: Path,
    *,
    skip_nested_bids_roots: bool = False,
    skipped_bids_roots: list[Path] | None = None,
    budget: _ScanBudget | None = None,
    depth: int = 0,
    scan_root: Path | None = None,
) -> list[Path]:
    budget = budget or _ScanBudget()
    if scan_root is None:
        scan_root = (path.parent if path.is_file() else path).resolve(strict=True)
    if path.is_file():
        substitution_kind = _path_substitution_kind(path)
        if substitution_kind is not None:
            _warn_skipped_substitution(path, substitution_kind, budget)
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
    owned_work_checkpoint(
        "Discovering source files",
        completed=budget.entries_visited,
    )
    result: list[Path] = []
    for item in budget.directory_entries(path):
        owned_work_checkpoint(
            "Discovering source files",
            completed=budget.entries_visited,
        )
        admitted_item = _admit_discovered_child(
            item,
            scan_root=scan_root,
            budget=budget,
        )
        if admitted_item is None:
            continue
        if admitted_item.is_file():
            if not budget.claim_file(admitted_item):
                break
            result.append(admitted_item)
            continue
        if not admitted_item.is_dir():
            continue
        if (
            skip_nested_bids_roots
            and _provisional_bids_root(
                admitted_item,
                budget,
                scan_root=scan_root,
            )[0]
        ):
            if skipped_bids_roots is not None:
                skipped_bids_roots.append(admitted_item)
            continue
        result.extend(
            _candidate_files(
                admitted_item,
                skip_nested_bids_roots=skip_nested_bids_roots,
                skipped_bids_roots=skipped_bids_roots,
                budget=budget,
                depth=depth + 1,
                scan_root=scan_root,
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
    scan_root = source_path.parent.resolve(strict=True)

    def _append_file(path: Path) -> None:
        if not path.is_file() or not budget.claim_file(path):
            return
        key = str(path)
        if key not in seen:
            seen.add(key)
            candidates.append(path)

    for item in budget.directory_entries(scan_root):
        admitted_item = _admit_discovered_child(
            item,
            scan_root=scan_root,
            budget=budget,
        )
        if admitted_item is None:
            continue
        if admitted_item.is_file():
            _append_file(admitted_item)
            continue
        if not admitted_item.is_dir():
            continue
        if admitted_item.name.lower() not in {"label", "labels", "event", "events"}:
            continue
        for child in budget.directory_entries(admitted_item):
            admitted_child = _admit_discovered_child(
                child,
                scan_root=scan_root,
                budget=budget,
            )
            if admitted_child is not None:
                _append_file(admitted_child)
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
    """Keep admitted raw subject-level EEG files in the selected BIDS root."""
    try:
        # Discovery has already rejected substitutions and resolved both paths
        # inside the retained directory identity. Re-resolving every file here
        # repeats expensive WSL/NTFS lstat walks without adding an admission check.
        parts = path.relative_to(bids_root).parts
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
    *,
    scan_root: Path | None = None,
) -> tuple[bool, str]:
    """Identify a possible BIDS root using stat and directory structure only."""
    if not path.is_dir():
        return False, "The selected BIDS source is not a folder."
    containment_root = scan_root or path.resolve(strict=True)
    description_path = path / "dataset_description.json"
    try:
        description_path.lstat()
    except FileNotFoundError:
        return (
            False,
            "dataset_description.json is missing from the selected BIDS root.",
        )
    except OSError:
        pass
    admitted_description = _admit_discovered_child(
        description_path,
        scan_root=containment_root,
        budget=budget,
    )
    if admitted_description is None or not admitted_description.is_file():
        return (
            False,
            "dataset_description.json is not safely contained in the selected "
            "BIDS root.",
        )
    description_path = admitted_description
    description_bytes = budget.observe_metadata_file(description_path)
    if description_bytes > DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES:
        return False, (
            "dataset_description.json exceeds the bounded discovery limit of "
            f"{DATASET_DESCRIPTION_DISCOVERY_MAX_BYTES} bytes (the shared BIDS "
            "metadata byte budget)."
        )
    if not _has_bids_subject_structure_on_disk(
        path,
        budget,
        scan_root=containment_root,
    ):
        return (
            False,
            "No BIDS subject/datatype structure was found under the selected root.",
        )
    return True, ""


def _has_bids_subject_structure_on_disk(
    path: Path,
    budget: _ScanBudget,
    *,
    scan_root: Path,
) -> bool:
    bids_datatype_dirs = {"eeg", "ieeg", "meg", "beh"}
    for subject_entry in budget.directory_entries(path):
        subject_dir = _admit_discovered_child(
            subject_entry,
            scan_root=scan_root,
            budget=budget,
        )
        if subject_dir is None or not subject_dir.is_dir():
            continue
        if not subject_dir.name.startswith("sub-"):
            continue
        if _has_admitted_bids_datatype_directory(
            subject_dir,
            bids_datatype_dirs=bids_datatype_dirs,
            scan_root=scan_root,
            budget=budget,
        ):
            return True
        for session_entry in budget.directory_entries(subject_dir):
            session_dir = _admit_discovered_child(
                session_entry,
                scan_root=scan_root,
                budget=budget,
            )
            if session_dir is None or not session_dir.is_dir():
                continue
            if _has_admitted_bids_datatype_directory(
                session_dir,
                bids_datatype_dirs=bids_datatype_dirs,
                scan_root=scan_root,
                budget=budget,
            ):
                return True
    return False


def _has_admitted_bids_datatype_directory(
    parent: Path,
    *,
    bids_datatype_dirs: set[str],
    scan_root: Path,
    budget: _ScanBudget,
) -> bool:
    for datatype_entry in budget.directory_entries(parent):
        datatype_dir = _admit_discovered_child(
            datatype_entry,
            scan_root=scan_root,
            budget=budget,
        )
        if (
            datatype_dir is not None
            and datatype_dir.is_dir()
            and datatype_dir.name in bids_datatype_dirs
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
            "BIDS folder detected during a regular folder import. Return to Import "
            "Data so subjects can be selected before review."
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
        f"{root}. Return to Import Data and choose that dataset root."
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
        return [f"{detail} Return to Import Data for regular EEG files."]
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
