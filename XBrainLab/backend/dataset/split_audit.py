"""Audit helpers for train/validation/test split artifacts."""

from __future__ import annotations

import json
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .dataset import Dataset


@dataclass(frozen=True)
class SplitAuditIssue:
    """One split-audit issue."""

    dataset_name: str
    severity: str
    message: str
    indices: list[int] = field(default_factory=list)


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

        issues.extend(_group_leakage_issues(dataset, protocol=protocol))

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
        group_set = {int(group) for group in groups}
        return [
            int(idx)
            for idx, value in enumerate(subject_values.tolist())
            if int(value) in group_set
        ]

    subjects = np.asarray(epoch_data.get_subject_list_by_mask(all_mask))
    sessions = np.asarray(epoch_data.get_session_list_by_mask(all_mask))
    group_set = {(int(subject), int(session)) for subject, session in groups}
    return [
        int(idx)
        for idx, pair in enumerate(
            zip(subjects.tolist(), sessions.tolist(), strict=False),
        )
        if (int(pair[0]), int(pair[1])) in group_set
    ]
