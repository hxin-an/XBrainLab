"""Registry loading, validation, and path materialization."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = (
    REPO_ROOT
    / "scripts"
    / "dev"
    / "moabb_user_journeys"
    / "data"
    / "moabb-datasets-v1.json"
)
SUPPORTED_CHECKSUMS = frozenset({"md5", "sha256"})
ALLOWED_SOURCE_HOSTS = frozenset(
    {
        "api.osf.io",
        "osf.io",
        "physionet.org",
        "www.physionet.org",
        "zenodo.org",
        "www.zenodo.org",
    }
)


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    """Load and validate the tracked dataset registry."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_registry(payload, repo_root=REPO_ROOT)
    return payload


def registry_sha256(path: Path = DEFAULT_REGISTRY_PATH) -> str:
    """Return the exact tracked registry digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_registry(registry: dict[str, Any], *, repo_root: Path) -> None:
    """Fail closed when source identity or resource boundaries are incomplete."""
    errors: list[str] = []
    if registry.get("schema_version") != "1.0.0":
        errors.append("registry schema_version must be 1.0.0")

    release = registry.get("moabb_release")
    if not isinstance(release, dict):
        errors.append("moabb_release must be an object")
    elif not _is_sha(release.get("commit"), length=40):
        errors.append("moabb_release.commit must be an exact 40-character SHA")

    policy = registry.get("resource_policy")
    if not isinstance(policy, dict):
        errors.append("resource_policy must be an object")
        policy = {}
    data_root = str(policy.get("data_root") or "")
    evidence_root = str(policy.get("evidence_root") or "")
    if data_root != "build/moabb-data":
        errors.append("resource_policy.data_root must be build/moabb-data")
    if not evidence_root.startswith("build/"):
        errors.append("resource_policy.evidence_root must stay under build/")
    for label, relative in (("data_root", data_root), ("evidence_root", evidence_root)):
        if relative and not _is_within_build(repo_root / relative, repo_root):
            errors.append(
                f"resource_policy.{label} escapes the repository build directory"
            )
    if policy.get("serial_downloads") is not True:
        errors.append("resource_policy.serial_downloads must be true")
    max_bytes = policy.get("max_download_bytes")
    if type(max_bytes) is not int or max_bytes <= 0 or max_bytes > 1024**3:
        errors.append("resource_policy.max_download_bytes must be in (0, 1 GiB]")

    datasets = registry.get("datasets")
    if not isinstance(datasets, list) or len(datasets) < 3:
        errors.append("registry must contain at least three datasets")
        datasets = []
    ids: set[str] = set()
    total_bytes = 0
    formats: set[str] = set()
    paradigms: set[str] = set()
    for index, dataset in enumerate(datasets):
        prefix = f"datasets[{index}]"
        if not isinstance(dataset, dict):
            errors.append(f"{prefix} must be an object")
            continue
        dataset_id = str(dataset.get("id") or "")
        if not dataset_id or dataset_id in ids:
            errors.append(f"{prefix}.id must be non-empty and unique")
        ids.add(dataset_id)
        formats.add(str(dataset.get("source_format") or "").casefold())
        paradigms.add(str(dataset.get("paradigm") or "").casefold())
        if type(dataset.get("expected_peak_ram_bytes")) is not int:
            errors.append(f"{prefix}.expected_peak_ram_bytes must be an integer")
        _validate_identity(dataset.get("identity"), prefix, errors)
        _validate_selection(dataset.get("selection"), prefix, errors)
        files = dataset.get("files")
        if not isinstance(files, list) or not files:
            errors.append(f"{prefix}.files must be a non-empty list")
            files = []
        file_paths: set[str] = set()
        for file_index, item in enumerate(files):
            file_prefix = f"{prefix}.files[{file_index}]"
            if not isinstance(item, dict):
                errors.append(f"{file_prefix} must be an object")
                continue
            url = str(item.get("url") or "")
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS:
                errors.append(
                    f"{file_prefix}.url must be an approved official HTTPS source"
                )
            relative_path = str(item.get("relative_path") or "")
            if not _is_safe_relative_path(relative_path):
                errors.append(f"{file_prefix}.relative_path is unsafe")
            if relative_path in file_paths:
                errors.append(f"{file_prefix}.relative_path is duplicated")
            file_paths.add(relative_path)
            size = item.get("size_bytes")
            if type(size) is not int or size <= 0:
                errors.append(f"{file_prefix}.size_bytes must be positive")
            else:
                total_bytes += size
            _validate_checksum(item.get("checksum"), file_prefix, errors)
            metadata_url = str(item.get("source_metadata_url") or "")
            metadata = urlparse(metadata_url)
            if (
                metadata.scheme != "https"
                or metadata.hostname not in ALLOWED_SOURCE_HOSTS
            ):
                errors.append(
                    f"{file_prefix}.source_metadata_url must be an approved official HTTPS source"
                )
        _validate_import(dataset.get("import"), file_paths, prefix, errors)
        _validate_workflow(
            dataset.get("workflow"),
            prefix,
            errors,
            paradigm=str(dataset.get("paradigm") or ""),
        )

    if not any("gdf" in value for value in formats):
        errors.append("registry must include a native GDF source")
    if not any("edf" in value for value in formats):
        errors.append("registry must include a native EDF source")
    if not any("p300" in value or "erp" in value for value in paradigms):
        errors.append("registry must include a P300/ERP source")
    if type(max_bytes) is int and total_bytes > max_bytes:
        errors.append(
            f"selected downloads exceed profile budget: {total_bytes} > {max_bytes}"
        )
    if errors:
        raise ValueError("Invalid MOABB registry:\n- " + "\n- ".join(errors))


def select_datasets(
    registry: dict[str, Any], dataset_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Return registry datasets in registry order."""
    datasets = list(registry["datasets"])
    if not dataset_ids:
        return datasets
    requested = set(dataset_ids)
    known = {str(dataset["id"]) for dataset in datasets}
    unknown = sorted(requested.difference(known))
    if unknown:
        raise ValueError(f"Unknown dataset id(s): {', '.join(unknown)}")
    return [dataset for dataset in datasets if dataset["id"] in requested]


def materialize_dataset(dataset: dict[str, Any], *, data_root: Path) -> dict[str, Any]:
    """Resolve registry-relative paths without changing semantic choices."""
    materialized = deepcopy(dataset)
    import_spec = materialized["import"]
    import_spec["source_path"] = str((data_root / import_spec["entrypoint"]).resolve())
    choices = dict(import_spec.get("choices") or {})
    choices["selected_eeg_files"] = [
        str((data_root / relative).resolve())
        for relative in import_spec["selected_eeg_files"]
    ]
    excluded = import_spec.get("excluded_label_carriers") or []
    if excluded:
        choices["excluded_label_carriers"] = [
            str((data_root / relative).resolve()) for relative in excluded
        ]
    import_spec["choices"] = choices
    for item in materialized["files"]:
        item["cache_path"] = str((data_root / item["relative_path"]).resolve())
    return materialized


def expected_download_bytes(datasets: list[dict[str, Any]]) -> int:
    """Return the exact declared payload size."""
    return sum(
        int(item["size_bytes"]) for dataset in datasets for item in dataset["files"]
    )


def _validate_identity(value: Any, prefix: str, errors: list[str]) -> None:
    required = {
        "title",
        "dataset_doi",
        "paper_doi",
        "license",
        "repository",
        "repository_url",
        "moabb_docs_url",
        "moabb_adapter_url",
    }
    if not isinstance(value, dict):
        errors.append(f"{prefix}.identity must be an object")
        return
    missing = sorted(key for key in required if not str(value.get(key) or "").strip())
    if missing:
        errors.append(f"{prefix}.identity is missing {', '.join(missing)}")


def _validate_selection(value: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix}.selection must be an object")
        return
    for key in ("subjects", "sessions", "runs"):
        if not isinstance(value.get(key), list) or not value[key]:
            errors.append(f"{prefix}.selection.{key} must be a non-empty list")
    if not str(value.get("reason") or "").strip():
        errors.append(f"{prefix}.selection.reason is required")
    for key in ("expected_trial_count", "expected_trials_per_class"):
        if key in value and (type(value[key]) is not int or value[key] <= 0):
            errors.append(f"{prefix}.selection.{key} must be a positive integer")


def _validate_checksum(value: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix}.checksum must be an object")
        return
    algorithm = str(value.get("algorithm") or "").casefold()
    digest = str(value.get("value") or "").casefold()
    expected_length = {"md5": 32, "sha256": 64}.get(algorithm)
    if algorithm not in SUPPORTED_CHECKSUMS or not _is_sha(digest, expected_length):
        errors.append(f"{prefix}.checksum must be a valid md5 or sha256 digest")


def _validate_import(
    value: Any, file_paths: set[str], prefix: str, errors: list[str]
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix}.import must be an object")
        return
    entrypoint = str(value.get("entrypoint") or "")
    selected = value.get("selected_eeg_files")
    if not _is_safe_relative_path(entrypoint):
        errors.append(f"{prefix}.import.entrypoint is unsafe")
    if not isinstance(selected, list) or not selected:
        errors.append(f"{prefix}.import.selected_eeg_files must be non-empty")
    else:
        unknown = [path for path in selected if path not in file_paths]
        if unknown:
            errors.append(f"{prefix}.import selected files are absent from files")
    if entrypoint not in file_paths and not any(
        Path(path).parent.as_posix() == entrypoint for path in file_paths
    ):
        errors.append(f"{prefix}.import.entrypoint is not represented by files")


def _validate_workflow(
    value: Any,
    prefix: str,
    errors: list[str],
    *,
    paradigm: str,
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix}.workflow must be an object")
        return
    required = {
        "preprocessing",
        "epoch",
        "split",
        "training_profiles",
        "quality_acceptance",
        "seed",
        "saliency",
    }
    missing = sorted(required.difference(value))
    if missing:
        errors.append(f"{prefix}.workflow is missing {', '.join(missing)}")
    profiles = value.get("training_profiles")
    if not isinstance(profiles, dict) or set(profiles) != {"smoke", "showcase"}:
        errors.append(
            f"{prefix}.workflow.training_profiles must define smoke and showcase"
        )
    else:
        smoke = profiles.get("smoke")
        showcase = profiles.get("showcase")
        for profile_name, model in profiles.items():
            if not isinstance(model, dict):
                errors.append(
                    f"{prefix}.workflow.training_profiles.{profile_name} must be an object"
                )
                continue
            if str(model.get("device") or "") != "cpu":
                errors.append(
                    f"{prefix}.workflow.training_profiles.{profile_name}.device must default to cpu"
                )
            if not str(model.get("stopping_budget") or "").strip():
                errors.append(
                    f"{prefix}.workflow.training_profiles.{profile_name} must explain its stopping budget"
                )
        if isinstance(smoke, dict) and smoke.get("epochs") != 1:
            errors.append(f"{prefix} smoke profile must remain a one-epoch smoke")
        if isinstance(showcase, dict) and (
            type(showcase.get("epochs")) is not int or showcase["epochs"] <= 1
        ):
            errors.append(
                f"{prefix} showcase profile needs a justified multi-epoch budget"
            )
    _validate_quality_acceptance(
        value.get("quality_acceptance"),
        paradigm=paradigm,
        prefix=prefix,
        errors=errors,
    )
    if type(value.get("seed")) is not int:
        errors.append(f"{prefix}.workflow.seed must be an integer")
    saliency = value.get("saliency")
    if not isinstance(saliency, dict):
        errors.append(f"{prefix}.workflow.saliency must be an object")
    elif (
        type(saliency.get("max_artifact_bytes")) is not int
        or saliency["max_artifact_bytes"] <= 0
        or saliency["max_artifact_bytes"] > 1024**3
    ):
        errors.append(
            f"{prefix}.workflow.saliency.max_artifact_bytes must be in (0, 1 GiB]"
        )


def _validate_quality_acceptance(
    value: Any,
    *,
    paradigm: str,
    prefix: str,
    errors: list[str],
) -> None:
    acceptance_prefix = f"{prefix}.workflow.quality_acceptance"
    if not isinstance(value, dict):
        errors.append(f"{acceptance_prefix} must be an object")
        return
    if value.get("held_out_split") != "test":
        errors.append(f"{acceptance_prefix}.held_out_split must be test")
    if not str(value.get("test_access_policy") or "").strip():
        errors.append(f"{acceptance_prefix}.test_access_policy is required")
    rules = value.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append(f"{acceptance_prefix}.rules must be non-empty")
        return
    metrics: set[str] = set()
    for index, rule in enumerate(rules):
        rule_prefix = f"{acceptance_prefix}.rules[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{rule_prefix} must be an object")
            continue
        metric = str(rule.get("metric") or "")
        metrics.add(metric)
        if metric not in {
            "accuracy",
            "balanced_accuracy",
            "macro_f1",
            "roc_auc_ovr",
        }:
            errors.append(f"{rule_prefix}.metric is unsupported")
        if rule.get("operator") not in {">", ">="}:
            errors.append(f"{rule_prefix}.operator must be > or >=")
        threshold = rule.get("threshold")
        if not isinstance(threshold, dict):
            errors.append(f"{rule_prefix}.threshold must be an object")
        elif threshold.get("kind") == "observed_baseline":
            if threshold.get("name") not in {
                "chance_baseline",
                "majority_baseline",
                "auc_chance_baseline",
            }:
                errors.append(f"{rule_prefix}.threshold baseline is unsupported")
        elif threshold.get("kind") == "fixed":
            value = threshold.get("value")
            if not str(threshold.get("name") or "").strip():
                errors.append(f"{rule_prefix}.threshold fixed name is required")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= 1
            ):
                errors.append(f"{rule_prefix}.threshold fixed value must be in [0, 1]")
        else:
            errors.append(
                f"{rule_prefix}.threshold must be an observed baseline or fixed value"
            )
        if not str(rule.get("rationale") or "").strip():
            errors.append(f"{rule_prefix}.rationale is required")
    if "p300" in paradigm.casefold() or "erp" in paradigm.casefold():
        if not metrics.intersection({"balanced_accuracy", "macro_f1", "roc_auc_ovr"}):
            errors.append(
                f"{acceptance_prefix} for P300/ERP must use an imbalance-aware metric"
            )


def _is_safe_relative_path(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _is_within_build(path: Path, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to((repo_root / "build").resolve())
    except ValueError:
        return False
    else:
        return True


def _is_sha(value: Any, length: int | None) -> bool:
    text = str(value or "")
    if length is not None and len(text) != length:
        return False
    return bool(text) and all(character in "0123456789abcdef" for character in text)
