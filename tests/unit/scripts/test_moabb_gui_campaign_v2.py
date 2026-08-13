from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import signal
import sys
import time
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEventLoop, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scripts.dev.moabb_gui_campaign_v2 import contract as campaign_contract
from scripts.dev.moabb_gui_campaign_v2 import runner as campaign_runner
from scripts.dev.moabb_gui_campaign_v2.contract import (
    CANCELLATION_MEANINGFUL_STAGES,
    CANCELLATION_PARTITIONS,
    DATASET_MATRIX,
    JOURNEY_MODES,
    REQUIRED_STAGES,
    _artifact_errors,
    _ready_dataset_errors,
    load_campaign_plan,
    receipt_plan_binding_errors,
    validate_campaign_plan,
    validate_campaign_receipt_denominator,
    validate_campaign_receipts,
    validate_journey_receipt,
)
from scripts.dev.moabb_gui_campaign_v2.driver import (
    MINIMUM_PRODUCTION_HOOKS,
    ActiveOperationEvidence,
    ClickAcknowledgement,
    DriverContractError,
    GuiCampaignDriver,
    ProgressWaitEvidence,
    VisibleControl,
    missing_product_source_hooks,
)
from scripts.dev.moabb_gui_campaign_v2.evidence import (
    JourneyEvidenceCollector,
    _metrics_from_table,
)
from scripts.dev.moabb_gui_campaign_v2.journey import (
    CANCELLATION_CONTROL,
    STAGE_CONTROL_ROUTE,
    ProductRecommendedJourneyScaffold,
    StageInteraction,
)
from scripts.dev.moabb_gui_campaign_v2.runner import (
    JourneyCommand,
    JourneyProcessOutcome,
    _campaign_child_environment,
    _quarantine_stale_receipt,
    _run_owned_process,
    _seal_journey_receipt,
    _validated_fresh_evidence_root,
    build_journey_commands,
)
from scripts.dev.moabb_gui_campaign_v2.worker import (
    _require_complete_public_route,
    build_product_journey,
)
from tests.unit.ui.data_split_test_support import dialog_context_kwargs
from XBrainLab.ui.dialogs.dataset.data_interpretation_loading_dialog import (
    DataInterpretationLoadingDialog,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)
from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DataSplittingDialog
from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
    DataSplittingPreviewDialog,
)
from XBrainLab.ui.main_window import MainWindow

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_QDIALOG_EXEC = QDialog.exec
PLAN_PATH = REPO_ROOT / "artifacts" / "user-journeys" / "moabb-gui-campaign-v2.json"


def _campaign_shortcut_violations(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    violations: set[str] = set()
    forbidden_import_names = {
        "ApplicationService",
        "execute_application_command",
        "execute_application_command_async",
        "get_application_service",
    }
    forbidden_attributes = {
        "_go_to_step",
        "_go_next_step",
        "_go_previous_step",
        "execute",
    }

    def inspect_module(module: str) -> None:
        if ".dialogs" in module:
            violations.add(f"dialog import: {module}")
        if module.startswith("XBrainLab.backend") and module != (
            "XBrainLab.backend.study"
        ):
            violations.add(f"backend import: {module}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                inspect_module(alias.name)
                if alias.name.rsplit(".", 1)[-1] in forbidden_import_names:
                    violations.add(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            inspect_module(module)
            for alias in node.names:
                if alias.name in forbidden_import_names:
                    violations.add(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in forbidden_attributes:
                    violations.add(f"forbidden call: {node.func.attr}")
                if node.func.attr.endswith("Dialog"):
                    violations.add(f"direct dialog: {node.func.attr}")
                is_dynamic_import = (
                    node.func.attr == "import_module"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "importlib"
                )
                if is_dynamic_import and node.args:
                    argument = node.args[0]
                    if isinstance(argument, ast.Constant) and isinstance(
                        argument.value, str
                    ):
                        inspect_module(argument.value)
            elif isinstance(node.func, ast.Name):
                if node.func.id.endswith("Dialog"):
                    violations.add(f"direct dialog: {node.func.id}")
                if node.func.id == "__import__" and node.args:
                    argument = node.args[0]
                    if isinstance(argument, ast.Constant) and isinstance(
                        argument.value, str
                    ):
                        inspect_module(argument.value)
    if "service.execute" in source:
        violations.add("direct service.execute")
    return tuple(sorted(violations))


RECEIPT_SCHEMA_PATH = (
    REPO_ROOT
    / "artifacts"
    / "user-journeys"
    / "moabb-gui-journey-receipt-v2.schema.json"
)
PACKAGE_ROOT = REPO_ROOT / "scripts" / "dev" / "moabb_gui_campaign_v2"


def _write_nonblank_png(path: Path) -> None:
    color_seed = hashlib.sha256(str(path).encode("utf-8")).digest()
    background = QColor(color_seed[0], color_seed[1], color_seed[2])
    foreground = QColor(
        255 - color_seed[0],
        255 - color_seed[1],
        255 - color_seed[2],
    )
    image = QImage(32, 32, QImage.Format.Format_ARGB32)
    image.fill(background)
    for x in range(8, 24):
        for y in range(8, 24):
            image.setPixelColor(x, y, foreground)
    assert image.save(str(path), "PNG")


def _wait_for_test_process_exit(pid: int, *, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.02)
    return False


def _kill_test_process_if_live(pid: int) -> None:
    """Emergency cleanup only for the PID this test just spawned."""
    with suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


def _producer_identity() -> dict[str, str]:
    return {
        "fingerprint": "1" * 64,
        "dataset_fingerprint": "2" * 64,
        "split_fingerprint": "3" * 64,
        "run_fingerprint": "4" * 64,
        "model_fingerprint": "5" * 64,
    }


def _correlation() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "fold": 0,
        "split": "test",
        "publication_generation": 7,
        "training_generation": 3,
        "training_boundary_stable": True,
        "split_specification_fingerprint": "e" * 64,
        "split_epoch_revision": 1,
        "producer_identities": [_producer_identity()],
    }


def _seal_test_process(
    receipt: dict[str, object],
    artifact_root: Path,
) -> Path:
    process = receipt["process"]
    assert isinstance(process, dict)
    process_receipt = artifact_root / "journey-process.json"
    payload = {
        "dataset": receipt["dataset"],
        "journey_mode": receipt["journey_mode"],
        "pid": process["pid"],
        "returncode": 0,
        "timed_out": False,
        "duration_seconds": 12.5,
        "residual_descendant_count": 0,
        "residual_process_group_status": "clean",
    }
    process_receipt.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    process.update(
        {
            "runner_verified": True,
            "timed_out": False,
            "duration_seconds": 12.5,
            "residual_descendant_count": 0,
            "residual_process_group_status": "clean",
            "process_receipt": str(process_receipt),
            "process_receipt_sha256": hashlib.sha256(
                process_receipt.read_bytes()
            ).hexdigest(),
        }
    )
    return process_receipt


def test_campaign_plan_pins_exact_fifteen_dataset_matrix() -> None:
    plan = load_campaign_plan(PLAN_PATH)

    assert plan["schema_version"] == "2.0.0"
    assert plan["profile_id"] == "moabb-15-gui-campaign-v2"
    assert tuple(plan["journey_modes"]) == JOURNEY_MODES
    assert tuple(plan["required_stages"]) == REQUIRED_STAGES
    assert [row["moabb_class"] for row in plan["datasets"]] == list(DATASET_MATRIX)
    assert {
        row["moabb_class"]: tuple(row["subjects"]) for row in plan["datasets"]
    } == DATASET_MATRIX
    assert validate_campaign_plan(plan) == []


def test_campaign_plan_partitions_cancellation_five_five_five() -> None:
    plan = load_campaign_plan(PLAN_PATH)
    assigned = {
        partition: [
            row["moabb_class"]
            for row in plan["datasets"]
            if row["cancellation_partition"] == partition
        ]
        for partition in CANCELLATION_PARTITIONS
    }

    assert {
        partition: len(rows) for partition, rows in assigned.items()
    } == dict.fromkeys(CANCELLATION_PARTITIONS, 5)
    assert [dataset for rows in assigned.values() for dataset in rows] == list(
        DATASET_MATRIX
    )
    targets = {
        partition: {
            row["cancellation_target"]
            for row in plan["datasets"]
            if row["cancellation_partition"] == partition
        }
        for partition in CANCELLATION_PARTITIONS
    }
    assert targets == {
        "import_review": {"import", "review"},
        "apply_epoch": {"apply", "epoch"},
        "training_saliency": {"training", "saliency"},
    }


def test_campaign_plan_requires_bids_identity_before_execution() -> None:
    plan = load_campaign_plan(PLAN_PATH)

    for dataset in plan["datasets"]:
        bids = dataset["bids"]
        assert bids["conversion_parent"].startswith("/mnt/d/")
        assert bids["root"] is None
        source_mode = dataset.get("source_mode", "moabb_convert")
        assert bids["root_resolution"] == {
            "source": (
                "formal_bids_mirror_receipt"
                if source_mode == "formal_bids_mirror"
                else "convert_to_bids_return_value"
            ),
            "must_be_descendant_of_conversion_parent": True,
            "required_basename_prefix": "MNE-BIDS-",
            "required_marker": "dataset_description.json",
        }
        assert bids["format"] in {"EDF", "BrainVision", "EEGLAB", "BDF"}
        assert (source_mode, bids["format"]) in {
            ("moabb_convert", "EDF"),
            ("moabb_convert", "BrainVision"),
            ("moabb_convert", "EEGLAB"),
            ("formal_bids_mirror", "BDF"),
        }
        assert bids["checksum_manifest"].startswith("/mnt/d/")
        assert dataset["execution_state"] == "awaiting_dataset_materialization"


def test_campaign_plan_rejects_reduced_denominator() -> None:
    plan = load_campaign_plan(PLAN_PATH)
    plan["datasets"].pop()

    errors = validate_campaign_plan(plan)

    assert any("exact 15-dataset inventory" in error for error in errors)


def test_campaign_plan_rejects_moabb_release_drift() -> None:
    plan = load_campaign_plan(PLAN_PATH)
    plan["moabb_release"]["commit"] = "0" * 40

    assert any(
        "MOABB release identity" in error for error in validate_campaign_plan(plan)
    )


def test_campaign_plan_pins_returned_nested_bids_root_inside_conversion_parent() -> (
    None
):
    plan = load_campaign_plan(PLAN_PATH)
    row = plan["datasets"][0]
    row["execution_state"] = "ready"
    row["bids"]["root"] = f"{row['bids']['conversion_parent']}/MNE-BIDS-bnci-2014-001"
    row["bids"]["dataset_revision_sha256"] = "a" * 64
    row["oracle"] = {
        "state": "pinned",
        "expected_events": ["class"],
        "expected_classes": ["class"],
        "source_event_id": {"class": 1},
        "expected_product_class_mapping": [
            {"class_index": 0, "event_code": "0", "class_name": "class"}
        ],
        "bids_event_values": {},
        "bids_value_crosscheck": "not-present",
    }

    assert validate_campaign_plan(plan) == []

    escaped = copy.deepcopy(plan)
    escaped_row = escaped["datasets"][0]
    escaped_row["bids"]["root"] = (
        f"{escaped_row['bids']['conversion_parent']}-sibling/MNE-BIDS-wrong"
    )
    assert any(
        "must remain inside conversion_parent" in error
        for error in validate_campaign_plan(escaped)
    )


def test_ready_oracle_allows_run_local_values_only_for_moabb_conversion() -> None:
    dataset = {
        "source_mode": "moabb_convert",
        "bids": {"dataset_revision_sha256": "a" * 64},
        "oracle": {
            "state": "pinned",
            "expected_events": ["left", "right"],
            "expected_classes": ["left", "right"],
            "source_event_id": {"left": 1, "right": 2},
            "expected_product_class_mapping": [
                {"class_index": 0, "event_code": "0", "class_name": "left"},
                {"class_index": 1, "event_code": "1", "class_name": "right"},
            ],
            "bids_event_values": {},
            "bids_value_crosscheck": "run-local",
        },
    }

    assert _ready_dataset_errors(dataset, prefix="dataset") == []

    formal_mirror = copy.deepcopy(dataset)
    formal_mirror["source_mode"] = "formal_bids_mirror"
    assert any(
        "truthful crosscheck" in error
        for error in _ready_dataset_errors(formal_mirror, prefix="dataset")
    )
    formal_mirror["oracle"]["bids_event_values"] = {"left": 9, "right": 7}
    formal_mirror["oracle"]["bids_value_crosscheck"] = (
        "formal-bids-mirror-authoritative"
    )
    assert _ready_dataset_errors(formal_mirror, prefix="dataset") == []


def test_receipt_binding_requires_plan_dataset_revision_and_semantic_oracle() -> None:
    plan = load_campaign_plan(PLAN_PATH)
    row = plan["datasets"][0]
    row["bids"]["dataset_revision_sha256"] = "a" * 64
    row["oracle"] = {
        "state": "pinned",
        "expected_events": ["left", "right"],
        "expected_classes": ["left", "right"],
        "source_event_id": {"left": 0, "right": 1},
        "expected_product_class_mapping": [
            {"class_index": 0, "event_code": "0", "class_name": "left"},
            {"class_index": 1, "event_code": "1", "class_name": "right"},
        ],
        "bids_event_values": {"left": 0, "right": 1},
        "bids_value_crosscheck": "matched",
    }
    plan["materialization"] = {
        "status": "ready",
        "environment_identity_sha256": "9" * 64,
    }
    receipt = {
        "dataset": row["moabb_class"],
        "source_identity": {
            "dataset_checksum_sha256": "a" * 64,
            "environment_identity_sha256": "9" * 64,
        },
        "event_class_summary": {
            "expected_events": ["left", "right"],
            "observed_events": ["left", "right"],
            "expected_classes": ["left", "right"],
            "observed_classes": ["left", "right"],
            "evaluation_class_labels": ["left", "right"],
            "saliency_class_mapping": [
                {"class_index": 0, "event_code": "0", "class_name": "left"},
                {"class_index": 1, "event_code": "1", "class_name": "right"},
            ],
        },
    }

    assert receipt_plan_binding_errors(plan, receipt) == []

    receipt["source_identity"]["dataset_checksum_sha256"] = "b" * 64
    receipt["event_class_summary"]["expected_classes"] = ["wrong"]
    errors = receipt_plan_binding_errors(plan, receipt)
    assert any("dataset checksum" in error for error in errors)
    assert any("class oracle" in error for error in errors)


def test_receipt_binding_rejects_coherent_environment_projection_forgery() -> None:
    plan = load_campaign_plan(PLAN_PATH)
    row = plan["datasets"][0]
    row["bids"]["dataset_revision_sha256"] = "a" * 64
    row["oracle"] = {
        "state": "pinned",
        "expected_events": ["left", "right"],
        "expected_classes": ["left", "right"],
        "source_event_id": {"left": 0, "right": 1},
        "expected_product_class_mapping": [
            {"class_index": 0, "event_code": "0", "class_name": "left"},
            {"class_index": 1, "event_code": "1", "class_name": "right"},
        ],
        "bids_event_values": {"left": 0, "right": 1},
        "bids_value_crosscheck": "matched",
    }
    environment = {
        "identity_sha256": "9" * 64,
        "git": {"commit": "1" * 40},
        "poetry_lock_sha256": "2" * 64,
        "cuda": "13.0",
        "gpu": "Frozen GPU",
    }
    plan["materialization"] = {
        "status": "ready",
        "environment_identity_sha256": environment["identity_sha256"],
    }
    receipt = {
        "dataset": row["moabb_class"],
        "source_identity": {
            "application_commit": "1" * 40,
            "poetry_lock_sha256": "2" * 64,
            "dataset_checksum_sha256": "a" * 64,
            "environment_identity_sha256": "9" * 64,
            "cuda": "13.0",
            "gpu": "Frozen GPU",
        },
        "event_class_summary": {
            "expected_events": ["left", "right"],
            "observed_events": ["left", "right"],
            "expected_classes": ["left", "right"],
            "observed_classes": ["left", "right"],
            "evaluation_class_labels": ["left", "right"],
            "saliency_class_mapping": [
                {"class_index": 0, "event_code": "0", "class_name": "left"},
                {"class_index": 1, "event_code": "1", "class_name": "right"},
            ],
        },
    }

    assert (
        receipt_plan_binding_errors(
            plan,
            receipt,
            authoritative_environment=environment,
        )
        == []
    )

    forged = copy.deepcopy(receipt)
    forged["source_identity"].update(
        {
            "application_commit": "3" * 40,
            "poetry_lock_sha256": "4" * 64,
            "cuda": "99.0",
            "gpu": "Forged GPU",
        }
    )
    errors = receipt_plan_binding_errors(
        plan,
        forged,
        authoritative_environment=environment,
    )

    assert any("application commit" in error for error in errors)
    assert any("Poetry lock" in error for error in errors)
    assert any("CUDA" in error for error in errors)
    assert any("GPU" in error for error in errors)


def test_receipt_binding_separates_source_codes_from_product_class_mapping() -> None:
    plan = load_campaign_plan(PLAN_PATH)
    row = plan["datasets"][0]
    row["bids"]["dataset_revision_sha256"] = "a" * 64
    row["oracle"] = {
        "state": "pinned",
        "expected_events": ["zeta", "alpha"],
        "expected_classes": ["zeta", "alpha"],
        "source_event_id": {"zeta": 7, "alpha": 9},
        "expected_product_class_mapping": [
            {"class_index": 0, "event_code": "0", "class_name": "alpha"},
            {"class_index": 1, "event_code": "1", "class_name": "zeta"},
        ],
        "bids_event_values": {"zeta": 7, "alpha": 9},
        "bids_value_crosscheck": "matched",
    }
    plan["materialization"] = {
        "status": "ready",
        "environment_identity_sha256": "9" * 64,
    }
    receipt = {
        "dataset": row["moabb_class"],
        "source_identity": {
            "dataset_checksum_sha256": "a" * 64,
            "environment_identity_sha256": "9" * 64,
        },
        "event_class_summary": {
            "expected_events": ["zeta", "alpha"],
            "observed_events": ["alpha", "zeta"],
            "expected_classes": ["zeta", "alpha"],
            "observed_classes": ["alpha", "zeta"],
            "evaluation_class_labels": ["alpha", "zeta"],
            "saliency_class_mapping": [
                {"class_index": 0, "event_code": "0", "class_name": "alpha"},
                {"class_index": 1, "event_code": "1", "class_name": "zeta"},
            ],
        },
    }

    assert receipt_plan_binding_errors(plan, receipt) == []

    forged = copy.deepcopy(receipt)
    forged["event_class_summary"]["observed_classes"] = ["zeta", "alpha"]
    forged["event_class_summary"]["evaluation_class_labels"] = ["zeta", "alpha"]
    forged["event_class_summary"]["saliency_class_mapping"] = [
        {"class_index": 0, "event_code": "0", "class_name": "zeta"},
        {"class_index": 1, "event_code": "1", "class_name": "alpha"},
    ]

    errors = receipt_plan_binding_errors(plan, forged)

    assert any("product class order" in error for error in errors)
    assert any("class-index/event-code" in error for error in errors)


def test_receipt_requires_full_stage_and_visual_artifact_contract(
    tmp_path: Path,
) -> None:
    screenshots = {}
    for stage in REQUIRED_STAGES:
        path = tmp_path / f"{stage}.png"
        _write_nonblank_png(path)
        screenshots[stage] = str(path)
    receipt = {
        "schema_version": "2.0.0",
        "artifact_type": "xbrainlab.moabb_gui_journey",
        "status": "completed",
        "dataset": "BNCI2014_001",
        "subjects": [1, 2, 3, 4, 5],
        "journey_mode": "cold",
        "process": {"fresh_process": True, "pid": 1234, "exit_code": 0},
        "source_identity": {
            "application_commit": "a" * 40,
            "campaign_plan_sha256": "f" * 64,
            "poetry_lock_sha256": "b" * 64,
            "dataset_checksum_sha256": "c" * 64,
            "environment_identity_sha256": "9" * 64,
            "cuda": "13.0",
            "gpu": "Test GPU",
        },
        "correlation": _correlation(),
        "stages": [
            {
                "stage": stage,
                "status": "completed",
                "elapsed_seconds": 0.1,
                "visible_control": "CampaignControl",
                "operation_id": f"op-{stage}",
                "click_ack_seconds": 0.01,
                "max_progress_silence_seconds": 0.05,
                "heartbeat_count": 1,
            }
            for stage in REQUIRED_STAGES
        ],
        "artifacts": {
            "screenshots": screenshots,
            "training_metrics": {
                "Train Loss": 1.0,
                "Train Acc": 50.0,
                "Val Loss": 1.1,
                "Val Acc": 49.0,
                "Test Acc": 48.0,
                "LR": 0.001,
            },
            "saliency_map": str(tmp_path / "saliency-map.png"),
            "spectrogram": str(tmp_path / "spectrogram-render.png"),
        },
        "ui_options": {
            "training_epochs": 1,
            "repeats": 1,
            "folds": 1,
            "selection_policy": "product_recommended_with_pinned_semantics",
            "event_value_decisions": [
                {
                    "event_value": "left",
                    "use": "class",
                    "class_name": "left",
                    "selection_basis": "oracle_expected_class",
                },
                {
                    "event_value": "right",
                    "use": "class",
                    "class_name": "right",
                    "selection_basis": "oracle_expected_class",
                },
            ],
            "filtering": {"bandpass_enabled": True},
            "epoch": {"window_mode": "event"},
            "split": {"cross_validation": False, "folds": 1},
            "model": {"stable_id": "eegnet"},
            "training": {
                "selected_device": "Auto",
                "runtime_devices": ["cuda:0"],
            },
            "saliency": {"method": "Gradient"},
        },
        "event_class_summary": {
            "expected_events": ["left", "right"],
            "observed_events": ["left", "right"],
            "expected_classes": ["left", "right"],
            "observed_classes": ["left", "right"],
            "review_mapping": [
                {
                    "event_value": "left",
                    "event_role": "stimulus",
                    "keep_event": True,
                    "use_as_class": True,
                    "class_name": "left",
                    "sources": ["embedded_events"],
                },
                {
                    "event_value": "right",
                    "event_role": "stimulus",
                    "keep_event": True,
                    "use_as_class": True,
                    "class_name": "right",
                    "sources": ["embedded_events"],
                },
            ],
            "applied_event_catalog": [
                {
                    "event_value": "left",
                    "event_role": "stimulus",
                    "keep_event": True,
                    "use_as_class": True,
                    "class_name": "left",
                    "sources": ["embedded_events"],
                },
                {
                    "event_value": "right",
                    "event_role": "stimulus",
                    "keep_event": True,
                    "use_as_class": True,
                    "class_name": "right",
                    "sources": ["embedded_events"],
                },
            ],
            "evaluation_class_labels": ["left", "right"],
            "saliency_class_mapping": [
                {"class_index": 0, "event_code": "0", "class_name": "left"},
                {"class_index": 1, "event_code": "1", "class_name": "right"},
            ],
        },
        "evaluation": {
            "correlation": _correlation(),
            "metrics": {
                "Precision": 0.5,
                "Recall": 0.5,
                "F1-Score": 0.5,
                "Support": 10.0,
            },
            "output_numeric_summary": {
                "shape": [10, 2],
                "dtype": "float32",
                "count": 20,
                "finite_count": 20,
                "nonfinite_count": 0,
                "minimum": -1.5,
                "maximum": 2.0,
            },
        },
        "saliency": {
            "explicit_compute_clicked": True,
            "map_rendered": True,
            "spectrogram_rendered": True,
            "correlation": _correlation(),
            "map_correlation": _correlation(),
            "spectrogram_correlation": _correlation(),
            "map_numeric_summary": {
                "count": 10,
                "finite_count": 10,
                "nonfinite_count": 0,
                "minimum": -1.0,
                "maximum": 1.0,
            },
            "spectrogram_numeric_summary": {
                "count": 10,
                "finite_count": 10,
                "nonfinite_count": 0,
                "minimum": -1.0,
                "maximum": 1.0,
            },
        },
        "cancellation": {
            "partition": "apply_epoch",
            "target": "apply",
            "attempted": True,
            "operation_id": "cancelled-apply-op",
            "stage_at_cancel": "Hashing reviewed import content",
            "phase_at_cancel": "running",
            "progress_at_cancel": {
                "display": "4194304/8388608",
                "completed": 4194304,
                "total": 8388608,
                "indeterminate": False,
            },
            "terminal_status": "cancelled",
            "retry_succeeded": True,
            "stop_handler_seconds": 0.01,
            "state_before": {
                "publication_generation": 17,
                "publication_revision": 21,
                "application_state_sha256": "1" * 64,
                "workflow_inputs_sha256": "2" * 64,
                "saliency_output_sha256": "3" * 64,
                "finished_run_count": 0,
            },
            "state_after": {
                "publication_generation": 17,
                "publication_revision": 21,
                "application_state_sha256": "1" * 64,
                "workflow_inputs_sha256": "2" * 64,
                "saliency_output_sha256": "3" * 64,
                "finished_run_count": 0,
            },
            "state_preserved": True,
            "review_session_before": {
                "scan_id": "scan-1",
                "candidate_id": "candidate-2",
                "preview_id": "preview-3",
                "publication_generation": 17,
            },
            "review_session_after": {
                "scan_id": "scan-1",
                "candidate_id": "candidate-2",
                "preview_id": "preview-3",
                "publication_generation": 17,
            },
            "same_review_session_retry": True,
        },
        "responsiveness": {
            "max_click_ack_seconds": 0.05,
            "max_progress_silence_seconds": 0.2,
        },
        "close": {
            "clean": True,
            "forced": False,
            "terminal_snapshot_observed": True,
            "application_closed": True,
            "close_attempt_id": "close-attempt-1",
            "pre_close_application_idle": True,
            "pre_close_remaining_workers": 0,
            "pre_close_remaining_subprocesses": 0,
        },
    }
    _write_nonblank_png(Path(receipt["artifacts"]["saliency_map"]))
    _write_nonblank_png(Path(receipt["artifacts"]["spectrogram"]))
    process_receipt = _seal_test_process(receipt, tmp_path)

    assert validate_journey_receipt(receipt, artifact_root=tmp_path) == []

    original_output_summary = copy.deepcopy(
        receipt["evaluation"]["output_numeric_summary"]
    )
    receipt["evaluation"]["output_numeric_summary"]["nonfinite_count"] = 1
    receipt["evaluation"]["output_numeric_summary"]["finite_count"] = 19
    assert any(
        "output numeric summary" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["evaluation"]["output_numeric_summary"] = copy.deepcopy(
        original_output_summary
    )
    receipt["evaluation"]["output_numeric_summary"]["shape"] = [5, 4]
    assert any(
        "output numeric summary" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["evaluation"]["output_numeric_summary"] = original_output_summary
    assert validate_journey_receipt(receipt, artifact_root=tmp_path) == []

    original_spectrogram = receipt["artifacts"]["spectrogram"]
    saliency_map = Path(receipt["artifacts"]["saliency_map"])
    receipt["artifacts"]["spectrogram"] = str(saliency_map)
    assert any(
        "reuse one path" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )

    hardlinked_spectrogram = tmp_path / "hardlinked-spectrogram.png"
    os.link(saliency_map, hardlinked_spectrogram)
    receipt["artifacts"]["spectrogram"] = str(hardlinked_spectrogram)
    assert any(
        "filesystem identity" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )

    copied_spectrogram = tmp_path / "copied-spectrogram.png"
    copied_spectrogram.write_bytes(saliency_map.read_bytes())
    receipt["artifacts"]["spectrogram"] = str(copied_spectrogram)
    assert any(
        "content identity" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["artifacts"]["spectrogram"] = original_spectrogram
    assert validate_journey_receipt(receipt, artifact_root=tmp_path) == []

    clean_close_path = Path(receipt["artifacts"]["screenshots"]["clean_close"])
    original_clean_close = clean_close_path.read_bytes()
    clean_close_path.write_bytes(
        Path(receipt["artifacts"]["screenshots"]["spectrogram"]).read_bytes()
    )
    assert validate_journey_receipt(receipt, artifact_root=tmp_path) == []
    clean_close_path.write_bytes(original_clean_close)

    original_semantic = copy.deepcopy(receipt["event_class_summary"])
    receipt["event_class_summary"].update(
        {
            "observed_events": ["right", "left"],
            "review_mapping": list(
                reversed(receipt["event_class_summary"]["review_mapping"])
            ),
        }
    )
    assert validate_journey_receipt(receipt, artifact_root=tmp_path) == []
    receipt["event_class_summary"] = original_semantic

    original_decisions = copy.deepcopy(receipt["ui_options"]["event_value_decisions"])
    receipt["ui_options"].pop("event_value_decisions")
    assert any(
        "actual event-value UI decisions" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["ui_options"]["event_value_decisions"] = copy.deepcopy(original_decisions)
    receipt["ui_options"]["event_value_decisions"][0].update(
        {
            "use": "ignore",
            "class_name": "",
            "selection_basis": "oracle_nonclass_event",
        }
    )
    assert any(
        "selected event-value decision differs" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["ui_options"]["event_value_decisions"] = original_decisions

    # A correctly cancelled owned operation can publish a newer lifecycle
    # revision while preserving every protected workflow value.
    receipt["cancellation"]["state_after"]["publication_generation"] = 18
    receipt["cancellation"]["state_after"]["publication_revision"] = 22
    assert validate_journey_receipt(receipt, artifact_root=tmp_path) == []
    receipt["cancellation"]["state_after"]["publication_generation"] = 17
    receipt["cancellation"]["state_after"]["publication_revision"] = 21

    for coordinate in ("publication_generation", "publication_revision"):
        original_coordinate = receipt["cancellation"]["state_after"][coordinate]
        receipt["cancellation"]["state_after"][coordinate] = (
            receipt["cancellation"]["state_before"][coordinate] - 1
        )
        assert any(
            "changed protected workflow state" in error
            for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
        )
        receipt["cancellation"]["state_after"][coordinate] = original_coordinate

    protected_mutations = {
        "application_state_sha256": "4" * 64,
        "workflow_inputs_sha256": "5" * 64,
        "saliency_output_sha256": "6" * 64,
        "finished_run_count": 1,
    }
    for field, forged_value in protected_mutations.items():
        original_value = receipt["cancellation"]["state_after"][field]
        receipt["cancellation"]["state_after"][field] = forged_value
        receipt["cancellation"]["state_preserved"] = True
        assert any(
            "changed protected workflow state" in error
            for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
        )
        receipt["cancellation"]["state_after"][field] = original_value

    receipt["process"]["runner_verified"] = False
    assert any(
        "not verified by the parent runner" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["process"]["runner_verified"] = True
    process_receipt.write_text('{"stale":true}\n', encoding="utf-8")
    assert any(
        "digest does not match" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    _seal_test_process(receipt, tmp_path)

    receipt["process"]["residual_descendant_count"] = 1
    assert any(
        "reports residual descendants" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["process"]["residual_descendant_count"] = 0
    receipt["process"]["residual_process_group_status"] = "residuals_reaped"
    assert any(
        "did not verify a clean process group" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["process"]["residual_process_group_status"] = "clean"

    owned_stage = next(
        item for item in receipt["stages"] if item["stage"] == "training"
    )
    owned_stage["heartbeat_count"] = 0
    owned_stage["elapsed_seconds"] = 5.1
    assert any(
        "training has no progress heartbeat" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    owned_stage["heartbeat_count"] = 1
    owned_stage["elapsed_seconds"] = 0.1
    click_stage = next(item for item in receipt["stages"] if item["stage"] == "model")
    click_stage["heartbeat_count"] = 0
    click_stage["max_progress_silence_seconds"] = None
    assert validate_journey_receipt(receipt, artifact_root=tmp_path) == []

    receipt["cancellation"]["attempted"] = False
    assert any(
        "cold receipt did not exercise" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["attempted"] = True
    receipt["journey_mode"] = "replay"
    assert any(
        "replay receipt unexpectedly" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["journey_mode"] = "cold"

    receipt["saliency"]["explicit_compute_clicked"] = False
    assert any(
        "explicit Compute Saliency" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )

    receipt["saliency"]["explicit_compute_clicked"] = True

    # Each rendered saliency view must carry its own identity.  A current
    # Spectrogram must not hide a stale Saliency Map from the previous fold.
    stale_map_identity = copy.deepcopy(receipt["saliency"]["map_correlation"])
    stale_map_identity["fold"] = 1
    receipt["saliency"]["map_correlation"] = stale_map_identity
    assert any(
        "Saliency Map does not match the current dataset/run/fold/split" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["saliency"]["map_correlation"] = _correlation()

    # The post-Apply catalog, read at the real Epoch dialog, must preserve
    # non-class events as well as supervised labels.  A review-only copy is
    # not sufficient evidence that the applied product state kept it.
    boundary = {
        "event_value": "boundary",
        "event_role": "boundary",
        "keep_event": True,
        "use_as_class": False,
        "class_name": "",
        "sources": ["embedded_events"],
    }
    receipt["event_class_summary"]["expected_events"].append("boundary")
    receipt["event_class_summary"]["observed_events"].append("boundary")
    receipt["event_class_summary"]["review_mapping"].append(boundary)
    receipt["event_class_summary"]["applied_event_catalog"].append(
        copy.deepcopy(boundary)
    )
    receipt["ui_options"]["event_value_decisions"].append(
        {
            "event_value": "boundary",
            "use": "ignore",
            "class_name": "",
            "selection_basis": "oracle_nonclass_event",
        }
    )
    assert validate_journey_receipt(receipt, artifact_root=tmp_path) == []
    receipt["event_class_summary"]["applied_event_catalog"].pop()
    assert any(
        "post-Apply event catalog does not cover the exact event set" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["event_class_summary"]["applied_event_catalog"].append(
        copy.deepcopy(boundary)
    )
    # The applied projection may originate from a different recording view;
    # provenance sources are intentionally not required to match the review.
    receipt["event_class_summary"]["applied_event_catalog"][-1]["sources"] = [
        "sub-01_applied_events.tsv"
    ]
    assert validate_journey_receipt(receipt, artifact_root=tmp_path) == []
    # Event role is a retained import semantic, not a display-only hint.  A
    # post-Apply role drift must fail even though class membership is unchanged.
    receipt["event_class_summary"]["applied_event_catalog"][-1]["event_role"] = (
        "stimulus"
    )
    assert any(
        "post-Apply event catalog semantics differ for 'boundary'" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["event_class_summary"]["applied_event_catalog"][-1]["event_role"] = (
        "boundary"
    )
    receipt["event_class_summary"]["applied_event_catalog"][-1]["sources"] = [
        "embedded_events"
    ]
    receipt["event_class_summary"]["review_mapping"][0]["use_as_class"] = False
    assert any(
        "observed classes do not derive" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["event_class_summary"]["review_mapping"][0]["use_as_class"] = True
    receipt["cancellation"]["state_after"]["application_state_sha256"] = "4" * 64
    receipt["cancellation"]["state_preserved"] = False
    assert any(
        "cancelled import changed protected workflow state" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["state_after"]["application_state_sha256"] = "1" * 64
    receipt["cancellation"]["state_preserved"] = True
    receipt["cancellation"]["same_review_session_retry"] = False
    assert any(
        "same review session" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["same_review_session_retry"] = True
    receipt["cancellation"]["review_session_after"]["candidate_id"] = "candidate-new"
    assert any(
        "same review session" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["review_session_after"]["candidate_id"] = "candidate-2"
    cancelled_operation_id = receipt["cancellation"].pop("operation_id")
    assert any(
        "exact operation id" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["operation_id"] = next(
        row["operation_id"]
        for row in receipt["stages"]
        if row["stage"] == "confirm_import"
    )
    assert any(
        "matches the successful retry" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["operation_id"] = cancelled_operation_id
    stage_at_cancel = receipt["cancellation"].pop("stage_at_cancel")
    assert any(
        "meaningful stage-at-cancel" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["stage_at_cancel"] = "Preparing interpretation apply"
    assert any(
        "meaningful stage-at-cancel" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["stage_at_cancel"] = "Creating EEG epochs"
    assert any(
        "meaningful stage-at-cancel" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["stage_at_cancel"] = stage_at_cancel
    receipt["cancellation"]["phase_at_cancel"] = "pending"
    assert any(
        "not running at the cancel click" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["phase_at_cancel"] = "running"
    progress_at_cancel = receipt["cancellation"].pop("progress_at_cancel")
    assert any(
        "progress-at-cancel" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["progress_at_cancel"] = {
        **progress_at_cancel,
        "completed": progress_at_cancel["total"] + 1,
    }
    assert any(
        "progress-at-cancel" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["cancellation"]["progress_at_cancel"] = progress_at_cancel
    receipt["close"]["terminal_snapshot_observed"] = False
    receipt["close"]["application_closed"] = False
    assert any(
        "terminal post-close snapshot" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["close"]["terminal_snapshot_observed"] = True
    receipt["close"]["application_closed"] = True
    receipt["close"]["close_attempt_id"] = ""
    assert any(
        "close-attempt identity" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["close"]["close_attempt_id"] = "close-attempt-1"
    receipt["close"]["pre_close_remaining_workers"] = 1
    assert any(
        "pre-close gate left owned work" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["close"]["pre_close_remaining_workers"] = 0
    receipt["close"]["pre_close_remaining_subprocesses"] = False
    assert any(
        "pre-close gate left owned work" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )
    receipt["close"]["pre_close_remaining_subprocesses"] = 0
    receipt["status"] = "failed"
    assert any(
        "status must be completed" in error
        for error in validate_journey_receipt(receipt, artifact_root=tmp_path)
    )


def test_spectrogram_stage_and_render_use_distinct_evidence_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qtbot,
) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    collector = JourneyEvidenceCollector(
        window=window,
        driver=MagicMock(spec=GuiCampaignDriver),
        artifact_root=tmp_path,
    )
    stage_path = tmp_path / "screenshots" / "spectrogram.png"
    collector.screenshots["spectrogram"] = str(stage_path)
    captured_stems: list[str] = []

    def save_control(_control: VisibleControl, stem: str) -> Path:
        captured_stems.append(stem)
        return tmp_path / "screenshots" / f"{stem}.png"

    monkeypatch.setattr(collector, "_save_control", save_control)
    monkeypatch.setattr(collector, "_visible_correlation_identity", lambda _control: {})
    monkeypatch.setattr(
        collector,
        "_visible_numeric_summary",
        lambda _control: {"count": 1},
    )

    collector.record_stage(
        StageInteraction(
            stage="spectrogram",
            controls=(VisibleControl.SPECTROGRAM_STATUS.value,),
            click_ack_seconds=0.01,
        )
    )

    assert captured_stems == ["spectrogram-render"]
    assert collector._sealed_evidence["spectrogram"] != str(stage_path)


def test_each_saliency_view_seals_its_own_visible_correlation_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qtbot,
) -> None:
    """A later Spectrogram render cannot overwrite Map identity evidence."""
    window = QWidget()
    qtbot.addWidget(window)
    collector = JourneyEvidenceCollector(
        window=window,
        driver=MagicMock(spec=GuiCampaignDriver),
        artifact_root=tmp_path,
    )
    collector.screenshots.update(
        {
            "saliency_map": str(tmp_path / "screenshots" / "saliency-map.png"),
            "spectrogram": str(tmp_path / "screenshots" / "spectrogram.png"),
        }
    )
    identities = {
        VisibleControl.SALIENCY_MAP_STATUS: {"run_id": "map-run"},
        VisibleControl.SPECTROGRAM_STATUS: {"run_id": "spectrogram-run"},
    }
    monkeypatch.setattr(
        collector,
        "_visible_correlation_identity",
        lambda control: identities[control],
    )
    monkeypatch.setattr(
        collector,
        "_visible_numeric_summary",
        lambda _control: {"count": 1},
    )
    monkeypatch.setattr(
        collector,
        "_visible_property_list",
        lambda _control, _name: ["left"],
    )
    monkeypatch.setattr(
        collector,
        "_visible_mapping_rows",
        lambda _control, _name: [
            {"class_index": 0, "event_code": "0", "class_name": "left"}
        ],
    )
    monkeypatch.setattr(
        collector,
        "_save_control",
        lambda _control, stem: tmp_path / "screenshots" / f"{stem}.png",
    )

    collector.record_stage(
        StageInteraction(
            stage="saliency_map",
            controls=(VisibleControl.SALIENCY_TABS.value,),
            click_ack_seconds=0.01,
        )
    )
    collector.record_stage(
        StageInteraction(
            stage="spectrogram",
            controls=(VisibleControl.SALIENCY_TABS.value,),
            click_ack_seconds=0.01,
        )
    )

    assert collector._sealed_evidence["saliency_map_identity"] == {"run_id": "map-run"}
    assert collector._sealed_evidence["spectrogram_identity"] == {
        "run_id": "spectrogram-run"
    }


def test_epoch_stage_seals_the_applied_catalog_before_epoch_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qtbot,
) -> None:
    """The post-Apply catalog is read while the real Epoch dialog is visible."""
    window = QWidget()
    qtbot.addWidget(window)
    collector = JourneyEvidenceCollector(
        window=window,
        driver=MagicMock(spec=GuiCampaignDriver),
        artifact_root=tmp_path,
    )
    catalog = [
        {
            "event_value": "boundary",
            "event_role": "boundary",
            "keep_event": True,
            "use_as_class": False,
            "class_name": "",
            "sources": ["sub-01_events.tsv"],
        }
    ]
    monkeypatch.setattr(collector, "_visible_mapping_rows", lambda *_args: catalog)
    monkeypatch.setattr(
        collector,
        "_save_widget",
        lambda _widget, stem: tmp_path / "screenshots" / f"{stem}.png",
    )

    collector.capture_visible_stage("epoch")
    collector.record_stage(
        StageInteraction(
            stage="epoch",
            controls=(VisibleControl.EPOCH_CONFIRM.value,),
            click_ack_seconds=0.01,
        )
    )

    assert collector._sealed_evidence["applied_event_catalog"] == catalog


def test_artifact_gate_rejects_corrupt_and_visually_blank_png(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"png")
    blank = tmp_path / "blank.png"
    image = QImage(32, 32, QImage.Format.Format_ARGB32)
    image.fill(QColor("black"))
    assert image.save(str(blank), "PNG")

    assert any(
        "decodable" in error
        for error in _artifact_errors(
            corrupt,
            artifact_root=tmp_path,
            label="corrupt",
        )
    )
    assert any(
        "visually blank" in error
        for error in _artifact_errors(
            blank,
            artifact_root=tmp_path,
            label="blank",
        )
    )


def test_metrics_collector_requires_every_named_terminal_cell(qtbot) -> None:
    table = QTableWidget(1, 3)
    table.setHorizontalHeaderLabels(["Status", "Train Loss", "Train Acc"])
    for column, value in enumerate(("Completed", "0.5", "75.0%")):
        table.setItem(0, column, QTableWidgetItem(value))
    qtbot.addWidget(table)

    with pytest.raises(DriverContractError, match="required 'Val Loss'"):
        _metrics_from_table(
            table,
            preferred_row="Completed",
            row_label_heading="Status",
            headings=("Train Loss", "Train Acc", "Val Loss"),
        )


def test_evaluation_collector_requires_backend_numeric_output_evidence(
    tmp_path: Path,
    qtbot,
) -> None:
    table = QTableWidget()
    qtbot.addWidget(table)
    driver = MagicMock(spec=GuiCampaignDriver)
    driver.control.return_value = table
    collector = JourneyEvidenceCollector(
        window=table,
        driver=driver,
        artifact_root=tmp_path,
    )

    with pytest.raises(DriverContractError, match="output numeric summary"):
        collector.evaluation_output_numeric_summary()

    expected = {
        "shape": [10, 2],
        "dtype": "float32",
        "count": 20,
        "finite_count": 20,
        "nonfinite_count": 0,
        "minimum": -1.5,
        "maximum": 2.0,
    }
    table.setProperty("evaluationOutputNumericSummary", expected)

    assert collector.evaluation_output_numeric_summary() == expected


def test_aggregate_receipt_denominator_requires_cold_and_replay_for_every_dataset() -> (
    None
):
    plan = load_campaign_plan(PLAN_PATH)
    receipts = [
        {
            "dataset": dataset,
            "journey_mode": mode,
            "status": "completed",
            "process": {"pid": index + 1},
            "cancellation": {
                "partition": next(
                    row["cancellation_partition"]
                    for row in plan["datasets"]
                    if row["moabb_class"] == dataset
                ),
                "target": next(
                    row["cancellation_target"]
                    for row in plan["datasets"]
                    if row["moabb_class"] == dataset
                ),
                "attempted": mode == "cold",
                "terminal_status": "cancelled" if mode == "cold" else "not_run",
                "retry_succeeded": mode == "cold",
            },
        }
        for index, (dataset, mode) in enumerate(
            item
            for dataset in DATASET_MATRIX
            for item in ((dataset, "cold"), (dataset, "replay"))
        )
    ]

    assert validate_campaign_receipt_denominator(plan, receipts) == []

    receipts.pop()
    assert any(
        "exact cold/replay denominator" in error
        for error in validate_campaign_receipt_denominator(plan, receipts)
    )


def test_campaign_receipt_validation_does_not_accept_denominator_only_rows(
    tmp_path: Path,
) -> None:
    plan = load_campaign_plan(PLAN_PATH)
    receipts = [
        {
            "dataset": dataset,
            "journey_mode": mode,
            "status": "completed",
            "cancellation": {
                "partition": next(
                    row["cancellation_partition"]
                    for row in plan["datasets"]
                    if row["moabb_class"] == dataset
                ),
                "target": next(
                    row["cancellation_target"]
                    for row in plan["datasets"]
                    if row["moabb_class"] == dataset
                ),
                "attempted": mode == "cold",
                "terminal_status": "cancelled" if mode == "cold" else "not_run",
                "retry_succeeded": mode == "cold",
            },
        }
        for dataset in DATASET_MATRIX
        for mode in JOURNEY_MODES
    ]

    errors = validate_campaign_receipts(
        plan,
        receipts,
        artifact_root=tmp_path,
        expected_plan_sha256="f" * 64,
    )

    assert any("receipt schema_version" in error for error in errors)


def test_campaign_receipts_reject_artifacts_reused_across_journey_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = load_campaign_plan(PLAN_PATH)
    first_dataset = next(iter(DATASET_MATRIX))
    shared_artifact = tmp_path / first_dataset / "cold" / "shared.png"
    shared_artifact.parent.mkdir(parents=True)
    _write_nonblank_png(shared_artifact)
    receipts = []
    for index, (dataset, mode) in enumerate(
        (dataset, mode) for dataset in DATASET_MATRIX for mode in JOURNEY_MODES
    ):
        planned = next(row for row in plan["datasets"] if row["moabb_class"] == dataset)
        receipts.append(
            {
                "dataset": dataset,
                "journey_mode": mode,
                "status": "completed",
                "process": {"pid": index + 1},
                "source_identity": {"campaign_plan_sha256": "f" * 64},
                "artifact_under_test": str(shared_artifact),
                "cancellation": {
                    "partition": planned["cancellation_partition"],
                    "target": planned["cancellation_target"],
                    "attempted": mode == "cold",
                    "terminal_status": "cancelled" if mode == "cold" else "not_run",
                    "retry_succeeded": mode == "cold",
                },
            }
        )

    def validate_artifact_scope(receipt, *, artifact_root, require_runner_seal=True):
        del require_runner_seal
        return campaign_contract._artifact_errors(
            receipt["artifact_under_test"],
            artifact_root=artifact_root,
            label="shared",
        )

    monkeypatch.setattr(
        campaign_contract,
        "validate_journey_receipt",
        validate_artifact_scope,
    )
    monkeypatch.setattr(
        campaign_contract,
        "receipt_plan_binding_errors",
        lambda *_args, **_kwargs: [],
    )

    errors = validate_campaign_receipts(
        plan,
        receipts,
        artifact_root=tmp_path,
        expected_plan_sha256="f" * 64,
    )

    assert (
        len([error for error in errors if "escapes the artifact root" in error]) == 29
    )


def test_driver_clicks_only_visible_enabled_public_controls() -> None:
    class _Control:
        def __init__(self) -> None:
            self.clicked = 0

        def objectName(self) -> str:
            return "DatasetImportBidsButton"

        def isVisible(self) -> bool:
            return True

        def isEnabled(self) -> bool:
            return True

        def click(self) -> None:
            self.clicked += 1

    control = _Control()
    driver = GuiCampaignDriver(control_lookup=lambda _: control)

    driver.click(VisibleControl.IMPORT_BIDS)

    assert control.clicked == 1

    control.isVisible = lambda: False  # type: ignore[method-assign]
    with pytest.raises(DriverContractError, match="not visible"):
        driver.click(VisibleControl.IMPORT_BIDS)


def test_driver_resolves_real_nonalphabetic_match_label_rows_before_next(
    qtbot,
) -> None:
    events_path = "/tmp/source/sub-01_task-choice_events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "source_kind": "bids",
            "eeg_files": ["/tmp/source/sub-01_task-choice_eeg.vhdr"],
            "label_carriers": [events_path],
            "bids": {"is_bids": True, "events_files": [events_path]},
        },
        preview={
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": Path(events_path).name,
                    "format": "BIDS events",
                    "selected_target_file": ("/tmp/source/sub-01_task-choice_eeg.vhdr"),
                    "label_candidates": ["trial_type"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "time_field",
                    "granularity": "trial",
                    "value_decisions": {
                        "zeta": {
                            "decision": "unresolved",
                            "suggested_name": "Zeta display name",
                            "count": 2,
                        },
                        "alpha": {
                            "decision": "unresolved",
                            "suggested_name": "Alpha display name",
                            "count": 2,
                        },
                        "middle": {
                            "decision": "unresolved",
                            "suggested_name": "Middle marker",
                            "count": 1,
                        },
                    },
                }
            ]
        },
        validation_decision={"decision": "needs_confirmation"},
        initial_step="Match Labels",
    )
    qtbot.addWidget(dialog)
    dialog.resize(1040, 820)
    dialog.show()
    qtbot.wait(0)

    assert dialog.next_button.isEnabled() is False
    assert dialog.next_button.property("eventClassMapping") == [
        {
            "event_value": "alpha",
            "event_role": "",
            "keep_event": None,
            "use_as_class": None,
            "class_name": "",
            "sources": [events_path],
        },
        {
            "event_value": "middle",
            "event_role": "",
            "keep_event": None,
            "use_as_class": None,
            "class_name": "",
            "sources": [events_path],
        },
        {
            "event_value": "zeta",
            "event_role": "",
            "keep_event": None,
            "use_as_class": None,
            "class_name": "",
            "sources": [events_path],
        },
    ]

    driver = GuiCampaignDriver(dialog, poll_interval_ms=0)
    decisions = driver.resolve_visible_event_value_decisions(
        expected_events=("zeta", "alpha", "middle"),
        expected_classes=("zeta", "alpha"),
    )

    assert decisions == [
        {
            "event_value": "alpha",
            "use": "class",
            "class_name": "alpha",
            "selection_basis": "oracle_expected_class",
        },
        {
            "event_value": "middle",
            "use": "ignore",
            "class_name": "",
            "selection_basis": "oracle_nonclass_event",
        },
        {
            "event_value": "zeta",
            "use": "class",
            "class_name": "zeta",
            "selection_basis": "oracle_expected_class",
        },
    ]
    assert dialog.next_button.isEnabled() is True
    assert dialog.next_button.property("eventClassMapping") == [
        {
            "event_value": "alpha",
            "event_role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "alpha",
            "sources": [events_path],
        },
        {
            "event_value": "middle",
            "event_role": "unknown",
            "keep_event": True,
            "use_as_class": False,
            "class_name": "",
            "sources": [events_path],
        },
        {
            "event_value": "zeta",
            "event_role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "zeta",
            "sources": [events_path],
        },
    ]
    assert all(
        selector.isVisible() and selector.isEnabled()
        for selector in dialog.findChildren(QComboBox, "EventValueUseSelector")
    )
    assert sorted(
        editor.text()
        for editor in dialog.findChildren(QLineEdit, "EventValueClassNameEditor")
        if editor.isVisible()
    ) == ["alpha", "zeta"]

    driver.click(VisibleControl.WIZARD_NEXT)

    assert dialog.apply_button.isVisible()


def test_driver_waits_for_current_fully_rendered_workflow_publication() -> None:
    calls = 0

    def workflow_state_snapshot() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("publication render is still pending")
        return {
            "generation": 7,
            "revision": 11,
            "state": {
                "raw": {"count": 1},
                "preprocessed": {"count": 1},
                "epoch": {"count": 1},
                "dataset": {"count": 1},
                "training": {"finished_run_count": 0},
                "visualization": {},
            },
        }

    root = MagicMock()
    root.workflow_state_snapshot.side_effect = workflow_state_snapshot
    driver = GuiCampaignDriver(root, poll_interval_ms=0)

    identity = driver.workflow_state_identity("apply", timeout_seconds=0.2)

    assert calls == 3
    assert identity["publication_generation"] == 7
    assert identity["publication_revision"] == 11


def test_driver_waits_for_exact_control_operation_not_later_status_owner(qtbot) -> None:
    window = QMainWindow()
    central = QWidget(window)
    layout = QVBoxLayout(central)
    compute = QPushButton("Computing...", central)
    compute.setObjectName("ComputeSaliencyButton")
    compute.setProperty("operationId", "old-compute")
    compute.setProperty("operationPhase", "completed")
    layout.addWidget(compute)
    window.setCentralWidget(central)
    status = window.statusBar()
    status.setObjectName("OwnedOperationProgress")
    status.setProperty("operationId", "later-render")
    status.setProperty("operationPhase", "running")
    status.setProperty("stage", "Rendering saliency canvas")
    status.setProperty("indeterminate", True)
    status.showMessage("Rendering saliency canvas")
    qtbot.addWidget(window)
    window.show()

    def publish_new_compute() -> None:
        compute.setProperty("operationId", "new-compute")
        compute.setProperty("operationPhase", "running")

    QTimer.singleShot(10, publish_new_compute)
    QTimer.singleShot(
        25,
        lambda: compute.setProperty("operationPhase", "completed"),
    )

    evidence = GuiCampaignDriver(window).wait_for_control_operation_completion(
        VisibleControl.COMPUTE_SALIENCY,
        excluding_operation_id="old-compute",
        timeout_seconds=1.0,
    )

    assert evidence.operation_id == "new-compute"


def test_training_wait_rejects_a_later_global_status_owner(qtbot) -> None:
    window = QMainWindow()
    table = QTableWidget(1, 1, window)
    table.setObjectName("TrainingHistoryTable")
    table.setHorizontalHeaderLabels(["Status"])
    table.setItem(0, 0, QTableWidgetItem("Running"))
    window.setCentralWidget(table)
    status = window.statusBar()
    status.setObjectName("OwnedOperationProgress")
    status.setProperty("operationId", "training-op")
    status.setProperty("operationPhase", "running")
    status.setProperty("stage", "Training model")
    status.setProperty("indeterminate", True)
    status.showMessage("Training model")
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()

    def replace_status_owner() -> None:
        status.setProperty("operationId", "later-operation")
        status.setProperty("operationPhase", "running")
        status.setProperty("stage", "Rendering result")
        status.showMessage("Rendering result")
        table.item(0, 0).setText("Completed")

    QTimer.singleShot(25, replace_status_owner)

    with pytest.raises(DriverContractError, match="changed owner"):
        GuiCampaignDriver(window).wait_for_training_completion(
            timeout_seconds=1.0,
        )


def test_training_wait_accepts_new_terminal_owner_after_fast_completion(qtbot) -> None:
    window = QMainWindow()
    table = QTableWidget(1, 1, window)
    table.setObjectName("TrainingHistoryTable")
    table.setHorizontalHeaderLabels(["Status"])
    table.setItem(0, 0, QTableWidgetItem("Completed"))
    window.setCentralWidget(table)
    status = window.statusBar()
    status.setObjectName("OwnedOperationProgress")
    status.setProperty("operationId", "fast-training-op")
    status.setProperty("operationPhase", "completed")
    status.setProperty("stage", "Training model")
    status.setProperty("indeterminate", False)
    status.showMessage("Training model · completed")
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()

    evidence = GuiCampaignDriver(window).wait_for_training_completion(
        timeout_seconds=1.0,
        excluding_operation_id="previous-operation",
    )

    assert evidence.operation_id == "fast-training-op"


def test_driver_clean_close_retains_product_background_snapshot(qtbot) -> None:
    class _AltF4Window(QMainWindow):
        shutdown_completed = pyqtSignal(object)

        def keyPressEvent(self, event) -> None:
            if (
                event.key() == Qt.Key.Key_F4
                and event.modifiers() & Qt.KeyboardModifier.AltModifier
            ):
                self.close()
                return
            super().keyPressEvent(event)

        def closeEvent(self, event) -> None:
            self.shutdown_completed.emit(
                {
                    "close_attempt_id": "close-attempt-1",
                    "application_closed": True,
                    "pre_close_application_idle": True,
                    "pre_close_remaining_workers": 0,
                    "pre_close_remaining_subprocesses": 0,
                }
            )
            super().closeEvent(event)

    window = _AltF4Window()
    qtbot.addWidget(window)
    window.show()
    driver = GuiCampaignDriver(window)

    driver.close_main_window(timeout_seconds=1.0)

    assert driver.close_completed is True
    assert driver.close_background_snapshot == {
        "close_attempt_id": "close-attempt-1",
        "application_closed": True,
        "pre_close_application_idle": True,
        "pre_close_remaining_workers": 0,
        "pre_close_remaining_subprocesses": 0,
    }


def test_driver_alt_f4_closes_the_real_main_window_through_terminal_snapshot(
    qtbot,
) -> None:
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(MagicMock())
    qtbot.addWidget(window)
    window.show()
    window._closing_in_progress = True
    snapshot = {
        "idle": True,
        "application_idle": True,
        "remaining_workers": 0,
        "remaining_subprocesses": 0,
    }
    window._close_attempt_id = "close-attempt-1"
    with (
        patch.object(window, "_stop_training_for_close", return_value=True),
        patch.object(window, "_begin_desktop_render_shutdown"),
        patch.object(
            window, "_finalize_visualization_native_render_resources", return_value=True
        ),
        patch.object(
            window, "_finalize_preprocess_native_plots_for_shutdown", return_value=True
        ),
        patch.object(window, "_close_assistant_for_shutdown", return_value=True),
        patch.object(
            window,
            "_finalize_application_publication_renderer_for_shutdown",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.close_application_runtime",
            return_value=True,
        ),
        patch.object(window, "background_work_snapshot", return_value=snapshot),
        patch.object(
            window.window_geometry,
            "persist_before_close",
            return_value=False,
        ),
    ):
        driver = GuiCampaignDriver(window)
        driver.close_main_window(timeout_seconds=1.0)

    assert driver.close_completed is True
    assert driver.close_terminal_snapshot_observed is True
    assert driver.close_background_snapshot == {
        "close_attempt_id": "close-attempt-1",
        "application_closed": True,
        "pre_close_application_idle": True,
        "pre_close_remaining_workers": 0,
        "pre_close_remaining_subprocesses": 0,
    }


def test_driver_clean_close_rejects_pre_close_snapshot_without_terminal_signal(
    qtbot,
) -> None:
    class _AltF4Window(QMainWindow):
        def keyPressEvent(self, event) -> None:
            if (
                event.key() == Qt.Key.Key_F4
                and event.modifiers() & Qt.KeyboardModifier.AltModifier
            ):
                self.close()
                return
            super().keyPressEvent(event)

    window = _AltF4Window()
    window.background_work_snapshot = lambda: {  # type: ignore[attr-defined]
        "idle": True,
        "application_idle": True,
        "remaining_workers": 0,
        "remaining_subprocesses": 0,
    }
    qtbot.addWidget(window)
    window.show()

    with pytest.raises(DriverContractError, match="terminal shutdown snapshot"):
        GuiCampaignDriver(window).close_main_window(timeout_seconds=0.1)


def test_driver_clean_close_rejects_boolean_owned_work_counts(qtbot) -> None:
    class _ForgedTerminalWindow(QMainWindow):
        shutdown_completed = pyqtSignal(object)

        def keyPressEvent(self, event) -> None:
            if (
                event.key() == Qt.Key.Key_F4
                and event.modifiers() & Qt.KeyboardModifier.AltModifier
            ):
                self.close()
                return
            super().keyPressEvent(event)

        def closeEvent(self, event) -> None:
            self.shutdown_completed.emit(
                {
                    "close_attempt_id": "close-attempt-1",
                    "application_closed": True,
                    "pre_close_application_idle": True,
                    "pre_close_remaining_workers": False,
                    "pre_close_remaining_subprocesses": False,
                }
            )
            super().closeEvent(event)

    window = _ForgedTerminalWindow()
    qtbot.addWidget(window)
    window.show()

    with pytest.raises(DriverContractError, match="terminal shutdown snapshot"):
        GuiCampaignDriver(window).close_main_window(timeout_seconds=0.1)


def test_driver_selects_moabb_bids_subject_labels_without_padding_assumption(
    qtbot,
) -> None:
    table = QTableWidget(3, 1)
    table.setObjectName("BidsSubjectSelectionTable")
    for row, label in enumerate(("sub-1", "sub-02", "sub-3")):
        item = QTableWidgetItem(label)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        item.setCheckState(Qt.CheckState.Unchecked)
        table.setItem(row, 0, item)
    qtbot.addWidget(table)
    table.show()
    qtbot.waitExposed(table)
    driver = GuiCampaignDriver(
        control_lookup=lambda control: (
            table if control is VisibleControl.SUBJECT_TABLE else None
        )
    )

    driver.select_subjects((1, 2))

    assert [table.item(row, 0).checkState() for row in range(3)] == [
        Qt.CheckState.Checked,
        Qt.CheckState.Checked,
        Qt.CheckState.Unchecked,
    ]


def test_import_modal_is_the_unique_progress_and_cancel_owner(qtbot) -> None:
    window = QMainWindow()
    status = window.statusBar()
    status.setObjectName("OwnedOperationProgress")
    status.setProperty("operationId", "shell-operation")
    status.setProperty("operationPhase", "running")
    dialog = DataInterpretationLoadingDialog(window)
    dialog.progress_bar.setProperty("operationId", "modal-operation")
    dialog.progress_bar.setProperty("operationPhase", "running")
    qtbot.addWidget(window)
    qtbot.addWidget(dialog)
    window.show()
    dialog.show()
    qtbot.waitUntil(lambda: QApplication.activeModalWidget() is dialog)
    driver = GuiCampaignDriver(window)

    assert driver.wait_for_active_operation(timeout_seconds=1.0) == "modal-operation"
    acknowledgement = driver.click(
        VisibleControl.OPERATION_CANCEL,
        timeout_seconds=1.0,
    )

    assert acknowledgement.object_name == "DataImportLoadingSecondaryButton"
    qtbot.waitUntil(lambda: not dialog.isVisible())


def test_driver_waits_past_early_stage_and_captures_meaningful_progress(qtbot) -> None:
    window = QMainWindow()
    status = window.statusBar()
    status.setObjectName("OwnedOperationProgress")
    status.setProperty("operationId", "apply-operation")
    status.setProperty("operationPhase", "running")
    status.setProperty("stage", "Preparing interpretation apply")
    status.setProperty("progress", "indeterminate")
    status.setProperty("indeterminate", True)
    status.showMessage("Preparing interpretation apply · Working…")
    qtbot.addWidget(window)
    window.show()

    def publish_meaningful_stage() -> None:
        status.setProperty("stage", "Hashing reviewed import content")
        status.setProperty("progress", "4/8")
        status.setProperty("indeterminate", False)
        status.showMessage("Hashing reviewed import content · 4/8")

    QTimer.singleShot(25, publish_meaningful_stage)

    evidence = GuiCampaignDriver(window).wait_for_meaningful_active_operation(
        allowed_stages=CANCELLATION_MEANINGFUL_STAGES["apply"],
        timeout_seconds=1.0,
    )

    assert evidence == ActiveOperationEvidence(
        operation_id="apply-operation",
        stage="Hashing reviewed import content",
        phase="running",
        progress={
            "display": "4/8",
            "completed": 4,
            "total": 8,
            "indeterminate": False,
        },
    )


def test_wait_for_transition_accepts_exact_nested_dataset_resource_check(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = QMainWindow()
    next_button = QPushButton("Next", window)
    next_button.setObjectName("DataImportNextButton")
    next_button.setAccessibleName("Next")
    next_button.hide()
    window.setCentralWidget(next_button)
    qtbot.addWidget(window)
    window.show()
    resource_check_results: list[QMessageBox.StandardButton] = []

    def open_resource_check() -> None:
        message_box = QMessageBox(window)
        message_box.setWindowTitle("Dataset Resource Check")
        message_box.setText("Continue with the selected bounded dataset?")
        message_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        nested_loop = QEventLoop()
        message_box.finished.connect(nested_loop.quit)
        QTimer.singleShot(250, message_box.reject)
        message_box.show()
        nested_loop.exec()
        selected = message_box.standardButton(message_box.clickedButton())
        resource_check_results.append(selected)
        if selected == QMessageBox.StandardButton.Yes:
            next_button.show()

    QTimer.singleShot(0, open_resource_check)
    # Qt may continue reporting the outer loading surface as active while the
    # synchronous resource prompt owns a deeper nested event loop.
    monkeypatch.setattr(QApplication, "activeModalWidget", lambda _self: window)

    driver = GuiCampaignDriver(window)
    widget, _progress = driver.wait_for_transition(
        VisibleControl.WIZARD_NEXT,
        timeout_seconds=1.0,
    )

    assert widget is next_button
    assert resource_check_results == [QMessageBox.StandardButton.Yes]
    assert driver.clicks[-1].control is VisibleControl.DATASET_RESOURCE_CHECK_YES
    assert driver.clicks[-1].accessible_name.replace("&", "") == "Yes"
    assert driver.clicks[-1].elapsed_seconds <= driver.acknowledgement_seconds


def test_driver_ignores_hidden_stale_active_modal_for_visible_preview(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_loading = QDialog()
    stale_loading.setObjectName("DataImportLoadingDialog")
    qtbot.addWidget(stale_loading)
    stale_loading.hide()

    preview = QDialog()
    next_button = QPushButton("Next", preview)
    next_button.setObjectName("DataImportNextButton")
    next_button.setAccessibleName("Next")
    qtbot.addWidget(preview)
    preview.show()
    monkeypatch.setattr(
        QApplication,
        "activeModalWidget",
        lambda _self: stale_loading,
    )

    assert (
        GuiCampaignDriver(preview).control(
            VisibleControl.WIZARD_NEXT,
            timeout_seconds=0.0,
        )
        is next_button
    )


@pytest.mark.parametrize(
    ("title", "buttons", "error"),
    [
        (
            "Unexpected Resource Warning",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            "unexpected message box",
        ),
        (
            "Dataset Resource Check",
            QMessageBox.StandardButton.Ok,
            "no visible enabled Yes action",
        ),
    ],
)
def test_wait_for_transition_rejects_unapproved_nested_message_box(
    qtbot,
    title: str,
    buttons: QMessageBox.StandardButton,
    error: str,
) -> None:
    window = QMainWindow()
    next_button = QPushButton("Next", window)
    next_button.setObjectName("DataImportNextButton")
    next_button.hide()
    window.setCentralWidget(next_button)
    qtbot.addWidget(window)
    window.show()

    def open_message_box() -> None:
        message_box = QMessageBox(window)
        message_box.setWindowTitle(title)
        message_box.setText("This action is outside the campaign contract.")
        message_box.setStandardButtons(buttons)
        nested_loop = QEventLoop()
        message_box.finished.connect(nested_loop.quit)
        QTimer.singleShot(250, message_box.reject)
        message_box.show()
        nested_loop.exec()

    QTimer.singleShot(0, open_message_box)

    with pytest.raises(DriverContractError, match=error):
        GuiCampaignDriver(window).wait_for_transition(
            VisibleControl.WIZARD_NEXT,
            timeout_seconds=1.0,
        )


def test_driver_accepts_bids_review_metadata_as_meaningful_progress(qtbot) -> None:
    window = QMainWindow()
    status = window.statusBar()
    status.setObjectName("OwnedOperationProgress")
    status.setProperty("operationId", "review-operation")
    status.setProperty("operationPhase", "running")
    status.setProperty("stage", "Materializing BIDS review metadata")
    status.setProperty("progress", "0/2")
    status.setProperty("indeterminate", False)
    status.showMessage("Materializing BIDS review metadata · 0/2")
    qtbot.addWidget(window)
    window.show()

    evidence = GuiCampaignDriver(window).wait_for_meaningful_active_operation(
        allowed_stages=CANCELLATION_MEANINGFUL_STAGES["review"],
        timeout_seconds=1.0,
    )

    assert evidence == ActiveOperationEvidence(
        operation_id="review-operation",
        stage="Materializing BIDS review metadata",
        phase="running",
        progress={
            "display": "0/2",
            "completed": 0,
            "total": 2,
            "indeterminate": False,
        },
    )


def test_cancel_click_rechecks_the_exact_meaningful_operation(qtbot) -> None:
    window = QMainWindow()
    cancel = QPushButton("Cancel", window)
    cancel.setObjectName("OwnedOperationCancelButton")
    cancel.setAccessibleName("Cancel")
    clicks: list[bool] = []
    cancel.clicked.connect(lambda: clicks.append(True))
    window.setCentralWidget(cancel)
    status = window.statusBar()
    status.setObjectName("OwnedOperationProgress")
    status.setProperty("operationId", "training-operation")
    status.setProperty("operationPhase", "running")
    status.setProperty("stage", "Training model")
    status.setProperty("progress", "indeterminate")
    status.setProperty("indeterminate", True)
    status.showMessage("Training model · Working…")
    qtbot.addWidget(window)
    window.show()
    driver = GuiCampaignDriver(window)
    active = driver.wait_for_meaningful_active_operation(
        allowed_stages=CANCELLATION_MEANINGFUL_STAGES["training"],
        timeout_seconds=1.0,
    )

    status.setProperty("stage", "Preparing training")
    status.showMessage("Preparing training · Working…")
    with pytest.raises(DriverContractError, match="left its meaningful stage"):
        driver.click_active_operation_cancel(
            VisibleControl.OPERATION_CANCEL,
            expected_operation_id=active.operation_id,
            allowed_stages=CANCELLATION_MEANINGFUL_STAGES["training"],
        )

    assert clicks == []
    status.setProperty("stage", "Training model")
    status.showMessage("Training model · Working…")
    acknowledgement, at_click = driver.click_active_operation_cancel(
        VisibleControl.OPERATION_CANCEL,
        expected_operation_id=active.operation_id,
        allowed_stages=CANCELLATION_MEANINGFUL_STAGES["training"],
    )

    assert acknowledgement.object_name == "OwnedOperationCancelButton"
    assert at_click == active
    assert clicks == [True]


def test_meaningful_cancellation_stage_families_are_product_backed() -> None:
    product_source = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (
            REPO_ROOT / "XBrainLab" / "backend",
            REPO_ROOT / "XBrainLab" / "ui",
        )
        for path in sorted(root.rglob("*.py"))
    )

    assert set(CANCELLATION_MEANINGFUL_STAGES) == {
        "import",
        "review",
        "apply",
        "epoch",
        "training",
        "saliency",
    }
    assert "Hashing reviewed import content" in CANCELLATION_MEANINGFUL_STAGES["apply"]
    assert (
        "Materializing BIDS review metadata" in CANCELLATION_MEANINGFUL_STAGES["review"]
    )
    assert (
        "Preparing interpretation candidate" in CANCELLATION_MEANINGFUL_STAGES["review"]
    )
    assert {
        "Preparing import",
        "Preparing import review",
        "Preparing interpretation apply",
        "Preparing training",
        "Preparing saliency",
    }.isdisjoint(set().union(*CANCELLATION_MEANINGFUL_STAGES.values()))
    for stages in CANCELLATION_MEANINGFUL_STAGES.values():
        assert stages
        assert all(stage in product_source for stage in stages)


def test_driver_traverses_both_real_split_modals(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        DataSplittingPreviewDialog,
        "exec",
        lambda dialog: REAL_QDIALOG_EXEC(dialog),
    )
    window = QMainWindow()
    central = QWidget(window)
    layout = QVBoxLayout(central)
    opener = QPushButton("Dataset Splitting", central)
    opener.setObjectName("TrainingSplitButton")
    layout.addWidget(opener)
    window.setCentralWidget(central)
    dialogs: list[DataSplittingDialog] = []

    def open_dialog() -> None:
        dialog = DataSplittingDialog(window, **dialog_context_kwargs())
        dialogs.append(dialog)
        REAL_QDIALOG_EXEC(dialog)

    opener.clicked.connect(open_dialog)
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    driver = GuiCampaignDriver(window)

    opened, first, preview = driver.open_split_dialog_and_confirm(
        timeout_seconds=5.0,
    )

    assert opened.control is VisibleControl.SPLIT
    assert first.control is VisibleControl.SPLIT_CONFIRM
    assert preview.control is VisibleControl.SPLIT_PREVIEW_CONFIRM
    assert dialogs and dialogs[0].get_result() is not None


def test_driver_source_has_no_backend_or_dialog_shortcuts() -> None:
    source_files = sorted(PACKAGE_ROOT.glob("*.py"))
    assert source_files

    for path in source_files:
        source = path.read_text(encoding="utf-8")
        assert _campaign_shortcut_violations(source) == (), path
    driver_source = (PACKAGE_ROOT / "driver.py").read_text(encoding="utf-8")
    assert ".set_value_decision(" not in driver_source
    assert ".setCurrentIndex(" not in driver_source


@pytest.mark.parametrize(
    "source",
    [
        "import XBrainLab.backend.application.service as svc\n",
        "from XBrainLab.backend import application\n",
        (
            "import importlib\n"
            "svc = importlib.import_module('XBrainLab.backend.application.service')\n"
        ),
        "svc = __import__('XBrainLab.backend.application.service')\n",
        "from XBrainLab.ui.dialogs.dataset import DataInterpretationPreviewDialog\n",
        "DataInterpretationPreviewDialog()\n",
        "ui.DataInterpretationPreviewDialog()\n",
    ],
)
def test_driver_source_guard_rejects_aliased_dynamic_and_dialog_shortcuts(
    source: str,
) -> None:
    assert _campaign_shortcut_violations(source)


def test_driver_source_guard_allows_the_real_study_host_import() -> None:
    source = "from XBrainLab.backend.study import Study\n"

    assert _campaign_shortcut_violations(source) == ()


def test_driver_route_is_dataset_agnostic_and_covers_every_required_stage() -> None:
    assert tuple(STAGE_CONTROL_ROUTE) == REQUIRED_STAGES
    assert set(CANCELLATION_CONTROL) == {
        "import",
        "review",
        "apply",
        "epoch",
        "training",
        "saliency",
    }

    for filename in ("driver.py", "journey.py", "worker.py"):
        source = (PACKAGE_ROOT / filename).read_text(encoding="utf-8")
        assert not any(dataset in source for dataset in DATASET_MATRIX), filename


def test_journey_scaffold_waits_for_owned_progress_and_both_render_statuses() -> None:
    source = (PACKAGE_ROOT / "journey.py").read_text(encoding="utf-8")

    assert "driver.wait_for_transition(" in source
    assert "driver.wait_for_render_status(" in source
    assert "VisibleControl.SALIENCY_MAP_STATUS" in source
    assert "VisibleControl.SPECTROGRAM_STATUS" in source


def test_cancellation_scaffold_rejects_stop_handler_over_100ms() -> None:
    class _SlowCancellationDriver:
        @staticmethod
        def wait_for_meaningful_active_operation(*, allowed_stages, timeout_seconds):
            del allowed_stages, timeout_seconds
            return ActiveOperationEvidence(
                operation_id="import-operation",
                stage="Discovering source files",
                phase="running",
                progress={
                    "display": "indeterminate",
                    "completed": None,
                    "total": None,
                    "indeterminate": True,
                },
            )

        @staticmethod
        def click_active_operation_cancel(
            control,
            *,
            expected_operation_id,
            allowed_stages,
        ):
            del expected_operation_id, allowed_stages
            return (
                ClickAcknowledgement(
                    control=control,
                    object_name="OwnedOperationCancelButton",
                    accessible_name="Cancel",
                    elapsed_seconds=0.101,
                ),
                ActiveOperationEvidence(
                    operation_id="import-operation",
                    stage="Discovering source files",
                    phase="running",
                    progress={
                        "display": "indeterminate",
                        "completed": None,
                        "total": None,
                        "indeterminate": True,
                    },
                ),
            )

    journey = ProductRecommendedJourneyScaffold(_SlowCancellationDriver())  # type: ignore[arg-type]

    with pytest.raises(DriverContractError, match="100 ms"):
        journey.cancel_current_operation(partition="import_review", target="import")


def test_worker_wires_locked_cold_and_replay_cancellation_arguments() -> None:
    class _Collector:
        @staticmethod
        def record_stage(_interaction) -> None:
            return None

        @staticmethod
        def record_before_close() -> None:
            return None

        @staticmethod
        def capture_visible_stage(_stage, *, replace=False) -> None:
            del replace

    row = copy.deepcopy(load_campaign_plan(PLAN_PATH)["datasets"][5])
    row["oracle"] = {
        "expected_events": ["zeta", "alpha"],
        "expected_classes": ["alpha"],
    }
    collector = _Collector()
    cold = build_product_journey(
        driver=object(),  # type: ignore[arg-type]
        row=row,
        mode="cold",
        collector=collector,  # type: ignore[arg-type]
    )
    replay = build_product_journey(
        driver=object(),  # type: ignore[arg-type]
        row=row,
        mode="replay",
        collector=collector,  # type: ignore[arg-type]
    )

    assert cold.mode == "cold"
    assert cold.cancellation.partition == row["cancellation_partition"]
    assert cold.cancellation.target == row["cancellation_target"]
    assert cold._expected_events == ("zeta", "alpha")
    assert cold._expected_classes == ("alpha",)
    assert replay.mode == "replay"
    assert replay.cancellation.partition == row["cancellation_partition"]
    assert replay.cancellation.target == row["cancellation_target"]


def test_import_action_and_subject_dialog_are_captured_on_distinct_surfaces() -> None:
    surface = {"name": "main_window"}
    captures: list[tuple[str, str]] = []

    class _ImportDriver:
        @staticmethod
        def _ack(control: VisibleControl) -> ClickAcknowledgement:
            return ClickAcknowledgement(control, control.value, "", 0.01)

        def open_modal_and_click(
            self,
            opener,
            confirm,
            *,
            before_confirm,
            timeout_seconds,
        ):
            del timeout_seconds
            surface["name"] = "subject_dialog"
            before_confirm()
            surface["name"] = "wizard"
            QApplication.processEvents()
            return (
                self._ack(opener),
                self._ack(confirm),
                ProgressWaitEvidence("import-op", 1, 0.01, 0.02),
            )

        @staticmethod
        def select_subjects(_subjects, *, timeout_seconds):
            del timeout_seconds
            return 0.01

        @staticmethod
        def resolve_visible_event_value_decisions(
            *, expected_events, expected_classes, timeout_seconds
        ):
            del timeout_seconds
            return [
                {
                    "event_value": value,
                    "use": "class" if value in expected_classes else "ignore",
                    "class_name": value if value in expected_classes else "",
                    "selection_basis": (
                        "oracle_expected_class"
                        if value in expected_classes
                        else "oracle_nonclass_event"
                    ),
                }
                for value in expected_events
            ]

        def wait_for_transition(self, control, *, timeout_seconds):
            del timeout_seconds
            return (
                self._ack(control),
                ProgressWaitEvidence("review-op", 1, 0.01, 0.02),
            )

        @staticmethod
        def wait_for_modal_interaction(
            _control,
            interaction,
            *,
            timeout_seconds,
        ):
            del timeout_seconds
            interaction(ProgressWaitEvidence("review-op", 1, 0.01, 0.02))

        def click(self, control, *, timeout_seconds):
            del timeout_seconds
            return self._ack(control)

        @staticmethod
        def visible_operation_id():
            return "previous-op"

        @staticmethod
        def wait_for_owned_operation_completion(
            *, timeout_seconds, excluding_operation_id
        ):
            del timeout_seconds, excluding_operation_id
            return ProgressWaitEvidence("apply-op", 1, 0.01, 0.02)

        @staticmethod
        def control(_control, *, timeout_seconds):
            del timeout_seconds
            return object()

    journey = ProductRecommendedJourneyScaffold(
        _ImportDriver(),  # type: ignore[arg-type]
        mode="replay",
        visible_stage_observer=lambda stage, *, replace=False: captures.append(
            (stage, surface["name"])
        ),
    )

    journey.import_and_review(
        (1, 2),
        expected_events=("zeta", "alpha"),
        expected_classes=("alpha",),
    )

    assert captures[:2] == [
        ("import_bids_folder", "main_window"),
        ("select_subjects", "subject_dialog"),
    ]
    assert journey.observed_ui_options["event_value_decisions"] == [
        {
            "event_value": "zeta",
            "use": "ignore",
            "class_name": "",
            "selection_basis": "oracle_nonclass_event",
        },
        {
            "event_value": "alpha",
            "use": "class",
            "class_name": "alpha",
            "selection_basis": "oracle_expected_class",
        },
    ]


def test_import_journey_traverses_and_closes_synchronous_preview_exec(qtbot) -> None:
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    next_button = QPushButton("Next", dialog)
    next_button.setObjectName("DataImportNextButton")
    next_button.setAccessibleName("Next: Load Labels")
    confirm_button = QPushButton("Confirm and Import", dialog)
    confirm_button.setObjectName("DataImportConfirmButton")
    confirm_button.setAccessibleName("Confirm and Import")
    confirm_button.hide()
    layout.addWidget(next_button)
    layout.addWidget(confirm_button)
    qtbot.addWidget(dialog)
    step = 0

    def advance() -> None:
        nonlocal step
        step += 1
        if step < 4:
            next_button.setAccessibleName(f"Next: step {step + 1}")
            return
        next_button.hide()
        confirm_button.show()

    next_button.clicked.connect(advance)
    confirm_button.clicked.connect(dialog.accept)
    gui_driver = GuiCampaignDriver(dialog, poll_interval_ms=1)

    class _SynchronousImportDriver:
        @staticmethod
        def _ack(control: VisibleControl) -> ClickAcknowledgement:
            return ClickAcknowledgement(control, control.value, "", 0.01)

        def open_modal_and_click(
            self,
            opener,
            confirm,
            *,
            before_confirm,
            timeout_seconds,
        ):
            del timeout_seconds
            before_confirm()
            result = REAL_QDIALOG_EXEC(dialog)
            assert result == QDialog.DialogCode.Accepted
            return (
                self._ack(opener),
                self._ack(confirm),
                ProgressWaitEvidence("import-op", 1, 0.01, 0.02),
            )

        @staticmethod
        def select_subjects(_subjects, *, timeout_seconds):
            del timeout_seconds
            return 0.01

        @staticmethod
        def resolve_visible_event_value_decisions(
            *, expected_events, expected_classes, timeout_seconds
        ):
            del timeout_seconds
            return [
                {
                    "event_value": value,
                    "use": "class" if value in expected_classes else "ignore",
                    "class_name": value if value in expected_classes else "",
                    "selection_basis": (
                        "oracle_expected_class"
                        if value in expected_classes
                        else "oracle_nonclass_event"
                    ),
                }
                for value in expected_events
            ]

        def wait_for_modal_interaction(
            self,
            target,
            interaction,
            *,
            timeout_seconds,
        ):
            return gui_driver.wait_for_modal_interaction(
                target,
                interaction,
                timeout_seconds=timeout_seconds,
            )

        @staticmethod
        def wait_for_transition(_control, *, timeout_seconds):
            del timeout_seconds
            raise AssertionError("preview interaction escaped synchronous exec()")

        @staticmethod
        def visible_operation_id():
            return "previous-op"

        def click(self, control, *, timeout_seconds):
            return gui_driver.click(control, timeout_seconds=timeout_seconds)

        @staticmethod
        def wait_for_owned_operation_completion(
            *, timeout_seconds, excluding_operation_id
        ):
            del timeout_seconds, excluding_operation_id
            return ProgressWaitEvidence("apply-op", 1, 0.01, 0.02)

        @staticmethod
        def control(control, *, timeout_seconds):
            del timeout_seconds
            if control is VisibleControl.NAV_PREPROCESS:
                return object()
            return gui_driver.control(control, timeout_seconds=0.0)

    journey = ProductRecommendedJourneyScaffold(
        _SynchronousImportDriver(),  # type: ignore[arg-type]
        mode="replay",
    )

    journey.import_and_review(
        (1,),
        expected_events=("stimulus",),
        expected_classes=("stimulus",),
    )

    assert step == 4
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert journey.observed_stage_order()[:5] == (
        "import_bids_folder",
        "select_subjects",
        "review_metadata",
        "match_labels",
        "confirm_import",
    )


@pytest.mark.parametrize(
    ("target", "expected_count"),
    (("import", 2), ("review", 2), ("apply", 1), ("epoch", 1)),
)
def test_cold_file_dialog_count_matches_locked_retry_route(
    target: str,
    expected_count: int,
) -> None:
    journey = ProductRecommendedJourneyScaffold(
        object(),  # type: ignore[arg-type]
        mode="cold",
        cancellation_partition=(
            "import_review" if target in {"import", "review"} else "apply_epoch"
        ),
        cancellation_target=target,
    )

    assert journey.expected_file_dialog_selection_count() == expected_count
    _require_complete_public_route(
        file_dialog_selection_count=expected_count,
        expected_file_dialog_selection_count=expected_count,
        observed_stage_order=REQUIRED_STAGES,
    )


def test_manifest_is_json_not_generated_python_policy() -> None:
    raw = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    assert raw["driver_policy"]["only_injected_boundary"] == "QFileDialog"
    assert raw["driver_policy"]["dataset_name_ui_branching"] is False
    assert raw["driver_policy"]["direct_backend_commands"] is False
    assert raw["driver_policy"]["direct_dialog_construction"] is False


def test_receipt_has_a_versioned_machine_readable_json_schema() -> None:
    schema = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith("moabb-gui-journey-receipt-v2.schema.json")
    assert schema["properties"]["schema_version"]["const"] == "2.0.0"
    assert schema["properties"]["journey_mode"]["enum"] == list(JOURNEY_MODES)
    process = schema["properties"]["process"]
    assert process["properties"]["runner_verified"]["const"] is True
    assert process["properties"]["timed_out"]["const"] is False
    assert process["properties"]["residual_descendant_count"]["const"] == 0
    assert process["properties"]["residual_process_group_status"]["const"] == "clean"
    assert "process_receipt_sha256" in process["required"]
    assert schema["properties"]["stages"]["minItems"] == len(REQUIRED_STAGES)
    assert schema["properties"]["stages"]["maxItems"] == len(REQUIRED_STAGES)
    cancellation = schema["properties"]["cancellation"]
    assert "state_before" in cancellation["required"]
    assert "operation_id" in cancellation["required"]
    assert "state_after" in cancellation["required"]
    assert "state_preserved" in cancellation["required"]
    assert "review_session_before" in cancellation["required"]
    assert "review_session_after" in cancellation["required"]
    assert "same_review_session_retry" in cancellation["required"]
    assert "stage_at_cancel" in cancellation["required"]
    assert "phase_at_cancel" in cancellation["required"]
    event_summary = schema["properties"]["event_class_summary"]
    assert "applied_event_catalog" in event_summary["required"]
    saliency = schema["properties"]["saliency"]
    assert "map_correlation" in saliency["required"]
    assert "spectrogram_correlation" in saliency["required"]
    assert "progress_at_cancel" in cancellation["required"]
    progress = schema["$defs"]["cancellationProgress"]
    assert set(progress["required"]) == {
        "display",
        "completed",
        "total",
        "indeterminate",
    }
    close = schema["properties"]["close"]
    assert "terminal_snapshot_observed" in close["required"]
    assert "application_closed" in close["required"]
    assert "close_attempt_id" in close["required"]
    assert "pre_close_application_idle" in close["required"]
    assert "pre_close_remaining_workers" in close["required"]
    assert "pre_close_remaining_subprocesses" in close["required"]
    stage_properties = schema["$defs"]["stage"]["properties"]
    assert stage_properties["click_ack_seconds"]["maximum"] == 2
    assert stage_properties["max_progress_silence_seconds"]["maximum"] == 5
    assert stage_properties["heartbeat_count"]["minimum"] == 0
    assert (
        schema["$defs"]["ownedStage"]["allOf"][1]["properties"]["operation_id"]["type"]
        == "string"
    )
    assert (
        schema["$defs"]["ownedStage"]["allOf"][1]["properties"]["heartbeat_count"][
            "minimum"
        ]
        == 0
    )
    assert schema["properties"]["artifacts"]["properties"]["screenshots"][
        "required"
    ] == list(REQUIRED_STAGES)
    evaluation = schema["properties"]["evaluation"]
    assert "output_numeric_summary" in evaluation["required"]
    assert evaluation["properties"]["output_numeric_summary"] == {
        "$ref": "#/$defs/evaluationOutputNumericSummary"
    }


def test_runner_builds_one_fresh_process_per_cold_and_replay(tmp_path: Path) -> None:
    plan = load_campaign_plan(PLAN_PATH)

    commands = build_journey_commands(
        plan_path=PLAN_PATH,
        plan=plan,
        evidence_root=tmp_path,
    )

    assert len(commands) == 30
    assert [(item.dataset, item.mode) for item in commands] == [
        (dataset, mode) for dataset in DATASET_MATRIX for mode in JOURNEY_MODES
    ]
    assert len({item.receipt_path for item in commands}) == 30
    for item in commands:
        assert item.argv[:3] == ("prlimit", "--core=0", "--")
        assert item.argv[4:7] == (
            "-m",
            "scripts.dev.moabb_gui_campaign_v2",
            "worker",
        )
        assert "--dataset" in item.argv
        assert "--mode" in item.argv


def test_runner_isolates_writable_caches_without_forcing_qt_platform(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")

    environment = _campaign_child_environment(tmp_path)

    assert environment["MNE_DONTWRITE_HOME"] == "true"
    assert environment["QT_QPA_PLATFORM"] == "xcb"
    for name in ("MNE_DATA", "MPLCONFIGDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        path = Path(environment[name])
        assert path.is_dir()
        assert path.is_relative_to(tmp_path)


def test_runner_rejects_non_d_or_overlapping_evidence_root() -> None:
    with pytest.raises(ValueError, match="absolute /mnt/d"):
        _validated_fresh_evidence_root(Path("relative"))
    with pytest.raises(ValueError, match="stored on /mnt/d"):
        _validated_fresh_evidence_root(Path("/tmp/campaign-evidence"))
    with pytest.raises(ValueError, match="must not overlap"):
        _validated_fresh_evidence_root(
            Path("/mnt/d/frozen-dataset/evidence"),
            protected_paths=[Path("/mnt/d/frozen-dataset")],
        )


def test_runner_quarantines_stale_green_receipt(tmp_path: Path) -> None:
    receipt = tmp_path / "journey-receipt.json"
    receipt.write_text('{"status":"completed"}', encoding="utf-8")

    _quarantine_stale_receipt(receipt)

    assert not receipt.exists()
    quarantined = list(tmp_path.glob("journey-receipt.stale-*.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text(encoding="utf-8")) == {
        "status": "completed"
    }


def test_runner_fails_closed_before_signalling_a_reused_member_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cleanup never signals a PID whose `/proc` start identity changed."""
    owned_group = campaign_runner._OwnedProcessGroup(
        leader_pid=71,
        process_group=71,
        session=71,
        leader_start_ticks=101,
    )
    original_member = campaign_runner._ProcessSnapshot(
        pid=72,
        process_group=71,
        session=71,
        start_ticks=202,
        state="S",
    )
    reused_member = campaign_runner._ProcessSnapshot(
        pid=72,
        process_group=71,
        session=71,
        start_ticks=303,
        state="S",
    )
    kill = MagicMock()
    monkeypatch.setattr(
        campaign_runner,
        "_live_owned_process_group_members",
        lambda _owned_group: [original_member],
    )
    monkeypatch.setattr(
        campaign_runner,
        "_process_snapshot",
        lambda _pid: reused_member,
    )
    monkeypatch.setattr(campaign_runner.os, "kill", kill)

    with pytest.raises(RuntimeError, match="member identity changed"):
        campaign_runner._signal_owned_process_group(owned_group, signal.SIGTERM)

    kill.assert_not_called()


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX")
def test_runner_timeout_reaps_owned_child_process_group(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    source = (
        "import pathlib,subprocess,sys,time;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid));"
        "time.sleep(60)"
    )

    outcome = _run_owned_process(
        (sys.executable, "-c", source),
        timeout_seconds=0.25,
        termination_timeout_seconds=2.0,
    )

    assert outcome.timed_out is True
    assert outcome.terminated_process_group is True
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        # Safety cleanup remains scoped to the one descendant this test owns.
        os.kill(child_pid, signal.SIGKILL)
        pytest.fail("owned journey descendant survived process-group timeout cleanup")


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX")
def test_runner_nonzero_leader_reaps_owned_residual_descendant(
    tmp_path: Path,
) -> None:
    """A failed worker still cannot leak a child into the next journey."""
    child_pid_path = tmp_path / "nonzero-child.pid"
    source = (
        "import pathlib,subprocess,sys;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid));"
        "sys.exit(7)"
    )

    outcome = _run_owned_process(
        (sys.executable, "-c", source),
        timeout_seconds=2.0,
        termination_timeout_seconds=2.0,
        residual_grace_period_seconds=0.05,
    )
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    try:
        assert outcome.returncode == 7
        assert outcome.leader_returncode == 7
        assert outcome.residual_descendant_count == 1
        assert outcome.residual_process_group_status == "residuals_reaped"
        assert outcome.terminated_process_group is True
        assert _wait_for_test_process_exit(child_pid, timeout_seconds=2.0)
    finally:
        _kill_test_process_if_live(child_pid)


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX")
def test_runner_timeout_kills_descendant_that_ignores_sigterm(tmp_path: Path) -> None:
    """Timeout cleanup continues after the leader exits on the first signal."""
    child_pid_path = tmp_path / "sigterm-ignoring-child.pid"
    child_source = (
        "import signal,time;"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
        "time.sleep(60)"
    )
    source = (
        "import pathlib,subprocess,sys,time;"
        f"child=subprocess.Popen([sys.executable,'-c',{child_source!r}]);"
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid));"
        "time.sleep(60)"
    )

    outcome = _run_owned_process(
        (sys.executable, "-c", source),
        timeout_seconds=0.25,
        termination_timeout_seconds=1.0,
    )
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    try:
        assert outcome.timed_out is True
        assert outcome.terminated_process_group is True
        assert outcome.killed_process_group is True
        assert outcome.residual_descendant_count == 1
        assert outcome.residual_process_group_status == "timeout_residuals_reaped"
        assert _wait_for_test_process_exit(child_pid, timeout_seconds=2.0)
    finally:
        _kill_test_process_if_live(child_pid)


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX")
def test_runner_rejects_successful_leader_that_leaves_owned_descendant(
    tmp_path: Path,
) -> None:
    """A zero-exit worker cannot seal green while its session still owns a child."""
    child_pid_path = tmp_path / "residual-child.pid"
    source = (
        "import pathlib,subprocess,sys;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid));"
    )

    outcome = _run_owned_process(
        (sys.executable, "-c", source),
        timeout_seconds=2.0,
        termination_timeout_seconds=2.0,
        residual_grace_period_seconds=0.05,
    )

    assert outcome.leader_returncode == 0
    assert outcome.returncode != 0
    assert outcome.residual_descendant_count == 1
    assert outcome.residual_process_group_status == "residuals_reaped"
    assert outcome.terminated_process_group is True
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        os.kill(child_pid, signal.SIGKILL)
        pytest.fail("residual journey descendant survived scoped cleanup")


def test_runner_captures_child_cwd_environment_and_logs(tmp_path: Path) -> None:
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    environment = dict(os.environ)
    environment["XBRAINLAB_CAMPAIGN_TEST_VALUE"] = "sealed-value"
    source = (
        "import os,pathlib,sys;"
        "print(pathlib.Path.cwd());"
        "print(os.environ['XBRAINLAB_CAMPAIGN_TEST_VALUE']);"
        "print('diagnostic',file=sys.stderr)"
    )

    outcome = _run_owned_process(
        (sys.executable, "-c", source),
        timeout_seconds=2.0,
        cwd=tmp_path,
        env=environment,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )

    assert outcome.returncode == 0
    assert outcome.leader_returncode == 0
    assert outcome.pid > 0
    assert outcome.residual_descendant_count == 0
    assert outcome.residual_process_group_status == "clean"
    assert str(tmp_path) in stdout_path.read_text(encoding="utf-8")
    assert "sealed-value" in stdout_path.read_text(encoding="utf-8")
    assert stderr_path.read_text(encoding="utf-8").strip() == "diagnostic"


def test_runner_seal_rejects_forged_worker_process_outcome(tmp_path: Path) -> None:
    receipt_path = tmp_path / "journey-receipt.json"
    process_receipt_path = tmp_path / "journey-process.json"
    process_receipt_path.write_text("{}\n", encoding="utf-8")
    command = JourneyCommand(
        dataset="BNCI2014_001",
        mode="cold",
        argv=("worker",),
        receipt_path=receipt_path,
    )
    payload = {
        "dataset": command.dataset,
        "journey_mode": command.mode,
        "process": {"pid": 9999, "exit_code": 0},
    }

    with pytest.raises(RuntimeError, match="PID does not match"):
        _seal_journey_receipt(
            command,
            JourneyProcessOutcome(returncode=0, pid=1234, duration_seconds=0.1),
            payload,
            process_receipt_path=process_receipt_path,
        )

    payload["process"] = {"pid": 1234, "exit_code": 0}
    with pytest.raises(RuntimeError, match="non-successful"):
        _seal_journey_receipt(
            command,
            JourneyProcessOutcome(returncode=7, pid=1234, duration_seconds=0.1),
            payload,
            process_receipt_path=process_receipt_path,
        )

    with pytest.raises(RuntimeError, match="residual process descendants"):
        _seal_journey_receipt(
            command,
            JourneyProcessOutcome(
                returncode=0,
                pid=1234,
                duration_seconds=0.1,
                leader_returncode=0,
                residual_descendant_count=1,
                residual_process_group_status="residuals_reaped",
            ),
            payload,
            process_receipt_path=process_receipt_path,
        )

    payload["process"]["exit_code"] = 99
    sealed = _seal_journey_receipt(
        command,
        JourneyProcessOutcome(returncode=0, pid=1234, duration_seconds=0.25),
        payload,
        process_receipt_path=process_receipt_path,
    )

    assert sealed["process"]["exit_code"] == 0
    assert sealed["process"]["runner_verified"] is True
    assert sealed["process"]["duration_seconds"] == 0.25
    assert sealed["process"]["residual_descendant_count"] == 0
    assert sealed["process"]["residual_process_group_status"] == "clean"
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == sealed


def test_worker_launches_real_main_window_without_direct_dialog_construction() -> None:
    source = (PACKAGE_ROOT / "worker.py").read_text(encoding="utf-8")

    assert "MainWindow(study)" in source
    assert "Study()" in source
    assert "QFileDialogPathBoundary" in source
    assert "ProductRecommendedJourneyScaffold" in source
    assert "journey.import_and_review" in source
    assert "journey.configure_preprocess_epoch_training" in source
    assert "journey.open_evaluation_and_saliency" in source
    assert "journey.clean_close" in source
    assert "DataInterpretationPreviewDialog(" not in source
    assert "BidsSubjectSelectionDialog(" not in source


def test_scaffold_reports_missing_public_product_hooks(tmp_path: Path) -> None:
    ui_root = tmp_path / "XBrainLab" / "ui"
    ui_root.mkdir(parents=True)
    (ui_root / "surface.py").write_text(
        'widget.setObjectName("OwnedOperationProgress")\n'
        'widget.setObjectName("TrainingEpochsInput")\n',
        encoding="utf-8",
    )

    assert missing_product_source_hooks(tmp_path) == tuple(
        name
        for name in MINIMUM_PRODUCTION_HOOKS
        if name not in {"OwnedOperationProgress", "TrainingEpochsInput"}
    )


def test_production_ui_exposes_every_minimum_campaign_hook() -> None:
    assert missing_product_source_hooks(REPO_ROOT) == ()
