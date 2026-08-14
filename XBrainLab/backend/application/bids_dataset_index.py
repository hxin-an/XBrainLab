"""Immutable, bounded filesystem index for one explicitly selected BIDS root."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from types import MappingProxyType
from typing import Any

from .data_interpretation_bids_resources import (
    bids_events_json_candidates,
    is_bids_events_file,
    is_bids_events_json_sidecar,
)
from .data_interpretation_formats import SUPPORTED_EEG_EXTENSIONS
from .data_interpretation_metadata import extract_bids_entity, relative_text
from .owned_work import owned_work_checkpoint

_INDEX_REGISTRY_LIMIT = 4
_INDEX_REGISTRY_LOCK = RLock()
_INDEX_REGISTRY: dict[str, BidsDatasetIndex] = {}


@dataclass(frozen=True)
class BidsDatasetCompleteness:
    """Bounded discovery outcome independent from metadata payload parsing."""

    complete: bool
    traversal_complete: bool
    blocked_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BidsRecording:
    """One indexed raw EEG recording and its local BIDS entities/sidecars."""

    file: str
    relative_path: str
    subject: str
    session: str
    task: str
    run: str
    acquisition: str
    datatype: str
    events_file: str = ""
    channels_file: str = ""
    electrodes_files: tuple[str, ...] = ()
    coordsystem_files: tuple[str, ...] = ()
    json_sidecar_files: tuple[str, ...] = ()

    def to_layout_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "name": Path(self.file).name,
            "relative_path": self.relative_path,
            "subject": self.subject,
            "session": self.session,
            "task": self.task,
            "run": self.run,
            "datatype": self.datatype,
            "events_file": self.events_file,
            "channels_file": self.channels_file,
        }


@dataclass(frozen=True)
class BidsSubjectEntry:
    """One subject catalog row derived from indexed recordings."""

    subject: str
    eeg_file_count: int
    sessions: tuple[str, ...]
    tasks: tuple[str, ...]
    runs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "label": f"sub-{self.subject}",
            "eeg_file_count": self.eeg_file_count,
            "sessions": list(self.sessions),
            "tasks": list(self.tasks),
            "runs": list(self.runs),
        }


@dataclass(frozen=True)
class _IndexedPathIdentity:
    path: str
    kind: str
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def capture(cls, path: Path) -> _IndexedPathIdentity:
        status = path.stat()
        kind = "directory" if stat.S_ISDIR(status.st_mode) else "file"
        return cls(
            path=str(path),
            kind=kind,
            device=int(status.st_dev),
            inode=int(status.st_ino),
            size=int(status.st_size),
            modified_ns=int(status.st_mtime_ns),
            changed_ns=int(status.st_ctime_ns),
        )

    def still_matches(self) -> bool:
        path = Path(self.path)
        try:
            if path.is_symlink():
                return False
            observed = self.capture(path)
        except (OSError, RuntimeError):
            return False
        return observed == self


@dataclass(frozen=True)
class BidsDatasetProjection:
    """Immutable selected-subject projection from a complete dataset index."""

    root: str
    selected_subjects: tuple[str, ...]
    all_files: tuple[str, ...]
    eeg_files: tuple[str, ...]
    events_files: tuple[str, ...]
    channels_files: tuple[str, ...]
    electrodes_files: tuple[str, ...]
    coordsystem_files: tuple[str, ...]
    json_sidecar_files: tuple[str, ...]
    metadata_files: tuple[str, ...]
    _events_json_by_carrier: tuple[tuple[str, tuple[str, ...]], ...]
    recordings: tuple[BidsRecording, ...]

    @property
    def layout(self) -> tuple[dict[str, Any], ...]:
        return tuple(recording.to_layout_dict() for recording in self.recordings)

    @property
    def events_json_by_carrier(self) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType(dict(self._events_json_by_carrier))

    @property
    def events_json_catalog(self) -> dict[str, tuple[str, ...]]:
        return dict(self._events_json_by_carrier)


@dataclass(frozen=True)
class BidsDatasetIndex:
    """One immutable result of resolving and walking one formal BIDS root."""

    root: str
    selection_root: str
    nested_bids_candidates: tuple[str, ...]
    root_validation_issue: str
    root_files: tuple[str, ...]
    subject_files: tuple[tuple[str, tuple[str, ...]], ...]
    subjects: tuple[BidsSubjectEntry, ...]
    recordings: tuple[BidsRecording, ...]
    skipped_nested_bids_roots: tuple[str, ...]
    metadata_discovery: tuple[tuple[str, int | bool], ...]
    warnings: tuple[str, ...]
    completeness: BidsDatasetCompleteness
    _identities: tuple[_IndexedPathIdentity, ...]

    @property
    def looks_like_bids(self) -> bool:
        return not self.root_validation_issue

    def matches_root(self, source_path: str | Path) -> bool:
        try:
            candidate = Path(source_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            return False
        return candidate.is_dir() and _path_key(candidate) in {
            _path_key(Path(self.root)),
            _path_key(Path(self.selection_root)),
        }

    def is_current(self) -> bool:
        """Recheck retained directory identities without walking the tree."""
        return bool(self._identities) and all(
            identity.still_matches() for identity in self._identities
        )

    @property
    def indexed_files(self) -> tuple[str, ...]:
        return _unique_sorted(
            [
                *self.root_files,
                *(
                    path
                    for _subject, subject_paths in self.subject_files
                    for path in subject_paths
                ),
            ]
        )

    def indexed_file_in_recording_directory(
        self,
        recording_path: str | Path,
        relative_dependency: str | Path,
    ) -> str | None:
        """Resolve one listed same-directory parser dependency without a walk."""
        recording = Path(recording_path).expanduser()
        if not self.contains_recording(recording):
            return None
        dependency = Path(relative_dependency)
        if dependency.is_absolute() or len(dependency.parts) != 1:
            return None
        candidate_key = _path_key(recording.parent / dependency)
        for indexed_path in self.indexed_files:
            if _path_key(Path(indexed_path)) == candidate_key:
                return indexed_path
        return None

    def contains_recording(self, recording_path: str | Path) -> bool:
        """Return whether a path is one of this exact index's raw recordings."""
        candidate_key = _path_key(Path(recording_path))
        return any(
            _path_key(Path(item.file)) == candidate_key for item in self.recordings
        )

    def subject_catalog(self) -> dict[str, Any]:
        rows = [subject.to_dict() for subject in self.subjects]
        warnings = list(self.warnings)
        if not rows:
            warnings.append("No top-level sub-* folders were found in this BIDS root.")
        if rows and not any(row["eeg_file_count"] for row in rows):
            warnings.append(
                "No supported raw EEG files were found in the BIDS subjects."
            )
        return {
            "root": self.root,
            "selection_root": self.selection_root,
            "resolved_nested_root": self.root != self.selection_root,
            "nested_bids_candidates": list(self.nested_bids_candidates),
            "subject_count": len(rows),
            "eeg_file_count": sum(int(row["eeg_file_count"]) for row in rows),
            "subjects": rows,
            "warnings": list(dict.fromkeys(warnings)),
        }

    @property
    def metadata_discovery_diagnostics(self) -> dict[str, int | bool]:
        return dict(self.metadata_discovery)

    def project(
        self,
        selected_subjects: list[str] | tuple[str, ...] | None = None,
    ) -> BidsDatasetProjection:
        available = {subject.subject for subject in self.subjects}
        requested = _normalize_subjects(selected_subjects)
        if requested:
            missing = [subject for subject in requested if subject not in available]
            if missing:
                raise ValueError(
                    "Selected BIDS subject folder was not found: "
                    + ", ".join(f"sub-{subject}" for subject in missing)
                )
            selected = tuple(requested)
        else:
            selected = tuple(subject.subject for subject in self.subjects)

        files_by_subject = dict(self.subject_files)
        projected_subject_files = (
            file_path
            for subject in selected
            for file_path in files_by_subject.get(subject, ())
            if not self.looks_like_bids
            or _is_projected_bids_eeg_resource(Path(file_path), Path(self.root))
        )
        selected_files = _unique_sorted(
            [
                *self.root_files,
                *projected_subject_files,
            ]
        )
        selected_set = {_path_key(Path(path)) for path in selected_files}
        recordings = tuple(
            recording for recording in self.recordings if recording.subject in selected
        )
        eeg_files = tuple(recording.file for recording in recordings)
        events_files = _unique_sorted(
            path for path in selected_files if is_bids_events_file(Path(path))
        )
        channels_files = _unique_sorted(
            recording.channels_file
            for recording in recordings
            if recording.channels_file
        )
        electrodes_files = _files_with_suffix(
            selected_files,
            names=("electrodes.tsv",),
            suffixes=("_electrodes.tsv",),
        )
        coordsystem_files = _files_with_suffix(
            selected_files,
            names=("coordsystem.json",),
            suffixes=("_coordsystem.json",),
        )
        json_sidecars = tuple(
            path
            for path in selected_files
            if Path(path).suffix.casefold() == ".json"
            and Path(path).name != "dataset_description.json"
        )
        dataset_description = str(Path(self.root) / "dataset_description.json")
        participants = str(Path(self.root) / "participants.tsv")
        metadata_files = _unique_preserving_order(
            [
                *(
                    path
                    for path in (dataset_description, participants)
                    if path in selected_files
                ),
                *channels_files,
                *electrodes_files,
                *coordsystem_files,
                *json_sidecars,
            ]
        )
        indexed_json = {
            _path_key(Path(path)): path
            for path in json_sidecars
            if is_bids_events_json_sidecar(Path(path))
        }
        events_json_by_carrier: list[tuple[str, tuple[str, ...]]] = []
        for carrier in events_files:
            sidecars = _unique_preserving_order(
                indexed_json[key]
                for candidate in bids_events_json_candidates(Path(carrier))
                if (key := _path_key(candidate)) in indexed_json and key in selected_set
            )
            events_json_by_carrier.append((carrier, sidecars))
        return BidsDatasetProjection(
            root=self.root,
            selected_subjects=selected,
            all_files=selected_files,
            eeg_files=eeg_files,
            events_files=events_files,
            channels_files=channels_files,
            electrodes_files=electrodes_files,
            coordsystem_files=coordsystem_files,
            json_sidecar_files=json_sidecars,
            metadata_files=metadata_files,
            _events_json_by_carrier=tuple(events_json_by_carrier),
            recordings=recordings,
        )


def build_bids_dataset_index(
    source_path: str | Path,
    *,
    _scan_budget: Any | None = None,
) -> BidsDatasetIndex:
    """Resolve and walk one unambiguous BIDS root under one shared budget."""
    from .data_interpretation_scan import (  # noqa: PLC0415
        _admit_discovered_child,
        _candidate_files,
        _has_supported_suffix,
        _is_raw_bids_eeg_scope_path,
        _provisional_bids_root,
        _ScanBudget,
    )

    selected = Path(source_path).expanduser()
    if not selected.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")
    selection_root = selected.resolve(strict=True)
    if not selection_root.is_dir():
        raise ValueError("The selected BIDS source is not a folder.")

    owned_work_checkpoint("Indexing BIDS root")
    budget = _scan_budget or _ScanBudget()
    root = selection_root
    looks_like_bids, root_issue = _provisional_bids_root(
        root,
        budget,
        scan_root=root,
    )
    nested_candidates: tuple[Path, ...] = ()
    exact_marker_present = _bids_root_marker_entry_exists(selection_root)
    nested_resolution_blocked = False
    if not looks_like_bids and not exact_marker_present:
        nested_candidates = _discover_nested_bids_roots(
            selection_root,
            budget=budget,
            admit_child=_admit_discovered_child,
            provisional_root=_provisional_bids_root,
        )
        if len(nested_candidates) == 1 and budget.traversal_complete:
            root = nested_candidates[0]
            looks_like_bids, root_issue = _provisional_bids_root(
                root,
                budget,
                scan_root=selection_root,
            )
        elif len(nested_candidates) > 1:
            nested_resolution_blocked = True
            root_issue = (
                "Multiple nested BIDS roots were found under the selected "
                "folder; select exactly one dataset root: "
                + ", ".join(str(path) for path in nested_candidates)
                + "."
            )
        elif not budget.traversal_complete:
            nested_resolution_blocked = True
            root_issue = (
                "A bounded traversal could not prove that the selected folder "
                "contains exactly one nested BIDS root; choose the exact dataset "
                "root."
            )
        else:
            root_issue = (
                "dataset_description.json is missing from the selected BIDS root, "
                "and no nested formal BIDS root was found."
            )
    skipped_nested_roots: list[Path] = []
    discovered = (
        []
        if nested_resolution_blocked
        else _candidate_files(
            root,
            skip_nested_bids_roots=True,
            skipped_bids_roots=skipped_nested_roots,
            budget=budget,
            scan_root=root,
        )
    )
    owned_work_checkpoint(
        "Classifying BIDS resources",
        completed=budget.files_collected,
        total=max(budget.files_collected, 1),
    )
    files = _unique_sorted(str(path) for path in discovered)
    root_files: list[str] = []
    files_by_subject: dict[str, list[str]] = {}
    for file_path in files:
        relative = Path(file_path).relative_to(root)
        if len(relative.parts) == 1:
            root_files.append(file_path)
            continue
        first = relative.parts[0]
        if first.startswith("sub-") and len(first) > 4:
            files_by_subject.setdefault(first[4:], []).append(file_path)

    subject_names: set[str] = set(files_by_subject)
    for entry in budget.directory_entries(root):
        admitted = _admit_discovered_child(
            entry,
            scan_root=root,
            budget=budget,
        )
        if (
            admitted is not None
            and admitted.is_dir()
            and admitted.name.startswith("sub-")
            and len(admitted.name) > 4
        ):
            subject_names.add(admitted.name[4:])

    recordings_paths = [
        Path(path)
        for path in files
        if _is_raw_bids_eeg_scope_path(Path(path), root)
        and _has_supported_suffix(Path(path), SUPPORTED_EEG_EXTENSIONS)
    ]
    indexed_paths = {_path_key(Path(path)): path for path in files}
    files_by_directory: dict[str, list[str]] = {}
    for file_path in files:
        files_by_directory.setdefault(str(Path(file_path).parent), []).append(file_path)
    recording_rows: list[BidsRecording] = []
    for index, path in enumerate(sorted(recordings_paths), start=1):
        owned_work_checkpoint(
            "Indexing BIDS recordings",
            completed=index,
            total=max(len(recordings_paths), 1),
        )
        recording_rows.append(
            _recording_from_path(
                path,
                root=root,
                directory_files=tuple(files_by_directory.get(str(path.parent), ())),
                indexed_paths=indexed_paths,
            )
        )
    recordings = tuple(recording_rows)
    subjects = tuple(
        _subject_entry(subject, recordings)
        for subject in sorted(subject_names, key=_natural_key)
    )
    warnings = list(budget.warnings)
    warnings.extend(
        f"Nested BIDS root was excluded from the selected dataset index: {path}."
        for path in skipped_nested_roots
    )
    blocked: list[str] = []
    if root_issue:
        blocked.append(root_issue)
    if looks_like_bids and not recordings:
        blocked.append("No supported raw EEG recordings were found in this BIDS root.")
    if not budget.traversal_complete:
        blocked.append(
            "BIDS dataset indexing stopped at a bounded traversal limit; choose a "
            "narrower or smaller explicit BIDS root."
        )
    completeness = BidsDatasetCompleteness(
        complete=not blocked,
        traversal_complete=budget.traversal_complete,
        blocked_reasons=tuple(dict.fromkeys(blocked)),
    )
    # Directory identities invalidate path projections on additions, removals,
    # renames, and substitutions without restating every indexed file on each
    # cache lookup. Payload freshness remains owned by resource admission.
    identity_paths = _unique_sorted(
        [str(selection_root), str(root), *budget.traversed_directories]
    )
    identities: list[_IndexedPathIdentity] = []
    for index, path in enumerate(identity_paths, start=1):
        owned_work_checkpoint(
            "Capturing BIDS resource identities",
            completed=index,
            total=max(len(identity_paths), 1),
        )
        try:
            identities.append(_IndexedPathIdentity.capture(Path(path)))
        except OSError:
            completeness = BidsDatasetCompleteness(
                complete=False,
                traversal_complete=completeness.traversal_complete,
                blocked_reasons=tuple(
                    dict.fromkeys(
                        [
                            *completeness.blocked_reasons,
                            f"Indexed BIDS path identity became unavailable: {path}.",
                        ]
                    )
                ),
            )
    changed_directories = budget.revalidate_traversed_directories()
    if changed_directories:
        completeness = BidsDatasetCompleteness(
            complete=False,
            traversal_complete=False,
            blocked_reasons=tuple(
                dict.fromkeys(
                    [
                        *completeness.blocked_reasons,
                        (
                            "One or more traversed BIDS directories changed while "
                            "the BIDS index was being built; retry after filesystem "
                            "changes stop."
                        ),
                    ]
                )
            ),
        )
        # Never let post-enumeration identities make a stale inventory appear
        # current. An empty seal also prevents registry reuse of this result.
        identities.clear()
    result = BidsDatasetIndex(
        root=str(root),
        selection_root=str(selection_root),
        nested_bids_candidates=tuple(str(path) for path in nested_candidates),
        root_validation_issue=root_issue,
        root_files=_unique_sorted(root_files),
        subject_files=tuple(
            (subject, _unique_sorted(paths))
            for subject, paths in sorted(
                files_by_subject.items(),
                key=lambda item: _natural_key(item[0]),
            )
        ),
        subjects=subjects,
        recordings=recordings,
        skipped_nested_bids_roots=tuple(str(path) for path in skipped_nested_roots),
        metadata_discovery=tuple(budget.metadata_discovery_diagnostics().items()),
        warnings=tuple(dict.fromkeys(warnings)),
        completeness=completeness,
        _identities=tuple(identities),
    )
    if result.is_current():
        remember_bids_dataset_index(result)
    return result


def remember_bids_dataset_index(index: BidsDatasetIndex) -> None:
    """Publish one bounded index for later backend consumers in this process."""
    with _INDEX_REGISTRY_LOCK:
        for path in (index.selection_root, index.root):
            _INDEX_REGISTRY[_path_key(Path(path))] = index
        while len({item.root for item in _INDEX_REGISTRY.values()}) > (
            _INDEX_REGISTRY_LIMIT
        ):
            _INDEX_REGISTRY.pop(next(iter(_INDEX_REGISTRY)))


def current_bids_dataset_index_for_path(
    source_path: str | Path,
) -> BidsDatasetIndex | None:
    """Return the deepest current index containing a source path, if retained."""
    try:
        candidate = Path(source_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    with _INDEX_REGISTRY_LOCK:
        matches = sorted(
            (
                index
                for index in _INDEX_REGISTRY.values()
                if candidate == Path(index.root)
                or candidate.is_relative_to(Path(index.root))
                or candidate == Path(index.selection_root)
            ),
            key=lambda index: len(Path(index.root).parts),
            reverse=True,
        )
        for index in matches:
            if any(
                candidate == Path(nested_root)
                or candidate.is_relative_to(Path(nested_root))
                for nested_root in index.skipped_nested_bids_roots
            ):
                continue
            is_current = index.is_current()
            if index.looks_like_bids and is_current:
                return index
            if not is_current:
                _INDEX_REGISTRY.pop(_path_key(Path(index.root)), None)
    return None


def _bids_root_marker_entry_exists(path: Path) -> bool:
    """Treat any exact-root marker entry as explicit ownership, even if unsafe."""
    try:
        (path / "dataset_description.json").lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _discover_nested_bids_roots(
    selection_root: Path,
    *,
    budget: Any,
    admit_child: Any,
    provisional_root: Any,
) -> tuple[Path, ...]:
    """Find topmost formal nested roots without following substitutions."""
    candidates: list[Path] = []

    def _visit(directory: Path, depth: int) -> None:
        if depth >= budget.max_depth:
            budget.warn_once(
                f"depth:{directory}",
                (
                    "Source scan skipped folders deeper than "
                    f"{budget.max_depth} levels: {directory}."
                ),
            )
            return
        owned_work_checkpoint(
            "Resolving nested BIDS root",
            completed=budget.entries_visited,
        )
        for entry in budget.directory_entries(directory):
            admitted = admit_child(
                entry,
                scan_root=selection_root,
                budget=budget,
            )
            if admitted is None or not admitted.is_dir():
                continue
            is_formal_root, _issue = provisional_root(
                admitted,
                budget,
                scan_root=selection_root,
            )
            if is_formal_root:
                candidates.append(admitted)
                continue
            _visit(admitted, depth + 1)

    _visit(selection_root, 0)
    return tuple(sorted(candidates, key=lambda path: _path_key(path)))


def _recording_from_path(
    path: Path,
    *,
    root: Path,
    directory_files: tuple[str, ...],
    indexed_paths: dict[str, str],
) -> BidsRecording:
    relative = relative_text(path, root)
    stem = _bids_raw_stem(path)
    electrodes = _files_with_suffix(
        directory_files,
        names=("electrodes.tsv",),
        suffixes=("_electrodes.tsv",),
    )
    coordsystem = _files_with_suffix(
        directory_files,
        names=("coordsystem.json",),
        suffixes=("_coordsystem.json",),
    )
    json_sidecars = tuple(
        value
        for value in directory_files
        if Path(value).suffix.casefold() == ".json"
        and Path(value).name != "dataset_description.json"
    )
    return BidsRecording(
        file=str(path),
        relative_path=relative,
        subject=extract_bids_entity(relative, "sub") or "",
        session=extract_bids_entity(relative, "ses") or "",
        task=extract_bids_entity(relative, "task") or "",
        run=extract_bids_entity(relative, "run") or "",
        acquisition=extract_bids_entity(relative, "acq") or "",
        datatype="eeg" if "/eeg/" in f"/{relative}/" else "",
        events_file=indexed_paths.get(
            _path_key(path.with_name(f"{stem}_events.tsv")),
            "",
        ),
        channels_file=indexed_paths.get(
            _path_key(path.with_name(f"{stem}_channels.tsv")),
            "",
        ),
        electrodes_files=electrodes,
        coordsystem_files=coordsystem,
        json_sidecar_files=json_sidecars,
    )


def _subject_entry(
    subject: str,
    recordings: tuple[BidsRecording, ...],
) -> BidsSubjectEntry:
    selected = tuple(row for row in recordings if row.subject == subject)
    return BidsSubjectEntry(
        subject=subject,
        eeg_file_count=len(selected),
        sessions=tuple(
            sorted(
                {row.session for row in selected if row.session},
                key=_natural_key,
            )
        ),
        tasks=tuple(
            sorted(
                {row.task for row in selected if row.task},
                key=str.casefold,
            )
        ),
        runs=tuple(sorted({row.run for row in selected if row.run}, key=_natural_key)),
    )


def _normalize_subjects(
    values: list[str] | tuple[str, ...] | None,
) -> list[str]:
    result: list[str] = []
    for raw_value in values or ():
        value = str(raw_value).strip()
        if value.casefold().startswith("sub-"):
            value = value[4:]
        if value and value not in result:
            result.append(value)
    return result


def _files_with_suffix(
    files: tuple[str, ...],
    *,
    names: tuple[str, ...],
    suffixes: tuple[str, ...],
) -> tuple[str, ...]:
    normalized_names = {name.casefold() for name in names}
    normalized_suffixes = tuple(suffix.casefold() for suffix in suffixes)
    return tuple(
        path
        for path in files
        if Path(path).name.casefold() in normalized_names
        or Path(path).name.casefold().endswith(normalized_suffixes)
    )


def _bids_raw_stem(path: Path) -> str:
    name = path.name
    stem = name[: -len(".fif.gz")] if name.casefold().endswith(".fif.gz") else path.stem
    for suffix in ("_eeg", "_raw"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _is_projected_bids_eeg_resource(path: Path, root: Path) -> bool:
    """Keep raw EEG resources and their inherited EEG/events JSON sidecars."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    if len(parts) < 2 or not parts[0].startswith("sub-"):
        return False
    directories = parts[:-1]
    if "eeg" in directories:
        return True
    if any(datatype in directories for datatype in ("beh", "ieeg", "meg")):
        return False
    name = path.name.casefold()
    return name in {
        "events.tsv",
        "channels.tsv",
        "electrodes.tsv",
        "events.json",
        "eeg.json",
        "coordsystem.json",
    } or name.endswith(
        (
            "_events.tsv",
            "_channels.tsv",
            "_electrodes.tsv",
            "_events.json",
            "_eeg.json",
            "_coordsystem.json",
        )
    )


def _path_key(path: Path) -> str:
    # Indexed paths and inheritance candidates are already anchored below the
    # canonical selected root. Avoid another NTFS lstat chain for every lookup.
    return os.path.normcase(os.path.abspath(os.fspath(path.expanduser())))


def _unique_sorted(values: Iterable[str | Path]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def _unique_preserving_order(values: Iterable[str | Path]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


def _natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
        if part
    )
