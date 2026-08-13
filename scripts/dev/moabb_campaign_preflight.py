#!/usr/bin/env python3
"""Fail-closed, no-download preflight for the fixed MOABB campaign."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import shutil
import sys
import urllib.parse
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple, cast

from tomllib import TOMLDecodeError, load

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = (
    REPO_ROOT / "artifacts" / "user-journeys" / "moabb-15-campaign-preflight-v1.json"
)
DEFAULT_PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
DEFAULT_POETRY_LOCK_PATH = REPO_ROOT / "poetry.lock"
EXPECTED_MOABB_VERSION = "1.5.0"
EXPECTED_MOABB_COMMIT = "140809d8c48bdf2be953951ff75f688122edee34"
EXPECTED_CLASS_NAMES = (
    "BNCI2014_001",
    "PhysionetMI",
    "Lee2021Mobile_ERP",
    "BNCI2014_009",
    "Nakanishi2015",
    "Ofner2017",
    "Ma2020",
    "ErpCore2021_P3",
    "Wang2016",
    "Chen2017SingleFlicker",
    "Thielen2021",
    "Hinss2021",
    "MAMEM1",
    "GuttmannFlury2025_SSVEP",
    "Zhou2020",
)
REQUIRED_CONVERSION_DISTRIBUTIONS = {
    "mne-bids": (0, 17),
    "pybv": (0, 7, 3),
    "edfio": (0, 4, 2),
    "edflib-python": (1, 0, 6),
    "eeglabio": (0, 1, 0),
}
REQUIRED_BIDS_OUTPUT_FORMATS = frozenset({"EDF", "BrainVision", "EEGLAB"})
SUPPORTED_BIDS_OUTPUT_FORMATS = REQUIRED_BIDS_OUTPUT_FORMATS | {"BDF"}


class PreflightInputs(NamedTuple):
    """Dependency-injected no-download inputs for deterministic validation."""

    manifest_path: Path
    mne_data_root: Path
    output_root: Path
    free_bytes: int
    distribution_version: Callable[[str], str]
    moabb_class_names: Callable[[], tuple[str, ...]]
    moabb_has_generic_bids_conversion: Callable[[], bool]
    configured_mne_data: Path | None
    poetry_dependency_blockers: Callable[[], list[str]]
    frozen_integrity_error: (
        Callable[[dict[str, Any], Path, Path, Path], str | None] | None
    ) = None

    @classmethod
    def from_environment(
        cls,
        *,
        mne_data_root: Path,
        output_root: Path,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
        distribution_version: Callable[[str], str] = importlib.metadata.version,
    ) -> PreflightInputs:
        probe_root = _nearest_existing_parent(
            _common_storage_parent(mne_data_root, output_root)
        )
        return cls(
            manifest_path=manifest_path,
            mne_data_root=mne_data_root,
            output_root=output_root,
            free_bytes=shutil.disk_usage(probe_root).free,
            distribution_version=distribution_version,
            moabb_class_names=_installed_moabb_class_names,
            moabb_has_generic_bids_conversion=_installed_moabb_has_generic_bids_conversion,
            configured_mne_data=(
                Path(configured) if (configured := os.environ.get("MNE_DATA")) else None
            ),
            poetry_dependency_blockers=poetry_dependency_blockers,
        )


class _DatasetStorageState(NamedTuple):
    expected_source_download_bytes: int
    remaining_source_download_bytes: int
    retained_materialized_bytes: int
    materialized_dataset_count: int


def load_campaign_manifest(
    path: Path = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Read the tracked preflight manifest without downloading data."""
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_preflight(inputs: PreflightInputs) -> dict[str, Any]:
    """Return a machine-readable decision; never download or create campaign roots."""
    blockers: list[str] = []
    try:
        manifest = load_campaign_manifest(inputs.manifest_path)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return _blocked_result([f"campaign manifest cannot be loaded: {exc}"])

    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        return _blocked_result(["campaign manifest datasets must be a list"])
    _validate_release(manifest, blockers)
    _validate_roots(inputs, blockers)
    checksum_root = _validate_materialization_identity(manifest, inputs, blockers)
    storage = _validate_dataset_manifest(
        datasets,
        inputs,
        blockers,
        checksum_root=checksum_root,
    )
    required_headroom = _required_headroom(
        manifest,
        storage.remaining_source_download_bytes,
        blockers,
    )
    blockers.extend(inputs.poetry_dependency_blockers())
    _validate_installed_environment(inputs, blockers)
    if inputs.free_bytes < required_headroom:
        blockers.append(
            "insufficient D-drive free space: "
            f"{inputs.free_bytes} available, {required_headroom} required"
        )

    return {
        "schema_version": "1.0.0",
        "status": "blocked" if blockers else "ready",
        "campaign_allowed": not blockers,
        "dataset_count": len(datasets),
        "expected_source_download_bytes": storage.expected_source_download_bytes,
        "remaining_source_download_bytes": storage.remaining_source_download_bytes,
        "retained_materialized_bytes": storage.retained_materialized_bytes,
        "materialization_phase": (
            "complete"
            if storage.materialized_dataset_count == len(datasets)
            else "partial"
            if storage.materialized_dataset_count
            else "acquisition"
        ),
        "required_headroom_bytes": required_headroom,
        "free_bytes": inputs.free_bytes,
        "mne_data_root": str(inputs.mne_data_root),
        "output_root": str(inputs.output_root),
        "blockers": blockers,
    }


def _validate_release(manifest: dict[str, Any], blockers: list[str]) -> None:
    release = manifest.get("moabb_release")
    if not isinstance(release, dict):
        blockers.append("manifest MOABB release identity is missing")
        return
    if release.get("version") != EXPECTED_MOABB_VERSION:
        blockers.append(f"manifest must pin MOABB {EXPECTED_MOABB_VERSION}")
    if release.get("commit") != EXPECTED_MOABB_COMMIT:
        blockers.append(f"manifest must pin MOABB commit {EXPECTED_MOABB_COMMIT}")


def _validate_roots(inputs: PreflightInputs, blockers: list[str]) -> None:
    for label, path in (
        ("MNE_DATA", inputs.mne_data_root),
        ("BIDS output", inputs.output_root),
    ):
        if not path.is_absolute() or not _is_d_drive_mount(path.resolve()):
            blockers.append(f"{label} must be an absolute D-drive (/mnt/d) path")
    native = inputs.mne_data_root.resolve()
    output = inputs.output_root.resolve()
    if (
        native == output
        or native.is_relative_to(output)
        or output.is_relative_to(native)
    ):
        blockers.append(
            "MNE_DATA and BIDS output roots must be distinct and non-overlapping"
        )
    if (
        inputs.configured_mne_data is not None
        and inputs.configured_mne_data.resolve() != inputs.mne_data_root.resolve()
    ):
        blockers.append(
            "MNE_DATA environment value does not match the requested source root"
        )


def _validate_materialization_identity(
    manifest: dict[str, Any],
    inputs: PreflightInputs,
    blockers: list[str],
) -> Path | None:
    materialization = manifest.get("materialization")
    if not isinstance(materialization, dict):
        blockers.append("final freeze manifest materialization identity is missing")
        return None
    expected_roots = {
        "mne_data_root": inputs.mne_data_root.resolve(),
        "output_root": inputs.output_root.resolve(),
    }
    for field, expected in expected_roots.items():
        path = Path(str(materialization.get(field) or ""))
        if not path.is_absolute() or path.resolve() != expected:
            blockers.append(f"final freeze {field} differs from the requested root")
    checksum_root = Path(str(materialization.get("checksum_root") or ""))
    if not checksum_root.is_absolute() or not _is_d_drive_mount(
        checksum_root.resolve()
    ):
        blockers.append("final freeze checksum_root must be an absolute D-drive path")
        checksum_root = None
    elif any(
        checksum_root.resolve() == owner
        or checksum_root.resolve().is_relative_to(owner)
        or owner.is_relative_to(checksum_root.resolve())
        for owner in expected_roots.values()
    ):
        blockers.append(
            "final freeze checksum_root must be distinct from source/BIDS roots"
        )
        checksum_root = None
    for field in (
        "environment_identity_sha256",
        "conversion_identity_sha256",
        "campaign_product_identity_sha256",
    ):
        digest = str(materialization.get(field) or "").casefold()
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            blockers.append(f"final freeze {field} is not a SHA256 identity")
    return checksum_root


def _validate_dataset_manifest(
    datasets: list[Any],
    inputs: PreflightInputs,
    blockers: list[str],
    *,
    checksum_root: Path | None,
) -> _DatasetStorageState:
    class_names: list[str] = []
    output_formats: set[str] = set()
    expected_bytes = 0
    remaining_bytes = 0
    retained_bytes = 0
    materialized_count = 0
    for index, dataset in enumerate(datasets):
        prefix = f"datasets[{index}]"
        if not isinstance(dataset, dict):
            blockers.append(f"{prefix} must be an object")
            continue
        class_name = str(dataset.get("moabb_class") or "")
        class_names.append(class_name)
        output_format = str(dataset.get("output_format") or "")
        output_formats.add(output_format)
        if output_format not in SUPPORTED_BIDS_OUTPUT_FORMATS:
            blockers.append(
                f"{class_name or prefix} output format is not a supported BIDS EEG format"
            )
        source_mode = str(dataset.get("source_mode") or "moabb_convert")
        if source_mode == "moabb_convert" and output_format == "BDF":
            blockers.append(
                f"{class_name or prefix} convert_to_bids output cannot be BDF"
            )
        elif source_mode == "formal_bids_mirror" and output_format != "BDF":
            blockers.append(
                f"{class_name or prefix} formal BIDS mirror must preserve its BDF format"
            )
        elif source_mode not in {"moabb_convert", "formal_bids_mirror"}:
            blockers.append(f"{class_name or prefix} source mode is unsupported")
        expected_subjects = 5 if index < 5 else 2
        subjects = dataset.get("subjects")
        if not isinstance(subjects, list) or len(subjects) != expected_subjects:
            blockers.append(
                f"{class_name or prefix} must pin exactly {expected_subjects} subjects"
            )
        size = dataset.get("source_download_bytes")
        if type(size) is not int or size <= 0:
            blockers.append(f"{class_name or prefix} source byte size is not verified")
        else:
            expected_bytes += size
        label = class_name or prefix
        declared_ready = dataset.get("status") == "ready"
        if not declared_ready:
            blockers.append(f"{label} frozen dataset status is not ready")
        byte_blocker_count = len(blockers)
        _validate_frozen_root(
            dataset.get("source_root"),
            owner_root=inputs.mne_data_root,
            label=f"{label} source root",
            blockers=blockers,
        )
        _validate_frozen_root(
            dataset.get("bids_root"),
            owner_root=inputs.output_root,
            label=f"{label} BIDS root",
            blockers=blockers,
        )
        _validate_checksum_manifest_path(
            dataset.get("source_checksum_manifest"),
            f"{label} source checksum manifest",
            blockers,
        )
        _validate_checksum_manifest_path(
            dataset.get("checksum_manifest"),
            f"{label} BIDS checksum manifest",
            blockers,
        )
        source_inventory_bytes = _validate_artifact_inventory(
            dataset,
            label=label,
            status_field="source_checksum_status",
            artifacts_field="source_artifacts",
            revision_field="source_revision_sha256",
            expected_bytes=(
                dataset.get("retained_source_bytes")
                if dataset.get("source_mode") == "formal_bids_mirror"
                else size
            ),
            blockers=blockers,
        )
        if dataset.get("source_mode") == "formal_bids_mirror":
            _validate_upstream_download_inventory(
                dataset,
                label=label,
                expected_bytes=size,
                blockers=blockers,
            )
        bids_inventory_bytes = _validate_artifact_inventory(
            dataset,
            label=f"{label} BIDS",
            status_field="bids_checksum_status",
            artifacts_field="bids_artifacts",
            revision_field="dataset_revision_sha256",
            expected_bytes=None,
            blockers=blockers,
        )
        integrity_verified = False
        if declared_ready and checksum_root is not None:
            integrity_error = _frozen_integrity_error(
                dataset,
                inputs=inputs,
                checksum_root=checksum_root,
            )
            if integrity_error:
                blockers.append(
                    f"{label} final byte verification failed: {integrity_error}"
                )
            else:
                integrity_verified = True
        exact_current_inventory = (
            declared_ready
            and checksum_root is not None
            and integrity_verified
            and source_inventory_bytes is not None
            and bids_inventory_bytes is not None
            and len(blockers) == byte_blocker_count
        )
        if exact_current_inventory:
            materialized_count += 1
            retained_bytes += cast(int, source_inventory_bytes) + cast(
                int, bids_inventory_bytes
            )
        elif type(size) is int and size > 0:
            remaining_bytes += size
        _validate_license_policy(dataset, class_name or prefix, blockers)
        resource_status = dataset.get("resource_status")
        if resource_status != "verified":
            blockers.append(
                f"{class_name or prefix} resource status is {resource_status or 'missing'}"
            )
    if tuple(class_names) != EXPECTED_CLASS_NAMES:
        missing = sorted(set(EXPECTED_CLASS_NAMES).difference(class_names))
        unexpected = sorted(set(class_names).difference(EXPECTED_CLASS_NAMES))
        blockers.append(
            "fixed MOABB class inventory mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )
    if not REQUIRED_BIDS_OUTPUT_FORMATS.issubset(output_formats):
        blockers.append(
            "fixed MOABB campaign must cover EDF, BrainVision, and EEGLAB output"
        )
    return _DatasetStorageState(
        expected_source_download_bytes=expected_bytes,
        remaining_source_download_bytes=remaining_bytes,
        retained_materialized_bytes=retained_bytes,
        materialized_dataset_count=materialized_count,
    )


def _frozen_integrity_error(
    dataset: dict[str, Any],
    *,
    inputs: PreflightInputs,
    checksum_root: Path,
) -> str | None:
    verifier = inputs.frozen_integrity_error
    if verifier is not None:
        return verifier(
            dataset,
            inputs.mne_data_root,
            inputs.output_root,
            checksum_root,
        )
    from scripts.dev.moabb_dataset_materializer import (
        frozen_dataset_integrity_error,
    )

    return frozen_dataset_integrity_error(
        dataset,
        source_owner=inputs.mne_data_root,
        bids_owner=inputs.output_root,
        checksum_owner=checksum_root,
    )


def _validate_license_policy(
    dataset: dict[str, Any], label: str, blockers: list[str]
) -> None:
    status = dataset.get("license_status")
    if status == "verified":
        return
    if status == "local-use-only":
        if dataset.get("redistribution_allowed") is not False:
            blockers.append(
                f"{label} local-use-only license policy must prohibit redistribution"
            )
        if not str(dataset.get("license_note") or "").strip():
            blockers.append(
                f"{label} local-use-only license policy must explain the unknown license"
            )
        return
    blockers.append(f"{label} license status is {status or 'missing'}")


def _validate_artifact_inventory(
    dataset: dict[str, Any],
    *,
    label: str,
    status_field: str,
    artifacts_field: str,
    revision_field: str,
    expected_bytes: Any,
    blockers: list[str],
) -> int | None:
    blocker_count = len(blockers)
    if dataset.get(status_field) != "verified":
        blockers.append(f"{label} checksum status is not verified")
    artifacts = dataset.get(artifacts_field)
    if not isinstance(artifacts, list) or not artifacts:
        blockers.append(f"{label} checksum artifact inventory is absent")
        return None
    artifact_bytes = 0
    paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        prefix = f"{label}.{artifacts_field}[{index}]"
        if not isinstance(artifact, dict):
            blockers.append(f"{prefix} must be an object")
            continue
        relative_path = str(artifact.get("relative_path") or "")
        if (
            not relative_path
            or Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
            or relative_path in paths
        ):
            blockers.append(f"{prefix}.relative_path is unsafe or duplicated")
        paths.add(relative_path)
        size = artifact.get("size_bytes")
        if type(size) is not int or size <= 0:
            blockers.append(f"{prefix}.size_bytes must be positive")
        else:
            artifact_bytes += size
        checksum = artifact.get("checksum")
        if not isinstance(checksum, dict):
            blockers.append(f"{prefix}.checksum is missing")
            continue
        algorithm = str(checksum.get("algorithm") or "").casefold()
        digest = str(checksum.get("value") or "").casefold()
        if (
            algorithm != "sha256"
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            blockers.append(f"{prefix}.checksum must be a valid SHA256 digest")
    if type(expected_bytes) is int and artifact_bytes != expected_bytes:
        blockers.append(
            f"{label} source artifact bytes do not match source_download_bytes"
        )
    if dataset.get(revision_field) != _canonical_sha256(artifacts):
        blockers.append(f"{label} aggregate checksum does not match its inventory")
    return artifact_bytes if len(blockers) == blocker_count else None


def _validate_upstream_download_inventory(
    dataset: dict[str, Any],
    *,
    label: str,
    expected_bytes: Any,
    blockers: list[str],
) -> None:
    if dataset.get("upstream_download_status") != "verified":
        blockers.append(f"{label} upstream download status is not verified")
    artifacts = dataset.get("upstream_download_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        blockers.append(f"{label} upstream download inventory is absent")
        return
    total_bytes = 0
    paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        prefix = f"{label}.upstream_download_artifacts[{index}]"
        if not isinstance(artifact, dict):
            blockers.append(f"{prefix} must be an object")
            continue
        relative_path = str(artifact.get("relative_path") or "")
        if (
            not relative_path
            or Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
            or relative_path in paths
        ):
            blockers.append(f"{prefix}.relative_path is unsafe or duplicated")
        paths.add(relative_path)
        size = artifact.get("size_bytes")
        if type(size) is not int or size <= 0:
            blockers.append(f"{prefix}.size_bytes must be positive")
        else:
            total_bytes += size
        source_url = str(artifact.get("source_url") or "")
        parsed_url = urllib.parse.urlparse(source_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.query
            or parsed_url.fragment
        ):
            blockers.append(f"{prefix}.source_url must be a stable HTTPS URL")
        _validate_upstream_checksum(
            artifact.get("upstream_checksum"),
            f"{prefix}.upstream_checksum",
            blockers,
        )
        checksum = artifact.get("checksum")
        if (
            not isinstance(checksum, dict)
            or checksum.get("algorithm") != "sha256"
            or not _valid_hex_digest(checksum.get("value"), length=64)
        ):
            blockers.append(f"{prefix}.checksum must be a valid SHA256 digest")
    if type(expected_bytes) is int and total_bytes != expected_bytes:
        blockers.append(f"{label} upstream bytes do not match source_download_bytes")
    if dataset.get("upstream_download_bytes") != total_bytes:
        blockers.append(f"{label} upstream download byte total is inconsistent")
    if dataset.get("upstream_download_revision_sha256") != _canonical_sha256(artifacts):
        blockers.append(f"{label} upstream aggregate identity does not match")
    bids_artifacts = dataset.get("bids_artifacts")
    projected_bids = [
        {
            "relative_path": artifact.get("relative_path"),
            "size_bytes": artifact.get("size_bytes"),
            "checksum": artifact.get("checksum"),
        }
        for artifact in artifacts
        if isinstance(artifact, dict)
    ]
    if projected_bids != bids_artifacts:
        blockers.append(
            f"{label} upstream download inventory differs from frozen BIDS bytes"
        )


def _validate_upstream_checksum(
    value: Any,
    label: str,
    blockers: list[str],
) -> None:
    if not isinstance(value, dict):
        blockers.append(f"{label} is missing")
        return
    algorithm = str(value.get("algorithm") or "").casefold()
    digest = value.get("value")
    if not (
        (algorithm == "sha256" and _valid_hex_digest(digest, length=64))
        or (algorithm == "git" and _valid_hex_digest(digest, length=40))
    ):
        blockers.append(f"{label} must be a pinned SHA256 or Git blob digest")


def _valid_hex_digest(value: Any, *, length: int) -> bool:
    digest = str(value or "").casefold()
    return len(digest) == length and all(
        character in "0123456789abcdef" for character in digest
    )


def _validate_frozen_root(
    value: Any,
    *,
    owner_root: Path,
    label: str,
    blockers: list[str],
) -> None:
    path = Path(str(value or ""))
    if not path.is_absolute():
        blockers.append(f"{label} must be an absolute D-drive path")
        return
    resolved = path.resolve()
    try:
        resolved.relative_to(owner_root.resolve())
    except ValueError:
        blockers.append(f"{label} must be contained by the requested D-drive root")
        return
    if not _is_d_drive_mount(resolved):
        blockers.append(f"{label} must be an absolute D-drive path")


def _validate_checksum_manifest_path(
    value: Any,
    label: str,
    blockers: list[str],
) -> None:
    path = Path(str(value or ""))
    if (
        not path.is_absolute()
        or not _is_d_drive_mount(path.resolve())
        or path.suffix.casefold() != ".sha256"
    ):
        blockers.append(f"{label} must be an absolute D-drive .sha256 path")


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _required_headroom(
    manifest: dict[str, Any], remaining_source_bytes: int, blockers: list[str]
) -> int:
    policy = manifest.get("resource_policy")
    if not isinstance(policy, dict):
        blockers.append("resource_policy is missing")
        return remaining_source_bytes
    multiplier = policy.get("minimum_headroom_multiplier")
    artifact_bytes = policy.get("minimum_artifact_headroom_bytes")
    if type(multiplier) is not int or multiplier < 4:
        blockers.append("minimum_headroom_multiplier must be an integer of at least 4")
        multiplier = 4
    if type(artifact_bytes) is not int or artifact_bytes <= 0:
        blockers.append("minimum_artifact_headroom_bytes must be positive")
        artifact_bytes = 0
    return remaining_source_bytes * multiplier + artifact_bytes


def _validate_installed_environment(
    inputs: PreflightInputs, blockers: list[str]
) -> None:
    try:
        version = inputs.distribution_version("moabb")
    except (importlib.metadata.PackageNotFoundError, KeyError):
        version = None
    if version != EXPECTED_MOABB_VERSION:
        blockers.append(
            f"installed environment must contain MOABB {EXPECTED_MOABB_VERSION}; "
            f"found {version or 'not installed'}"
        )
    _require_distribution(inputs, "pyxdf", (1, 16, 4), blockers, "the XDF adapter")
    for distribution, minimum in REQUIRED_CONVERSION_DISTRIBUTIONS.items():
        _require_distribution(
            inputs,
            distribution,
            minimum,
            blockers,
            "the EDF/BrainVision/EEGLAB BIDS writers",
        )
    try:
        installed_classes = inputs.moabb_class_names()
    except (ImportError, AttributeError) as exc:
        blockers.append(f"MOABB class inventory cannot be inspected: {exc}")
        return
    missing = [name for name in EXPECTED_CLASS_NAMES if name not in installed_classes]
    if missing:
        blockers.append(
            f"installed MOABB class inventory is missing: {', '.join(missing)}"
        )
    try:
        has_conversion = inputs.moabb_has_generic_bids_conversion()
    except (ImportError, AttributeError) as exc:
        blockers.append(f"MOABB generic BIDS conversion cannot be inspected: {exc}")
    else:
        if not has_conversion:
            blockers.append("MOABB BaseDataset.convert_to_bids is missing")


def poetry_dependency_blockers(
    pyproject_path: Path = DEFAULT_PYPROJECT_PATH,
    lock_path: Path = DEFAULT_POETRY_LOCK_PATH,
) -> list[str]:
    """Validate the reproducible Poetry source contract without resolving packages."""
    blockers: list[str] = []
    try:
        with pyproject_path.open("rb") as handle:
            pyproject = load(handle)
    except (FileNotFoundError, TOMLDecodeError) as exc:
        return [f"pyproject.toml cannot be inspected: {exc}"]
    dependencies = pyproject.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if not isinstance(dependencies, dict):
        return ["pyproject.toml Poetry dependencies are missing"]
    moabb_constraint = _dependency_constraint(dependencies.get("moabb"))
    if moabb_constraint not in {EXPECTED_MOABB_VERSION, f"=={EXPECTED_MOABB_VERSION}"}:
        blockers.append(
            f"pyproject.toml must pin moabb exactly to {EXPECTED_MOABB_VERSION}"
        )
    pyxdf_constraint = _dependency_constraint(dependencies.get("pyxdf"))
    if not _has_minimum_constraint(pyxdf_constraint, (1, 16, 4)):
        blockers.append("pyproject.toml must declare pyxdf>=1.16.4")
    for name, minimum in REQUIRED_CONVERSION_DISTRIBUTIONS.items():
        constraint = _dependency_constraint(dependencies.get(name))
        if not _has_minimum_constraint(constraint, minimum):
            blockers.append(
                "pyproject.toml must declare "
                f"{name}>={'.'.join(map(str, minimum))} for BIDS export"
            )

    try:
        with lock_path.open("rb") as handle:
            lock = load(handle)
    except (FileNotFoundError, TOMLDecodeError) as exc:
        blockers.append(f"poetry.lock cannot be inspected: {exc}")
        return blockers
    packages = lock.get("package")
    if not isinstance(packages, list):
        blockers.append("poetry.lock package inventory is missing")
        return blockers
    versions = {
        str(package.get("name") or "").casefold(): str(package.get("version") or "")
        for package in packages
        if isinstance(package, dict)
    }
    if versions.get("moabb") != EXPECTED_MOABB_VERSION:
        blockers.append(f"poetry.lock must contain moabb {EXPECTED_MOABB_VERSION}")
    locked_pyxdf = versions.get("pyxdf")
    if not locked_pyxdf or _numeric_version(locked_pyxdf) < (1, 16, 4):
        blockers.append("poetry.lock must contain pyxdf>=1.16.4")
    for name, minimum in REQUIRED_CONVERSION_DISTRIBUTIONS.items():
        version = versions.get(name)
        if not version or _numeric_version(version) < minimum:
            blockers.append(
                "poetry.lock must contain "
                f"{name}>={'.'.join(map(str, minimum))} for BIDS export"
            )
    return blockers


def _dependency_constraint(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("version") or "").strip()
    return ""


def _has_minimum_constraint(value: str, minimum: tuple[int, ...]) -> bool:
    if value and value[0].isdigit() and _numeric_version(value) >= minimum:
        return True
    for raw_clause in value.split(","):
        clause = raw_clause.strip()
        if clause.startswith(">=") and _numeric_version(clause[2:]) >= minimum:
            return True
        if clause.startswith("==") and _numeric_version(clause[2:]) >= minimum:
            return True
    return False


def _require_distribution(
    inputs: PreflightInputs,
    name: str,
    minimum: tuple[int, ...],
    blockers: list[str],
    purpose: str,
) -> None:
    try:
        version = inputs.distribution_version(name)
    except (importlib.metadata.PackageNotFoundError, KeyError):
        version = None
    version_too_old = bool(version and minimum and _numeric_version(version) < minimum)
    if not version or version_too_old:
        requirement = f">={'.'.join(map(str, minimum))}" if minimum else ""
        blockers.append(
            f"installed environment must contain {name}{requirement} for {purpose}"
        )


def _installed_moabb_class_names() -> tuple[str, ...]:
    os.environ.setdefault("MNE_DONTWRITE_HOME", "true")
    module = importlib.import_module("moabb.datasets")
    return tuple(name for name in dir(module) if not name.startswith("_"))


def _installed_moabb_has_generic_bids_conversion() -> bool:
    os.environ.setdefault("MNE_DONTWRITE_HOME", "true")
    module = importlib.import_module("moabb.datasets.base")
    return callable(getattr(module.BaseDataset, "convert_to_bids", None))


def _numeric_version(value: str) -> tuple[int, ...]:
    components: list[int] = []
    for part in value.split("."):
        digits = "".join(character for character in part if character.isdigit())
        if not digits:
            break
        components.append(int(digits))
    return tuple(components)


def _is_d_drive_mount(path: Path) -> bool:
    parts = PurePosixPath(path).parts
    return len(parts) >= 3 and parts[:3] == ("/", "mnt", "d")


def _common_storage_parent(first: Path, second: Path) -> Path:
    try:
        return Path(os.path.commonpath((first, second)))
    except ValueError:
        return first


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _blocked_result(blockers: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "blocked",
        "campaign_allowed": False,
        "dataset_count": 0,
        "expected_source_download_bytes": 0,
        "remaining_source_download_bytes": 0,
        "retained_materialized_bytes": 0,
        "materialization_phase": "unknown",
        "required_headroom_bytes": 0,
        "free_bytes": 0,
        "mne_data_root": "",
        "output_root": "",
        "blockers": blockers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the fixed MOABB campaign without downloading data."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--mne-data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = evaluate_preflight(
        PreflightInputs.from_environment(
            manifest_path=args.manifest.resolve(),
            mne_data_root=args.mne_data_root.resolve(),
            output_root=args.output_root.resolve(),
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["campaign_allowed"] else 1


if __name__ == "__main__":
    sys.exit(main())
