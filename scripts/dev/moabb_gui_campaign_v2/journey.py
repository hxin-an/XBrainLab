"""Dataset-agnostic visible-control sequence for one MainWindow journey."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QCheckBox

from .contract import (
    CANCELLATION_MEANINGFUL_STAGES,
    CANCELLATION_TARGETS,
    REQUIRED_STAGES,
    workflow_state_semantics_preserved,
)
from .driver import (
    ActiveOperationEvidence,
    ClickAcknowledgement,
    DriverContractError,
    GuiCampaignDriver,
    ProgressWaitEvidence,
    VisibleControl,
)

_LONG_OPERATION_TIMEOUT_SECONDS: Final = 3600.0

STAGE_CONTROL_ROUTE: Final[dict[str, VisibleControl | None]] = {
    "import_bids_folder": VisibleControl.IMPORT_BIDS,
    "select_subjects": VisibleControl.SUBJECT_CONTINUE,
    "review_metadata": VisibleControl.WIZARD_NEXT,
    "match_labels": VisibleControl.WIZARD_NEXT,
    "confirm_import": VisibleControl.WIZARD_CONFIRM,
    "preprocess": VisibleControl.DIALOG_CONFIRM,
    "epoch": VisibleControl.EPOCH_CONFIRM,
    "split": VisibleControl.SPLIT_CONFIRM,
    "model": VisibleControl.MODEL_CONFIRM,
    "training": VisibleControl.START_TRAINING,
    "evaluation": VisibleControl.EVALUATION_METRICS,
    "compute_saliency": VisibleControl.COMPUTE_SALIENCY,
    "saliency_map": VisibleControl.SALIENCY_TABS,
    "spectrogram": VisibleControl.SALIENCY_TABS,
    "clean_close": None,
}

CANCELLATION_CONTROL: Final[dict[str, VisibleControl]] = {
    "import": VisibleControl.OPERATION_CANCEL,
    "review": VisibleControl.OPERATION_CANCEL,
    "apply": VisibleControl.OPERATION_CANCEL,
    "epoch": VisibleControl.OPERATION_CANCEL,
    "training": VisibleControl.STOP_TRAINING,
    "saliency": VisibleControl.OPERATION_CANCEL,
}


@dataclass(frozen=True)
class StageInteraction:
    """The visible action that reached one campaign stage."""

    stage: str
    controls: tuple[str, ...]
    click_ack_seconds: float
    operation_id: str | None = None
    heartbeat_count: int = 0
    max_progress_silence_seconds: float | None = None
    elapsed_seconds: float = 0.0


@dataclass
class CancellationRunEvidence:
    """Cold-only visible cancel and same-process retry evidence."""

    partition: str
    target: str
    attempted: bool = False
    operation_id: str | None = None
    stage_at_cancel: str | None = None
    phase_at_cancel: str | None = None
    progress_at_cancel: dict[str, Any] | None = None
    terminal_status: str = "not_run"
    stop_handler_seconds: float | None = None
    retry_succeeded: bool = False
    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None
    state_preserved: bool = False
    review_session_before: dict[str, Any] | None = None
    review_session_after: dict[str, Any] | None = None
    same_review_session_retry: bool = False


class ProductRecommendedJourneyScaffold:
    """Drive the common recommended route without branching on dataset identity."""

    def __init__(
        self,
        driver: GuiCampaignDriver,
        *,
        mode: str = "replay",
        cancellation_partition: str = "import_review",
        cancellation_target: str = "import",
        expected_events: tuple[str, ...] = (),
        expected_classes: tuple[str, ...] = (),
        stage_observer: Callable[[StageInteraction], None] | None = None,
        visible_stage_observer: Callable[..., None] | None = None,
        before_close_observer: Callable[[], None] | None = None,
    ) -> None:
        self.driver = driver
        self.interactions: list[StageInteraction] = []
        self.mode = mode
        self.cancellation = CancellationRunEvidence(
            partition=cancellation_partition,
            target=cancellation_target,
        )
        self._expected_events = tuple(expected_events)
        self._expected_classes = tuple(expected_classes)
        self._stage_observer = stage_observer
        self._visible_stage_observer = visible_stage_observer
        self._before_close_observer = before_close_observer
        self.observed_ui_options: dict[str, Any] = {
            "selection_policy": "product_recommended_with_pinned_semantics",
        }

    def import_and_review(
        self,
        subjects: tuple[int, ...],
        *,
        expected_events: tuple[str, ...] | None = None,
        expected_classes: tuple[str, ...] | None = None,
    ) -> None:
        """Open BIDS, select the fixed cohort, and traverse every wizard page.

        The preview is owned by synchronous ``QDialog.exec()``; using the
        ordinary ``driver.wait_for_transition(...)`` after Subject Continue
        would run too late to interact with that nested event loop.
        """
        event_oracle = tuple(expected_events or self._expected_events)
        class_oracle = tuple(expected_classes or self._expected_classes)
        if self._expected_events and event_oracle != self._expected_events:
            raise DriverContractError("worker and journey event oracles differ")
        if self._expected_classes and class_oracle != self._expected_classes:
            raise DriverContractError("worker and journey class oracles differ")
        if self._should_cancel("import") or self._should_cancel("review"):
            self._exercise_import_review_cancellation(subjects)
        subject_acknowledgement: list[float] = [0.0]
        review_progress: list[ProgressWaitEvidence] = []
        review_acknowledgements: list[ClickAcknowledgement] = []
        confirm_acknowledgements: list[ClickAcknowledgement] = []
        confirm_baselines: list[str | None] = []
        review_sessions: list[Any] = []
        apply_states_before: list[dict[str, Any]] = []
        modal_failures: list[BaseException] = []
        self._capture_visible_stage("import_bids_folder")

        def confirm_import() -> None:
            if self._should_cancel("apply"):
                review_sessions.append(
                    self.driver.read_control_property(
                        VisibleControl.WIZARD_CONFIRM,
                        "reviewSessionIdentity",
                    )
                )
                apply_states_before.append(self.driver.workflow_state_identity("apply"))
            confirm_baselines.append(self.driver.visible_operation_id())
            self._capture_visible_stage("confirm_import")
            confirm_acknowledgements.append(
                self.driver.click(
                    VisibleControl.WIZARD_CONFIRM,
                    timeout_seconds=30.0,
                )
            )

        def interact_with_reopened_confirmation() -> None:
            try:
                self.driver.wait_for_modal_interaction(
                    VisibleControl.WIZARD_CONFIRM,
                    lambda _progress: confirm_import(),
                    timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
                )
            except BaseException as exc:
                modal_failures.append(exc)

        def traverse_preview(progress: ProgressWaitEvidence) -> None:
            review_progress.append(progress)
            first = self.driver.click(
                VisibleControl.WIZARD_NEXT,
                timeout_seconds=30.0,
            )
            second = self.driver.click(
                VisibleControl.WIZARD_NEXT,
                timeout_seconds=30.0,
            )
            review_acknowledgements.extend((first, second))
            self._capture_visible_stage("review_metadata")
            match_acknowledgement = self.driver.click(
                VisibleControl.WIZARD_NEXT,
                timeout_seconds=30.0,
            )
            self.observed_ui_options["event_value_decisions"] = (
                self.driver.resolve_visible_event_value_decisions(
                    expected_events=event_oracle,
                    expected_classes=class_oracle,
                    timeout_seconds=30.0,
                )
            )
            self._capture_visible_stage("match_labels")
            review_acknowledgements.append(match_acknowledgement)
            self.driver.click(VisibleControl.WIZARD_NEXT, timeout_seconds=30.0)
            try:
                self.driver.control(
                    VisibleControl.WIZARD_CONFIRM,
                    timeout_seconds=0.0,
                )
            except DriverContractError:
                # Match Labels may close the synchronous preview so the backend
                # can refresh its decision before reopening Review and Import.
                QTimer.singleShot(0, interact_with_reopened_confirmation)
                return
            confirm_import()

        def interact_with_synchronous_preview() -> None:
            try:
                self.driver.wait_for_modal_interaction(
                    VisibleControl.WIZARD_NEXT,
                    traverse_preview,
                    timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
                )
            except BaseException as exc:
                modal_failures.append(exc)

        def choose_subjects() -> None:
            self._capture_visible_stage("select_subjects")
            subject_acknowledgement[0] = self.driver.select_subjects(
                subjects,
                timeout_seconds=30.0,
            )
            # Continue opens DataInterpretationPreviewDialog with synchronous
            # QDialog.exec(). Arm the public-control interaction before that
            # nested event loop starts so the click can return normally.
            QTimer.singleShot(0, interact_with_synchronous_preview)

        (
            import_acknowledgement,
            acknowledgement,
            import_progress,
        ) = self.driver.open_modal_and_click(
            VisibleControl.IMPORT_BIDS,
            VisibleControl.SUBJECT_CONTINUE,
            before_confirm=choose_subjects,
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
        )
        if modal_failures:
            raise modal_failures[0]
        self._record(
            "import_bids_folder",
            (VisibleControl.IMPORT_BIDS,),
            import_acknowledgement.elapsed_seconds,
            progress=import_progress,
        )
        self._record(
            "select_subjects",
            (VisibleControl.SUBJECT_TABLE, VisibleControl.SUBJECT_CONTINUE),
            max(acknowledgement.elapsed_seconds, subject_acknowledgement[0]),
        )
        if len(review_progress) != 1 or len(review_acknowledgements) != 3:
            raise DriverContractError(
                "synchronous data interpretation preview did not complete"
            )
        first, second, match_acknowledgement = review_acknowledgements
        self._record(
            "review_metadata",
            (VisibleControl.WIZARD_NEXT, VisibleControl.WIZARD_NEXT),
            max(first.elapsed_seconds, second.elapsed_seconds),
            progress=review_progress[0],
        )
        self._record(
            "match_labels",
            (VisibleControl.WIZARD_NEXT,),
            match_acknowledgement.elapsed_seconds,
        )
        if len(confirm_acknowledgements) != 1:
            raise DriverContractError(
                "synchronous Review and Import confirmation did not complete"
            )
        confirm_acknowledgement = confirm_acknowledgements[0]
        confirm_baseline = confirm_baselines[0]
        review_session = review_sessions[0] if review_sessions else None
        apply_state_before = apply_states_before[0] if apply_states_before else None
        if self._should_cancel("apply"):
            retry_acknowledgements: list[ClickAcknowledgement] = []
            retry_baselines: list[str | None] = []
            retry_review_sessions: list[Any] = []

            def confirm_reopened_review(_progress: ProgressWaitEvidence) -> None:
                retry_review_sessions.append(
                    self.driver.read_control_property(
                        VisibleControl.WIZARD_CONFIRM,
                        "reviewSessionIdentity",
                    )
                )
                retry_baselines.append(self.driver.visible_operation_id())
                retry_acknowledgements.append(
                    self.driver.click(
                        VisibleControl.WIZARD_CONFIRM,
                        timeout_seconds=30.0,
                    )
                )

            def schedule_reopened_review_interaction() -> None:
                QTimer.singleShot(
                    0,
                    lambda: self.driver.wait_for_modal_interaction(
                        VisibleControl.WIZARD_CONFIRM,
                        confirm_reopened_review,
                        timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
                    ),
                )

            self._cancel_active_stage(
                "apply",
                review_session=review_session,
                state_before=apply_state_before,
                after_cancel_requested=schedule_reopened_review_interaction,
            )
            if (
                len(retry_acknowledgements) != 1
                or len(retry_baselines) != 1
                or len(retry_review_sessions) != 1
            ):
                raise DriverContractError(
                    "cancelled Apply did not reopen its synchronous review dialog"
                )
            retry_review_session = retry_review_sessions[0]
            confirm_baseline = retry_baselines[0]
            confirm_acknowledgement = retry_acknowledgements[0]
            self.cancellation.review_session_after = _json_mapping(retry_review_session)
            self.cancellation.same_review_session_retry = bool(
                self.cancellation.review_session_before
                == self.cancellation.review_session_after
            )
            if not self.cancellation.same_review_session_retry:
                raise DriverContractError(
                    "Apply cancellation did not retry the same review session"
                )
        confirm_progress = self.driver.wait_for_owned_operation_completion(
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
            excluding_operation_id=confirm_baseline,
        )
        self.driver.control(VisibleControl.NAV_PREPROCESS, timeout_seconds=30.0)
        self._record(
            "confirm_import",
            (VisibleControl.WIZARD_CONFIRM,),
            confirm_acknowledgement.elapsed_seconds,
            progress=confirm_progress,
        )
        if self.cancellation.target in {"import", "review"}:
            self._mark_retry_succeeded(self.cancellation.target)
        self._mark_retry_succeeded("apply")

    def configure_preprocess_epoch_training(self) -> None:
        """Apply product defaults and bound training to 1 epoch/repeat/fold."""
        self.driver.click(VisibleControl.NAV_PREPROCESS, timeout_seconds=30.0)
        preprocess_baseline = self.driver.visible_operation_id()

        def capture_preprocess_options() -> None:
            self._capture_filtering_options()
            self._capture_visible_stage("preprocess")

        _, preprocess_acknowledgement, _ = self.driver.open_modal_and_click(
            VisibleControl.FILTERING,
            VisibleControl.DIALOG_CONFIRM,
            before_confirm=capture_preprocess_options,
            timeout_seconds=30.0,
        )
        preprocess_progress = self.driver.wait_for_owned_operation_completion(
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
            excluding_operation_id=preprocess_baseline,
        )
        self.driver.control(VisibleControl.CREATE_EPOCH, timeout_seconds=30.0)
        self._record(
            "preprocess",
            (VisibleControl.DIALOG_CONFIRM,),
            preprocess_acknowledgement.elapsed_seconds,
            progress=preprocess_progress,
        )
        epoch_baseline = self.driver.visible_operation_id()
        epoch_state_before: dict[str, Any] | None = None

        def capture_epoch_options() -> None:
            nonlocal epoch_state_before
            self._capture_epoch_options()
            self._capture_visible_stage("epoch")
            if self._should_cancel("epoch"):
                epoch_state_before = self.driver.workflow_state_identity("epoch")

        _, epoch_acknowledgement, _ = self.driver.open_modal_and_click(
            VisibleControl.CREATE_EPOCH,
            VisibleControl.EPOCH_CONFIRM,
            before_confirm=capture_epoch_options,
            timeout_seconds=30.0,
        )
        if self._should_cancel("epoch"):
            self._cancel_active_stage("epoch", state_before=epoch_state_before)
            self.driver.control(VisibleControl.CREATE_EPOCH, timeout_seconds=30.0)
            epoch_baseline = self.driver.visible_operation_id()

            def capture_epoch_retry_options() -> None:
                self._capture_epoch_options()
                self._capture_visible_stage("epoch", replace=True)

            _, epoch_acknowledgement, _ = self.driver.open_modal_and_click(
                VisibleControl.CREATE_EPOCH,
                VisibleControl.EPOCH_CONFIRM,
                before_confirm=capture_epoch_retry_options,
                timeout_seconds=30.0,
            )
        epoch_progress = self.driver.wait_for_owned_operation_completion(
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
            excluding_operation_id=epoch_baseline,
        )
        self.driver.control(VisibleControl.NAV_TRAINING, timeout_seconds=30.0)
        self._record(
            "epoch",
            (VisibleControl.EPOCH_CONFIRM,),
            epoch_acknowledgement.elapsed_seconds,
            progress=epoch_progress,
        )
        self._mark_retry_succeeded("epoch")

        self.driver.click(VisibleControl.NAV_TRAINING, timeout_seconds=30.0)

        def capture_split_preview_options() -> None:
            self._capture_split_preview_options()
            self._capture_visible_stage("split", replace=True)

        _, split_acknowledgement, split_preview_acknowledgement = (
            self.driver.open_split_dialog_and_confirm(
                before_first_confirm=self._capture_split_options,
                before_preview_confirm=capture_split_preview_options,
                timeout_seconds=30.0,
            )
        )
        self._record(
            "split",
            (
                VisibleControl.SPLIT_CONFIRM,
                VisibleControl.SPLIT_PREVIEW_CONFIRM,
            ),
            max(
                split_acknowledgement.elapsed_seconds,
                split_preview_acknowledgement.elapsed_seconds,
            ),
        )

        def capture_model_options() -> None:
            self._capture_model_options()
            self._capture_visible_stage("model")

        _, model_acknowledgement, _ = self.driver.open_modal_and_click(
            VisibleControl.MODEL,
            VisibleControl.MODEL_CONFIRM,
            before_confirm=capture_model_options,
            timeout_seconds=30.0,
        )
        self._record(
            "model",
            (VisibleControl.MODEL_CONFIRM,),
            model_acknowledgement.elapsed_seconds,
        )

        def configure_bounded_training() -> None:
            self.driver.replace_text(VisibleControl.TRAINING_EPOCHS, "1")
            self.driver.replace_text(VisibleControl.TRAINING_REPEATS, "1")
            self.observed_ui_options["training_epochs"] = int(
                self.driver.control(VisibleControl.TRAINING_EPOCHS).text()
            )
            self.observed_ui_options["repeats"] = int(
                self.driver.control(VisibleControl.TRAINING_REPEATS).text()
            )
            self.observed_ui_options["training"] = {
                "epochs": self.observed_ui_options["training_epochs"],
                "repeats": self.observed_ui_options["repeats"],
                "batch_size": int(
                    self.driver.read_control_value(VisibleControl.TRAINING_BATCH_SIZE)
                ),
                "learning_rate": float(
                    self.driver.read_control_value(
                        VisibleControl.TRAINING_LEARNING_RATE
                    )
                ),
                "optimizer": self.driver.read_control_value(
                    VisibleControl.TRAINING_OPTIMIZER
                ),
                "selected_device": self.driver.read_control_value(
                    VisibleControl.TRAINING_DEVICE
                ),
                "evaluation": self.driver.read_control_value(
                    VisibleControl.TRAINING_EVALUATION
                ),
            }

        self.driver.open_modal_and_click(
            VisibleControl.TRAINING_SETTINGS,
            VisibleControl.TRAINING_CONFIRM,
            before_confirm=configure_bounded_training,
            timeout_seconds=30.0,
        )
        training_baseline = self.driver.visible_operation_id()
        training_state_before = (
            self.driver.workflow_state_identity("training")
            if self._should_cancel("training")
            else None
        )
        training_acknowledgement = self.driver.click(
            VisibleControl.START_TRAINING,
            timeout_seconds=30.0,
        )
        if self._should_cancel("training"):
            self._cancel_active_stage(
                "training",
                state_before=training_state_before,
            )
            self.driver.control(VisibleControl.START_TRAINING, timeout_seconds=30.0)
            training_baseline = self.driver.visible_operation_id()
            training_acknowledgement = self.driver.click(
                VisibleControl.START_TRAINING,
                timeout_seconds=30.0,
            )
        training_progress = self.driver.wait_for_training_completion(
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
            excluding_operation_id=training_baseline,
        )
        history = self.driver.control(
            VisibleControl.TRAINING_HISTORY,
            timeout_seconds=30.0,
        )
        runtime_devices = history.property("terminalTrainingDevices")
        if not isinstance(runtime_devices, list) or not runtime_devices:
            raise DriverContractError(
                "completed training lacks a backend-published runtime device"
            )
        normalized_devices = [str(value).strip() for value in runtime_devices]
        if any(not value.startswith("cuda:") for value in normalized_devices):
            raise DriverContractError("campaign training did not remain on CUDA")
        training_options = self.observed_ui_options.get("training")
        if isinstance(training_options, dict):
            training_options["runtime_devices"] = normalized_devices
        self._record(
            "training",
            (VisibleControl.START_TRAINING,),
            training_acknowledgement.elapsed_seconds,
            progress=training_progress,
        )
        self._mark_retry_succeeded("training")

    def open_evaluation_and_saliency(self) -> None:
        """Open finite Evaluation, explicitly compute Saliency, and click both views."""
        evaluation_baseline = self.driver.visible_operation_id()
        evaluation_acknowledgement = self.driver.click(
            VisibleControl.NAV_EVALUATION,
            timeout_seconds=30.0,
        )
        evaluation_progress = self.driver.wait_for_owned_operation_completion(
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
            excluding_operation_id=evaluation_baseline,
        )
        evaluation_table = self.driver.wait_for_table_rows(
            VisibleControl.EVALUATION_METRICS,
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
        )
        if str(evaluation_table.property("operationId") or "").strip() != str(
            evaluation_progress.operation_id or ""
        ):
            raise DriverContractError(
                "Evaluation table does not match its owned render operation"
            )
        self._record(
            "evaluation",
            (VisibleControl.NAV_EVALUATION, VisibleControl.EVALUATION_METRICS),
            evaluation_acknowledgement.elapsed_seconds,
            progress=evaluation_progress,
        )

        self.driver.click(VisibleControl.NAV_VISUALIZATION, timeout_seconds=30.0)
        self.observed_ui_options["saliency"] = {
            "method": self.driver.read_control_property(
                VisibleControl.COMPUTE_SALIENCY,
                "saliencyMethod",
            ),
            "parameters": self.driver.read_control_property(
                VisibleControl.COMPUTE_SALIENCY,
                "saliencyParameters",
            ),
            "normalize": self.driver.read_control_property(
                VisibleControl.COMPUTE_SALIENCY,
                "saliencyNormalize",
            ),
        }
        compute_baseline = self.driver.control_operation_id(
            VisibleControl.COMPUTE_SALIENCY
        )
        saliency_state_before = (
            self.driver.workflow_state_identity("saliency")
            if self._should_cancel("saliency")
            else None
        )
        compute_acknowledgement = self.driver.click(
            VisibleControl.COMPUTE_SALIENCY,
            timeout_seconds=30.0,
        )
        if self._should_cancel("saliency"):
            self._cancel_active_stage(
                "saliency",
                state_before=saliency_state_before,
            )
            self.driver.control(VisibleControl.COMPUTE_SALIENCY, timeout_seconds=30.0)
            compute_baseline = self.driver.control_operation_id(
                VisibleControl.COMPUTE_SALIENCY
            )
            compute_acknowledgement = self.driver.click(
                VisibleControl.COMPUTE_SALIENCY,
                timeout_seconds=30.0,
            )
        compute_progress = self.driver.wait_for_control_operation_completion(
            VisibleControl.COMPUTE_SALIENCY,
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
            excluding_operation_id=compute_baseline,
        )
        self._record(
            "compute_saliency",
            (VisibleControl.COMPUTE_SALIENCY,),
            compute_acknowledgement.elapsed_seconds,
            progress=compute_progress,
        )
        self._mark_retry_succeeded("saliency")
        map_acknowledgement = self.driver.choose_tab(
            "Saliency Map",
            timeout_seconds=30.0,
        )
        map_progress = self.driver.wait_for_render_status(
            VisibleControl.SALIENCY_MAP_STATUS,
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
        )
        self._record(
            "saliency_map",
            (VisibleControl.SALIENCY_TABS,),
            map_acknowledgement.elapsed_seconds,
            progress=map_progress,
        )
        spectrogram_acknowledgement = self.driver.choose_tab(
            "Spectrogram",
            timeout_seconds=30.0,
        )
        spectrogram_progress = self.driver.wait_for_render_status(
            VisibleControl.SPECTROGRAM_STATUS,
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
        )
        self._record(
            "spectrogram",
            (VisibleControl.SALIENCY_TABS,),
            spectrogram_acknowledgement.elapsed_seconds,
            progress=spectrogram_progress,
        )

    def cancel_current_operation(
        self,
        *,
        partition: str,
        target: str,
    ) -> tuple[ClickAcknowledgement, ActiveOperationEvidence]:
        """Exercise only the cancellation target assigned by the locked plan."""
        if target not in CANCELLATION_TARGETS.get(partition, frozenset()):
            raise ValueError(f"{target!r} is not assigned to {partition!r}")
        allowed_stages = CANCELLATION_MEANINGFUL_STAGES[target]
        active = self.driver.wait_for_meaningful_active_operation(
            allowed_stages=allowed_stages,
            timeout_seconds=30.0,
        )
        acknowledgement, at_click = self.driver.click_active_operation_cancel(
            CANCELLATION_CONTROL[target],
            expected_operation_id=active.operation_id,
            allowed_stages=allowed_stages,
        )
        if acknowledgement.elapsed_seconds > 0.1:
            raise DriverContractError(
                f"{target} stop handler exceeded the 100 ms campaign limit"
            )
        return acknowledgement, at_click

    def clean_close(self) -> None:
        """Request the real MainWindow close path; receipt validation checks quiescence."""
        if self._before_close_observer is not None:
            self._before_close_observer()
        started = time.monotonic()
        self.driver.close_main_window()
        self._record("clean_close", (), time.monotonic() - started)

    def observed_stage_order(self) -> tuple[str, ...]:
        return tuple(item.stage for item in self.interactions)

    def expected_file_dialog_selection_count(self) -> int:
        return (
            2
            if self.mode == "cold" and self.cancellation.target in {"import", "review"}
            else 1
        )

    def _exercise_import_review_cancellation(
        self,
        subjects: tuple[int, ...],
    ) -> None:
        state_before = (
            self.driver.workflow_state_identity("import")
            if self.cancellation.target == "import"
            else None
        )
        self.driver.click(VisibleControl.IMPORT_BIDS, timeout_seconds=30.0)
        if self.cancellation.target == "review":
            captured_review_state: list[dict[str, Any]] = []

            def select_subjects_and_capture(_progress: ProgressWaitEvidence) -> None:
                self.driver.select_subjects(subjects, timeout_seconds=30.0)
                captured_review_state.append(
                    self.driver.workflow_state_identity("review")
                )
                self.driver.click(
                    VisibleControl.SUBJECT_CONTINUE,
                    timeout_seconds=30.0,
                )

            self.driver.wait_for_modal_interaction(
                VisibleControl.SUBJECT_TABLE,
                select_subjects_and_capture,
                timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
            )
            state_before = captured_review_state[0] if captured_review_state else None
        self._cancel_active_stage(
            self.cancellation.target,
            state_before=state_before,
        )
        self.driver.control(VisibleControl.IMPORT_BIDS, timeout_seconds=30.0)

    def _should_cancel(self, target: str) -> bool:
        return (
            self.mode == "cold"
            and not self.cancellation.attempted
            and self.cancellation.target == target
        )

    def _cancel_active_stage(
        self,
        target: str,
        *,
        review_session: Any | None = None,
        state_before: dict[str, Any] | None = None,
        after_cancel_requested: Callable[[], None] | None = None,
    ) -> None:
        before = state_before or self.driver.workflow_state_identity(target)
        acknowledgement, at_click = self.cancel_current_operation(
            partition=self.cancellation.partition,
            target=target,
        )
        if after_cancel_requested is not None:
            after_cancel_requested()
        terminal = self.driver.wait_for_operation_terminal(
            at_click.operation_id,
            timeout_seconds=_LONG_OPERATION_TIMEOUT_SECONDS,
            expected_phase="cancelled",
        )
        after = self.driver.workflow_state_identity(target)
        if not workflow_state_semantics_preserved(before, after):
            raise DriverContractError(
                f"{target} cancellation changed protected workflow state"
            )
        self.cancellation.attempted = True
        self.cancellation.operation_id = terminal.operation_id
        self.cancellation.stage_at_cancel = at_click.stage
        self.cancellation.phase_at_cancel = at_click.phase
        self.cancellation.progress_at_cancel = dict(at_click.progress)
        self.cancellation.terminal_status = terminal.terminal_phase
        self.cancellation.stop_handler_seconds = acknowledgement.elapsed_seconds
        self.cancellation.state_before = before
        self.cancellation.state_after = after
        self.cancellation.state_preserved = True
        if target == "apply":
            self.cancellation.review_session_before = _json_mapping(review_session)

    def _mark_retry_succeeded(self, target: str) -> None:
        if self.cancellation.attempted and self.cancellation.target == target:
            self.cancellation.retry_succeeded = True

    def _click_stage(
        self,
        stage: str,
        control: VisibleControl,
        *,
        timeout_seconds: float = 2.0,
    ) -> ClickAcknowledgement:
        acknowledgement = self.driver.click(control, timeout_seconds=timeout_seconds)
        self._record(stage, (control,), acknowledgement.elapsed_seconds)
        return acknowledgement

    def _capture_split_options(self) -> None:
        cross_validation = self.driver.control(
            VisibleControl.SPLIT_CROSS_VALIDATION,
            timeout_seconds=30.0,
        )
        if not isinstance(cross_validation, QCheckBox):
            raise DriverContractError(
                "split cross-validation control is not a checkbox"
            )
        if cross_validation.isChecked():
            self.driver.click(
                VisibleControl.SPLIT_CROSS_VALIDATION,
                timeout_seconds=2.0,
            )
        if cross_validation.isChecked():
            raise DriverContractError(
                "bounded campaign could not disable visible cross-validation"
            )
        folds = 1
        self.observed_ui_options["folds"] = folds
        self.observed_ui_options["split"] = {
            "training_mode": self.driver.read_control_value(
                VisibleControl.SPLIT_TRAINING_MODE
            ),
            "testing_strategy": self.driver.read_control_value(
                VisibleControl.SPLIT_TESTING_STRATEGY
            ),
            "validation_strategy": self.driver.read_control_value(
                VisibleControl.SPLIT_VALIDATION_STRATEGY
            ),
            "cross_validation": bool(cross_validation.isChecked()),
            "folds": folds,
        }
        self._capture_visible_stage("split")

    def _capture_visible_stage(self, stage: str, *, replace: bool = False) -> None:
        observer = self._visible_stage_observer
        if observer is not None:
            observer(stage, replace=replace)

    def _capture_split_preview_options(self) -> None:
        split = self.observed_ui_options.get("split")
        if not isinstance(split, dict):
            raise DriverContractError("split controls were not captured")
        split["configuration"] = self.driver.read_control_property(
            VisibleControl.SPLIT_PREVIEW_CONFIRM,
            "splitConfiguration",
        )
        split["specification_fingerprint"] = self.driver.read_control_property(
            VisibleControl.SPLIT_PREVIEW_CONFIRM,
            "splitSpecificationFingerprint",
        )

    def _capture_filtering_options(self) -> None:
        bandpass = bool(
            self.driver.read_control_value(VisibleControl.FILTERING_BANDPASS)
        )
        notch = bool(self.driver.read_control_value(VisibleControl.FILTERING_NOTCH))
        self.observed_ui_options["filtering"] = {
            "bandpass_enabled": bandpass,
            "low_frequency_hz": (
                self.driver.read_control_value(VisibleControl.FILTERING_LOW_FREQUENCY)
                if bandpass
                else None
            ),
            "high_frequency_hz": (
                self.driver.read_control_value(VisibleControl.FILTERING_HIGH_FREQUENCY)
                if bandpass
                else None
            ),
            "notch_enabled": notch,
            "notch_mode": (
                self.driver.read_control_value(VisibleControl.FILTERING_NOTCH_MODE)
                if notch
                else None
            ),
            "notch_frequency_hz": (
                self.driver.read_control_value(VisibleControl.FILTERING_NOTCH_FREQUENCY)
                if notch
                else None
            ),
        }

    def _capture_epoch_options(self) -> None:
        baseline = bool(self.driver.read_control_value(VisibleControl.EPOCH_BASELINE))
        start = float(self.driver.read_control_value(VisibleControl.EPOCH_START))
        end = float(self.driver.read_control_value(VisibleControl.EPOCH_END))
        self.observed_ui_options["epoch"] = {
            "window_mode": self.driver.read_control_value(
                VisibleControl.EPOCH_WINDOW_MODE
            ),
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": end - start,
            "baseline": {
                "enabled": baseline,
                "start_seconds": (
                    self.driver.read_control_value(VisibleControl.EPOCH_BASELINE_START)
                    if baseline
                    else None
                ),
                "end_seconds": (
                    self.driver.read_control_value(VisibleControl.EPOCH_BASELINE_END)
                    if baseline
                    else None
                ),
            },
        }

    def _capture_model_options(self) -> None:
        selected = self.driver.read_control_value(VisibleControl.MODEL_COMBO)
        if not isinstance(selected, dict):
            raise DriverContractError("model selection is not publicly readable")
        display = str(selected.get("display") or "").strip()
        stable_value = selected.get("value")
        stable_id = str(stable_value or display).strip()
        if not display or not stable_id:
            raise DriverContractError("model selection identity is incomplete")
        self.observed_ui_options["model"] = {
            "stable_id": stable_id,
            "display": display,
        }

    def _record(
        self,
        stage: str,
        controls: tuple[VisibleControl, ...],
        click_ack_seconds: float,
        *,
        progress: ProgressWaitEvidence | None = None,
    ) -> None:
        if stage not in REQUIRED_STAGES:
            raise ValueError(f"Unknown campaign stage: {stage}")
        interaction = StageInteraction(
            stage=stage,
            controls=tuple(control.value for control in controls),
            click_ack_seconds=click_ack_seconds,
            operation_id=progress.operation_id if progress is not None else None,
            heartbeat_count=(progress.heartbeat_count if progress is not None else 0),
            max_progress_silence_seconds=(
                progress.max_progress_silence_seconds if progress is not None else None
            ),
            elapsed_seconds=(
                progress.elapsed_seconds + click_ack_seconds
                if progress is not None
                else click_ack_seconds
            ),
        )
        self.interactions.append(interaction)
        if self._stage_observer is not None:
            self._stage_observer(interaction)


def _json_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DriverContractError("review session identity is unavailable")
    payload = json.loads(json.dumps(value, sort_keys=True))
    if (
        not isinstance(payload, dict)
        or not all(
            str(payload.get(field) or "").strip()
            for field in ("scan_id", "candidate_id", "preview_id")
        )
        or (
            type(payload.get("publication_generation")) is not int
            or payload["publication_generation"] < 0
        )
    ):
        raise DriverContractError("review session identity is incomplete")
    return payload
