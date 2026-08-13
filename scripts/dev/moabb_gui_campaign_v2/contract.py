"""Fail-closed plan and receipt contracts for the 15-dataset GUI campaign."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

SCHEMA_VERSION: Final = "2.0.0"
PROFILE_ID: Final = "moabb-15-gui-campaign-v2"
ARTIFACT_TYPE: Final = "xbrainlab.moabb_gui_journey"
MOABB_RELEASE: Final = {
    "version": "1.5.0",
    "tag": "v1.5",
    "commit": "140809d8c48bdf2be953951ff75f688122edee34",
    "repository": "https://github.com/NeuroTechX/moabb",
}
JOURNEY_MODES: Final = ("cold", "replay")
REQUIRED_STAGES: Final = (
    "import_bids_folder",
    "select_subjects",
    "review_metadata",
    "match_labels",
    "confirm_import",
    "preprocess",
    "epoch",
    "split",
    "model",
    "training",
    "evaluation",
    "compute_saliency",
    "saliency_map",
    "spectrogram",
    "clean_close",
)
OWNED_OPERATION_STAGES: Final = frozenset(
    {
        "import_bids_folder",
        "review_metadata",
        "confirm_import",
        "preprocess",
        "epoch",
        "training",
        "evaluation",
        "compute_saliency",
        "saliency_map",
        "spectrogram",
    }
)
CANCELLATION_PARTITIONS: Final = (
    "import_review",
    "apply_epoch",
    "training_saliency",
)
CANCELLATION_TARGETS: Final[dict[str, frozenset[str]]] = {
    "import_review": frozenset({"import", "review"}),
    "apply_epoch": frozenset({"apply", "epoch"}),
    "training_saliency": frozenset({"training", "saliency"}),
}
CANCELLATION_MEANINGFUL_STAGES: Final[dict[str, frozenset[str]]] = {
    "import": frozenset(
        {
            "Discovering source files",
            "Resolving nested BIDS root",
            "Indexing BIDS root",
            "Classifying BIDS resources",
            "Indexing BIDS recordings",
            "Capturing BIDS resource identities",
        }
    ),
    "review": frozenset(
        {
            "Discovering source files",
            "Resolving nested BIDS root",
            "Indexing BIDS root",
            "Classifying BIDS resources",
            "Indexing BIDS recordings",
            "Capturing BIDS resource identities",
            "Hashing reviewed import content",
        }
    ),
    "apply": frozenset(
        {
            "Hashing reviewed import content",
            "Verifying reviewed import content",
            "Loading reviewed EEG recordings",
            "Binding reviewed source identity",
            "Applying reviewed channel metadata",
            "Applying reviewed recording metadata",
            "Applying reviewed label carriers",
        }
    ),
    "epoch": frozenset(
        {
            "Copying EEG recordings for preprocessing",
            "Preparing working EEG recordings",
            "Checking EEG epoch boundaries",
            "Validating EEG epoch recordings",
            "Creating EEG epochs",
            "Applying queued EEG epoch normalization",
        }
    ),
    "training": frozenset({"Training model"}),
    "saliency": frozenset({"Computing saliency"}),
}
DATASET_MATRIX: Final[dict[str, tuple[int, ...]]] = {
    "BNCI2014_001": (1, 2, 3, 4, 5),
    "PhysionetMI": (1, 2, 3, 4, 5),
    "Lee2021Mobile_ERP": (1, 2, 3, 4, 5),
    "BNCI2014_009": (1, 2, 3, 4, 5),
    "Nakanishi2015": (1, 2, 3, 4, 5),
    "Ofner2017": (1, 2),
    "Ma2020": (1, 2),
    "ErpCore2021_P3": (1, 2),
    "Wang2016": (1, 2),
    "Chen2017SingleFlicker": (1, 2),
    "Thielen2021": (1, 2),
    "Hinss2021": (1, 2),
    "MAMEM1": (1, 2),
    "GuttmannFlury2025_SSVEP": (1, 2),
    "Zhou2020": (1, 2),
}
_REQUIRED_BIDS_FORMATS: Final = frozenset({"EDF", "BrainVision", "EEGLAB"})
_SUPPORTED_BIDS_FORMATS: Final = _REQUIRED_BIDS_FORMATS | {"BDF"}
_CONVERT_ROOT_RESOLUTION: Final = {
    "source": "convert_to_bids_return_value",
    "must_be_descendant_of_conversion_parent": True,
    "required_basename_prefix": "MNE-BIDS-",
    "required_marker": "dataset_description.json",
}
_MIRROR_ROOT_RESOLUTION: Final = {
    "source": "formal_bids_mirror_receipt",
    "must_be_descendant_of_conversion_parent": True,
    "required_basename_prefix": "MNE-BIDS-",
    "required_marker": "dataset_description.json",
}
_HEX = frozenset("0123456789abcdef")
_TRAINING_METRIC_KEYS: Final = frozenset(
    {"Train Loss", "Train Acc", "Val Loss", "Val Acc", "Test Acc", "LR"}
)
_EVALUATION_METRIC_KEYS: Final = frozenset(
    {"Precision", "Recall", "F1-Score", "Support"}
)


class CampaignContractError(ValueError):
    """One or more campaign invariants are not satisfied."""


def load_campaign_plan(path: Path) -> dict[str, Any]:
    """Load the tracked v2 plan and reject an invalid denominator."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CampaignContractError("Campaign plan must be a JSON object.")
    errors = validate_campaign_plan(payload)
    if errors:
        raise CampaignContractError("Invalid campaign plan:\n- " + "\n- ".join(errors))
    return payload


def campaign_plan_sha256(path: Path) -> str:
    """Return the digest that binds receipts to one exact tracked plan."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_campaign_plan(plan: Mapping[str, Any]) -> list[str]:
    """Validate the immutable denominator while allowing planned data to be pending."""
    errors: list[str] = []
    if plan.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if plan.get("profile_id") != PROFILE_ID:
        errors.append(f"profile_id must be {PROFILE_ID}")
    if _mapping(plan.get("moabb_release")) != MOABB_RELEASE:
        errors.append("MOABB release identity must match the locked v1.5.0 source")
    if tuple(plan.get("journey_modes") or ()) != JOURNEY_MODES:
        errors.append("journey_modes must be exact cold then replay")
    if tuple(plan.get("required_stages") or ()) != REQUIRED_STAGES:
        errors.append("required_stages must match the complete GUI happy path")

    policy = _mapping(plan.get("driver_policy"))
    if policy.get("only_injected_boundary") != "QFileDialog":
        errors.append("QFileDialog must be the only injected boundary")
    for field in (
        "dataset_name_ui_branching",
        "direct_backend_commands",
        "direct_dialog_construction",
        "private_wizard_navigation",
    ):
        if policy.get(field) is not False:
            errors.append(f"driver_policy.{field} must be false")
    if policy.get("visible_enabled_clicks_only") is not True:
        errors.append("driver must click visible and enabled controls only")
    if policy.get("fresh_process_per_journey") is not True:
        errors.append("each cold/replay journey must use a fresh process")

    profiles = _mapping(plan.get("ui_profiles"))
    recommended = _mapping(profiles.get("product_recommended_bounded"))
    training = _mapping(recommended.get("training"))
    if {
        "epochs": training.get("epochs"),
        "repeats": training.get("repeats"),
        "folds": training.get("folds"),
    } != {"epochs": 1, "repeats": 1, "folds": 1}:
        errors.append("bounded training profile must be exactly 1 epoch/repeat/fold")
    saliency = _mapping(recommended.get("saliency"))
    if saliency.get("explicit_compute") is not True:
        errors.append("saliency must require an explicit Compute Saliency click")
    if tuple(saliency.get("required_views") or ()) != (
        "Saliency Map",
        "Spectrogram",
    ):
        errors.append("Saliency Map and Spectrogram must both be required")

    rows = plan.get("datasets")
    if not isinstance(rows, list):
        errors.append("datasets must be a list")
        return errors
    observed_names = [
        str(row.get("moabb_class") or "") if isinstance(row, Mapping) else ""
        for row in rows
    ]
    if observed_names != list(DATASET_MATRIX):
        errors.append("datasets must preserve the exact 15-dataset inventory")

    conversion_parents: set[str] = set()
    roots: set[str] = set()
    checksum_paths: set[str] = set()
    formats: set[str] = set()
    partitions: Counter[str] = Counter()
    targets_by_partition: dict[str, set[str]] = {
        partition: set() for partition in CANCELLATION_PARTITIONS
    }
    for index, raw in enumerate(rows):
        prefix = f"datasets[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        dataset = str(raw.get("moabb_class") or "")
        expected_subjects = DATASET_MATRIX.get(dataset)
        subjects = raw.get("subjects")
        if expected_subjects is not None and tuple(subjects or ()) != expected_subjects:
            errors.append(f"{prefix}.subjects does not match the fixed matrix")
        if raw.get("ui_profile") != "product_recommended_bounded":
            errors.append(f"{prefix}.ui_profile must use the shared product profile")
        partition = str(raw.get("cancellation_partition") or "")
        partitions[partition] += 1
        if partition not in CANCELLATION_PARTITIONS:
            errors.append(f"{prefix}.cancellation_partition is invalid")
        cancellation_target = str(raw.get("cancellation_target") or "")
        if cancellation_target not in CANCELLATION_TARGETS.get(partition, frozenset()):
            errors.append(f"{prefix}.cancellation_target is invalid")
        elif partition in targets_by_partition:
            targets_by_partition[partition].add(cancellation_target)

        bids = _mapping(raw.get("bids"))
        if bids.get("formal_bids") is not True:
            errors.append(f"{prefix}.bids.formal_bids must be true")
        output_format = str(bids.get("format") or "")
        formats.add(output_format)
        if output_format not in _SUPPORTED_BIDS_FORMATS:
            errors.append(f"{prefix}.bids.format is unsupported")
        source_mode = str(raw.get("source_mode") or "moabb_convert")
        if source_mode == "moabb_convert" and output_format == "BDF":
            errors.append(f"{prefix}.bids.format cannot be BDF for convert_to_bids")
        elif source_mode == "formal_bids_mirror" and output_format != "BDF":
            errors.append(f"{prefix}.bids.format must preserve mirror BDF bytes")
        elif source_mode not in {"moabb_convert", "formal_bids_mirror"}:
            errors.append(f"{prefix}.source_mode is unsupported")
        conversion_parent = str(bids.get("conversion_parent") or "")
        if not _is_d_mounted_absolute(conversion_parent):
            errors.append(
                f"{prefix}.bids.conversion_parent must be an absolute /mnt/d path"
            )
        if not conversion_parent or conversion_parent in conversion_parents:
            errors.append(
                f"{prefix}.bids.conversion_parent must be non-empty and unique"
            )
        conversion_parents.add(conversion_parent)

        root_resolution = _mapping(bids.get("root_resolution"))
        expected_resolution = (
            _MIRROR_ROOT_RESOLUTION
            if source_mode == "formal_bids_mirror"
            else _CONVERT_ROOT_RESOLUTION
        )
        if root_resolution != expected_resolution:
            errors.append(
                f"{prefix}.bids.root_resolution must pin its source-owned BIDS root"
            )

        checksum_path = str(bids.get("checksum_manifest") or "")
        if not _is_d_mounted_absolute(checksum_path):
            errors.append(
                f"{prefix}.bids.checksum_manifest must be an absolute /mnt/d path"
            )
        if not checksum_path or checksum_path in checksum_paths:
            errors.append(
                f"{prefix}.bids.checksum_manifest must be non-empty and unique"
            )
        checksum_paths.add(checksum_path)
        state = str(raw.get("execution_state") or "")
        if state not in {"awaiting_dataset_materialization", "ready"}:
            errors.append(f"{prefix}.execution_state is invalid")
        root_value = bids.get("root")
        if state == "awaiting_dataset_materialization" and root_value is not None:
            errors.append(
                f"{prefix}.bids.root must stay null until its BIDS source is frozen"
            )
        if state == "ready":
            root = str(root_value or "")
            if not _is_d_mounted_absolute(root):
                errors.append(f"{prefix}.bids.root must be an absolute /mnt/d path")
            if not root or root in roots:
                errors.append(f"{prefix}.bids.root must be non-empty and unique")
            elif not _is_descendant_path(root, conversion_parent):
                errors.append(
                    f"{prefix}.bids.root must remain inside conversion_parent"
                )
            elif not Path(root).name.startswith("MNE-BIDS-"):
                errors.append(f"{prefix}.bids.root must be the frozen MNE-BIDS root")
            roots.add(root)
        oracle = _mapping(raw.get("oracle"))
        if oracle.get("state") not in {"awaiting_dataset_materialization", "pinned"}:
            errors.append(f"{prefix}.oracle.state is invalid")
        if state == "ready":
            errors.extend(_ready_dataset_errors(raw, prefix=prefix))

    if not _REQUIRED_BIDS_FORMATS.issubset(formats):
        errors.append("campaign BIDS output must cover EDF, BrainVision, and EEGLAB")
    for partition in CANCELLATION_PARTITIONS:
        if partitions[partition] != 5:
            errors.append(f"cancellation partition {partition} must contain 5 datasets")
        if targets_by_partition[partition] != set(CANCELLATION_TARGETS[partition]):
            errors.append(
                f"cancellation partition {partition} must cover both target stages"
            )
    return errors


def execution_preflight_errors(
    plan: Mapping[str, Any],
    *,
    dataset: str | None = None,
    environment: Mapping[str, Any] | None = None,
) -> list[str]:
    """Require materialized, checksum-pinned BIDS bytes before any GUI process starts."""
    from scripts.dev.moabb_dataset_materializer import (
        bids_tree_integrity_error,
        exact_environment_identity,
    )

    errors = validate_campaign_plan(plan)
    if environment is None:
        try:
            environment = exact_environment_identity()
        except Exception as exc:
            errors.append(f"exact campaign environment is unavailable: {exc}")
            environment = {}
    git = _mapping(environment.get("git"))
    if git.get("dirty") is True:
        errors.append("campaign requires clean product source at the exact commit")
    if (
        not str(environment.get("cuda") or "").strip()
        or not str(environment.get("gpu") or "").strip()
    ):
        errors.append("campaign requires a usable CUDA/GPU environment")
    materialization = _mapping(plan.get("materialization"))
    expected_environment = str(materialization.get("environment_identity_sha256") or "")
    current_environment = str(environment.get("identity_sha256") or "")
    if materialization.get("status") != "ready":
        errors.append("campaign materialization is not ready")
    if not _hex_digest(expected_environment, 64):
        errors.append("campaign materialization environment identity is invalid")
    elif current_environment != expected_environment:
        errors.append("campaign environment differs from dataset materialization")
    rows = plan.get("datasets")
    if not isinstance(rows, list):
        return errors
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            continue
        if dataset is not None and raw.get("moabb_class") != dataset:
            continue
        prefix = f"datasets[{index}]"
        if raw.get("execution_state") != "ready":
            errors.append(f"{prefix} is not execution-ready")
            continue
        errors.extend(_ready_dataset_errors(raw, prefix=prefix))
        bids = _mapping(raw.get("bids"))
        root = Path(str(bids.get("root") or ""))
        checksum_manifest = Path(str(bids.get("checksum_manifest") or ""))
        if not root.is_dir():
            errors.append(f"{prefix}.bids.root is not materialized")
        elif not (root / "dataset_description.json").is_file():
            errors.append(f"{prefix}.bids.root lacks the formal BIDS dataset marker")
        if not checksum_manifest.is_file():
            errors.append(f"{prefix}.bids.checksum_manifest is missing")
        if root.is_dir() and checksum_manifest.is_file():
            integrity_error = bids_tree_integrity_error(
                root=root,
                checksum_manifest=checksum_manifest,
                expected_revision_sha256=str(bids.get("dataset_revision_sha256") or ""),
            )
            if integrity_error is not None:
                errors.append(f"{prefix} {integrity_error}")
    return list(dict.fromkeys(errors))


def validate_journey_receipt(
    receipt: Mapping[str, Any],
    *,
    artifact_root: Path,
    require_runner_seal: bool = True,
) -> list[str]:
    """Validate one successful cold or replay receipt without trusting prose."""
    errors: list[str] = []
    if receipt.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"receipt schema_version must be {SCHEMA_VERSION}")
    if receipt.get("artifact_type") != ARTIFACT_TYPE:
        errors.append("receipt artifact_type is invalid")
    if receipt.get("status") != "completed":
        errors.append("receipt status must be completed")
    dataset = str(receipt.get("dataset") or "")
    if dataset not in DATASET_MATRIX:
        errors.append("receipt dataset is outside the fixed inventory")
    elif tuple(receipt.get("subjects") or ()) != DATASET_MATRIX[dataset]:
        errors.append("receipt subjects do not match the fixed matrix")
    journey_mode = receipt.get("journey_mode")
    if journey_mode not in JOURNEY_MODES:
        errors.append("receipt journey_mode must be cold or replay")

    process = _mapping(receipt.get("process"))
    if process.get("fresh_process") is not True:
        errors.append("receipt must prove a fresh process")
    if not _positive_int(process.get("pid")):
        errors.append("receipt process pid is invalid")
    if process.get("exit_code") != 0:
        errors.append("receipt process did not exit cleanly")
    if require_runner_seal:
        errors.extend(
            _runner_process_seal_errors(
                process,
                artifact_root=artifact_root,
                dataset=dataset,
                journey_mode=str(journey_mode or ""),
            )
        )

    identity = _mapping(receipt.get("source_identity"))
    if not _hex_digest(identity.get("application_commit"), 40):
        errors.append("receipt application commit is invalid")
    for field in (
        "campaign_plan_sha256",
        "poetry_lock_sha256",
        "dataset_checksum_sha256",
        "environment_identity_sha256",
    ):
        if not _hex_digest(identity.get(field), 64):
            errors.append(f"receipt {field} is invalid")
    cuda = str(identity.get("cuda") or "").strip()
    gpu = str(identity.get("gpu") or "").strip()
    if not cuda or not gpu or "unavailable" in {cuda.casefold(), gpu.casefold()}:
        errors.append("receipt CUDA/GPU identity is incomplete")

    correlation = _mapping(receipt.get("correlation"))
    errors.extend(_correlation_errors(correlation, prefix="receipt"))
    stage_rows = receipt.get("stages")
    if not isinstance(stage_rows, list):
        errors.append("receipt stages must be a list")
        stage_rows = []
    observed_stages = [
        str(row.get("stage") or "") if isinstance(row, Mapping) else ""
        for row in stage_rows
    ]
    if observed_stages != list(REQUIRED_STAGES):
        errors.append("receipt stages do not match the complete ordered happy path")
    for index, row in enumerate(stage_rows):
        if not isinstance(row, Mapping):
            errors.append(f"receipt stages[{index}] must be an object")
            continue
        if row.get("status") != "completed":
            errors.append(f"receipt stage {row.get('stage')} is not completed")
        if not _finite_nonnegative(row.get("elapsed_seconds")):
            errors.append(f"receipt stage {row.get('stage')} elapsed time is invalid")
        if not str(row.get("visible_control") or "").strip():
            errors.append(f"receipt stage {row.get('stage')} lacks a visible control")
        stage = str(row.get("stage") or "")
        operation_id = row.get("operation_id")
        if stage in OWNED_OPERATION_STAGES and not str(operation_id or "").strip():
            errors.append(f"receipt stage {stage} lacks a backend operation id")
        if operation_id is not None and not str(operation_id).strip():
            errors.append(f"receipt stage {stage} has an invalid operation id")
        click_ack = row.get("click_ack_seconds")
        click_ack_number = _finite_nonnegative_float(click_ack)
        if click_ack_number is None or click_ack_number > 2:
            errors.append(
                f"receipt stage {stage} click acknowledgement exceeded 2 seconds"
            )
        progress_silence = row.get("max_progress_silence_seconds")
        progress_silence_number = _finite_nonnegative_float(progress_silence)
        heartbeat_count = row.get("heartbeat_count")
        if stage in OWNED_OPERATION_STAGES:
            if progress_silence_number is None or progress_silence_number > 5:
                errors.append(
                    f"receipt stage {stage} progress silence exceeded 5 seconds"
                )
            if type(heartbeat_count) is not int or heartbeat_count < 0:
                errors.append(f"receipt stage {stage} heartbeat count is invalid")
            elif float(row.get("elapsed_seconds") or 0) >= 5 and heartbeat_count < 1:
                errors.append(
                    f"receipt stage {stage} has no progress heartbeat evidence"
                )
        else:
            if progress_silence is not None and (
                progress_silence_number is None or progress_silence_number > 5
            ):
                errors.append(
                    f"receipt stage {stage} progress silence exceeded 5 seconds"
                )
            if type(heartbeat_count) is not int or heartbeat_count < 0:
                errors.append(f"receipt stage {stage} heartbeat count is invalid")

    artifacts = _mapping(receipt.get("artifacts"))
    screenshots = _mapping(artifacts.get("screenshots"))
    if set(screenshots) != set(REQUIRED_STAGES):
        errors.append("receipt must include one screenshot for every required stage")
    for name, value in screenshots.items():
        if name in REQUIRED_STAGES:
            errors.extend(
                _artifact_errors(value, artifact_root=artifact_root, label=name)
            )
    for field in ("saliency_map", "spectrogram"):
        errors.extend(
            _artifact_errors(
                artifacts.get(field), artifact_root=artifact_root, label=field
            )
        )
    errors.extend(
        _visual_artifact_identity_errors(artifacts, artifact_root=artifact_root)
    )
    training_metrics = artifacts.get("training_metrics")
    if not _exact_finite_metric_mapping(training_metrics, _TRAINING_METRIC_KEYS):
        errors.append("receipt training metrics are incomplete or non-finite")

    ui_options = _mapping(receipt.get("ui_options"))
    if {
        "training_epochs": ui_options.get("training_epochs"),
        "repeats": ui_options.get("repeats"),
        "folds": ui_options.get("folds"),
    } != {"training_epochs": 1, "repeats": 1, "folds": 1}:
        errors.append("receipt bounded training options must be 1 epoch/repeat/fold")
    if ui_options.get("selection_policy") != (
        "product_recommended_with_pinned_semantics"
    ):
        errors.append(
            "receipt must distinguish product-recommended controls from pinned "
            "event semantics"
        )
    for option_group in (
        "filtering",
        "epoch",
        "split",
        "model",
        "training",
        "saliency",
    ):
        if not _mapping(ui_options.get(option_group)):
            errors.append(f"receipt UI options lack observed {option_group} values")
    training_options = _mapping(ui_options.get("training"))
    runtime_devices = training_options.get("runtime_devices")
    if (
        not isinstance(runtime_devices, list)
        or not runtime_devices
        or any(
            not isinstance(device, str) or not device.startswith("cuda:")
            for device in runtime_devices
        )
    ):
        errors.append("receipt training runtime device must prove CUDA execution")

    semantic = _mapping(receipt.get("event_class_summary"))
    for field in (
        "expected_events",
        "observed_events",
        "expected_classes",
        "observed_classes",
    ):
        if not _unique_nonempty_string_list(semantic.get(field)):
            errors.append(f"receipt event/class summary {field} is incomplete")
    expected_event_set = _string_value_set(semantic.get("expected_events"))
    observed_event_set = _string_value_set(semantic.get("observed_events"))
    expected_class_set = _string_value_set(semantic.get("expected_classes"))
    observed_class_set = _string_value_set(semantic.get("observed_classes"))
    if expected_event_set != observed_event_set:
        errors.append("receipt observed events do not match the oracle set")
    if expected_class_set != observed_class_set:
        errors.append("receipt observed classes do not match the oracle set")
    review_mapping = semantic.get("review_mapping")
    review_by_event: dict[str, Mapping[str, Any]] = {}
    if not isinstance(review_mapping, list) or not review_mapping:
        errors.append("receipt lacks reviewed event-value semantic mapping")
        review_mapping = []
    else:
        for index, row in enumerate(review_mapping):
            if not _valid_review_semantic_row(row):
                errors.append(
                    f"receipt review_mapping[{index}] is incomplete or invalid"
                )
                continue
            event_value = str(row.get("event_value") or "")
            if event_value in review_by_event:
                errors.append(f"receipt review_mapping repeats event {event_value!r}")
            else:
                review_by_event[event_value] = row
        mapped_events = [
            str(row.get("event_value") or "")
            for row in review_mapping
            if isinstance(row, Mapping)
        ]
        mapped_classes = [
            str(row.get("class_name") or "")
            for row in review_mapping
            if isinstance(row, Mapping) and row.get("use_as_class") is True
        ]
        if mapped_events != semantic.get("observed_events"):
            errors.append("receipt observed events do not derive from Match Labels")
        if set(mapped_classes) != observed_class_set:
            errors.append("receipt observed classes do not derive from Match Labels")
    if set(review_by_event) != expected_event_set:
        errors.append("receipt Match Labels rows do not cover the exact event set")
    for event_value, row in review_by_event.items():
        is_expected_class = event_value in expected_class_set
        if (
            row.get("keep_event") is not True
            or row.get("use_as_class") is not is_expected_class
            or str(row.get("class_name") or "")
            != (event_value if is_expected_class else "")
        ):
            errors.append(f"receipt Match Labels semantics differ for {event_value!r}")

    applied_event_catalog = semantic.get("applied_event_catalog")
    applied_by_event: dict[str, Mapping[str, Any]] = {}
    if not isinstance(applied_event_catalog, list) or not applied_event_catalog:
        errors.append("receipt lacks post-Apply event catalog evidence")
        applied_event_catalog = []
    else:
        for index, row in enumerate(applied_event_catalog):
            if not _valid_review_semantic_row(row):
                errors.append(
                    f"receipt applied_event_catalog[{index}] is incomplete or invalid"
                )
                continue
            event_value = str(row.get("event_value") or "")
            if event_value in applied_by_event:
                errors.append(
                    f"receipt post-Apply event catalog repeats event {event_value!r}"
                )
            else:
                applied_by_event[event_value] = row
    if set(applied_by_event) != expected_event_set:
        errors.append(
            "receipt post-Apply event catalog does not cover the exact event set"
        )
    for event_value, review_row in review_by_event.items():
        applied_row = applied_by_event.get(event_value)
        if applied_row is None:
            continue
        if any(
            applied_row.get(field) != review_row.get(field)
            for field in ("event_role", "keep_event", "use_as_class", "class_name")
        ):
            errors.append(
                f"receipt post-Apply event catalog semantics differ for {event_value!r}"
            )

    selected_decisions = ui_options.get("event_value_decisions")
    decision_by_event: dict[str, Mapping[str, Any]] = {}
    if not isinstance(selected_decisions, list) or not selected_decisions:
        errors.append("receipt lacks actual event-value UI decisions")
    else:
        for index, row in enumerate(selected_decisions):
            if not _valid_selected_event_value_decision(row):
                errors.append(f"receipt event_value_decisions[{index}] is invalid")
                continue
            event_value = str(row.get("event_value") or "")
            if event_value in decision_by_event:
                errors.append(
                    f"receipt event-value UI decisions repeat {event_value!r}"
                )
            else:
                decision_by_event[event_value] = row
    if set(decision_by_event) != expected_event_set:
        errors.append("receipt event-value UI decisions do not cover the oracle set")
    for event_value, decision in decision_by_event.items():
        is_expected_class = event_value in expected_class_set
        expected_use = "class" if is_expected_class else "ignore"
        expected_basis = (
            "oracle_expected_class" if is_expected_class else "oracle_nonclass_event"
        )
        review_row = review_by_event.get(event_value)
        if (
            decision.get("use") != expected_use
            or str(decision.get("class_name") or "")
            != (event_value if is_expected_class else "")
            or decision.get("selection_basis") != expected_basis
            or review_row is None
            or review_row.get("use_as_class") is not is_expected_class
            or str(review_row.get("class_name") or "")
            != str(decision.get("class_name") or "")
        ):
            errors.append(
                f"receipt selected event-value decision differs for {event_value!r}"
            )
    evaluation_classes = semantic.get("evaluation_class_labels")
    if not _unique_nonempty_string_list(evaluation_classes):
        errors.append("receipt lacks visible Evaluation class labels")
    saliency_mapping = semantic.get("saliency_class_mapping")
    if not isinstance(saliency_mapping, list) or not saliency_mapping:
        errors.append("receipt lacks Saliency class-index mapping")
        saliency_mapping = []
    elif any(
        not _valid_saliency_class_row(row, expected_index=index)
        for index, row in enumerate(saliency_mapping)
    ):
        errors.append("receipt Saliency class-index mapping is invalid")
    saliency_classes = [
        str(row.get("class_name") or "")
        for row in saliency_mapping
        if isinstance(row, Mapping)
    ]
    if semantic.get("observed_classes") != evaluation_classes:
        errors.append("Evaluation class labels differ from Match Labels")
    if evaluation_classes != saliency_classes:
        errors.append("Saliency class labels differ from Evaluation")

    evaluation = _mapping(receipt.get("evaluation"))
    if _mapping(evaluation.get("correlation")) != correlation:
        errors.append("Evaluation does not match the current dataset/run/fold/split")
    if not _exact_finite_metric_mapping(
        evaluation.get("metrics"), _EVALUATION_METRIC_KEYS
    ):
        errors.append("Evaluation metrics are incomplete or non-finite")
    evaluation_metrics = _mapping(evaluation.get("metrics"))
    if not _valid_evaluation_output_summary(
        evaluation.get("output_numeric_summary"),
        class_count=(
            len(evaluation_classes) if isinstance(evaluation_classes, list) else 0
        ),
        sample_count=evaluation_metrics.get("Support"),
    ):
        errors.append(
            "Evaluation output numeric summary is incomplete, non-finite, or "
            "inconsistent with visible classes/support"
        )

    saliency = _mapping(receipt.get("saliency"))
    if saliency.get("explicit_compute_clicked") is not True:
        errors.append("receipt must prove an explicit Compute Saliency click")
    if saliency.get("map_rendered") is not True:
        errors.append("receipt must prove the Saliency Map rendered")
    if saliency.get("spectrogram_rendered") is not True:
        errors.append("receipt must prove the Spectrogram rendered")
    if _mapping(saliency.get("correlation")) != correlation:
        errors.append("Saliency does not match the current dataset/run/fold/split")
    if _mapping(saliency.get("map_correlation")) != correlation:
        errors.append("Saliency Map does not match the current dataset/run/fold/split")
    if _mapping(saliency.get("spectrogram_correlation")) != correlation:
        errors.append("Spectrogram does not match the current dataset/run/fold/split")
    for field in ("map_numeric_summary", "spectrogram_numeric_summary"):
        if not _valid_numeric_summary(saliency.get(field)):
            errors.append(f"Saliency {field} is incomplete or non-finite")

    cancellation = _mapping(receipt.get("cancellation"))
    if journey_mode == "cold" and cancellation.get("attempted") is not True:
        errors.append("cold receipt did not exercise its locked cancellation")
    if journey_mode == "replay" and cancellation.get("attempted") is not False:
        errors.append("replay receipt unexpectedly repeated cancellation")
    if cancellation.get("attempted") is True:
        partition = str(cancellation.get("partition") or "")
        target = str(cancellation.get("target") or "")
        if partition not in CANCELLATION_PARTITIONS:
            errors.append("receipt cancellation partition is invalid")
        if target not in CANCELLATION_TARGETS.get(partition, frozenset()):
            errors.append("receipt cancellation target is invalid")
        if cancellation.get("terminal_status") != "cancelled":
            errors.append("receipt cancellation did not reach a cancelled state")
        if cancellation.get("retry_succeeded") is not True:
            errors.append("receipt cancellation retry did not succeed")
        cancellation_operation_id = str(cancellation.get("operation_id") or "").strip()
        if not cancellation_operation_id:
            errors.append("receipt cancellation lacks its exact operation id")
        stage_at_cancel = str(cancellation.get("stage_at_cancel") or "").strip()
        if stage_at_cancel not in CANCELLATION_MEANINGFUL_STAGES.get(
            target, frozenset()
        ):
            errors.append(
                "receipt cancellation lacks a target-specific meaningful "
                "stage-at-cancel"
            )
        if cancellation.get("phase_at_cancel") != "running":
            errors.append("receipt cancellation was not running at the cancel click")
        if not _valid_cancellation_progress(cancellation.get("progress_at_cancel")):
            errors.append("receipt cancellation progress-at-cancel is invalid")
        target_stage = {
            "import": "import_bids_folder",
            "review": "review_metadata",
            "apply": "confirm_import",
            "epoch": "epoch",
            "training": "training",
            "saliency": "compute_saliency",
        }.get(target)
        successful_retry_operation_id = next(
            (
                str(row.get("operation_id") or "").strip()
                for row in stage_rows
                if isinstance(row, Mapping) and row.get("stage") == target_stage
            ),
            "",
        )
        if cancellation_operation_id and (
            cancellation_operation_id == successful_retry_operation_id
        ):
            errors.append(
                "receipt cancellation operation id matches the successful retry"
            )
        before_state = cancellation.get("state_before")
        after_state = cancellation.get("state_after")
        if not _valid_workflow_state_identity(before_state) or not (
            _valid_workflow_state_identity(after_state)
        ):
            errors.append("receipt cancellation state identity is incomplete")
        elif not workflow_state_semantics_preserved(before_state, after_state) or (
            cancellation.get("state_preserved") is not True
        ):
            errors.append("cancelled import changed protected workflow state")
        if target == "apply" and (
            not _valid_review_session_identity(
                cancellation.get("review_session_before")
            )
            or not _valid_review_session_identity(
                cancellation.get("review_session_after")
            )
            or cancellation.get("review_session_before")
            != cancellation.get("review_session_after")
            or cancellation.get("same_review_session_retry") is not True
        ):
            errors.append("Apply cancellation did not retry the same review session")
        if target != "apply" and (
            cancellation.get("review_session_before") is not None
            or cancellation.get("review_session_after") is not None
            or cancellation.get("same_review_session_retry") is not False
        ):
            errors.append("non-Apply cancellation contains review-session evidence")
        stop_seconds = cancellation.get("stop_handler_seconds")
        stop_seconds_number = _finite_nonnegative_float(stop_seconds)
        if stop_seconds_number is None or stop_seconds_number > 0.1:
            errors.append("receipt stop handler exceeded 100 ms")
    else:
        if (
            cancellation.get("state_before") is not None
            or cancellation.get("operation_id") is not None
            or cancellation.get("stage_at_cancel") is not None
            or cancellation.get("phase_at_cancel") is not None
            or cancellation.get("progress_at_cancel") is not None
            or cancellation.get("state_after") is not None
            or cancellation.get("state_preserved") is not False
            or cancellation.get("review_session_before") is not None
            or cancellation.get("review_session_after") is not None
            or cancellation.get("same_review_session_retry") is not False
        ):
            errors.append("non-cancellation receipt contains cancellation evidence")

    responsiveness = _mapping(receipt.get("responsiveness"))
    click_ack = responsiveness.get("max_click_ack_seconds")
    progress_silence = responsiveness.get("max_progress_silence_seconds")
    click_ack_number = _finite_nonnegative_float(click_ack)
    if click_ack_number is None or click_ack_number > 2:
        errors.append("receipt GUI click acknowledgement exceeded 2 seconds")
    progress_silence_number = _finite_nonnegative_float(progress_silence)
    if progress_silence_number is None or progress_silence_number > 5:
        errors.append("receipt long-work progress silence exceeded 5 seconds")

    close = _mapping(receipt.get("close"))
    if close.get("clean") is not True or close.get("forced") is not False:
        errors.append("receipt must prove a clean, non-forced close")
    close_attempt_id = close.get("close_attempt_id")
    if not isinstance(close_attempt_id, str) or not close_attempt_id.strip():
        errors.append("close lacks the terminal close-attempt identity")
    if (
        close.get("terminal_snapshot_observed") is not True
        or close.get("application_closed") is not True
    ):
        errors.append("close lacks a terminal post-close snapshot")
    if close.get("pre_close_application_idle") is not True:
        errors.append("close did not verify pre-close application-owned work was idle")
    pre_close_workers = close.get("pre_close_remaining_workers")
    pre_close_subprocesses = close.get("pre_close_remaining_subprocesses")
    if not (
        isinstance(pre_close_workers, int)
        and not isinstance(pre_close_workers, bool)
        and pre_close_workers == 0
        and isinstance(pre_close_subprocesses, int)
        and not isinstance(pre_close_subprocesses, bool)
        and pre_close_subprocesses == 0
    ):
        errors.append("receipt pre-close gate left owned work or subprocesses behind")
    return errors


def validate_campaign_receipt_denominator(
    plan: Mapping[str, Any], receipts: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Validate the exact 30-journey inventory and cancellation assignment."""
    errors = validate_campaign_plan(plan)
    expected = [(dataset, mode) for dataset in DATASET_MATRIX for mode in JOURNEY_MODES]
    observed = [
        (str(row.get("dataset") or ""), str(row.get("journey_mode") or ""))
        for row in receipts
    ]
    if observed != expected:
        errors.append(
            "campaign receipts do not preserve the exact cold/replay denominator"
        )
    partitions = {
        str(row.get("moabb_class") or ""): str(row.get("cancellation_partition") or "")
        for row in plan.get("datasets", [])
        if isinstance(row, Mapping)
    }
    targets = {
        str(row.get("moabb_class") or ""): str(row.get("cancellation_target") or "")
        for row in plan.get("datasets", [])
        if isinstance(row, Mapping)
    }
    for row in receipts:
        dataset = str(row.get("dataset") or "")
        mode = str(row.get("journey_mode") or "")
        if row.get("status") != "completed":
            errors.append(f"{dataset}/{mode} did not complete")
        cancellation = _mapping(row.get("cancellation"))
        if cancellation.get("partition") != partitions.get(dataset):
            errors.append(
                f"{dataset}/{mode} cancellation partition does not match plan"
            )
        if cancellation.get("target") != targets.get(dataset):
            errors.append(f"{dataset}/{mode} cancellation target does not match plan")
        if mode == "cold" and (
            cancellation.get("attempted") is not True
            or cancellation.get("terminal_status") != "cancelled"
            or cancellation.get("retry_succeeded") is not True
        ):
            errors.append(f"{dataset}/cold did not cancel then retry successfully")
        if mode == "replay" and cancellation.get("attempted") is not False:
            errors.append(f"{dataset}/replay unexpectedly repeated cancellation")
    pids = [
        _mapping(row.get("process")).get("pid")
        for row in receipts
        if isinstance(row, Mapping)
    ]
    if len(pids) != len(set(pids)):
        errors.append("campaign journeys did not use 30 unique process identities")
    return errors


def receipt_plan_binding_errors(
    plan: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    authoritative_environment: Mapping[str, Any] | None = None,
) -> list[str]:
    """Bind one receipt to the locked dataset bytes and semantic oracle."""
    dataset = str(receipt.get("dataset") or "")
    planned = next(
        (
            row
            for row in plan.get("datasets", [])
            if isinstance(row, Mapping) and row.get("moabb_class") == dataset
        ),
        None,
    )
    if planned is None:
        return ["receipt dataset is absent from the locked campaign plan"]
    errors: list[str] = []
    bids = _mapping(planned.get("bids"))
    expected_revision = str(bids.get("dataset_revision_sha256") or "")
    identity = _mapping(receipt.get("source_identity"))
    if identity.get("dataset_checksum_sha256") != expected_revision:
        errors.append("receipt dataset checksum does not match the locked plan")
    materialization = _mapping(plan.get("materialization"))
    if identity.get("environment_identity_sha256") != materialization.get(
        "environment_identity_sha256"
    ):
        errors.append(
            "receipt environment identity does not match dataset materialization"
        )
    if authoritative_environment is not None:
        git = _mapping(authoritative_environment.get("git"))
        expected_identity = {
            "application_commit": git.get("commit"),
            "poetry_lock_sha256": authoritative_environment.get("poetry_lock_sha256"),
            "environment_identity_sha256": authoritative_environment.get(
                "identity_sha256"
            ),
            "cuda": authoritative_environment.get("cuda"),
            "gpu": authoritative_environment.get("gpu"),
        }
        projection_labels = {
            "application_commit": "application commit",
            "poetry_lock_sha256": "Poetry lock",
            "environment_identity_sha256": "environment identity",
            "cuda": "CUDA",
            "gpu": "GPU",
        }
        for field, expected in expected_identity.items():
            if identity.get(field) != expected:
                errors.append(
                    f"receipt {projection_labels[field]} does not match the "
                    "frozen materialization environment"
                )
    oracle = _mapping(planned.get("oracle"))
    semantic = _mapping(receipt.get("event_class_summary"))
    if _string_value_set(semantic.get("expected_events")) != _string_value_set(
        oracle.get("expected_events")
    ):
        errors.append("receipt event oracle does not match the locked plan")
    if _string_value_set(semantic.get("expected_classes")) != _string_value_set(
        oracle.get("expected_classes")
    ):
        errors.append("receipt class oracle does not match the locked plan")
    expected_product_mapping = oracle.get("expected_product_class_mapping")
    product_class_order = [
        str(row.get("class_name") or "")
        for row in expected_product_mapping or ()
        if isinstance(row, Mapping)
    ]
    if (
        semantic.get("observed_classes") != product_class_order
        or semantic.get("evaluation_class_labels") != product_class_order
    ):
        errors.append("receipt product class order does not match the locked plan")
    if semantic.get("saliency_class_mapping") != expected_product_mapping:
        errors.append(
            "receipt Saliency class-index/event-code mapping does not match the "
            "locked product mapping"
        )
    return errors


def validate_campaign_receipts(
    plan: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    *,
    artifact_root: Path,
    expected_plan_sha256: str,
    authoritative_environment: Mapping[str, Any] | None = None,
) -> list[str]:
    """Validate all receipt evidence plus one shared source/environment identity."""
    errors = validate_campaign_receipt_denominator(plan, receipts)
    shared_identities: list[tuple[str, str, str, str, str, str]] = []
    for receipt in receipts:
        dataset = str(receipt.get("dataset") or "unknown")
        mode = str(receipt.get("journey_mode") or "unknown")
        errors.extend(
            f"{dataset}/{mode}: {error}"
            for error in validate_journey_receipt(
                receipt,
                artifact_root=artifact_root / dataset / mode,
            )
        )
        errors.extend(
            f"{dataset}/{mode}: {error}"
            for error in receipt_plan_binding_errors(
                plan,
                receipt,
                authoritative_environment=authoritative_environment,
            )
        )
        identity = _mapping(receipt.get("source_identity"))
        if identity.get("campaign_plan_sha256") != expected_plan_sha256:
            errors.append(f"{dataset}/{mode}: receipt does not match the locked plan")
        shared_identities.append(
            (
                str(identity.get("application_commit") or ""),
                str(identity.get("campaign_plan_sha256") or ""),
                str(identity.get("poetry_lock_sha256") or ""),
                str(identity.get("environment_identity_sha256") or ""),
                str(identity.get("cuda") or ""),
                str(identity.get("gpu") or ""),
            )
        )
    if len(set(shared_identities)) > 1:
        errors.append(
            "campaign receipts do not share one commit, plan, Poetry lock, and "
            "CUDA/GPU environment"
        )
    return errors


def _valid_review_semantic_row(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    event_value = str(value.get("event_value") or "").strip()
    event_role = str(value.get("event_role") or "").strip()
    keep_event = value.get("keep_event")
    use_as_class = value.get("use_as_class")
    class_name = str(value.get("class_name") or "").strip()
    return bool(
        event_value
        and event_role
        and isinstance(keep_event, bool)
        and isinstance(use_as_class, bool)
        and (not use_as_class or class_name)
        and _nonempty_string_list(value.get("sources"))
    )


def _valid_saliency_class_row(value: Any, *, expected_index: int) -> bool:
    return bool(
        isinstance(value, Mapping)
        and value.get("class_index") == expected_index
        and str(value.get("event_code") or "").strip() == str(expected_index)
        and str(value.get("class_name") or "").strip()
    )


def _valid_selected_event_value_decision(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and set(value) == {"event_value", "use", "class_name", "selection_basis"}
        and str(value.get("event_value") or "").strip()
        and value.get("use") in {"class", "ignore"}
        and isinstance(value.get("class_name"), str)
        and value.get("selection_basis")
        in {"oracle_expected_class", "oracle_nonclass_event"}
    )


def _valid_workflow_state_identity(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return bool(
        set(value)
        == {
            "publication_generation",
            "publication_revision",
            "application_state_sha256",
            "workflow_inputs_sha256",
            "saliency_output_sha256",
            "finished_run_count",
        }
        and all(
            _hex_digest(value.get(field), 64)
            for field in (
                "application_state_sha256",
                "workflow_inputs_sha256",
                "saliency_output_sha256",
            )
        )
        and type(value.get("publication_generation")) is int
        and value.get("publication_generation", -1) >= 0
        and type(value.get("publication_revision")) is int
        and value.get("publication_revision", 0) >= 1
        and type(value.get("finished_run_count")) is int
        and value.get("finished_run_count", -1) >= 0
    )


def workflow_state_semantics_preserved(before: Any, after: Any) -> bool:
    """Compare protected workflow truth while retaining publication provenance.

    Owned-operation terminal publication may legitimately advance the global
    generation/revision even when cancellation leaves the target's protected
    values unchanged.  Evidence keeps both coordinates, requires them to move
    monotonically, and compares the semantic digests/count independently.
    """
    if not _valid_workflow_state_identity(before) or not (
        _valid_workflow_state_identity(after)
    ):
        return False
    protected_fields = (
        "application_state_sha256",
        "workflow_inputs_sha256",
        "saliency_output_sha256",
        "finished_run_count",
    )
    return bool(
        all(before[field] == after[field] for field in protected_fields)
        and after["publication_generation"] >= before["publication_generation"]
        and after["publication_revision"] >= before["publication_revision"]
    )


def _valid_review_session_identity(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return bool(
        set(value)
        == {"scan_id", "candidate_id", "preview_id", "publication_generation"}
        and all(
            str(value.get(field) or "").strip()
            for field in ("scan_id", "candidate_id", "preview_id")
        )
        and type(value.get("publication_generation")) is int
        and value.get("publication_generation", -1) >= 0
    )


def _runner_process_seal_errors(
    process: Mapping[str, Any],
    *,
    artifact_root: Path,
    dataset: str,
    journey_mode: str,
) -> list[str]:
    """Validate the parent-owned receipt written only after child reaping."""
    errors: list[str] = []
    if process.get("runner_verified") is not True:
        return ["receipt process outcome was not verified by the parent runner"]
    if process.get("timed_out") is not False:
        errors.append("receipt process runner seal reports a timeout")
    if process.get("residual_descendant_count") != 0:
        errors.append("receipt process runner seal reports residual descendants")
    if process.get("residual_process_group_status") != "clean":
        errors.append(
            "receipt process runner seal did not verify a clean process group"
        )
    if not _finite_nonnegative(process.get("duration_seconds")):
        errors.append("receipt process runner duration is invalid")
    receipt_value = str(process.get("process_receipt") or "").strip()
    expected_digest = process.get("process_receipt_sha256")
    if not receipt_value or not _hex_digest(expected_digest, 64):
        errors.append("receipt process runner seal is incomplete")
        return errors
    path = Path(receipt_value)
    if path.is_symlink():
        errors.append("receipt process evidence is unavailable inside artifact root")
        return errors
    try:
        root = artifact_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        payload_bytes = resolved.read_bytes()
    except (OSError, RuntimeError, ValueError):
        errors.append("receipt process evidence is unavailable inside artifact root")
        return errors
    actual_digest = hashlib.sha256(payload_bytes).hexdigest()
    if actual_digest != expected_digest:
        errors.append("receipt process evidence digest does not match runner seal")
        return errors
    try:
        payload = json.loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append("receipt process evidence is not valid JSON")
        return errors
    if not isinstance(payload, Mapping):
        errors.append("receipt process evidence is not an object")
        return errors
    expected = {
        "dataset": dataset,
        "journey_mode": journey_mode,
        "pid": process.get("pid"),
        "returncode": process.get("exit_code"),
        "timed_out": False,
        "residual_descendant_count": 0,
        "residual_process_group_status": "clean",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        errors.append("receipt process evidence does not match the journey outcome")
    if payload.get("duration_seconds") != process.get("duration_seconds"):
        errors.append("receipt process duration does not match runner evidence")
    return errors


def _ready_dataset_errors(dataset: Mapping[str, Any], *, prefix: str) -> list[str]:
    errors: list[str] = []
    bids = _mapping(dataset.get("bids"))
    if not _hex_digest(bids.get("dataset_revision_sha256"), 64):
        errors.append(f"{prefix}.bids.dataset_revision_sha256 is invalid")
    oracle = _mapping(dataset.get("oracle"))
    if oracle.get("state") != "pinned":
        errors.append(f"{prefix}.oracle must be pinned before execution")
    for field in ("expected_events", "expected_classes"):
        if not _nonempty_string_list(oracle.get(field)):
            errors.append(f"{prefix}.oracle.{field} must be non-empty")
    expected_events = oracle.get("expected_events")
    expected_classes = oracle.get("expected_classes")
    expected_event_values: list[str] = (
        [item for item in expected_events if isinstance(item, str)]
        if isinstance(expected_events, list)
        else []
    )
    expected_class_values: list[str] = (
        [item for item in expected_classes if isinstance(item, str)]
        if isinstance(expected_classes, list)
        else []
    )
    if expected_event_values and len(set(expected_event_values)) != len(
        expected_event_values
    ):
        errors.append(f"{prefix}.oracle.expected_events must be unique")
    if expected_class_values and len(set(expected_class_values)) != len(
        expected_class_values
    ):
        errors.append(f"{prefix}.oracle.expected_classes must be unique")
    source_event_id = oracle.get("source_event_id")
    if not (
        isinstance(source_event_id, Mapping)
        and isinstance(expected_events, list)
        and set(source_event_id) == _string_value_set(expected_events)
        and all(type(value) is int and value >= 0 for value in source_event_id.values())
        and len(set(source_event_id.values())) == len(source_event_id)
    ):
        errors.append(
            f"{prefix}.oracle.source_event_id must map every event exactly once"
        )
    elif isinstance(expected_classes, list) and not _string_value_set(
        expected_classes
    ).issubset(source_event_id):
        errors.append(
            f"{prefix}.oracle expected classes are absent from source_event_id"
        )
    expected_product_mapping = oracle.get("expected_product_class_mapping")
    canonical_product_mapping = [
        {
            "class_index": index,
            "event_code": str(index),
            "class_name": class_name,
        }
        for index, class_name in enumerate(sorted(expected_class_values))
    ]
    if expected_product_mapping != canonical_product_mapping:
        errors.append(
            f"{prefix}.oracle.expected_product_class_mapping is not the "
            "deterministic product epoch mapping"
        )
    bids_event_values = oracle.get("bids_event_values")
    bids_crosscheck = oracle.get("bids_value_crosscheck")
    if bids_event_values == {}:
        if bids_crosscheck != "not-present":
            errors.append(
                f"{prefix}.oracle BIDS event values lack a truthful crosscheck"
            )
    elif not (
        isinstance(bids_event_values, Mapping)
        and isinstance(expected_events, list)
        and set(bids_event_values) == _string_value_set(expected_events)
        and all(
            type(value) is int and value >= 0 for value in bids_event_values.values()
        )
        and len(set(bids_event_values.values())) == len(bids_event_values)
        and bids_crosscheck in {"matched", "formal-bids-mirror-authoritative"}
    ):
        errors.append(
            f"{prefix}.oracle BIDS event values must independently map every "
            "event exactly once"
        )
    return errors


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _valid_cancellation_progress(value: Any) -> bool:
    progress = _mapping(value)
    if set(progress) != {"display", "completed", "total", "indeterminate"}:
        return False
    display = str(progress.get("display") or "").strip()
    indeterminate = progress.get("indeterminate")
    completed = progress.get("completed")
    total = progress.get("total")
    if indeterminate is True:
        return display == "indeterminate" and completed is None and total is None
    if indeterminate is not False:
        return False
    if (
        type(completed) is not int
        or completed < 0
        or type(total) is not int
        or total <= 0
        or completed > total
    ):
        return False
    return display == f"{completed}/{total}"


def _is_d_mounted_absolute(value: str) -> bool:
    return value == "/mnt/d" or value.startswith("/mnt/d/")


def _is_descendant_path(value: str, parent: str) -> bool:
    try:
        Path(value).resolve().relative_to(Path(parent).resolve())
    except (OSError, ValueError):
        return False
    return Path(value).resolve() != Path(parent).resolve()


def _hex_digest(value: Any, length: int) -> bool:
    text = str(value or "").casefold()
    return len(text) == length and all(character in _HEX for character in text)


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _finite_nonnegative(value: Any) -> bool:
    return _finite_nonnegative_float(value) is not None


def _finite_nonnegative_float(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def _finite_metric_mapping(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(
            isinstance(metric, (int, float))
            and not isinstance(metric, bool)
            and math.isfinite(float(metric))
            for metric in value.values()
        )
    )


def _exact_finite_metric_mapping(value: Any, keys: frozenset[str]) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == keys
        and _finite_metric_mapping(value)
    )


def _nonempty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _unique_nonempty_string_list(value: Any) -> bool:
    return bool(_nonempty_string_list(value) and len(set(value)) == len(value))


def _string_value_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item.strip() for item in value if isinstance(item, str) and item.strip()}


def _correlation_errors(value: Mapping[str, Any], *, prefix: str) -> list[str]:
    errors: list[str] = []
    if not str(value.get("run_id") or "").strip():
        errors.append(f"{prefix} correlation run_id is missing")
    if not str(value.get("split") or "").strip():
        errors.append(f"{prefix} correlation split is missing")
    if type(value.get("fold")) is not int or int(value["fold"]) < 0:
        errors.append(f"{prefix} correlation fold is invalid")
    for field in ("publication_generation", "training_generation"):
        if type(value.get(field)) is not int or int(value[field]) < 0:
            errors.append(f"{prefix} correlation {field} is invalid")
    if value.get("training_boundary_stable") is not True:
        errors.append(f"{prefix} correlation training boundary is unstable")
    if not _hex_digest(value.get("split_specification_fingerprint"), 64):
        errors.append(f"{prefix} correlation split fingerprint is invalid")
    if (
        type(value.get("split_epoch_revision")) is not int
        or int(value["split_epoch_revision"]) < 1
    ):
        errors.append(f"{prefix} correlation split epoch revision is invalid")
    producers = value.get("producer_identities")
    if not isinstance(producers, list) or not producers:
        errors.append(f"{prefix} correlation producer identities are missing")
    else:
        for index, producer in enumerate(producers):
            payload = _mapping(producer)
            for field in (
                "fingerprint",
                "dataset_fingerprint",
                "split_fingerprint",
                "run_fingerprint",
                "model_fingerprint",
            ):
                if not _hex_digest(payload.get(field), 64):
                    errors.append(f"{prefix} producer[{index}] {field} is invalid")
    return errors


def _artifact_errors(value: Any, *, artifact_root: Path, label: str) -> list[str]:
    path = Path(str(value or "")).expanduser()
    root = artifact_root.expanduser().resolve()
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return [f"receipt artifact {label} escapes the artifact root"]
    if path.is_symlink():
        return [f"receipt artifact {label} must not be a symlink"]
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        return [f"receipt artifact {label} is missing or empty"]
    image = QImage(str(resolved))
    if image.isNull() or image.width() < 16 or image.height() < 16:
        return [f"receipt artifact {label} is not a decodable nonzero PNG"]
    sample = image.scaled(
        32,
        32,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    colors = {
        sample.pixelColor(x, y).rgba()
        for x in range(sample.width())
        for y in range(sample.height())
    }
    if len(colors) < 2:
        return [f"receipt artifact {label} is visually blank"]
    return []


def _visual_artifact_identity_errors(
    artifacts: Mapping[str, Any],
    *,
    artifact_root: Path,
) -> list[str]:
    """Require every stage/result visual to be independently captured evidence."""
    screenshots = _mapping(artifacts.get("screenshots"))
    candidates = [
        (f"screenshot[{stage}]", screenshots.get(stage)) for stage in REQUIRED_STAGES
    ]
    candidates.extend(
        (field, artifacts.get(field)) for field in ("saliency_map", "spectrogram")
    )
    root = artifact_root.expanduser().resolve()
    paths: dict[Path, str] = {}
    content_identities: dict[str, str] = {}
    errors: list[str] = []
    for label, value in candidates:
        path = Path(str(value or "")).expanduser()
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if path.is_symlink() or not resolved.is_file():
            continue

        previous_label = paths.get(resolved)
        if previous_label is not None:
            errors.append(
                f"receipt visual artifacts {previous_label} and {label} reuse one path"
            )
            continue

        try:
            aliased_label = next(
                (
                    existing_label
                    for existing_path, existing_label in paths.items()
                    if resolved.samefile(existing_path)
                ),
                None,
            )
            if aliased_label is not None:
                errors.append(
                    "receipt visual artifacts "
                    f"{aliased_label} and {label} reuse one filesystem identity"
                )
                continue
            paths[resolved] = label
            if label not in {"saliency_map", "spectrogram"}:
                continue
            with resolved.open("rb") as handle:
                content_identity = hashlib.file_digest(handle, "sha256").hexdigest()
        except OSError:
            continue
        previous_label = content_identities.setdefault(content_identity, label)
        if previous_label != label:
            errors.append(
                "receipt visual artifacts "
                f"{previous_label} and {label} reuse one content identity"
            )
    return errors


def _valid_numeric_summary(value: Any) -> bool:
    summary = _mapping(value)
    count = summary.get("count")
    finite_count = summary.get("finite_count")
    nonfinite_count = summary.get("nonfinite_count")
    minimum = summary.get("minimum")
    maximum = summary.get("maximum")
    return (
        type(count) is int
        and count > 0
        and type(finite_count) is int
        and finite_count == count
        and nonfinite_count == 0
        and isinstance(minimum, (int, float))
        and not isinstance(minimum, bool)
        and math.isfinite(float(minimum))
        and isinstance(maximum, (int, float))
        and not isinstance(maximum, bool)
        and math.isfinite(float(maximum))
        and float(minimum) <= float(maximum)
    )


def _valid_evaluation_output_summary(
    value: Any,
    *,
    class_count: int,
    sample_count: Any,
) -> bool:
    summary = _mapping(value)
    required = {
        "shape",
        "dtype",
        "count",
        "finite_count",
        "nonfinite_count",
        "minimum",
        "maximum",
    }
    if set(summary) != required:
        return False
    shape = summary.get("shape")
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or any(type(dimension) is not int or dimension < 1 for dimension in shape)
        or type(class_count) is not int
        or class_count < 1
        or shape[1] != class_count
    ):
        return False
    dtype = summary.get("dtype")
    if not isinstance(dtype, str) or not any(
        dtype.startswith(prefix) and dtype.removeprefix(prefix).isdigit()
        for prefix in ("float", "int", "uint")
    ):
        return False
    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, (int, float))
        or not math.isfinite(float(sample_count))
        or float(sample_count) != shape[0]
    ):
        return False
    return summary.get("count") == shape[0] * shape[1] and _valid_numeric_summary(
        {
            "count": summary.get("count"),
            "finite_count": summary.get("finite_count"),
            "nonfinite_count": summary.get("nonfinite_count"),
            "minimum": summary.get("minimum"),
            "maximum": summary.get("maximum"),
        }
    )
