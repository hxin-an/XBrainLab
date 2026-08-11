"""Evidence manifest construction and artifact integrity helpers."""

from __future__ import annotations

import hashlib
import importlib.metadata
import math
import platform
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from .registry import REPO_ROOT
from .storage import utc_now, write_json_atomic

EVIDENCE_SCHEMA_VERSION = "1.0.0"
BASELINE_SHA = "e2a3e0c3263bb70360074d419174ee153ee41b67"  # pragma: allowlist secret


def build_manifest(
    *,
    run_id: str,
    registry: dict[str, Any],
    plan: dict[str, Any],
    command: list[str],
    execution_profile: str,
) -> dict[str, Any]:
    """Create an honest empty execution manifest."""
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "run_id": run_id,
        "status": "planned",
        "quality_evidence_status": "pending",
        "started_at": utc_now(),
        "completed_at": None,
        "application": {
            "git_sha": _git_output("rev-parse", "HEAD"),
            "baseline_sha": BASELINE_SHA,
            "dirty_paths": _dirty_paths(),
        },
        "runner": {
            "registry_sha256": plan["registry_sha256"],
            "registry_profile": registry["profile_id"],
            "moabb_release": dict(registry["moabb_release"]),
            "execution_profile": execution_profile,
            "python": sys.version,
            "platform": platform.platform(),
            "dependencies": _dependency_versions(),
            "command": list(command),
        },
        "resource_policy": {
            "data_root": plan["data_root"],
            "expected_download_bytes": plan["expected_download_bytes"],
            "max_download_bytes": plan["max_download_bytes"],
            "serial_downloads": plan["serial_downloads"],
        },
        "datasets": [],
        "failures": [],
        "claim_boundary": [
            "A completed workflow is engineering evidence, not a MOABB benchmark replication.",
            "One-epoch smoke runs never qualify as model-quality evidence.",
            "Automated execution does not replace human Windows UI acceptance.",
        ],
    }


def empty_dataset_evidence(
    dataset: dict[str, Any],
    *,
    source_artifacts: list[dict[str, Any]],
    execution_profile: str,
    attempt: int,
    previous_failure: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create required fields before executing any product command."""
    identity = dataset["identity"]
    workflow = dataset["workflow"]
    model = dict(workflow["training_profiles"][execution_profile])
    model["actual_device"] = None
    return {
        "dataset": {
            "id": dataset["id"],
            "moabb_class": dataset["moabb_class"],
            "moabb_code": dataset["moabb_code"],
            "paradigm": dataset["paradigm"],
            "source_format": dataset["source_format"],
            "source": identity["repository_url"],
            "source_adapter": identity["moabb_adapter_url"],
            "license": identity["license"],
            "dataset_doi": identity["dataset_doi"],
            "paper_doi": identity["paper_doi"],
        },
        "selection": dict(dataset["selection"]),
        "source_artifacts": list(source_artifacts),
        "import": {
            "recipe": {
                "source_path": dataset["import"]["source_path"],
                "source_hint": dataset["import"]["source_hint"],
                "choices": dataset["import"]["choices"],
            },
            "recipe_artifact": None,
            "validation_decision": None,
            "applied": False,
        },
        "preprocessing": [],
        "epoch": dict(workflow["epoch"]),
        "split": dict(workflow["split"]),
        "model": model,
        "seed": int(workflow["seed"]),
        "metrics": {},
        "training_curves": [],
        "quality_acceptance": {
            "specification": deepcopy(workflow["quality_acceptance"]),
            "evaluations": [],
            "passed": False,
            "status": "not_evaluated",
        },
        "quality_evidence_status": "pending",
        "saliency": {
            "methods": list(workflow["saliency"]["methods"]),
            "params": {
                key: value
                for key, value in workflow["saliency"].items()
                if key != "max_artifact_bytes"
            },
            "artifacts": [],
        },
        "screenshots": [],
        "timings": {},
        "command_trace": [],
        "failures": [],
        "resume": {
            "attempt": attempt,
            "strategy": "replay_from_source",
            "previous_failure": previous_failure,
        },
        "claim_boundary": list(dataset["claim_boundary"]),
    }


def artifact_record(path: Path, **metadata: Any) -> dict[str, Any]:
    """Hash an existing artifact; never create placeholder evidence."""
    if not path.is_file():
        raise FileNotFoundError(f"Artifact is missing: {path}")
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        **metadata,
    }


def persist_training_curves(
    output_path: Path,
    *,
    training_history: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist actual multi-point history; one-point smoke is not a curve."""
    rows = training_history.get("rows")
    if not isinstance(rows, list) or not _contains_multi_point_curve(rows):
        return None
    write_json_atomic(
        output_path,
        {
            "schema_version": "1.0.0",
            "created_at": utc_now(),
            "rows": rows,
        },
    )
    return artifact_record(output_path, kind="training_curves")


def collect_existing_artifacts(
    directory: Path, pattern: str, *, kind: str
) -> list[dict[str, Any]]:
    """Collect only files produced by a real external capture or product run."""
    if not directory.is_dir():
        return []
    return [
        artifact_record(path, kind=kind) for path in sorted(directory.glob(pattern))
    ]


def showcase_quality_complete(dataset_evidence: dict[str, Any]) -> bool:
    """Require accepted held-out metrics and verified product saliency artifacts."""
    if not dataset_evidence["training_curves"]:
        return False
    if not str(dataset_evidence.get("model", {}).get("actual_device") or ""):
        return False
    if not _reproducibility_verified(dataset_evidence):
        return False
    acceptance = dataset_evidence.get("quality_acceptance", {})
    if not isinstance(acceptance, dict) or acceptance.get("passed") is not True:
        return False
    requested_methods = set(dataset_evidence.get("saliency", {}).get("methods", []))
    artifacts = dataset_evidence.get("saliency", {}).get("artifacts", [])
    verified_methods = {
        artifact.get("method")
        for artifact in artifacts
        if isinstance(artifact, dict)
        and artifact.get("source") == "application_service_saliency_render"
        and _artifact_still_matches(artifact)
    }
    return bool(requested_methods) and requested_methods.issubset(verified_methods)


def _reproducibility_verified(dataset_evidence: dict[str, Any]) -> bool:
    model = dataset_evidence.get("model", {})
    if not isinstance(model, dict):
        return False
    reproducibility = model.get("reproducibility")
    resolved_state = model.get("resolved_training_state")
    training_option = (
        resolved_state.get("training_option")
        if isinstance(resolved_state, dict)
        else None
    )
    base_seed = dataset_evidence.get("seed")
    repeat_count = model.get("repeat", 1)
    if (
        type(base_seed) is not int
        or type(repeat_count) is not int
        or repeat_count < 1
        or not isinstance(reproducibility, dict)
        or not isinstance(training_option, dict)
    ):
        return False
    expected_seeds = [base_seed + index for index in range(repeat_count)]
    return (
        reproducibility.get("base_seed") == base_seed
        and reproducibility.get("derivation") == "base_seed + zero_based_repeat_index"
        and reproducibility.get("configured_training_state_verified") is True
        and reproducibility.get("persisted_train_records_verified") is True
        and reproducibility.get("repeat_seeds") == expected_seeds
        and training_option.get("seed") == base_seed
        and training_option.get("repeat_seeds") == expected_seeds
    )


def evaluate_quality_acceptance(
    specification: dict[str, Any],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply predeclared baseline-relative or fixed rules to held-out metrics."""
    evaluated: list[dict[str, Any]] = []
    for evaluation in evaluations:
        metrics = evaluation.get("metrics", {})
        baselines = evaluation.get("baselines", {})
        rule_results: list[dict[str, Any]] = []
        for rule in specification["rules"]:
            metric_name = rule["metric"]
            threshold = rule["threshold"]
            threshold_name = threshold["name"]
            metric_value = metrics.get(metric_name)
            threshold_value = (
                threshold.get("value")
                if threshold.get("kind") == "fixed"
                else baselines.get(threshold_name)
            )
            passed = _compare_metric(
                metric_value,
                threshold_value,
                operator=rule["operator"],
            )
            rule_results.append(
                {
                    "metric": metric_name,
                    "value": metric_value,
                    "operator": rule["operator"],
                    "threshold_name": threshold_name,
                    "threshold_value": threshold_value,
                    "passed": passed,
                    "rationale": rule["rationale"],
                }
            )
        evaluated.append(
            {
                **evaluation,
                "acceptance_rules": rule_results,
                "passed": evaluation.get("valid") is True
                and evaluation.get("split") == specification["held_out_split"]
                and evaluation.get("test_prediction_read_count") == 1
                and bool(rule_results)
                and all(result["passed"] for result in rule_results),
            }
        )
    passed = bool(evaluated) and all(item["passed"] for item in evaluated)
    return {
        "specification": deepcopy(specification),
        "evaluations": evaluated,
        "passed": passed,
        "status": "accepted" if passed else "threshold_not_met",
    }


def validate_evidence_manifest(manifest: dict[str, Any]) -> None:
    """Lightweight runtime guard matching the tracked JSON schema's required truth."""
    required = {
        "schema_version",
        "run_id",
        "status",
        "quality_evidence_status",
        "application",
        "runner",
        "resource_policy",
        "datasets",
        "failures",
        "claim_boundary",
    }
    missing = sorted(required.difference(manifest))
    if missing:
        raise ValueError(f"Evidence manifest is missing: {', '.join(missing)}")
    if manifest["schema_version"] != EVIDENCE_SCHEMA_VERSION:
        raise ValueError("Unsupported evidence schema version.")
    if manifest["status"] not in {"planned", "partial", "failed", "completed"}:
        raise ValueError("Invalid evidence status.")
    if manifest["quality_evidence_status"] not in {"pending", "complete", "failed"}:
        raise ValueError("Invalid quality_evidence_status.")
    runner = manifest.get("runner")
    execution_profile = (
        runner.get("execution_profile") if isinstance(runner, dict) else None
    )
    if (
        execution_profile == "smoke"
        and manifest["quality_evidence_status"] != "pending"
    ):
        raise ValueError("Smoke evidence must keep quality_evidence_status pending.")
    if (
        execution_profile == "showcase"
        and manifest["status"] == "completed"
        and manifest["quality_evidence_status"] != "complete"
    ):
        raise ValueError("A completed showcase requires complete quality evidence.")
    dataset_required = {
        "dataset",
        "selection",
        "source_artifacts",
        "import",
        "preprocessing",
        "epoch",
        "split",
        "model",
        "seed",
        "metrics",
        "training_curves",
        "quality_acceptance",
        "quality_evidence_status",
        "saliency",
        "screenshots",
        "timings",
        "command_trace",
        "failures",
        "resume",
        "claim_boundary",
    }
    for dataset in manifest["datasets"]:
        missing_dataset = sorted(dataset_required.difference(dataset))
        if missing_dataset:
            raise ValueError(
                f"Dataset evidence is missing: {', '.join(missing_dataset)}"
            )
        quality_status = dataset["quality_evidence_status"]
        if quality_status not in {"pending", "complete", "failed"}:
            raise ValueError("Dataset quality_evidence_status is invalid.")
        acceptance = dataset["quality_acceptance"]
        if not isinstance(acceptance, dict) or not {
            "specification",
            "evaluations",
            "passed",
            "status",
        }.issubset(acceptance):
            raise ValueError("Dataset quality_acceptance is incomplete.")
        if quality_status == "complete" and not showcase_quality_complete(dataset):
            raise ValueError(
                "Complete dataset quality evidence lacks accepted metrics, curves, "
                "actual device, or verified saliency artifacts."
            )


def _contains_multi_point_curve(rows: list[Any]) -> bool:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if any(
            key != "test_accuracy" and isinstance(values, list) and len(values) > 1
            for key, values in row.items()
        ):
            return True
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for split in metrics.values():
            if not isinstance(split, dict):
                continue
            if any(
                isinstance(values, list) and len(values) > 1
                for values in split.values()
            ):
                return True
    return False


def _row_has_held_out_metric(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    test_accuracy = row.get("test_accuracy")
    if isinstance(test_accuracy, list):
        return any(value is not None for value in test_accuracy)
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        return False
    test = metrics.get("test")
    if not isinstance(test, dict):
        return False
    return any(
        isinstance(values, list) and any(value is not None for value in values)
        for values in test.values()
    )


def _compare_metric(value: Any, threshold: Any, *, operator: str) -> bool:
    if isinstance(value, bool) or isinstance(threshold, bool):
        return False
    if not isinstance(value, (int, float)) or not isinstance(threshold, (int, float)):
        return False
    if not math.isfinite(float(value)) or not math.isfinite(float(threshold)):
        return False
    if operator == ">":
        return float(value) > float(threshold)
    if operator == ">=":
        return float(value) >= float(threshold)
    return False


def _artifact_still_matches(artifact: dict[str, Any]) -> bool:
    try:
        path = Path(str(artifact["path"]))
        return (
            path.is_file()
            and path.stat().st_size == artifact["size_bytes"]
            and _sha256_file(path) == artifact["sha256"]
        )
    except (KeyError, OSError, TypeError, ValueError):
        return False


def _git_output(*args: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _dirty_paths() -> list[str]:
    output = _git_output("status", "--short")
    return [line[3:].strip() for line in output.splitlines() if len(line) >= 4]


def _dependency_versions() -> dict[str, str | None]:
    packages = ("braindecode", "mne", "numpy", "torch")
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
