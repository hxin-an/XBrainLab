"""Fail-closed evidence contract for app-polish UI captures."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    ROOT,
    collect_source_identity,
    inspect_screenshot_artifact,
    validate_source_identity,
)

SCHEMA_VERSION = 5
ARTIFACT_TYPE = "xbrainlab.app_polish_ui_surfaces"
MANIFEST_NAME = "app-polish-evidence.json"
GENERATOR = "scripts/dev/capture_ui_polish_surfaces.py"
APP_POLISH_SURFACES = (
    "model-selection-dialog.png",
    "training-setting-dialog.png",
    "preprocess-rereference-dialog.png",
    "preprocess-epoching-internal-events-dialog.png",
    "preprocess-epoching-bids-interval-duration-dialog.png",
    "data-splitting-dialog.png",
    "data-splitting-dialog-narrow.png",
    "data-splitting-preview-dialog.png",
    "assistant-setup-required-narrow.png",
    "assistant-active-turn-narrow.png",
    "assistant-loading.png",
    "assistant-failed.png",
    "assistant-recovery-loading.png",
    "saliency-setting-dialog.png",
    "saliency-setting-single-method.png",
    "saliency-setting-empty-state.png",
    "set-montage-dialog.png",
    "evaluation-controls-panel.png",
    "evaluation-metrics-table.png",
    "training-history-few-rows.png",
    "training-history-many-rows.png",
)
DEFAULT_MAX_AGE = timedelta(hours=24)
_FUTURE_TOLERANCE = timedelta(minutes=5)
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCREENSHOT_FIELDS = (
    "path",
    "exists",
    "readable",
    "byte_size",
    "sha256",
    "dimensions",
    "format",
)


def build_app_polish_evidence(
    output_dir: Path,
    *,
    expected_surfaces: Sequence[str],
    selected_surfaces: Sequence[str],
    surface_contracts: Mapping[str, Mapping[str, Any]],
    generated_at: datetime | None = None,
    capture_started_at: datetime | None = None,
    source_identity: Mapping[str, Any] | None = None,
    source_identity_at_start: Mapping[str, Any] | None = None,
    qt_platform: str = "",
) -> dict[str, Any]:
    """Build a content-addressed manifest after every capture has settled."""
    root = output_dir.expanduser().resolve()
    expected = list(dict.fromkeys(map(str, expected_surfaces)))
    selected = list(dict.fromkeys(map(str, selected_surfaces)))
    screenshots: dict[str, dict[str, Any]] = {}
    for filename in selected:
        metadata = inspect_screenshot_artifact(root / filename)
        metadata["path"] = filename
        screenshots[filename] = metadata

    captured_at = (generated_at or datetime.now(UTC)).astimezone(UTC)
    identity = dict(
        source_identity
        if source_identity is not None
        else collect_source_identity(ROOT, refresh=True)
    )
    started_at = (capture_started_at or captured_at).astimezone(UTC)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at_utc": captured_at.isoformat(),
        "generator": GENERATOR,
        "capture_environment": {
            "qt_platform": str(qt_platform),
            "capture_kind": "deterministic_qt_widget",
            "qt_style": "Fusion",
            "application_stylesheet": "Stylesheets.MAIN_WINDOW",
        },
        "capture_session": build_source_bound_capture_session(
            source_identity=identity,
            source_identity_at_start=source_identity_at_start,
            capture_started_at=started_at,
            completed_at=captured_at,
        ),
        "capture_scope": {
            "expected_surfaces": expected,
            "selected_surfaces": selected,
            "complete": selected == expected,
        },
        "source_identity": identity,
        "screenshots": screenshots,
        "surface_contracts": {
            str(name): dict(contract)
            for name, contract in surface_contracts.items()
            if str(name) in selected
        },
        "claim_boundary": (
            "Automated Qt capture evidence; not human Windows desktop acceptance."
        ),
    }


def write_app_polish_evidence(
    output_dir: Path,
    payload: Mapping[str, Any],
) -> Path:
    """Atomically publish the app-polish JSON manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / MANIFEST_NAME
    temporary = output_dir / f".{MANIFEST_NAME}.tmp"
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def load_app_polish_evidence(output_dir: Path) -> dict[str, Any]:
    """Read the canonical app-polish manifest as a mapping."""
    value = json.loads((output_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("App-polish evidence root must be a JSON object.")
    return value


def validate_app_polish_evidence(
    payload: Mapping[str, Any],
    *,
    output_dir: Path,
    require_complete: bool = True,
    max_age: timedelta | None = DEFAULT_MAX_AGE,
    now: datetime | None = None,
    refresh_source_identity: bool = True,
    current_source_identity: Mapping[str, Any] | None = None,
    expected_surfaces: Sequence[str] = APP_POLISH_SURFACES,
) -> tuple[bool, str]:
    """Reject missing, stale, tampered, or semantically inconsistent evidence."""
    if refresh_source_identity and current_source_identity is not None:
        return False, "Current source identity override cannot bypass refresh."
    if not refresh_source_identity and current_source_identity is None:
        return False, "Disabled source refresh requires an explicit current identity."
    if payload.get("schema_version") != SCHEMA_VERSION:
        return False, "App-polish schema version is missing or unsupported."
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        return False, "Artifact is not app-polish UI evidence."
    if payload.get("generator") != GENERATOR:
        return False, "App-polish generator identity is missing or unsupported."
    capture_environment = _mapping(payload.get("capture_environment"))
    if (
        capture_environment.get("capture_kind") != "deterministic_qt_widget"
        or capture_environment.get("qt_style") != "Fusion"
        or capture_environment.get("application_stylesheet")
        != "Stylesheets.MAIN_WINDOW"
    ):
        return False, "App-polish capture did not use the formal application theme."

    ok, reason = _validate_timestamp(
        payload.get("generated_at_utc"),
        now=now,
        max_age=max_age,
    )
    if not ok:
        return ok, reason
    ok, reason = _validate_source_identity(
        payload.get("source_identity"),
        refresh=refresh_source_identity,
        current_identity=current_source_identity,
    )
    if not ok:
        return ok, reason
    ok, reason = _validate_capture_session(
        payload.get("capture_session"),
        generated_at=payload.get("generated_at_utc"),
        source_identity=payload.get("source_identity"),
    )
    if not ok:
        return ok, reason

    scope = _mapping(payload.get("capture_scope"))
    expected = _string_list(scope.get("expected_surfaces"))
    selected = _string_list(scope.get("selected_surfaces"))
    canonical_expected = list(dict.fromkeys(map(str, expected_surfaces)))
    if expected != canonical_expected:
        return (
            False,
            "App-polish expected surfaces do not match the canonical surface inventory.",
        )
    if not expected or len(expected) != len(set(expected)):
        return False, "App-polish expected surface list is missing or duplicated."
    if not selected or len(selected) != len(set(selected)):
        return False, "App-polish selected surface list is missing or duplicated."
    if any(name not in expected for name in selected):
        return False, "App-polish selected surfaces are outside the capture contract."
    complete = selected == expected
    if bool(scope.get("complete")) is not complete:
        return False, "App-polish capture completeness flag is inconsistent."
    if require_complete and not complete:
        return False, "App-polish evidence is a partial capture, not current evidence."

    screenshots = _mapping(payload.get("screenshots"))
    contracts = _mapping(payload.get("surface_contracts"))
    if set(screenshots) != set(selected):
        return False, "App-polish screenshot manifest does not match selected surfaces."
    if set(contracts) != set(selected):
        return False, "App-polish surface contracts do not match selected surfaces."
    root = output_dir.expanduser().resolve()
    for filename in selected:
        ok, reason = _validate_screenshot(root, filename, screenshots.get(filename))
        if not ok:
            return ok, reason
        ok, reason = _validate_surface_contract(filename, contracts.get(filename))
        if not ok:
            return ok, reason
    ok, reason = _validate_training_history_visual_pair(contracts)
    if not ok:
        return ok, reason

    claim_boundary = str(payload.get("claim_boundary") or "")
    if "not human Windows desktop acceptance" not in claim_boundary:
        return False, "App-polish claim boundary does not exclude human acceptance."
    return True, ""


def _validate_timestamp(
    value: object,
    *,
    now: datetime | None,
    max_age: timedelta | None,
) -> tuple[bool, str]:
    text = str(value or "")
    if not text:
        return False, "App-polish UTC timestamp is missing."
    try:
        generated_at = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False, "App-polish UTC timestamp is invalid."
    if generated_at.tzinfo is None or generated_at.utcoffset() != timedelta(0):
        return False, "App-polish timestamp is not UTC."
    current = (now or datetime.now(UTC)).astimezone(UTC)
    generated_at = generated_at.astimezone(UTC)
    if generated_at > current + _FUTURE_TOLERANCE:
        return False, "App-polish timestamp is implausibly in the future."
    if max_age is not None and current - generated_at > max_age:
        return False, "App-polish evidence timestamp is stale."
    return True, ""


def _validate_capture_session(
    value: object,
    *,
    generated_at: object,
    source_identity: object,
) -> tuple[bool, str]:
    return validate_source_bound_capture_session(
        value,
        generated_at=generated_at,
        source_identity=source_identity,
        artifact_name="App-polish",
    )


def build_source_bound_capture_session(
    *,
    source_identity: Mapping[str, Any],
    source_identity_at_start: Mapping[str, Any] | None,
    capture_started_at: datetime,
    completed_at: datetime,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Build the shared source-stability binding used by capture manifests."""
    starting_identity = dict(source_identity_at_start or source_identity)
    starting_digest = str(starting_identity.get("source_digest") or "")
    completion_digest = str(source_identity.get("source_digest") or "")
    if not starting_digest or starting_digest != completion_digest:
        raise RuntimeError("Product source changed during capture; discard this run.")
    session: dict[str, Any] = {
        "started_at_utc": capture_started_at.astimezone(UTC).isoformat(),
        "completed_at_utc": completed_at.astimezone(UTC).isoformat(),
        "source_digest_at_start": starting_digest,
        "source_digest_at_completion": completion_digest,
        "source_identity_stable": True,
    }
    if session_id:
        session["session_id"] = session_id
    return session


def validate_source_bound_capture_session(
    value: object,
    *,
    generated_at: object,
    source_identity: object,
    artifact_name: str,
) -> tuple[bool, str]:
    session = _mapping(value)
    required = {
        "started_at_utc",
        "completed_at_utc",
        "source_digest_at_start",
        "source_digest_at_completion",
        "source_identity_stable",
    }
    if not required <= set(session):
        return False, f"{artifact_name} capture completion binding is incomplete."
    try:
        started = datetime.fromisoformat(
            str(session.get("started_at_utc") or "").replace("Z", "+00:00")
        )
        completed = datetime.fromisoformat(
            str(session.get("completed_at_utc") or "").replace("Z", "+00:00")
        )
        generated = datetime.fromisoformat(
            str(generated_at or "").replace("Z", "+00:00")
        )
    except ValueError:
        return False, f"{artifact_name} capture completion timestamps are invalid."
    if (
        started.tzinfo is None
        or completed.tzinfo is None
        or generated.tzinfo is None
        or started.utcoffset() != timedelta(0)
        or completed.utcoffset() != timedelta(0)
        or generated.utcoffset() != timedelta(0)
        or started > completed
        or completed != generated
    ):
        return False, f"{artifact_name} capture completion timestamps are inconsistent."

    identity_digest = str(_mapping(source_identity).get("source_digest") or "")
    start_digest = str(session.get("source_digest_at_start") or "")
    completion_digest = str(session.get("source_digest_at_completion") or "")
    if (
        session.get("source_identity_stable") is not True
        or not _HEX_SHA256.fullmatch(start_digest)
        or start_digest != completion_digest
        or completion_digest != identity_digest
    ):
        return (
            False,
            f"{artifact_name} capture completion is not bound to one source identity.",
        )
    return True, ""


def _validate_source_identity(
    value: object,
    *,
    refresh: bool,
    current_identity: Mapping[str, Any] | None,
) -> tuple[bool, str]:
    return validate_source_bound_identity(
        value,
        refresh=refresh,
        current_identity=current_identity,
        artifact_name="App-polish",
    )


def validate_source_bound_identity(
    value: object,
    *,
    refresh: bool,
    current_identity: Mapping[str, Any] | None,
    artifact_name: str,
) -> tuple[bool, str]:
    return validate_source_identity(
        value,
        expected_repo_root=ROOT,
        refresh=refresh,
        current_identity=current_identity,
        artifact_name=artifact_name,
    )


def _validate_screenshot(
    root: Path,
    filename: str,
    value: object,
) -> tuple[bool, str]:
    return validate_source_bound_screenshot(
        root,
        filename,
        value,
        artifact_name="App-polish",
    )


def validate_source_bound_screenshot(
    root: Path,
    filename: str,
    value: object,
    *,
    artifact_name: str,
) -> tuple[bool, str]:
    metadata = _mapping(value)
    if not metadata:
        return False, f"{artifact_name} screenshot metadata is missing: {filename}."
    missing = [field for field in SCREENSHOT_FIELDS if field not in metadata]
    if missing:
        return False, f"{artifact_name} screenshot metadata is incomplete: {filename}."
    relative = Path(str(metadata.get("path") or ""))
    if (
        relative.is_absolute()
        or relative != Path(filename)
        or relative.name != filename
    ):
        return False, f"{artifact_name} screenshot path is not canonical: {filename}."
    observed = inspect_screenshot_artifact(root / relative)
    observed["path"] = filename
    for field in SCREENSHOT_FIELDS:
        if metadata.get(field) != observed.get(field):
            return (
                False,
                f"{artifact_name} screenshot metadata/hash mismatch: {filename} ({field}).",
            )
    dimensions = metadata.get("dimensions")
    if not (
        isinstance(dimensions, list)
        and len(dimensions) == 2
        and all(isinstance(item, int) and item > 0 for item in dimensions)
    ):
        return False, f"{artifact_name} screenshot dimensions are invalid: {filename}."
    if int(metadata.get("byte_size") or 0) <= 0:
        return False, f"{artifact_name} screenshot byte size is invalid: {filename}."
    if not _HEX_SHA256.fullmatch(str(metadata.get("sha256") or "")):
        return False, f"{artifact_name} screenshot hash is invalid: {filename}."
    return True, ""


def _validate_surface_contract(filename: str, value: object) -> tuple[bool, str]:
    contract = _mapping(value)
    if contract.get("contract_version") != 1 or contract.get("passed") is not True:
        return False, f"App-polish surface contract did not pass: {filename}."
    verified_controls = _string_list(contract.get("verified_controls"))
    if not verified_controls:
        return False, f"App-polish visible-control contract is missing: {filename}."
    frame_readiness = _mapping(contract.get("frame_readiness"))
    required_regions = _string_list(frame_readiness.get("required_regions"))
    if (
        frame_readiness.get("consecutive_complete_frames") != 2
        or frame_readiness.get("stable") is not True
        or not required_regions
        or frame_readiness.get("reference_validated") is not True
        or frame_readiness.get("capture_method") != "QWidget.grab"
    ):
        return False, f"App-polish frame readiness contract is incomplete: {filename}."
    try:
        changed_ratio = float(cast(Any, frame_readiness.get("max_changed_pixel_ratio")))
    except (TypeError, ValueError):
        return False, f"App-polish frame readiness ratio is invalid: {filename}."
    if not 0.0 <= changed_ratio <= 0.12:
        return False, f"App-polish frame readiness did not settle: {filename}."
    comparison_count = _positive_int(frame_readiness.get("reference_comparison_count"))
    try:
        minimum_edge_recall = float(
            cast(Any, frame_readiness.get("minimum_reference_edge_recall"))
        )
        maximum_reference_change = float(
            cast(Any, frame_readiness.get("maximum_reference_changed_pixel_ratio"))
        )
    except (TypeError, ValueError):
        return False, f"App-polish reference render metrics are invalid: {filename}."
    if (
        comparison_count < len(required_regions)
        or not 0.42 <= minimum_edge_recall <= 1.0
        or not 0.0 <= maximum_reference_change <= 1.0
    ):
        return False, f"App-polish reference render contract failed: {filename}."
    reference_regions = _mapping_list(frame_readiness.get("reference_regions"))
    if len(reference_regions) != comparison_count:
        return False, f"App-polish reference region evidence is incomplete: {filename}."
    region_names = [
        str(region.get("surface_name") or "") for region in reference_regions
    ]
    if len(region_names) != len(set(region_names)) or not set(required_regions) <= set(
        region_names
    ):
        return False, f"App-polish reference region names are inconsistent: {filename}."
    observed_edge_recalls: list[float] = []
    observed_changed_ratios: list[float] = []
    for region in reference_regions:
        ok, reason = _validate_reference_region(filename, region)
        if not ok:
            return ok, reason
        observed_edge_recalls.append(float(region["edge_recall"]))
        observed_changed_ratios.append(float(region["changed_pixel_ratio"]))
    if round(min(observed_edge_recalls), 6) != round(minimum_edge_recall, 6) or round(
        max(observed_changed_ratios), 6
    ) != round(maximum_reference_change, 6):
        return (
            False,
            f"App-polish reference region summary is inconsistent: {filename}.",
        )

    if filename == "data-splitting-preview-dialog.png":
        if contract.get("kind") != "data_splitting_preview":
            return False, "Data splitting semantic contract kind is invalid."
        fold_count = _positive_int(contract.get("k_fold_count"))
        rows = contract.get("dataset_rows")
        rows = rows if isinstance(rows, list) else []
        expected_names = [f"Fold_{index}" for index in range(fold_count)]
        names = [str(_mapping(row).get("name") or "") for row in rows]
        if contract.get("split_unit") != "K Fold" or fold_count < 2:
            return False, "Data splitting K-fold control is invalid."
        if len(rows) != fold_count or names != expected_names:
            return False, "Data splitting K-fold count and result rows disagree."
        if any(
            _positive_int(_mapping(row).get("total"))
            != _positive_int(contract.get("trial_count"))
            for row in rows
        ):
            return False, "Data splitting row totals disagree with the trial count."

    epoch_scenarios = {
        "preprocess-epoching-internal-events-dialog.png": "internal_events",
        "preprocess-epoching-bids-interval-duration-dialog.png": (
            "bids_interval_duration"
        ),
    }
    if filename in epoch_scenarios:
        if contract.get("kind") != "epoching_dialog":
            return False, f"Epoch surface contract kind is invalid: {filename}."
        if contract.get("scenario") != epoch_scenarios[filename]:
            return False, f"Epoch scenario identity is invalid: {filename}."
        if contract.get("primary_action") != "Create Epochs":
            return False, f"Epoch primary action is missing: {filename}."
        if contract.get("cancel_action") != "Cancel":
            return False, f"Epoch cancel action is missing: {filename}."
        if _positive_int(contract.get("selected_event_count")) <= 0:
            return False, f"Epoch event selection is empty: {filename}."
        required_controls = {
            "preprocess-epoching-internal-events-dialog.png": (
                "Create Epochs",
                "Suggested from import",
                "labels inside EEG files",
                "Events inside EEG files",
                "Events",
                "Time Window",
                "Apply baseline correction",
                "Cancel",
            ),
            "preprocess-epoching-bids-interval-duration-dialog.png": (
                "Create Epochs",
                "BIDS events from import",
                "BIDS events confirmed in Match Labels.",
                "Label interval",
                "trial_type",
                "onset + duration",
                "Use event duration.",
                "Events",
                "Time Window",
                "Apply baseline correction",
                "Cancel",
            ),
        }[filename]
        missing_controls = [
            item
            for item in required_controls
            if not any(item in observed for observed in verified_controls)
        ]
        if missing_controls:
            return False, f"Epoch visible-control contract is incomplete: {filename}."
        if filename == "preprocess-epoching-internal-events-dialog.png" and (
            contract.get("source") != "labels inside EEG files"
            or contract.get("placement_method") != "internal_events"
            or contract.get("placement_label") != "Events inside EEG files"
            or contract.get("window_mode") != "event_locked"
        ):
            return False, "Internal-event Epoch contract is inconsistent."
        if filename.endswith("bids-interval-duration-dialog.png") and (
            contract.get("source") != "BIDS events"
            or contract.get("placement_method") != "interval"
            or contract.get("placement_label") != "Label interval"
            or contract.get("label_field") != "trial_type"
            or contract.get("window_mode") != "duration"
            or contract.get("time_field") != "onset"
            or contract.get("duration_field") != "duration"
        ):
            return False, "BIDS interval/duration Epoch contract is inconsistent."

    training_scenarios = {
        "training-history-few-rows.png": (2, False),
        "training-history-many-rows.png": (9, True),
    }
    if filename in training_scenarios:
        expected_rows, expected_running = training_scenarios[filename]
        if contract.get("kind") != "training_history":
            return False, f"Training History contract kind is invalid: {filename}."
        if _positive_int(contract.get("row_count")) != expected_rows:
            return False, f"Training History row count is invalid: {filename}."
        if contract.get("running") is not expected_running:
            return False, f"Training History running state is invalid: {filename}."
        statuses = _string_list(contract.get("statuses"))
        start_enabled = contract.get("start_enabled") is True
        stop_enabled = contract.get("stop_enabled") is True
        if expected_running:
            coherent = "Running" in statuses and not start_enabled and stop_enabled
        else:
            coherent = (
                bool(statuses)
                and set(statuses) == {"Completed"}
                and start_enabled
                and not stop_enabled
            )
        if not coherent or contract.get("key_columns_fit") is not True:
            return (
                False,
                f"Training History state contract is inconsistent: {filename}.",
            )
        visible_row_capacity = _positive_int(contract.get("visible_row_capacity"))
        if visible_row_capacity <= 0:
            return False, f"Training History visible capacity is missing: {filename}."
        expected_visible_rows = list(range(min(expected_rows, visible_row_capacity)))
        if contract.get("fully_visible_rows") != expected_visible_rows:
            return False, f"Training History visible rows are incomplete: {filename}."
        if contract.get("partially_visible_rows"):
            return False, f"Training History clips a partial row: {filename}."
        if (
            _button_visual_signature(contract.get("start_visual")) is None
            or _button_visual_signature(contract.get("stop_visual")) is None
        ):
            return False, f"Training History button evidence is incomplete: {filename}."
        required_chrome = {
            "Training History chrome title: TRAINING PLOTS",
            "Training History chrome title: TRAINING HISTORY",
            "Training History chrome tab: Accuracy",
            "Training History chrome tab: Loss",
            "Training History chrome tab: Log",
        }
        if not required_chrome <= set(region_names):
            return False, f"Training History chrome evidence is incomplete: {filename}."
        required_cell_names = {
            f"Training History cell row {row}: {column}"
            for row in ((1, 2, 3) if expected_running else (1, 2))
            for column in ("Group", "Run", "Model", "Status")
        }
        if expected_running:
            required_cell_names.update(
                {
                    f"Training History cell row {row}: {column}"
                    for row in (1, 2)
                    for column in ("Epochs", "Train Loss", "Train Acc", "Val Loss")
                }
            )
        if not required_cell_names <= set(region_names):
            return False, f"Training History cell evidence is incomplete: {filename}."
    return True, ""


def _validate_training_history_visual_pair(
    contracts: Mapping[str, Any],
) -> tuple[bool, str]:
    few = _mapping(contracts.get("training-history-few-rows.png"))
    many = _mapping(contracts.get("training-history-many-rows.png"))
    if not few or not many:
        return True, ""
    few_start = _button_visual_signature(few.get("start_visual"))
    many_start = _button_visual_signature(many.get("start_visual"))
    few_stop = _button_visual_signature(few.get("stop_visual"))
    many_stop = _button_visual_signature(many.get("stop_visual"))
    signatures = [
        signature
        for signature in (few_start, many_start, few_stop, many_stop)
        if signature is not None
    ]
    if len(signatures) != 4:
        return False, "Training History button visual evidence is incomplete."
    few_start, many_start, few_stop, many_stop = signatures
    if _rgb_distance(few_start, many_start) < 35.0:
        return False, "Training History disabled Start is not visually distinct."
    if _rgb_distance(few_stop, many_stop) < 35.0:
        return False, "Training History disabled Stop is not visually distinct."
    if many_start["color_span"] >= few_start["color_span"] - 8.0:
        return False, "Training History disabled Start still reads as primary."
    return True, ""


def _button_visual_signature(value: object) -> dict[str, float] | None:
    signature = _mapping(value)
    rgb = signature.get("mean_rgb")
    if (
        not isinstance(rgb, list)
        or len(rgb) != 3
        or not all(isinstance(channel, (int, float)) for channel in rgb)
    ):
        return None
    try:
        parsed = {
            "red": float(rgb[0]),
            "green": float(rgb[1]),
            "blue": float(rgb[2]),
            "luminance": float(cast(Any, signature.get("luminance"))),
            "color_span": float(cast(Any, signature.get("color_span"))),
        }
    except (TypeError, ValueError):
        return None
    if not all(0.0 <= parsed[channel] <= 255.0 for channel in ("red", "green", "blue")):
        return None
    if (
        not 0.0 <= parsed["luminance"] <= 255.0
        or not 0.0 <= parsed["color_span"] <= 255.0
    ):
        return None
    return parsed


def _rgb_distance(
    first: Mapping[str, float],
    second: Mapping[str, float],
) -> float:
    return (
        sum(
            (first[channel] - second[channel]) ** 2
            for channel in ("red", "green", "blue")
        )
        ** 0.5
    )


def _validate_reference_region(
    filename: str,
    region: Mapping[str, Any],
) -> tuple[bool, str]:
    name = str(region.get("surface_name") or "")
    bounds = region.get("bounds")
    if (
        not name
        or not isinstance(bounds, list)
        or len(bounds) != 4
        or not all(isinstance(value, int) for value in bounds)
        or bounds[0] >= bounds[2]
        or bounds[1] >= bounds[3]
    ):
        return False, f"App-polish reference region geometry is invalid: {filename}."
    try:
        edge_recall = float(cast(Any, region.get("edge_recall")))
        changed_ratio = float(cast(Any, region.get("changed_pixel_ratio")))
        missing_tile_ratio = float(cast(Any, region.get("missing_detail_tile_ratio")))
        minimum_edge_recall = float(
            cast(Any, region.get("minimum_required_edge_recall"))
        )
        maximum_changed_ratio = float(
            cast(Any, region.get("maximum_allowed_changed_pixel_ratio"))
        )
        maximum_missing_tile_ratio = float(
            cast(Any, region.get("maximum_allowed_missing_detail_tile_ratio"))
        )
    except (TypeError, ValueError):
        return False, f"App-polish reference region metrics are invalid: {filename}."
    minimum_edge_pixels = _positive_int(region.get("minimum_reference_edge_pixels"))
    if (
        minimum_edge_pixels < 4
        or _positive_int(region.get("reference_edge_pixels")) < minimum_edge_pixels
        or _positive_int(region.get("detail_tile_count")) < 1
        or not 0.0 <= edge_recall <= 1.0
        or not 0.0 <= changed_ratio <= 1.0
        or not 0.0 <= missing_tile_ratio <= 1.0
        or not 0.0 <= minimum_edge_recall <= 1.0
        or not 0.0 <= maximum_changed_ratio <= 1.0
        or not 0.0 <= maximum_missing_tile_ratio <= 1.0
        or edge_recall < minimum_edge_recall
        or changed_ratio > maximum_changed_ratio
        or missing_tile_ratio > maximum_missing_tile_ratio
    ):
        return False, f"App-polish reference region failed: {filename} ({name})."
    return True, ""


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [str(item) for item in value]


def _mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _positive_int(value: object) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0
