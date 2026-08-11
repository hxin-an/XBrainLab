"""Lightweight BIDS subject discovery before full Data Interpretation scan."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .data_interpretation_formats import SUPPORTED_EEG_EXTENSIONS

_MAX_CATALOG_ENTRIES = 20_000
_MAX_SUBJECT_DEPTH = 5
_ENTITY_PATTERN = re.compile(
    r"(?:^|_)(?P<key>sub|ses|task|run)-(?P<value>[^_]+)",
    re.IGNORECASE,
)


def inspect_bids_subject_catalog(source_path: str | Path) -> dict[str, Any]:
    """Return BIDS subject summaries without opening EEG or tabular payloads."""
    root = Path(source_path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("The selected BIDS source is not a folder.")
    if not (root / "dataset_description.json").is_file():
        raise ValueError(
            "The selected folder is not a BIDS root: "
            "dataset_description.json is missing."
        )

    warnings: list[str] = []
    subjects: list[dict[str, Any]] = []
    entry_budget = [_MAX_CATALOG_ENTRIES]
    for subject_dir in _subject_directories(root):
        entities = {
            "sessions": set(),
            "tasks": set(),
            "runs": set(),
        }
        eeg_files = 0
        for path in _bounded_files(subject_dir, entry_budget=entry_budget):
            if not _is_bids_eeg_file(path, subject_dir):
                continue
            eeg_files += 1
            parsed = _filename_entities(path.name)
            if parsed.get("ses"):
                entities["sessions"].add(parsed["ses"])
            if parsed.get("task"):
                entities["tasks"].add(parsed["task"])
            if parsed.get("run"):
                entities["runs"].add(parsed["run"])

        subject = subject_dir.name[4:]
        subjects.append(
            {
                "subject": subject,
                "label": subject_dir.name,
                "eeg_file_count": eeg_files,
                "sessions": sorted(entities["sessions"], key=_natural_key),
                "tasks": sorted(entities["tasks"], key=str.casefold),
                "runs": sorted(entities["runs"], key=_natural_key),
            }
        )
        if entry_budget[0] <= 0:
            warnings.append(
                "BIDS subject discovery stopped at its bounded directory-entry limit."
            )
            break

    subjects.sort(key=lambda item: _natural_key(str(item["subject"])))
    if not subjects:
        warnings.append("No top-level sub-* folders were found in this BIDS root.")
    if subjects and not any(item["eeg_file_count"] for item in subjects):
        warnings.append("No supported raw EEG files were found in the BIDS subjects.")
    return {
        "root": str(root),
        "subject_count": len(subjects),
        "eeg_file_count": sum(int(item["eeg_file_count"]) for item in subjects),
        "subjects": subjects,
        "warnings": warnings,
    }


def _subject_directories(root: Path) -> list[Path]:
    directories: list[Path] = []
    with os.scandir(root) as entries:
        for entry in entries:
            if not entry.name.startswith("sub-") or entry.is_symlink():
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    directories.append(Path(entry.path).resolve(strict=True))
            except OSError:
                continue
    return sorted(directories, key=lambda path: _natural_key(path.name[4:]))


def _bounded_files(
    root: Path,
    *,
    entry_budget: list[int],
    depth: int = 0,
):
    if depth >= _MAX_SUBJECT_DEPTH or entry_budget[0] <= 0:
        return
    try:
        entries = os.scandir(root)
    except OSError:
        return
    with entries:
        for entry in entries:
            entry_budget[0] -= 1
            if entry_budget[0] < 0:
                return
            if entry.is_symlink():
                continue
            path = Path(entry.path)
            try:
                if entry.is_file(follow_symlinks=False):
                    yield path.resolve(strict=True)
                elif entry.is_dir(follow_symlinks=False):
                    yield from _bounded_files(
                        path,
                        entry_budget=entry_budget,
                        depth=depth + 1,
                    )
            except OSError:
                continue


def _is_bids_eeg_file(path: Path, subject_root: Path) -> bool:
    normalized = path.name.casefold()
    if not normalized.endswith(
        tuple(suffix.casefold() for suffix in SUPPORTED_EEG_EXTENSIONS)
    ):
        return False
    if "_eeg." not in normalized:
        return False
    try:
        relative_parts = path.relative_to(subject_root).parts
    except ValueError:
        return False
    return "eeg" in relative_parts[:-1]


def _filename_entities(filename: str) -> dict[str, str]:
    return {
        match.group("key").casefold(): match.group("value")
        for match in _ENTITY_PATTERN.finditer(filename)
    }


def _natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
        if part
    )
