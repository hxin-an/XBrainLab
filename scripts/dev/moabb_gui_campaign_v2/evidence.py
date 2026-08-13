"""Evidence collectors that read only public, visible GUI surfaces."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import QApplication, QTableWidget, QWidget

from .contract import campaign_plan_sha256
from .driver import DriverContractError, GuiCampaignDriver, VisibleControl
from .journey import ProductRecommendedJourneyScaffold, StageInteraction


class JourneyEvidenceCollector:
    """Capture screenshots, displayed metrics, and rendered identity."""

    def __init__(
        self,
        *,
        window: QWidget,
        driver: GuiCampaignDriver,
        artifact_root: Path,
    ) -> None:
        self.window = window
        self.driver = driver
        self.artifact_root = artifact_root.resolve()
        self.screenshot_root = self.artifact_root / "screenshots"
        self.screenshots: dict[str, str] = {}
        self._before_close_path: Path | None = None
        self._sealed_evidence: dict[str, Any] = {}
        self._before_close_evidence: dict[str, Any] | None = None

    def record_stage(self, interaction: StageInteraction) -> None:
        """Persist the visible production surface for one completed stage."""
        if interaction.stage == "clean_close":
            if self._before_close_path is None:
                raise DriverContractError("clean-close screenshot was not captured")
            self.screenshots[interaction.stage] = str(self._before_close_path)
            return
        if interaction.stage not in self.screenshots:
            self.capture_visible_stage(interaction.stage)
        if interaction.stage == "training":
            self._sealed_evidence["training_metrics"] = self.training_metrics()
        elif interaction.stage == "epoch":
            if "applied_event_catalog" not in self._sealed_evidence:
                raise DriverContractError(
                    "Epoch dialog did not expose the post-Apply event catalog"
                )
        elif interaction.stage == "match_labels":
            if "review_event_class_mapping" not in self._sealed_evidence:
                raise DriverContractError(
                    "Match Labels dialog did not expose its event/class mapping"
                )
        elif interaction.stage == "evaluation":
            self._sealed_evidence["evaluation_metrics"] = self.evaluation_metrics()
            self._sealed_evidence["evaluation_output_numeric_summary"] = (
                self.evaluation_output_numeric_summary()
            )
            self._sealed_evidence["evaluation_class_labels"] = (
                self.evaluation_class_labels()
            )
            self._sealed_evidence["evaluation_identity"] = (
                self._visible_correlation_identity(VisibleControl.EVALUATION_METRICS)
            )
        elif interaction.stage == "saliency_map":
            self._sealed_evidence["saliency_map_identity"] = (
                self._visible_correlation_identity(VisibleControl.SALIENCY_MAP_STATUS)
            )
            self._sealed_evidence["event_labels"] = self._visible_property_list(
                VisibleControl.SALIENCY_MAP_STATUS,
                "eventLabels",
            )
            self._sealed_evidence["class_labels"] = self._visible_property_list(
                VisibleControl.SALIENCY_MAP_STATUS,
                "classLabels",
            )
            self._sealed_evidence["saliency_class_mapping"] = (
                self._visible_mapping_rows(
                    VisibleControl.SALIENCY_MAP_STATUS,
                    "classMapping",
                )
            )
            self._sealed_evidence["saliency_map"] = str(
                self._save_control(
                    VisibleControl.SALIENCY_MAP_STATUS,
                    "saliency-map",
                )
            )
            self._sealed_evidence["saliency_map_numeric_summary"] = (
                self._visible_numeric_summary(VisibleControl.SALIENCY_MAP_STATUS)
            )
        elif interaction.stage == "spectrogram":
            self._sealed_evidence["spectrogram_identity"] = (
                self._visible_correlation_identity(VisibleControl.SPECTROGRAM_STATUS)
            )
            self._sealed_evidence["spectrogram"] = str(
                self._save_control(
                    VisibleControl.SPECTROGRAM_STATUS,
                    "spectrogram-render",
                )
            )
            self._sealed_evidence["spectrogram_numeric_summary"] = (
                self._visible_numeric_summary(VisibleControl.SPECTROGRAM_STATUS)
            )

    def capture_visible_stage(self, stage: str, *, replace: bool = False) -> None:
        """Capture the foreground modal/window before its production click."""
        if stage == "match_labels":
            # The preview is owned by synchronous QDialog.exec().  Seal its
            # public mapping while that dialog is still visible; record_stage
            # runs only after Confirm has closed the nested event loop.
            self._sealed_evidence["review_event_class_mapping"] = (
                self._visible_mapping_rows(
                    VisibleControl.WIZARD_NEXT,
                    "eventClassMapping",
                )
            )
        if stage == "epoch":
            # Read the detached applied handoff while the real Epoch dialog is
            # visible, before confirmation mutates the working dataset.
            self._sealed_evidence["applied_event_catalog"] = self._visible_mapping_rows(
                VisibleControl.EPOCH_EVENT_TABLE,
                "appliedEventCatalog",
            )
        if stage in self.screenshots and not replace:
            return
        app = QApplication.instance()
        modal = app.activeModalWidget() if app is not None else None
        active = app.activeWindow() if app is not None else None
        surface = modal if modal is not None and modal.isVisible() else active
        if surface is None or not surface.isVisible():
            surface = self.window
        self.screenshots[stage] = str(self._save_widget(surface, stage))

    def record_before_close(self) -> None:
        """Capture the final visible artifact immediately before Alt+F4."""
        self._before_close_path = self._save_widget(self.window, "clean_close")
        required = {
            "training_metrics",
            "review_event_class_mapping",
            "applied_event_catalog",
            "evaluation_metrics",
            "evaluation_output_numeric_summary",
            "evaluation_class_labels",
            "evaluation_identity",
            "saliency_map_identity",
            "spectrogram_identity",
            "event_labels",
            "class_labels",
            "saliency_class_mapping",
            "saliency_map",
            "saliency_map_numeric_summary",
            "spectrogram",
            "spectrogram_numeric_summary",
        }
        missing = sorted(required.difference(self._sealed_evidence))
        if missing:
            raise DriverContractError(
                "visible evidence was not sealed before close: " + ", ".join(missing)
            )
        self._before_close_evidence = dict(self._sealed_evidence)

    def training_metrics(self) -> dict[str, float]:
        if self._before_close_evidence is not None:
            return dict(self._before_close_evidence["training_metrics"])
        table = self.driver.control(
            VisibleControl.TRAINING_HISTORY,
            timeout_seconds=30.0,
        )
        return _metrics_from_table(
            table,
            preferred_row="Completed",
            row_label_heading="Status",
            headings=(
                "Train Loss",
                "Train Acc",
                "Val Loss",
                "Val Acc",
                "Test Acc",
                "LR",
            ),
        )

    def evaluation_metrics(self) -> dict[str, float]:
        if self._before_close_evidence is not None:
            return dict(self._before_close_evidence["evaluation_metrics"])
        table = self.driver.control(
            VisibleControl.EVALUATION_METRICS,
            timeout_seconds=30.0,
        )
        return _metrics_from_table(
            table,
            preferred_row="Macro Avg",
            row_label_heading="Class",
            headings=("Precision", "Recall", "F1-Score", "Support"),
        )

    def evaluation_class_labels(self) -> list[str]:
        if self._before_close_evidence is not None:
            return list(self._before_close_evidence["evaluation_class_labels"])
        table = self.driver.control(
            VisibleControl.EVALUATION_METRICS,
            timeout_seconds=30.0,
        )
        if not isinstance(table, QTableWidget):
            raise DriverContractError("visible Evaluation result is not a table")
        columns = _table_headings(table)
        class_column = columns.get("Class")
        if class_column is None:
            raise DriverContractError("visible Evaluation table lacks class labels")
        aggregate_rows = {"macro avg", "micro avg", "weighted avg", "accuracy"}
        labels = [
            item.text().strip()
            for row in range(table.rowCount())
            if (item := table.item(row, class_column)) is not None
            and item.text().strip()
            and item.text().strip().casefold() not in aggregate_rows
        ]
        if not labels:
            raise DriverContractError("visible Evaluation table has no class rows")
        return labels

    def evaluation_output_numeric_summary(self) -> dict[str, Any]:
        """Read the backend-validated held-out output summary from the table."""
        if self._before_close_evidence is not None:
            return dict(
                self._before_close_evidence["evaluation_output_numeric_summary"]
            )
        table = self.driver.control(
            VisibleControl.EVALUATION_METRICS,
            timeout_seconds=30.0,
        )
        value = table.property("evaluationOutputNumericSummary")
        if not isinstance(value, dict):
            raise DriverContractError(
                "visible Evaluation output numeric summary is unavailable"
            )
        return dict(value)

    def evaluation_correlation(self) -> dict[str, Any]:
        return _correlation_from_identity(self._evidence_value("evaluation_identity"))

    def saliency_map_correlation(self) -> dict[str, Any]:
        return _correlation_from_identity(self._evidence_value("saliency_map_identity"))

    def spectrogram_correlation(self) -> dict[str, Any]:
        return _correlation_from_identity(self._evidence_value("spectrogram_identity"))

    def event_class_summary(
        self,
        *,
        expected_events: list[str],
        expected_classes: list[str],
    ) -> dict[str, list[str]]:
        review_mapping = list(self._evidence_value("review_event_class_mapping"))
        applied_event_catalog = list(self._evidence_value("applied_event_catalog"))
        saliency_mapping = list(self._evidence_value("saliency_class_mapping"))
        observed_events = [str(row.get("event_value") or "") for row in review_mapping]
        reviewed_classes = [
            str(row.get("class_name") or "")
            for row in review_mapping
            if row.get("use_as_class") is True
        ]
        if not observed_events or not reviewed_classes:
            raise DriverContractError("Match Labels lacks public event/class evidence")
        saliency_classes = [
            str(row.get("class_name") or "") for row in saliency_mapping
        ]
        evaluation_classes = list(self._evidence_value("evaluation_class_labels"))
        if set(reviewed_classes) != set(saliency_classes) or set(
            reviewed_classes
        ) != set(evaluation_classes):
            raise DriverContractError(
                "Match Labels, Evaluation, and Saliency class semantics differ"
            )
        return {
            "expected_events": list(expected_events),
            "observed_events": observed_events,
            "expected_classes": list(expected_classes),
            "observed_classes": evaluation_classes,
            "review_mapping": review_mapping,
            "applied_event_catalog": applied_event_catalog,
            "evaluation_class_labels": evaluation_classes,
            "saliency_class_mapping": saliency_mapping,
        }

    def saliency_numeric_summaries(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            dict(self._evidence_value("saliency_map_numeric_summary")),
            dict(self._evidence_value("spectrogram_numeric_summary")),
        )

    def saliency_artifacts(self) -> tuple[str, str]:
        return (
            str(self._evidence_value("saliency_map")),
            str(self._evidence_value("spectrogram")),
        )

    def close_evidence(self) -> dict[str, Any]:
        snapshot = self.driver.close_background_snapshot or {}
        return {
            "clean": self.driver.close_completed,
            "forced": False,
            "terminal_snapshot_observed": (
                self.driver.close_terminal_snapshot_observed
            ),
            "application_closed": snapshot.get("application_closed") is True,
            "close_attempt_id": str(snapshot.get("close_attempt_id") or ""),
            "pre_close_application_idle": (
                snapshot.get("pre_close_application_idle") is True
            ),
            "pre_close_remaining_workers": int(
                snapshot.get("pre_close_remaining_workers", 1)
            ),
            "pre_close_remaining_subprocesses": int(
                snapshot.get("pre_close_remaining_subprocesses", 1)
            ),
        }

    def _save_widget(self, widget: QWidget, stem: str) -> Path:
        self.screenshot_root.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_root / f"{stem}.png"
        if not widget.grab().save(str(path), "PNG") or path.stat().st_size <= 0:
            raise DriverContractError(f"could not capture visible artifact {stem!r}")
        return path.resolve()

    def _save_control(self, control: VisibleControl, stem: str) -> Path:
        widget = self.driver.control(control, timeout_seconds=30.0)
        return self._save_widget(widget, stem)

    def _visible_correlation_identity(
        self,
        control: VisibleControl,
    ) -> dict[str, Any]:
        widget = self.driver.control(control, timeout_seconds=30.0)
        return {
            "run_id": str(widget.property("runId") or "").strip(),
            "split": str(widget.property("evaluationSplit") or "").strip(),
            "generation": widget.property("publicationGeneration"),
            "fold": widget.property("fold"),
            "publication_generation": widget.property("publicationGeneration"),
            "training_generation": widget.property("trainingGeneration"),
            "training_boundary_stable": widget.property("trainingBoundaryStable"),
            "split_specification_fingerprint": str(
                widget.property("splitSpecificationFingerprint") or ""
            ).strip(),
            "split_epoch_revision": widget.property("splitEpochRevision"),
            "producer_identities": widget.property("producerIdentities"),
        }

    def _visible_numeric_summary(self, control: VisibleControl) -> dict[str, Any]:
        widget = self.driver.control(control, timeout_seconds=30.0)
        value = widget.property("saliencyNumericSummary")
        if not isinstance(value, dict):
            raise DriverContractError("visible saliency numeric summary is unavailable")
        return dict(value)

    def _visible_property_list(
        self,
        control: VisibleControl,
        name: str,
    ) -> list[str]:
        widget = self.driver.control(control, timeout_seconds=30.0)
        return _string_property_list(widget, name)

    def _visible_mapping_rows(
        self,
        control: VisibleControl,
        name: str,
    ) -> list[dict[str, Any]]:
        widget = self.driver.control(control, timeout_seconds=30.0)
        value = widget.property(name)
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, dict) for item in value)
        ):
            raise DriverContractError(f"{control.value} lacks public {name!r} evidence")
        return [dict(item) for item in value]

    def _evidence_value(self, key: str) -> Any:
        if self._before_close_evidence is None:
            raise DriverContractError("visible evidence was not sealed before close")
        return self._before_close_evidence[key]


def source_identity(
    *,
    repo_root: Path,
    plan_path: Path,
    dataset_revision: str,
    environment: dict[str, Any],
) -> dict[str, str]:
    """Bind one receipt to the exact Git, plan, lock, dataset, and CUDA state."""
    del repo_root
    git = environment.get("git")
    if not isinstance(git, dict):
        raise DriverContractError("exact Git identity is unavailable")
    commit = str(git.get("commit") or "")
    cuda = str(environment.get("cuda") or "unavailable")
    gpu = str(environment.get("gpu") or "unavailable")
    lock_digest = str(environment.get("poetry_lock_sha256") or "")
    environment_digest = str(environment.get("identity_sha256") or "")
    return {
        "application_commit": commit,
        "campaign_plan_sha256": campaign_plan_sha256(plan_path),
        "poetry_lock_sha256": lock_digest,
        "dataset_checksum_sha256": dataset_revision,
        "environment_identity_sha256": environment_digest,
        "cuda": cuda,
        "gpu": gpu,
    }


def completed_receipt(
    *,
    dataset: str,
    subjects: list[int],
    mode: str,
    journey: ProductRecommendedJourneyScaffold,
    collector: JourneyEvidenceCollector,
    source: dict[str, str],
    expected_events: list[str],
    expected_classes: list[str],
    pid: int,
) -> dict[str, Any]:
    """Assemble one receipt solely after every collector succeeds."""
    evaluation_correlation = collector.evaluation_correlation()
    saliency_map_correlation = collector.saliency_map_correlation()
    spectrogram_correlation = collector.spectrogram_correlation()
    if (
        evaluation_correlation != saliency_map_correlation
        or evaluation_correlation != spectrogram_correlation
    ):
        raise DriverContractError(
            "Evaluation and rendered saliency views have different run/fold/split identities"
        )
    saliency_map, spectrogram = collector.saliency_artifacts()
    map_numeric_summary, spectrogram_numeric_summary = (
        collector.saliency_numeric_summaries()
    )
    clicks = [item.elapsed_seconds for item in journey.driver.clicks]
    progress_silences = [
        item.max_progress_silence_seconds
        for item in journey.interactions
        if item.max_progress_silence_seconds is not None
    ]
    cancellation = journey.cancellation
    return {
        "schema_version": "2.0.0",
        "artifact_type": "xbrainlab.moabb_gui_journey",
        "status": "completed",
        "dataset": dataset,
        "subjects": subjects,
        "journey_mode": mode,
        # The worker can only publish provisional self-identity. The parent
        # runner replaces this block with an independently verified process
        # receipt after the child has actually exited.
        "process": {
            "fresh_process": True,
            "pid": pid,
            "exit_code": 0,
            "runner_verified": False,
        },
        "source_identity": source,
        "correlation": evaluation_correlation,
        "stages": [
            {
                "stage": item.stage,
                "status": "completed",
                "elapsed_seconds": item.elapsed_seconds,
                "visible_control": ",".join(item.controls) or "MainWindow",
                "operation_id": item.operation_id,
                "click_ack_seconds": item.click_ack_seconds,
                "max_progress_silence_seconds": (item.max_progress_silence_seconds),
                "heartbeat_count": item.heartbeat_count,
            }
            for item in journey.interactions
        ],
        "artifacts": {
            "screenshots": collector.screenshots,
            "training_metrics": collector.training_metrics(),
            "saliency_map": saliency_map,
            "spectrogram": spectrogram,
        },
        "ui_options": {
            **journey.observed_ui_options,
        },
        "event_class_summary": collector.event_class_summary(
            expected_events=expected_events,
            expected_classes=expected_classes,
        ),
        "evaluation": {
            "correlation": evaluation_correlation,
            "metrics": collector.evaluation_metrics(),
            "output_numeric_summary": (collector.evaluation_output_numeric_summary()),
        },
        "saliency": {
            "explicit_compute_clicked": any(
                click.control is VisibleControl.COMPUTE_SALIENCY
                for click in journey.driver.clicks
            ),
            "map_rendered": True,
            "spectrogram_rendered": True,
            # Keep the legacy aggregate for stable receipt readers, while the
            # contract independently seals the two rendered view identities.
            "correlation": spectrogram_correlation,
            "map_correlation": saliency_map_correlation,
            "spectrogram_correlation": spectrogram_correlation,
            "map_numeric_summary": map_numeric_summary,
            "spectrogram_numeric_summary": spectrogram_numeric_summary,
        },
        "cancellation": {
            "partition": cancellation.partition,
            "target": cancellation.target,
            "attempted": cancellation.attempted,
            "operation_id": cancellation.operation_id,
            "stage_at_cancel": cancellation.stage_at_cancel,
            "phase_at_cancel": cancellation.phase_at_cancel,
            "progress_at_cancel": cancellation.progress_at_cancel,
            "terminal_status": cancellation.terminal_status,
            "retry_succeeded": cancellation.retry_succeeded,
            "state_before": cancellation.state_before,
            "state_after": cancellation.state_after,
            "state_preserved": cancellation.state_preserved,
            "review_session_before": cancellation.review_session_before,
            "review_session_after": cancellation.review_session_after,
            "same_review_session_retry": (cancellation.same_review_session_retry),
            **(
                {"stop_handler_seconds": cancellation.stop_handler_seconds}
                if cancellation.stop_handler_seconds is not None
                else {}
            ),
        },
        "responsiveness": {
            "max_click_ack_seconds": max(clicks, default=0.0),
            "max_progress_silence_seconds": max(progress_silences, default=0.0),
        },
        "close": collector.close_evidence(),
    }


def _metrics_from_table(
    table: Any,
    *,
    preferred_row: str,
    row_label_heading: str,
    headings: tuple[str, ...],
) -> dict[str, float]:
    if not isinstance(table, QTableWidget) or table.rowCount() <= 0:
        raise DriverContractError("visible metrics table has no rows")
    columns = _table_headings(table)
    label_column = columns.get(row_label_heading)
    if label_column is None:
        raise DriverContractError(
            f"visible metrics table lacks {row_label_heading!r} heading"
        )
    row = next(
        (
            index
            for index in range(table.rowCount())
            if label_column is not None
            and table.item(index, label_column) is not None
            and table.item(index, label_column).text().strip() == preferred_row
        ),
        -1,
    )
    if row < 0:
        raise DriverContractError(
            f"visible metrics table lacks {preferred_row!r} terminal row"
        )
    metrics: dict[str, float] = {}
    for heading in headings:
        column = columns.get(heading)
        if column is None or table.item(row, column) is None:
            raise DriverContractError(
                f"visible metrics table lacks required {heading!r} value"
            )
        text = table.item(row, column).text().strip().rstrip("%")
        try:
            value = float(text)
        except ValueError as exc:
            raise DriverContractError(
                f"visible metric {heading!r} is not numeric"
            ) from exc
        if not math.isfinite(value):
            raise DriverContractError(f"visible metric {heading!r} is not finite")
        metrics[heading] = value
    return metrics


def _correlation_from_identity(
    identity: Any,
) -> dict[str, Any]:
    if not isinstance(identity, dict):
        raise DriverContractError("visible result identity is unavailable")
    run_id = str(identity.get("run_id") or "").strip()
    split = str(identity.get("split") or "").strip()
    publication_generation = identity.get("publication_generation")
    training_generation = identity.get("training_generation")
    training_boundary_stable = identity.get("training_boundary_stable")
    split_fingerprint = str(
        identity.get("split_specification_fingerprint") or ""
    ).strip()
    split_epoch_revision = identity.get("split_epoch_revision")
    producer_identities = identity.get("producer_identities")
    fold = identity.get("fold")
    if (
        not run_id
        or not split
        or isinstance(fold, bool)
        or not isinstance(fold, int)
        or isinstance(publication_generation, bool)
        or not isinstance(publication_generation, int)
        or isinstance(training_generation, bool)
        or not isinstance(training_generation, int)
        or training_boundary_stable is not True
        or not split_fingerprint
        or isinstance(split_epoch_revision, bool)
        or not isinstance(split_epoch_revision, int)
        or split_epoch_revision < 1
        or not isinstance(producer_identities, list)
        or not producer_identities
    ):
        raise DriverContractError("visible result identity is incomplete")
    detached_producers = [
        _producer_identity_payload(item) for item in producer_identities
    ]
    return {
        "run_id": run_id,
        "fold": fold,
        "split": split,
        "publication_generation": publication_generation,
        "training_generation": training_generation,
        "training_boundary_stable": True,
        "split_specification_fingerprint": split_fingerprint,
        "split_epoch_revision": split_epoch_revision,
        "producer_identities": detached_producers,
    }


def _producer_identity_payload(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise DriverContractError("visible producer identity is invalid")
    fields = (
        "fingerprint",
        "dataset_fingerprint",
        "split_fingerprint",
        "run_fingerprint",
        "model_fingerprint",
    )
    payload = {field: str(value.get(field) or "").strip() for field in fields}
    if any(not payload[field] for field in fields):
        raise DriverContractError("visible producer identity is incomplete")
    return payload


def _string_property_list(widget: QWidget, name: str) -> list[str]:
    value = widget.property(name)
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _table_headings(table: QTableWidget) -> dict[str, int]:
    return {
        item.text().strip(): column
        for column in range(table.columnCount())
        if (item := table.horizontalHeaderItem(column)) is not None
    }
