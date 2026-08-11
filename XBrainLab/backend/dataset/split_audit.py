"""Audit helpers for train/validation/test split artifacts."""

from __future__ import annotations

import json
import platform
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import numpy as np

from XBrainLab.backend.supervised_readiness import (
    INSUFFICIENT_USABLE_CLASSES_KIND,
    MINIMUM_SUPERVISED_CLASS_COUNT,
    insufficient_usable_classes_message,
)
from XBrainLab.backend.utils.logger import logger

from .dataset import Dataset
from .epochs import EpochWindowProvenance, is_opaque_source_recording_id

EPOCH_WINDOW_INTERVAL_SEMANTICS = "half-open [start, end) samples"
MAX_DIAGNOSTIC_INDICES = 100
MAX_PROVENANCE_RECORDS = 100
MAX_PROVENANCE_SOURCE_SUMMARIES = 50
MAX_SELECTION_EVIDENCE_RECORDS = 100


@dataclass(frozen=True)
class SplitAuditIssue:
    """One split-audit issue."""

    dataset_name: str
    severity: str
    message: str
    indices: list[int] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SplitAuditResult:
    """Validation result for generated split datasets."""

    ok: bool
    dataset_count: int
    issues: list[SplitAuditIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "dataset_count": self.dataset_count,
            "issues": [asdict(issue) for issue in self.issues],
        }


def split_indices(dataset: Dataset) -> dict[str, list[int]]:
    """Return sorted train/validation/test indices for one dataset."""
    return {
        "train": _mask_indices(dataset.train_mask),
        "validation": _mask_indices(dataset.val_mask),
        "test": _mask_indices(dataset.test_mask),
    }


def audit_dataset_splits(
    datasets: list[Dataset],
    *,
    protocol: str = "trial-wise",
) -> SplitAuditResult:
    """Check split mutual exclusivity, leakage, and empty split risks."""
    issues: list[SplitAuditIssue] = []
    for dataset in datasets:
        name = dataset.get_name()
        train = set(_mask_indices(dataset.train_mask))
        val = set(_mask_indices(dataset.val_mask))
        test = set(_mask_indices(dataset.test_mask))

        for left_name, left, right_name, right in (
            ("train", train, "validation", val),
            ("train", train, "test", test),
            ("validation", val, "test", test),
        ):
            overlap = sorted(left & right)
            if overlap:
                issues.append(
                    SplitAuditIssue(
                        dataset_name=name,
                        severity="error",
                        message=(
                            f"{left_name} and {right_name} splits overlap; "
                            "this is data leakage."
                        ),
                        indices=overlap,
                    )
                )

        for split_name, values in (
            ("train", train),
            ("validation", val),
            ("test", test),
        ):
            if not values:
                issues.append(
                    SplitAuditIssue(
                        dataset_name=name,
                        severity="warning",
                        message=f"{split_name} split is empty.",
                    )
                )

        issues.extend(_class_coverage_issues(dataset))
        issues.extend(_group_leakage_issues(dataset, protocol=protocol))
        issues.extend(
            _epoch_window_leakage_issues(
                dataset,
                protocol=protocol,
            ),
        )

    return SplitAuditResult(
        ok=not any(issue.severity == "error" for issue in issues),
        dataset_count=len(datasets),
        issues=issues,
    )


def build_split_artifact(
    datasets: list[Dataset],
    *,
    seed: int | None = None,
    repeat: int | None = None,
    protocol: str = "trial-wise",
    extra_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable split artifact for rerun and audit."""
    audit = audit_dataset_splits(datasets, protocol=protocol)
    return {
        "schema_version": 1,
        "protocol": protocol,
        "seed": seed,
        "repeat": repeat,
        "audit": audit.to_dict(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "config": extra_config or {},
        "datasets": [
            {
                "name": dataset.get_name(),
                "selected": bool(dataset.is_selected),
                "indices": split_indices(dataset),
                "counts": {
                    "train": int(dataset.get_train_len()),
                    "validation": int(dataset.get_val_len()),
                    "test": int(dataset.get_test_len()),
                },
                "groups": _dataset_group_summary(dataset),
                "epoch_window_provenance": _epoch_window_provenance_artifact(
                    dataset,
                ),
                "trial_selection_evidence": _trial_selection_evidence_artifact(
                    dataset,
                ),
            }
            for dataset in datasets
        ],
    }


def write_split_artifact(
    datasets: list[Dataset],
    path: str | Path,
    *,
    seed: int | None = None,
    repeat: int | None = None,
    protocol: str = "trial-wise",
    extra_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a split artifact and return the emitted payload."""
    payload = build_split_artifact(
        datasets,
        seed=seed,
        repeat=repeat,
        protocol=protocol,
        extra_config=extra_config,
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _mask_indices(mask: np.ndarray) -> list[int]:
    return [int(idx) for idx in np.where(mask)[0]]


def _dataset_group_summary(dataset: Dataset) -> dict[str, dict[str, list[int]]]:
    epoch_data = dataset.get_epoch_data()
    result: dict[str, dict[str, list[int]]] = {}
    for split_name, mask in (
        ("train", dataset.train_mask),
        ("validation", dataset.val_mask),
        ("test", dataset.test_mask),
    ):
        result[split_name] = {
            "subjects": _unique_ints(epoch_data.get_subject_list_by_mask(mask)),
            "sessions": _unique_ints(epoch_data.get_session_list_by_mask(mask)),
            "labels": _unique_ints(epoch_data.get_label_list_by_mask(mask)),
        }
    return result


def _unique_ints(values: np.ndarray) -> list[int]:
    return [int(value) for value in sorted(set(np.asarray(values).tolist()))]


def _epoch_window_provenance(
    dataset: Dataset,
) -> tuple[list[EpochWindowProvenance | None], int]:
    """Return provenance aligned to dataset epoch indices and reported count."""
    expected_count = len(np.asarray(dataset.train_mask))
    epoch_data = dataset.get_epoch_data()
    getter = getattr(epoch_data, "get_epoch_window_provenance", None)
    if not callable(getter):
        return [None] * expected_count, 0

    try:
        raw_reported = getter()
        if not isinstance(raw_reported, Iterable):
            return [None] * expected_count, 0
        reported = list(raw_reported)
    except Exception:
        logger.debug("Failed to read epoch-window provenance", exc_info=True)
        return [None] * expected_count, 0

    aligned: list[EpochWindowProvenance | None] = []
    for index in range(expected_count):
        item = reported[index] if index < len(reported) else None
        aligned.append(item if _is_valid_epoch_window(item) else None)
    return aligned, len(reported)


def _is_valid_epoch_window(value: Any) -> bool:
    return (
        isinstance(value, EpochWindowProvenance)
        and is_opaque_source_recording_id(value.source_recording_id)
        and value.window_start_sample < value.window_end_sample_exclusive
        and np.isfinite(value.source_sfreq)
        and value.source_sfreq > 0
        and np.isfinite(value.epoch_sfreq)
        and value.epoch_sfreq > 0
    )


def _epoch_window_provenance_artifact(dataset: Dataset) -> dict[str, Any]:
    provenance, reported_count = _epoch_window_provenance(dataset)
    records: list[dict[str, Any]] = []
    records_digest = sha256()
    source_ids: set[str] = set()
    source_summaries: dict[str, dict[str, Any]] = {}
    record_count = 0
    verified_count = 0
    unverified_count = 0
    missing_count = 0
    missing_indices: list[int] = []
    unverified_indices: list[int] = []
    for index, item in enumerate(provenance):
        if item is None:
            missing_count += 1
            if len(missing_indices) < MAX_DIAGNOSTIC_INDICES:
                missing_indices.append(index)
            continue

        record = {"epoch_index": index, **asdict(item)}
        encoded = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        records_digest.update(len(encoded).to_bytes(8, "big"))
        records_digest.update(encoded)
        record_count += 1
        if len(records) < MAX_PROVENANCE_RECORDS:
            records.append(record)
        if item.source_coordinates_verified:
            verified_count += 1
        else:
            unverified_count += 1
            if len(unverified_indices) < MAX_DIAGNOSTIC_INDICES:
                unverified_indices.append(index)

        source_ids.add(item.source_recording_id)
        if (
            item.source_recording_id not in source_summaries
            and len(source_summaries) < MAX_PROVENANCE_SOURCE_SUMMARIES
        ):
            source_summaries[item.source_recording_id] = {
                "source_recording_id": item.source_recording_id,
                "record_count": 0,
                "verified_count": 0,
                "window_start_sample": item.window_start_sample,
                "window_end_sample_exclusive": item.window_end_sample_exclusive,
            }
        summary = source_summaries.get(item.source_recording_id)
        if summary is not None:
            summary["record_count"] += 1
            summary["verified_count"] += int(item.source_coordinates_verified)
            summary["window_start_sample"] = min(
                summary["window_start_sample"],
                item.window_start_sample,
            )
            summary["window_end_sample_exclusive"] = max(
                summary["window_end_sample_exclusive"],
                item.window_end_sample_exclusive,
            )

    if missing_count == 0 and unverified_count == 0:
        status = "complete"
    elif record_count == 0:
        status = "missing"
    elif missing_count == 0 and verified_count == 0:
        status = "unverified"
    else:
        status = "partial"
    return {
        "status": status,
        "interval_semantics": EPOCH_WINDOW_INTERVAL_SEMANTICS,
        "epoch_count": len(provenance),
        "reported_count": reported_count,
        "available_count": verified_count,
        "record_count": record_count,
        "records_emitted": len(records),
        "records_truncated": len(records) < record_count,
        "records_sha256": records_digest.hexdigest(),
        "verified_count": verified_count,
        "unverified_count": unverified_count,
        "unverified_indices": unverified_indices,
        "unverified_indices_truncated": len(unverified_indices) < unverified_count,
        "missing_count": missing_count,
        "missing_indices": missing_indices,
        "missing_indices_truncated": len(missing_indices) < missing_count,
        "source_count": len(source_ids),
        "source_summaries": list(source_summaries.values()),
        "source_summaries_truncated": len(source_summaries) < len(source_ids),
        "atomic_group_summary": _atomic_group_summary(dataset, len(provenance)),
        "records": records,
    }


def _atomic_group_summary(dataset: Dataset, epoch_count: int) -> dict[str, Any]:
    getter = getattr(dataset.get_epoch_data(), "get_trial_group_list", None)
    if not callable(getter):
        return {"available": False, "reason": "group provenance unavailable"}
    try:
        groups = np.asarray(getter(), dtype=np.int64)
    except Exception:
        logger.debug("Failed to read atomic trial groups", exc_info=True)
        return {"available": False, "reason": "group provenance unreadable"}
    if groups.ndim != 1 or len(groups) != epoch_count:
        return {"available": False, "reason": "group count mismatch"}
    _, counts = np.unique(groups, return_counts=True)
    group_digest = sha256(groups.astype("<i8", copy=False).tobytes()).hexdigest()
    return {
        "available": True,
        "group_count": len(counts),
        "non_singleton_group_count": int(np.sum(counts > 1)),
        "largest_group_size": int(counts.max()) if len(counts) else 0,
        "group_ids_sha256": group_digest,
    }


def _trial_selection_evidence_artifact(dataset: Dataset) -> dict[str, Any]:
    epoch_data = dataset.get_epoch_data()
    getter = getattr(epoch_data, "get_trial_selection_evidence", None)
    if not callable(getter):
        return {
            "record_count": 0,
            "records_emitted": 0,
            "records_truncated": False,
            "records": [],
        }
    try:
        raw_records = getter()
        all_records = list(raw_records) if isinstance(raw_records, Iterable) else []
    except Exception:
        logger.debug("Failed to read trial selection evidence", exc_info=True)
        all_records = []
    dropped_getter = getattr(
        epoch_data,
        "get_trial_selection_evidence_dropped",
        None,
    )
    raw_dropped = dropped_getter() if callable(dropped_getter) else 0
    if isinstance(raw_dropped, int):
        dropped = raw_dropped
    elif isinstance(raw_dropped, np.integer):
        dropped = int(cast(np.integer[Any], raw_dropped).item())
    else:
        dropped = 0
    records = all_records[-MAX_SELECTION_EVIDENCE_RECORDS:]
    record_count = dropped + len(all_records)
    return {
        "record_count": record_count,
        "records_emitted": len(records),
        "records_truncated": len(records) < record_count,
        "records": records,
    }


def _epoch_window_leakage_issues(
    dataset: Dataset,
    *,
    protocol: str,
) -> list[SplitAuditIssue]:
    provenance, reported_count = _epoch_window_provenance(dataset)
    missing_indices = [index for index, item in enumerate(provenance) if item is None]
    unverified_indices = [
        index
        for index, item in enumerate(provenance)
        if item is not None and not item.source_coordinates_verified
    ]
    unavailable_indices = sorted({*missing_indices, *unverified_indices})
    issues: list[SplitAuditIssue] = []
    if unavailable_indices:
        displayed_indices = unavailable_indices[:MAX_DIAGNOSTIC_INDICES]
        trial_wise = protocol.strip().lower() in {
            "trial",
            "trial-wise",
            "trialwise",
        }
        issues.append(
            SplitAuditIssue(
                dataset_name=dataset.get_name(),
                severity="error" if trial_wise else "warning",
                message=(
                    (
                        "Trial-wise split is blocked because temporal leakage "
                        "cannot be ruled out"
                        if trial_wise
                        else "Epoch-window leakage audit is incomplete"
                    )
                    + "; verified source-recording coordinates are unavailable "
                    f"for {len(unavailable_indices)} of {len(provenance)} "
                    "epoch(s)."
                ),
                indices=displayed_indices,
                details={
                    "kind": "missing_epoch_window_provenance",
                    "protocol": protocol,
                    "interval_semantics": EPOCH_WINDOW_INTERVAL_SEMANTICS,
                    "epoch_count": len(provenance),
                    "reported_count": reported_count,
                    "available_count": len(provenance) - len(unavailable_indices),
                    "missing_count": len(missing_indices),
                    "unverified_count": len(unverified_indices),
                    "unavailable_count": len(unavailable_indices),
                    "indices_truncated": len(displayed_indices)
                    < len(unavailable_indices),
                },
            ),
        )

    split_windows = _split_epoch_windows(dataset, provenance)
    for left_name, right_name in (
        ("train", "validation"),
        ("train", "test"),
        ("validation", "test"),
    ):
        overlaps: list[dict[str, Any]] = []
        common_sources = sorted(
            set(split_windows[left_name]) & set(split_windows[right_name]),
        )
        for source_id in common_sources:
            pair = _first_epoch_window_overlap(
                split_windows[left_name][source_id],
                split_windows[right_name][source_id],
            )
            if pair is None:
                continue
            left, right = pair
            overlaps.append(
                {
                    "source_recording_id": source_id,
                    "left_epoch_index": left[0],
                    "right_epoch_index": right[0],
                    "left_window": [
                        left[1].window_start_sample,
                        left[1].window_end_sample_exclusive,
                    ],
                    "right_window": [
                        right[1].window_start_sample,
                        right[1].window_end_sample_exclusive,
                    ],
                    "overlap_window": [
                        max(
                            left[1].window_start_sample,
                            right[1].window_start_sample,
                        ),
                        min(
                            left[1].window_end_sample_exclusive,
                            right[1].window_end_sample_exclusive,
                        ),
                    ],
                },
            )
            if len(overlaps) >= MAX_DIAGNOSTIC_INDICES:
                break

        if overlaps:
            indices = sorted(
                {
                    int(item[index_key])
                    for item in overlaps
                    for index_key in ("left_epoch_index", "right_epoch_index")
                },
            )
            issues.append(
                SplitAuditIssue(
                    dataset_name=dataset.get_name(),
                    severity="error",
                    message=(
                        f"{left_name} and {right_name} epoch windows overlap "
                        "within the same source recording; this is temporal "
                        "data leakage."
                    ),
                    indices=indices,
                    details={
                        "kind": "epoch_window_overlap",
                        "left_split": left_name,
                        "right_split": right_name,
                        "interval_semantics": EPOCH_WINDOW_INTERVAL_SEMANTICS,
                        "overlaps": overlaps,
                    },
                ),
            )
    return issues


def _split_epoch_windows(
    dataset: Dataset,
    provenance: list[EpochWindowProvenance | None],
) -> dict[str, dict[str, list[tuple[int, EpochWindowProvenance]]]]:
    result: dict[str, dict[str, list[tuple[int, EpochWindowProvenance]]]] = {}
    for split_name, mask in (
        ("train", dataset.train_mask),
        ("validation", dataset.val_mask),
        ("test", dataset.test_mask),
    ):
        by_source: dict[str, list[tuple[int, EpochWindowProvenance]]] = {}
        for index in _mask_indices(mask):
            item = provenance[index]
            if item is None or not item.source_coordinates_verified:
                continue
            by_source.setdefault(item.source_recording_id, []).append((index, item))
        result[split_name] = by_source
    return result


def _first_epoch_window_overlap(
    left: list[tuple[int, EpochWindowProvenance]],
    right: list[tuple[int, EpochWindowProvenance]],
) -> (
    tuple[
        tuple[int, EpochWindowProvenance],
        tuple[int, EpochWindowProvenance],
    ]
    | None
):
    left_sorted = sorted(
        left,
        key=lambda item: (
            item[1].window_start_sample,
            item[1].window_end_sample_exclusive,
            item[0],
        ),
    )
    right_sorted = sorted(
        right,
        key=lambda item: (
            item[1].window_start_sample,
            item[1].window_end_sample_exclusive,
            item[0],
        ),
    )
    left_index = 0
    right_index = 0
    while left_index < len(left_sorted) and right_index < len(right_sorted):
        left_item = left_sorted[left_index]
        right_item = right_sorted[right_index]
        left_window = left_item[1]
        right_window = right_item[1]
        if left_window.window_end_sample_exclusive <= right_window.window_start_sample:
            left_index += 1
        elif (
            right_window.window_end_sample_exclusive <= left_window.window_start_sample
        ):
            right_index += 1
        else:
            return left_item, right_item
    return None


def _class_coverage_issues(dataset: Dataset) -> list[SplitAuditIssue]:
    epoch_data = dataset.get_epoch_data()
    all_mask = np.ones_like(dataset.train_mask, dtype=bool)
    try:
        all_labels = _unique_ints(epoch_data.get_label_list_by_mask(all_mask))
    except Exception:
        logger.debug("Failed to read all labels for split audit", exc_info=True)
        return []
    if len(all_labels) < MINIMUM_SUPERVISED_CLASS_COUNT:
        return [
            SplitAuditIssue(
                dataset_name=dataset.get_name(),
                severity="error",
                message=insufficient_usable_classes_message(
                    str(label) for label in all_labels
                ),
                indices=list(range(len(np.asarray(dataset.train_mask)))),
                details={
                    "kind": INSUFFICIENT_USABLE_CLASSES_KIND,
                    "minimum_class_count": MINIMUM_SUPERVISED_CLASS_COUNT,
                    "usable_class_labels": all_labels,
                },
            )
        ]

    issues: list[SplitAuditIssue] = []
    for split_name, mask in (
        ("train", dataset.train_mask),
        ("validation", dataset.val_mask),
        ("test", dataset.test_mask),
    ):
        if not np.asarray(mask).any():
            continue
        try:
            present = set(_unique_ints(epoch_data.get_label_list_by_mask(mask)))
        except Exception:
            logger.debug(
                "Failed to read %s labels for split audit",
                split_name,
                exc_info=True,
            )
            continue
        missing = [label for label in all_labels if label not in present]
        if not missing:
            continue
        severity = "error" if split_name == "train" else "warning"
        missing_indices = _indices_for_labels(dataset, labels=missing)
        issues.append(
            SplitAuditIssue(
                dataset_name=dataset.get_name(),
                severity=severity,
                message=(
                    f"{split_name} split is missing class label(s) "
                    f"{', '.join(str(label) for label in missing)}."
                ),
                indices=missing_indices,
            )
        )
    return issues


def _indices_for_labels(dataset: Dataset, *, labels: list[int]) -> list[int]:
    epoch_data = dataset.get_epoch_data()
    all_mask = np.ones_like(dataset.train_mask, dtype=bool)
    try:
        label_values = np.asarray(epoch_data.get_label_list_by_mask(all_mask))
    except Exception:
        return []
    label_set = {int(label) for label in labels}
    return [
        int(idx)
        for idx, value in enumerate(label_values.tolist())
        if int(value) in label_set
    ]


def _group_leakage_issues(
    dataset: Dataset,
    *,
    protocol: str,
) -> list[SplitAuditIssue]:
    normalized = protocol.strip().lower()
    if normalized in {"trial", "trial-wise", "trialwise"}:
        return []

    if normalized in {"subject", "subject-wise", "subjectwise"}:
        groups = _split_groups(dataset, key="subject")
        label = "subject"
    elif normalized in {"session", "session-wise", "sessionwise"}:
        groups = _split_groups(dataset, key="session")
        label = "session"
    else:
        return [
            SplitAuditIssue(
                dataset_name=dataset.get_name(),
                severity="warning",
                message=(
                    f"Unknown split protocol '{protocol}'; group leakage was not "
                    "audited."
                ),
            )
        ]

    issues: list[SplitAuditIssue] = []
    for left_name, right_name in (
        ("train", "validation"),
        ("train", "test"),
        ("validation", "test"),
    ):
        overlap = sorted(groups[left_name] & groups[right_name])
        if overlap:
            issues.append(
                SplitAuditIssue(
                    dataset_name=dataset.get_name(),
                    severity="error",
                    message=(
                        f"{label} groups overlap between {left_name} and "
                        f"{right_name}; this violates {protocol} validation."
                    ),
                    indices=_indices_for_groups(
                        dataset,
                        groups=overlap,
                        key=label,
                    ),
                )
            )
    return issues


def _split_groups(dataset: Dataset, *, key: str) -> dict[str, set[Any]]:
    epoch_data = dataset.get_epoch_data()
    result: dict[str, set[Any]] = {}
    for split_name, mask in (
        ("train", dataset.train_mask),
        ("validation", dataset.val_mask),
        ("test", dataset.test_mask),
    ):
        if key == "subject":
            result[split_name] = {
                int(value)
                for value in np.asarray(
                    epoch_data.get_subject_list_by_mask(mask),
                ).tolist()
            }
        else:
            subjects = np.asarray(epoch_data.get_subject_list_by_mask(mask)).tolist()
            sessions = np.asarray(epoch_data.get_session_list_by_mask(mask)).tolist()
            result[split_name] = {
                (int(subject), int(session))
                for subject, session in zip(subjects, sessions, strict=False)
            }
    return result


def _indices_for_groups(
    dataset: Dataset,
    *,
    groups: list[Any],
    key: str,
) -> list[int]:
    epoch_data = dataset.get_epoch_data()
    all_mask = np.ones_like(dataset.train_mask, dtype=bool)
    if key == "subject":
        subject_values = np.asarray(epoch_data.get_subject_list_by_mask(all_mask))
        subject_group_set = {int(group) for group in groups}
        return [
            int(idx)
            for idx, value in enumerate(subject_values.tolist())
            if int(value) in subject_group_set
        ]

    subjects = np.asarray(epoch_data.get_subject_list_by_mask(all_mask))
    sessions = np.asarray(epoch_data.get_session_list_by_mask(all_mask))
    session_group_set = {(int(subject), int(session)) for subject, session in groups}
    return [
        int(idx)
        for idx, pair in enumerate(
            zip(subjects.tolist(), sessions.tolist(), strict=False),
        )
        if (int(pair[0]), int(pair[1])) in session_group_set
    ]
