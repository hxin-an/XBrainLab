#!/usr/bin/env python3
"""Validate thesis split-artifact structure and leakage audit fields."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate_artifact(payload: dict[str, Any]) -> list[str]:
    """Return validation errors for a split artifact payload."""
    errors: list[str] = []
    required = {
        "schema_version",
        "protocol",
        "audit",
        "environment",
        "config",
        "datasets",
    }
    missing = sorted(required - set(payload))
    if missing:
        errors.append(f"Missing top-level fields: {', '.join(missing)}")

    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    audit = payload.get("audit")
    if not isinstance(audit, dict):
        errors.append("audit must be an object")
    else:
        if audit.get("ok") is not True:
            errors.append("audit.ok must be true for thesis evidence artifacts")
        issues = audit.get("issues", [])
        if not isinstance(issues, list):
            errors.append("audit.issues must be a list")
        else:
            error_issues = [
                issue
                for issue in issues
                if isinstance(issue, dict) and issue.get("severity") == "error"
            ]
            if error_issues:
                errors.append(f"artifact contains {len(error_issues)} leakage error(s)")

    datasets = payload.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        errors.append("datasets must be a non-empty list")
        return errors

    for idx, dataset in enumerate(datasets):
        errors.extend(_validate_dataset(dataset, idx))
    return errors


def _validate_dataset(dataset: Any, idx: int) -> list[str]:
    if not isinstance(dataset, dict):
        return [f"datasets[{idx}] must be an object"]

    errors: list[str] = []
    name = str(dataset.get("name", f"datasets[{idx}]"))
    indices = dataset.get("indices")
    counts = dataset.get("counts")
    if not isinstance(indices, dict):
        errors.append(f"{name}: indices must be an object")
        return errors
    if not isinstance(counts, dict):
        errors.append(f"{name}: counts must be an object")
        counts = {}

    split_sets: dict[str, set[int]] = {}
    for split in ("train", "validation", "test"):
        values = indices.get(split)
        if not isinstance(values, list):
            errors.append(f"{name}: indices.{split} must be a list")
            continue
        try:
            split_sets[split] = {int(value) for value in values}
        except (TypeError, ValueError):
            errors.append(f"{name}: indices.{split} must contain integers")
            continue
        expected_count = counts.get(split)
        if expected_count is not None and int(expected_count) != len(values):
            errors.append(
                f"{name}: counts.{split} does not match indices.{split} length",
            )

    for left, right in (
        ("train", "validation"),
        ("train", "test"),
        ("validation", "test"),
    ):
        overlap = sorted(split_sets.get(left, set()) & split_sets.get(right, set()))
        if overlap:
            errors.append(
                f"{name}: {left}/{right} overlap at indices {overlap[:10]}",
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    payload = json.loads(args.artifact.read_text(encoding="utf-8"))
    errors = validate_artifact(payload)
    if args.format == "json":
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
    elif errors:
        print("Split artifact validation failed:")
        for error in errors:
            print(f"- {error}")
    else:
        print("Split artifact validation passed.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
