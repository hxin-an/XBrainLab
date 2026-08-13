"""Fresh-process MainWindow worker for one campaign journey.

This module owns no backend command shortcut. It creates the real product
``Study`` and ``MainWindow`` and hands all interaction to visible-control
driver primitives.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from scripts.dev.moabb_dataset_materializer import exact_environment_identity
from XBrainLab.ui.qt_runtime import configure_qt_platform_for_runtime

configure_qt_platform_for_runtime()

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from .contract import (
    DATASET_MATRIX,
    REQUIRED_STAGES,
    execution_preflight_errors,
    validate_journey_receipt,
)
from .driver import (
    DriverContractError,
    GuiCampaignDriver,
    QFileDialogPathBoundary,
    missing_product_source_hooks,
)
from .evidence import JourneyEvidenceCollector, completed_receipt, source_identity
from .journey import ProductRecommendedJourneyScaffold

REPO_ROOT = Path(__file__).resolve().parents[3]


def run_worker(
    *,
    plan: dict[str, Any],
    dataset: str,
    mode: str,
    receipt_path: Path,
    plan_path: Path | None = None,
) -> int:
    """Launch one real MainWindow and execute the dataset-agnostic GUI route."""
    try:
        environment = exact_environment_identity()
    except Exception as exc:
        environment = {}
        environment_errors = [f"exact campaign environment is unavailable: {exc}"]
    else:
        environment_errors = []
    errors = execution_preflight_errors(
        plan,
        dataset=dataset,
        environment=environment,
    )
    errors.extend(environment_errors)
    errors.extend(
        f"product UI hook is missing: {name}"
        for name in missing_product_source_hooks(REPO_ROOT)
    )
    if errors:
        _write_failure_receipt(
            receipt_path,
            dataset=dataset,
            mode=mode,
            failure="execution_preflight",
            details=errors,
            exit_code=2,
        )
        return 2
    row = next(
        (item for item in plan["datasets"] if item.get("moabb_class") == dataset),
        None,
    )
    if row is None or dataset not in DATASET_MATRIX:
        _write_failure_receipt(
            receipt_path,
            dataset=dataset,
            mode=mode,
            failure="dataset_inventory",
            details=["Dataset is outside the fixed campaign inventory."],
            exit_code=2,
        )
        return 2

    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_DontUseNativeDialogs,
        True,
    )
    app = QApplication.instance() or QApplication(["xbrainlab-moabb-gui-worker"])
    app.setOrganizationName("XBrainLab")
    app.setApplicationName("XBrainLab")
    app.setApplicationDisplayName("XBrainLab")
    app.setStyle("Fusion")

    from XBrainLab.backend.study import Study
    from XBrainLab.ui.dialog_button_policy import (
        install_dialog_button_policy,
    )
    from XBrainLab.ui.main_window import MainWindow

    install_dialog_button_policy(app)
    study = Study()
    window = MainWindow(study)
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    window.show()
    app.processEvents()
    driver = GuiCampaignDriver(window)
    artifact_root = receipt_path.parent.resolve()
    collector = JourneyEvidenceCollector(
        window=window,
        driver=driver,
        artifact_root=artifact_root,
    )
    journey = build_product_journey(
        driver=driver,
        row=row,
        mode=mode,
        collector=collector,
    )
    bids_root = Path(row["bids"]["root"])
    started = time.monotonic()
    try:
        with QFileDialogPathBoundary(bids_root) as file_boundary:
            journey.import_and_review(
                tuple(row["subjects"]),
                expected_events=tuple(row["oracle"]["expected_events"]),
                expected_classes=tuple(row["oracle"]["expected_classes"]),
            )
            journey.configure_preprocess_epoch_training()
            journey.open_evaluation_and_saliency()
            journey.clean_close()
        _require_complete_public_route(
            file_dialog_selection_count=file_boundary.selection_count,
            expected_file_dialog_selection_count=(
                journey.expected_file_dialog_selection_count()
            ),
            observed_stage_order=journey.observed_stage_order(),
        )
        receipt = completed_receipt(
            dataset=dataset,
            subjects=list(row["subjects"]),
            mode=mode,
            journey=journey,
            collector=collector,
            source=source_identity(
                repo_root=REPO_ROOT,
                plan_path=(
                    plan_path
                    or REPO_ROOT
                    / "artifacts"
                    / "user-journeys"
                    / "moabb-gui-campaign-v2.json"
                ),
                dataset_revision=str(row["bids"]["dataset_revision_sha256"]),
                environment=environment,
            ),
            expected_events=list(row["oracle"]["expected_events"]),
            expected_classes=list(row["oracle"]["expected_classes"]),
            pid=os.getpid(),
        )
        receipt_errors = validate_journey_receipt(
            receipt,
            artifact_root=artifact_root,
            require_runner_seal=False,
        )
        _require_valid_receipt(receipt_errors)
    except Exception as exc:
        _request_clean_close(driver, app, window)
        _write_failure_receipt(
            receipt_path,
            dataset=dataset,
            mode=mode,
            failure=type(exc).__name__,
            details=[str(exc)],
            elapsed_seconds=time.monotonic() - started,
            clicks=_click_rows(driver),
            exit_code=3,
        )
        return 3
    else:
        _write_receipt(receipt_path, receipt)
        return 0
    finally:
        app.processEvents()


def build_product_journey(
    *,
    driver: GuiCampaignDriver,
    row: dict[str, Any],
    mode: str,
    collector: JourneyEvidenceCollector,
) -> ProductRecommendedJourneyScaffold:
    """Wire one locked plan row into the dataset-agnostic journey."""
    return ProductRecommendedJourneyScaffold(
        driver,
        mode=mode,
        cancellation_partition=str(row["cancellation_partition"]),
        cancellation_target=str(row["cancellation_target"]),
        expected_events=tuple(row["oracle"]["expected_events"]),
        expected_classes=tuple(row["oracle"]["expected_classes"]),
        stage_observer=collector.record_stage,
        visible_stage_observer=collector.capture_visible_stage,
        before_close_observer=collector.record_before_close,
    )


def _require_valid_receipt(errors: list[str]) -> None:
    if errors:
        raise DriverContractError(
            "completed receipt failed validation: " + "; ".join(errors)
        )


def _require_complete_public_route(
    *,
    file_dialog_selection_count: int,
    expected_file_dialog_selection_count: int,
    observed_stage_order: tuple[str, ...],
) -> None:
    if file_dialog_selection_count != expected_file_dialog_selection_count:
        raise DriverContractError(
            "The journey QFileDialog selection count did not match its locked "
            "cold/replay cancellation route."
        )
    if observed_stage_order != REQUIRED_STAGES:
        raise DriverContractError(
            "The visible-control route did not preserve the complete stage order."
        )


def _click_rows(driver: GuiCampaignDriver) -> list[dict[str, Any]]:
    return [
        {
            "control": click.control.value,
            "object_name": click.object_name,
            "accessible_name": click.accessible_name,
            "elapsed_seconds": click.elapsed_seconds,
        }
        for click in driver.clicks
    ]


def _request_clean_close(
    driver: GuiCampaignDriver,
    app: QApplication,
    window: Any,
) -> None:
    try:
        if window.isVisible():
            driver.close_main_window()
        deadline = time.monotonic() + 5.0
        while window.isVisible() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
    except Exception:
        # Failure receipts retain the original blocker. A still-visible window is
        # reflected in the process exit and cannot qualify as a green journey.
        return


def _write_failure_receipt(
    path: Path,
    *,
    dataset: str,
    mode: str,
    failure: str,
    details: list[str],
    elapsed_seconds: float = 0.0,
    clicks: list[dict[str, Any]] | None = None,
    exit_code: int = 3,
) -> None:
    """Persist a non-qualifying diagnostic without private dataset paths."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "2.0.0",
        "artifact_type": "xbrainlab.moabb_gui_journey",
        "status": "failed",
        "dataset": dataset,
        "journey_mode": mode,
        "process": {
            "fresh_process": True,
            "pid": os.getpid(),
            "exit_code": exit_code,
        },
        "failure": failure,
        "details": details,
        "elapsed_seconds": elapsed_seconds,
        "clicks": clicks or [],
    }
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    """Atomically publish one already validated receipt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
