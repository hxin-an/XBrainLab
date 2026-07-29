"""Action handler for dataset panel operations.

Provides logic for importing EEG data files, applying labels,
running smart parse, and managing event filtering.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QTableWidgetItem,
)

from XBrainLab.backend.application.commands import (
    ApplyInterpretationCommand,
    ApplySmartParseCommand,
    CommandName,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    MetadataUpdate,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    RemoveFilesCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.errors import ApplicationError, PreconditionError
from XBrainLab.backend.application.resource_preflight import (
    ResourcePreflightContractError,
    ResourcePreflightView,
)
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
    InterpretationReviewIdentity,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    CommandReviewContext,
    ControllerCompatibilityUnavailableError,
    application_ui_runtime,
    blocked_reason,
    execute_application_command,
    execute_application_command_async,
    get_application_view_publication,
    get_command_capability,
    get_command_review_context,
    has_real_application_context,
    is_stale_publication_result,
    run_controller_compatibility_call,
)
from XBrainLab.ui.async_command_runner import qt_object_deleted
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.interaction_outcome import (
    InteractionOutcome,
    reserve_interaction_continuation,
)
from XBrainLab.ui.status import show_status_message

DataInterpretationPreviewDialog: Any | None = None
EventFilterDialog: Any | None = None
ImportLabelDialog: Any | None = None
LabelMappingDialog: Any | None = None
SmartParserDialog: Any | None = None


@dataclass(frozen=True)
class DatasetTableRowIdentity:
    """Stable identity for one row in a published Dataset table."""

    canonical_filepath: str
    rendered_row: int


@dataclass(frozen=True)
class DatasetTableSelection:
    """Rows selected from one immutable Dataset-table publication."""

    publication_generation: int | None
    rows: tuple[DatasetTableRowIdentity, ...]


@dataclass(frozen=True)
class _InterpretationReviewState:
    scan: dict[str, Any]
    preview: dict[str, Any]
    candidate: dict[str, Any]
    candidate_id: str | None
    decision: dict[str, Any]
    publication_generation: int | None = None


@dataclass(frozen=True)
class _PublishedInterpretationReview:
    payload: dict[str, Any]
    identity: InterpretationReviewIdentity


def _data_interpretation_preview_dialog_class():
    patched = globals()["DataInterpretationPreviewDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (  # noqa: PLC0415
        DataInterpretationPreviewDialog,
    )

    return DataInterpretationPreviewDialog


def _event_filter_dialog_class():
    patched = globals()["EventFilterDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.event_filter_dialog import (  # noqa: PLC0415
        EventFilterDialog,
    )

    return EventFilterDialog


def _import_label_dialog_class():
    patched = globals()["ImportLabelDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.import_label_dialog import (  # noqa: PLC0415
        ImportLabelDialog,
    )

    return ImportLabelDialog


def _label_mapping_dialog_class():
    patched = globals()["LabelMappingDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.label_mapping_dialog import (  # noqa: PLC0415
        LabelMappingDialog,
    )

    return LabelMappingDialog


def _smart_parser_dialog_class():
    patched = globals()["SmartParserDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.smart_parser_dialog import (  # noqa: PLC0415
        SmartParserDialog,
    )

    return SmartParserDialog


class DatasetActionHandler:
    """Helper class to handle complex actions for DatasetPanel.

    Decouples action logic (import, labeling, parsing) from the main
    ``DatasetPanel`` view class.

    Attributes:
        panel: The parent ``DatasetPanel`` instance.

    """

    def __init__(self, panel):
        """Initialize the action handler.

        Args:
            panel: The parent ``DatasetPanel`` that owns this handler.

        """
        self.panel = panel

    @property
    def controller(self):
        """DatasetController: The dataset controller from the parent panel."""
        return getattr(self.panel, "controller", None)

    @property
    def main_window(self):
        """QMainWindow: The application main window reference."""
        return getattr(self.panel, "main_window", None)

    def _update_panel_after_command_result(self, result) -> None:
        if result is None:
            self.panel.update_panel()

    def _show_status(self, message: str) -> None:
        show_status_message(self.panel, message)

    def _compatibility_controller_value(
        self,
        blocked_title: str,
        fallback: Callable[[], Any],
        *,
        warn_when_unavailable: bool = True,
    ) -> tuple[bool, Any]:
        """Read controller compatibility state only for mock UI contexts."""
        try:
            return True, run_controller_compatibility_call(self.panel, fallback)
        except ControllerCompatibilityUnavailableError as exc:
            if warn_when_unavailable:
                QMessageBox.warning(self.panel, blocked_title, str(exc))
            return False, None

    def _compatibility_locked_preflight_blocked(
        self,
        controller: Any,
        *,
        blocked_title: str,
        locked_message: str,
        block_when_unavailable: bool = True,
    ) -> bool:
        available, is_locked = self._compatibility_controller_value(
            blocked_title,
            lambda: bool(controller.is_locked()),
            warn_when_unavailable=block_when_unavailable,
        )
        if not available:
            return block_when_unavailable
        if is_locked:
            QMessageBox.warning(self.panel, blocked_title, locked_message)
            return True
        return False

    def _compatibility_filenames_for_smart_parse(self) -> list[str] | None:
        controller = self.controller
        if controller is None:
            return []
        available, filenames = self._compatibility_controller_value(
            "Smart Parse Blocked",
            controller.get_filenames,
        )
        if not available:
            return None
        return list(filenames or [])

    def _compatibility_target_files_from_controller(self, selected_rows) -> list[Any]:
        controller = self.controller
        if controller is None:
            QMessageBox.warning(
                self.panel,
                "Add Labels Blocked",
                "Dataset controller unavailable.",
            )
            return []
        available, data_list = self._compatibility_controller_value(
            "Add Labels Blocked",
            controller.get_loaded_data_list,
        )
        if not available:
            return []
        self._last_target_file_indices = [
            i for i in selected_rows if i < len(data_list)
        ]
        return [data_list[i] for i in self._last_target_file_indices]

    def _compatibility_smart_filter_suggestions(
        self,
        raw_file,
        target_count: int,
    ) -> list[int]:
        controller = self.controller
        if controller is None:
            return []
        available, suggestions = self._compatibility_controller_value(
            "Smart Filter Blocked",
            lambda: controller.get_smart_filter_suggestions(raw_file, target_count),
            warn_when_unavailable=False,
        )
        if not available:
            logger.warning(
                "Skipped compatibility smart-filter suggestions in real Study context.",
            )
            return []
        return [int(item) for item in suggestions or []]

    def import_data(self) -> InteractionOutcome:
        """Scan, preview, validate, and apply an EEG data interpretation."""
        scan_capability = get_command_capability(self.panel, CommandName.SCAN_SOURCE)
        if scan_capability is not None and not scan_capability.enabled:
            message = blocked_reason(
                scan_capability,
                "Data interpretation is not available right now.",
            )
            QMessageBox.warning(
                self.panel,
                "Interpretation Blocked",
                message,
            )
            return InteractionOutcome.blocked(message)

        controller = self.controller
        if controller is None:
            message = "Dataset controller unavailable."
            QMessageBox.critical(
                self.panel,
                "Import failed",
                message,
            )
            return InteractionOutcome.failed(message)

        if scan_capability is None and self._compatibility_locked_preflight_blocked(
            controller,
            blocked_title="Interpretation Blocked",
            locked_message="Dataset is locked. Please clear or reset before importing.",
            block_when_unavailable=False,
        ):
            return InteractionOutcome.blocked(
                "Dataset is locked or its import state could not be verified."
            )

        filter_str = (
            "All files (*);;"
            "EEG files (*.set *.SET *.gdf *.GDF *.fif *.FIF *.edf *.EDF "
            "*.bdf *.BDF *.cnt *.CNT *.vhdr *.VHDR);;"
            "EEGLAB (*.set *.SET);;GDF (*.gdf *.GDF);;"
            "FIF (*.fif *.FIF);;EDF/BDF (*.edf *.EDF *.bdf *.BDF);;"
            "Neuroscan CNT (*.cnt *.CNT);;BrainVision (*.vhdr *.VHDR)"
        )
        filepaths, _ = QFileDialog.getOpenFileNames(
            self.panel,
            "Choose EEG Source for Interpretation",
            "",
            filter_str,
        )
        if not filepaths:
            return InteractionOutcome.cancelled("No EEG source was selected.")

        try:
            outcome = self._run_data_interpretation_import(list(filepaths))
            if outcome is not None:
                return outcome
            if scan_capability is not None:
                message = "Data Interpretation command service is unavailable."
                QMessageBox.critical(
                    self.panel,
                    "Interpretation unavailable",
                    message,
                )
                return InteractionOutcome.failed(message)
            if has_real_application_context(self.panel):
                QMessageBox.warning(
                    self.panel,
                    "Interpretation Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return InteractionOutcome.blocked(
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
                )
            result = execute_application_command(
                self.panel,
                LoadDataCommand(
                    paths=list(filepaths),
                ),
            )
            if result is not None and result.failed:
                QMessageBox.critical(
                    self.panel,
                    "Import failed",
                    result.message,
                )
                return self._interaction_failure_outcome(result, result.message)
            if result is None:
                QMessageBox.warning(
                    self.panel,
                    "Interpretation Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return InteractionOutcome.blocked(
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
                )
            self._show_status(result.message)
            return InteractionOutcome.completed(result.message)
        except Exception:
            message = present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.DATA_IMPORT,
                message_box=QMessageBox,
            )
            return InteractionOutcome.failed(message)

    def review_current_import(
        self,
        *,
        initial_step: str = "Review and Import",
        expected_identity: InterpretationReviewIdentity | None = None,
    ) -> InteractionOutcome:
        """Reopen the exact backend-published review without rescanning files."""
        if expected_identity is not None and not isinstance(
            expected_identity,
            InterpretationReviewIdentity,
        ):
            raise TypeError("Expected interpretation review identity must be typed.")
        try:
            published_review = self._read_interpretation_review(expected_identity)
        except (ApplicationError, ControllerCompatibilityUnavailableError) as exc:
            message = str(exc)
            QMessageBox.warning(
                self.panel,
                "Import review unavailable",
                message,
            )
            return InteractionOutcome.blocked(message)

        try:
            publication = published_review.payload
            scan = dict(publication["scan_result"])
            candidate = dict(publication["candidate"])
            preview = dict(publication["preview"])
            decision = dict(publication["validation_decision"])
            choices = dict(publication.get("choices") or {})
            label_sources = [
                str(item)
                for item in publication.get("label_sources", [])
                if str(item).strip()
            ]
            source_path = str(publication["source_path"])
            source_hint = str(publication.get("source_hint") or "auto")
        except (KeyError, TypeError, ValueError):
            message = present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.DATA_IMPORT_REVIEW,
                message_box=QMessageBox,
            )
            return InteractionOutcome.failed(message)

        review_state = _InterpretationReviewState(
            scan=scan,
            preview=preview,
            candidate=candidate,
            candidate_id=self._optional_payload_id(candidate, "candidate_id"),
            decision=decision,
            publication_generation=published_review.identity.publication_generation,
        )
        return self._continue_data_interpretation_import(
            source_path=source_path,
            source_hint=source_hint,
            choices=choices,
            label_sources=label_sources,
            review_state=review_state,
            initial_step=initial_step,
        )

    def _read_interpretation_review(
        self,
        expected_identity: InterpretationReviewIdentity | None,
    ) -> _PublishedInterpretationReview:
        runtime = application_ui_runtime(self.panel)
        if runtime is None:
            raise ControllerCompatibilityUnavailableError(
                "The Data Import review runtime is unavailable."
            )

        publication_before = runtime.get_view_publication()
        if expected_identity is None:
            expected_identity = self._identity_from_publication(publication_before)
        self._require_interpretation_identity(
            publication_before,
            expected_identity,
        )
        review = runtime.get_interpretation_review(
            expected_identity=expected_identity,
        )
        self._require_review_payload_identity(review, expected_identity)
        publication_after = runtime.get_view_publication()
        self._require_interpretation_identity(
            publication_after,
            expected_identity,
        )
        return _PublishedInterpretationReview(
            payload=dict(review),
            identity=expected_identity,
        )

    @staticmethod
    def _identity_from_publication(
        publication: object,
    ) -> InterpretationReviewIdentity:
        if isinstance(publication, ApplicationViewPublication) and publication.usable:
            interpretation = publication.state.interpretation
            if (
                isinstance(interpretation.latest_scan_id, str)
                and interpretation.latest_scan_id.strip()
                and isinstance(interpretation.latest_candidate_id, str)
                and interpretation.latest_candidate_id.strip()
            ):
                return InterpretationReviewIdentity(
                    publication_generation=publication.generation,
                    scan_id=interpretation.latest_scan_id,
                    candidate_id=interpretation.latest_candidate_id,
                )
        raise PreconditionError(
            "The Data Import review identity could not be verified. Refresh the "
            "review and try again.",
            diagnostics={"stale_interpretation_review": True},
        )

    @staticmethod
    def _require_interpretation_identity(
        publication: object,
        expected_identity: InterpretationReviewIdentity,
    ) -> None:
        if isinstance(publication, ApplicationViewPublication):
            interpretation = publication.state.interpretation
            matches = (
                publication.usable
                and publication.generation == expected_identity.publication_generation
                and interpretation.latest_scan_id == expected_identity.scan_id
                and interpretation.latest_candidate_id == expected_identity.candidate_id
            )
            if matches:
                return
        raise PreconditionError(
            "The Data Import review changed before it could be opened. Open the "
            "current review and try again.",
            diagnostics={"stale_interpretation_review": True},
        )

    @staticmethod
    def _require_review_payload_identity(
        review: object,
        expected_identity: InterpretationReviewIdentity,
    ) -> None:
        if not isinstance(review, dict):
            raise PreconditionError(
                "The Data Import review identity could not be verified.",
                diagnostics={"stale_interpretation_review": True},
            )
        scan = review.get("scan_result")
        candidate = review.get("candidate")
        scan_id = scan.get("scan_id") if isinstance(scan, dict) else None
        candidate_id = (
            candidate.get("candidate_id") if isinstance(candidate, dict) else None
        )
        if (
            scan_id == expected_identity.scan_id
            and candidate_id == expected_identity.candidate_id
        ):
            return
        raise PreconditionError(
            "The Data Import review identity could not be verified.",
            diagnostics={
                "stale_interpretation_review": True,
                "review_payload_mismatch": True,
            },
        )

    def import_folder_source(self):
        """Interpret a folder or BIDS root through the Data Interpretation flow."""
        if not self._can_start_interpretation():
            return
        source_path = QFileDialog.getExistingDirectory(
            self.panel,
            "Choose Folder or BIDS Root for Interpretation",
            "",
        )
        if not source_path:
            return
        try:
            handled = self._run_data_interpretation_import([source_path])
            if not handled:
                QMessageBox.critical(
                    self.panel,
                    "Interpretation unavailable",
                    "Data Interpretation command service is unavailable.",
                )
        except Exception:
            present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.DATA_IMPORT,
                message_box=QMessageBox,
            )

    def import_bids_source(self):
        """Interpret a BIDS EEG folder through the Data Interpretation flow."""
        if not self._can_start_interpretation():
            return
        source_path = QFileDialog.getExistingDirectory(
            self.panel,
            "Choose BIDS Folder for Import",
            "",
        )
        if not source_path:
            return
        try:
            handled = self._run_data_interpretation_import(
                [source_path],
                source_hint="bids",
            )
            if not handled:
                QMessageBox.critical(
                    self.panel,
                    "Interpretation unavailable",
                    "Data Interpretation command service is unavailable.",
                )
        except Exception:
            present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.DATA_IMPORT,
                message_box=QMessageBox,
            )

    def reload_interpretation_recipe(self):
        """Reload a saved import recipe, preview it, and apply after review."""
        if not self._can_start_interpretation(
            CommandName.RELOAD_INTERPRETATION_RECIPE,
            blocked_title="Recipe Reload Blocked",
            fallback_reason="Recipe reload is not available right now.",
        ):
            return
        review_context = get_command_review_context(
            self.panel,
            CommandName.RELOAD_INTERPRETATION_RECIPE,
        )
        if review_context is not None and not review_context.capability.enabled:
            QMessageBox.warning(
                self.panel,
                "Recipe Reload Blocked",
                blocked_reason(
                    review_context.capability,
                    "Recipe reload is not available right now.",
                ),
            )
            return
        recipe_path, _ = QFileDialog.getOpenFileName(
            self.panel,
            "Choose Import Recipe",
            "",
            "Import Recipe (*.json);;JSON (*.json)",
        )
        if not recipe_path:
            return

        def _handle_reload_result(result) -> InteractionOutcome | None:
            resource_outcome = self._preview_resource_preflight_outcome(
                result,
                retry=lambda token: _dispatch(
                    resource_preflight_confirmed=True,
                    resource_preflight_token=token,
                ),
            )
            if resource_outcome is not None:
                return resource_outcome
            self._continue_reloaded_interpretation_recipe(result)
            return None

        def _dispatch(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome | None:
            return self._execute_interpretation_command_async(
                ReloadInterpretationRecipeCommand(
                    recipe_path=recipe_path,
                    resource_preflight_confirmed=resource_preflight_confirmed,
                    resource_preflight_token=resource_preflight_token,
                ),
                on_result=_handle_reload_result,
                error_title="Recipe reload failed",
                expected_publication_generation=(
                    review_context.publication_generation
                    if review_context is not None
                    else None
                ),
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_IMPORT_RECIPE_RELOAD
                ),
            )

        started = _dispatch()
        if not started:
            QMessageBox.critical(
                self.panel,
                "Recipe reload unavailable",
                "Data Interpretation command service is unavailable.",
            )

    def _continue_reloaded_interpretation_recipe(self, reload_result) -> None:
        """Open the recipe review after its backend state is ready."""
        if self._result_failed(reload_result, "Recipe reload failed"):
            return

        scan = self._diagnostic_payload(reload_result, "scan_result")
        preview = self._diagnostic_payload(reload_result, "preview")
        candidate = self._diagnostic_payload(reload_result, "candidate")
        decision = self._diagnostic_payload(
            reload_result,
            "validation_decision",
        )
        raw_base_choices = candidate.get("choices")
        base_choices: dict[str, Any] = (
            {str(key): value for key, value in raw_base_choices.items()}
            if isinstance(raw_base_choices, dict)
            else {}
        )
        try:
            review_state = self._review_state_from_parts(
                scan=scan,
                preview=preview,
                candidate=candidate,
                decision=decision,
            )
        except (ApplicationError, ControllerCompatibilityUnavailableError) as exc:
            QMessageBox.warning(
                self.panel,
                "Import review changed",
                str(exc),
            )
            return
        dialog_class = _data_interpretation_preview_dialog_class()
        dialog = dialog_class(
            self.panel,
            scan_result=scan,
            preview=preview,
            validation_decision=decision,
            choices=base_choices,
        )
        if not dialog.exec():
            return

        raw_dialog_result = dialog.get_result()
        dialog_result = (
            dict(raw_dialog_result) if isinstance(raw_dialog_result, dict) else {}
        )
        raw_dialog_choices = dialog_result.get("choices")
        dialog_choices: dict[str, Any] = (
            {str(key): value for key, value in raw_dialog_choices.items()}
            if isinstance(raw_dialog_choices, dict)
            else {}
        )
        dialog_choices = self._merge_interpretation_choices(
            base_choices,
            dialog_choices,
        )
        if (
            str(decision.get("decision")) == "blocked"
            and dialog_choices == base_choices
        ):
            QMessageBox.critical(
                self.panel,
                "Interpretation blocked",
                self._decision_reason(decision),
            )
            return
        if dialog_choices != base_choices:

            def _handle_preview_result(result) -> InteractionOutcome | None:
                resource_outcome = self._preview_resource_preflight_outcome(
                    result,
                    retry=lambda token: _dispatch_preview(
                        resource_preflight_confirmed=True,
                        resource_preflight_token=token,
                    ),
                )
                if resource_outcome is not None:
                    return resource_outcome
                self._continue_reloaded_recipe_preview(
                    result,
                    scan=scan,
                    dialog_result=dialog_result,
                )
                return None

            def _dispatch_preview(
                *,
                resource_preflight_confirmed: bool = False,
                resource_preflight_token: str | None = None,
            ) -> InteractionOutcome | None:
                return self._execute_interpretation_command_async(
                    PreviewInterpretationCommand(
                        scan_id=self._optional_payload_id(scan, "scan_id"),
                        choices=dialog_choices,
                        resource_preflight_confirmed=resource_preflight_confirmed,
                        resource_preflight_token=resource_preflight_token,
                    ),
                    on_result=_handle_preview_result,
                    error_title="Interpretation preview failed",
                    expected_publication_generation=(
                        review_state.publication_generation
                    ),
                    unexpected_error_context=(
                        UnexpectedErrorContext.DATA_INTERPRETATION_PREVIEW
                    ),
                )

            started = _dispatch_preview()
            if not started:
                QMessageBox.critical(
                    self.panel,
                    "Interpretation preview unavailable",
                    "Data Interpretation command service is unavailable.",
                )
            return

        self._apply_interpretation_async(review_state, dialog_result)

    def _continue_reloaded_recipe_preview(
        self,
        preview_result,
        *,
        scan: dict[str, Any],
        dialog_result: dict[str, Any],
    ) -> None:
        """Validate a re-previewed recipe candidate without blocking the GUI."""
        if self._result_failed(preview_result, "Interpretation preview failed"):
            return
        preview = self._diagnostic_payload(preview_result, "preview")
        candidate = self._diagnostic_payload(preview_result, "candidate")
        candidate_id = self._optional_payload_id(candidate, "candidate_id")
        try:
            preview_state = self._review_state_from_parts(
                scan=scan,
                preview=preview,
                candidate=candidate,
                decision={},
            )
        except (ApplicationError, ControllerCompatibilityUnavailableError) as exc:
            QMessageBox.warning(
                self.panel,
                "Import review changed",
                str(exc),
            )
            return
        started = self._execute_interpretation_command_async(
            ValidateInterpretationCommand(candidate_id=candidate_id),
            on_result=lambda result: self._continue_reloaded_recipe_validation(
                result,
                scan=scan,
                preview=preview,
                candidate=candidate,
                candidate_id=candidate_id,
                dialog_result=dialog_result,
            ),
            error_title="Interpretation validation failed",
            expected_publication_generation=(preview_state.publication_generation),
            unexpected_error_context=(
                UnexpectedErrorContext.DATA_INTERPRETATION_VALIDATION
            ),
        )
        if not started:
            QMessageBox.critical(
                self.panel,
                "Interpretation validation unavailable",
                "Data Interpretation command service is unavailable.",
            )

    def _continue_reloaded_recipe_validation(
        self,
        validation_result,
        *,
        scan: dict[str, Any],
        preview: dict[str, Any],
        candidate: dict[str, Any],
        candidate_id: str | None,
        dialog_result: dict[str, Any],
    ) -> None:
        """Apply a validated reloaded recipe through the shared async path."""
        if self._result_failed(
            validation_result,
            "Interpretation validation failed",
        ):
            return
        decision = self._diagnostic_payload(
            validation_result,
            "validation_decision",
        )
        if str(decision.get("decision")) == "blocked":
            QMessageBox.critical(
                self.panel,
                "Interpretation blocked",
                self._decision_reason(decision),
            )
            return
        try:
            review_state = self._review_state_from_parts(
                scan=scan,
                preview=preview,
                candidate=candidate,
                decision=decision,
            )
        except (ApplicationError, ControllerCompatibilityUnavailableError) as exc:
            QMessageBox.warning(
                self.panel,
                "Import review changed",
                str(exc),
            )
            return
        self._apply_interpretation_async(review_state, dialog_result)

    def _can_start_interpretation(
        self,
        command_name: CommandName = CommandName.SCAN_SOURCE,
        *,
        blocked_title: str = "Interpretation Blocked",
        fallback_reason: str = "Data interpretation is not available right now.",
    ) -> bool:
        """Return whether the UI can start a Data Interpretation source flow."""
        capability = get_command_capability(self.panel, command_name)
        if capability is not None and not capability.enabled:
            QMessageBox.warning(
                self.panel,
                blocked_title,
                blocked_reason(
                    capability,
                    fallback_reason,
                ),
            )
            return False

        controller = self.controller
        if controller is None:
            QMessageBox.critical(
                self.panel,
                "Import failed",
                "Dataset controller unavailable.",
            )
            return False

        if capability is None:
            return not self._compatibility_locked_preflight_blocked(
                controller,
                blocked_title=blocked_title,
                locked_message=(
                    "Dataset is locked. Please clear or reset before importing."
                ),
            )
        return True

    def _run_data_interpretation_import(
        self,
        filepaths: list[str],
        *,
        source_hint: str = "auto",
    ) -> InteractionOutcome | None:
        """Run the Data Interpretation command sequence for selected files."""
        source_path, choices = self._interpretation_source_and_choices(filepaths)
        return self._start_interpretation_review_async(
            source_path,
            source_hint,
            choices,
            [],
        )

    def _continue_data_interpretation_import(
        self,
        *,
        source_path: str,
        source_hint: str,
        choices: dict[str, Any],
        label_sources: list[str],
        review_state: _InterpretationReviewState,
        initial_step: str = "",
    ) -> InteractionOutcome:
        dialog_kwargs: dict[str, Any] = {
            "scan_result": review_state.scan,
            "preview": review_state.preview,
            "validation_decision": review_state.decision,
            "choices": dict(choices),
        }
        if initial_step:
            dialog_kwargs["initial_step"] = initial_step
        dialog_class = _data_interpretation_preview_dialog_class()
        dialog = dialog_class(self.panel, **dialog_kwargs)
        if not dialog.exec():
            return InteractionOutcome.cancelled(
                "Data interpretation review was cancelled."
            )

        raw_dialog_result = dialog.get_result()
        dialog_result = (
            dict(raw_dialog_result) if isinstance(raw_dialog_result, dict) else {}
        )
        raw_dialog_choices = dialog_result.get("choices")
        dialog_choices: dict[str, Any] = (
            {str(key): value for key, value in raw_dialog_choices.items()}
            if isinstance(raw_dialog_choices, dict)
            else {}
        )
        updated_choices = self._merge_interpretation_choices(
            choices,
            dialog_choices,
        )
        next_label_sources = self._dialog_label_sources(
            dialog_result,
            label_sources,
        )
        if next_label_sources != label_sources:
            updated_choices = self._choices_after_label_source_change(updated_choices)
            return self._start_interpretation_review_async(
                source_path,
                source_hint,
                updated_choices,
                next_label_sources,
                initial_step=str(dialog_result.get("resume_step") or ""),
            ) or InteractionOutcome.blocked(
                "Data interpretation review could not be started."
            )

        if (
            str(review_state.decision.get("decision")) == "blocked"
            and updated_choices == choices
        ):
            QMessageBox.critical(
                self.panel,
                "Interpretation blocked",
                self._decision_reason(review_state.decision),
            )
            return InteractionOutcome.blocked(
                self._decision_reason(review_state.decision)
            )

        if updated_choices != choices:
            resume_step = str(dialog_result.get("resume_step") or "").strip()
            if resume_step == "Match Labels":
                return self._start_interpretation_review_async(
                    source_path,
                    source_hint,
                    updated_choices,
                    label_sources,
                    initial_step=resume_step,
                ) or InteractionOutcome.blocked(
                    "Data interpretation preview could not be refreshed."
                )
            return self._review_interpretation_for_apply_async(
                source_path=source_path,
                source_hint=source_hint,
                choices=updated_choices,
                label_sources=label_sources,
                dialog_result=dialog_result,
            ) or InteractionOutcome.blocked(
                "Data interpretation review could not be refreshed."
            )
        return self._apply_interpretation_async(review_state, dialog_result)

    def _execute_interpretation_command_async(
        self,
        command,
        *,
        on_result: Callable[[Any], InteractionOutcome | None],
        error_title: str,
        refresh: bool = False,
        expected_publication_generation: int | None = None,
        blocked_title: str = "Interpretation Blocked",
        unexpected_error_context: UnexpectedErrorContext = (
            UnexpectedErrorContext.DATA_INTERPRETATION_REVIEW
        ),
    ) -> InteractionOutcome | None:
        """Dispatch one wizard command and continue from its Qt result callback."""

        def _handle_error(error: tuple) -> None:
            present_unexpected_error(
                self.panel,
                unexpected_error_context,
                error_info=error,
                message_box=QMessageBox,
                title=error_title,
            )

        def _deliver_result(result) -> InteractionOutcome | None:
            return on_result(result)

        if execute_application_command_async(
            self.panel,
            command,
            on_result=_deliver_result,
            on_error=_handle_error,
            refresh=refresh,
            busy_target=self.panel,
            expected_publication_generation=expected_publication_generation,
        ):
            return InteractionOutcome.accepted(
                "Data interpretation command was scheduled."
            )
        if has_real_application_context(self.panel):
            QMessageBox.warning(
                self.panel,
                blocked_title,
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
        if expected_publication_generation is None:
            result = execute_application_command(
                self.panel,
                command,
            )
        else:
            result = execute_application_command(
                self.panel,
                command,
                expected_publication_generation=expected_publication_generation,
            )
        if result is None:
            return None
        callback_outcome = on_result(result)
        if callback_outcome is not None:
            return callback_outcome
        if result.failed:
            return self._interaction_failure_outcome(result, result.message)
        return InteractionOutcome.completed(result.message)

    def _start_interpretation_review_async(
        self,
        source_path: str,
        source_hint: str,
        choices: dict[str, Any],
        label_sources: list[str],
        *,
        initial_step: str = "",
    ) -> InteractionOutcome | None:
        """Run scan/preview/validate off the Qt thread for real Study-backed UI."""

        def _handle_review_result(review_result) -> InteractionOutcome:
            resource_outcome = self._preview_resource_preflight_outcome(
                review_result,
                retry=lambda token: _dispatch(
                    resource_preflight_confirmed=True,
                    resource_preflight_token=token,
                ),
            )
            if resource_outcome is not None:
                return resource_outcome
            if self._result_failed(
                review_result,
                "Interpretation review failed",
            ):
                return self._interaction_failure_outcome(
                    review_result,
                    review_result.message,
                )
            try:
                review_state = self._review_state_from_review_result(review_result)
            except (
                ApplicationError,
                ControllerCompatibilityUnavailableError,
            ) as exc:
                QMessageBox.warning(
                    self.panel,
                    "Import review changed",
                    str(exc),
                )
                return InteractionOutcome.blocked(str(exc))
            return self._continue_data_interpretation_import(
                source_path=source_path,
                source_hint=source_hint,
                choices=dict(choices),
                label_sources=list(label_sources),
                review_state=review_state,
                initial_step=initial_step,
            )

        def _dispatch(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome | None:
            return self._execute_interpretation_command_async(
                ReviewInterpretationCommand(
                    source_path=source_path,
                    source_hint=source_hint,
                    label_sources=label_sources,
                    choices=choices,
                    resource_preflight_confirmed=resource_preflight_confirmed,
                    resource_preflight_token=resource_preflight_token,
                ),
                on_result=_handle_review_result,
                error_title="Interpretation failed",
                refresh=False,
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_REVIEW
                ),
            )

        return _dispatch()

    def _review_interpretation_for_apply_async(
        self,
        *,
        source_path: str,
        source_hint: str,
        choices: dict[str, Any],
        label_sources: list[str],
        dialog_result: dict[str, Any],
    ) -> InteractionOutcome | None:
        """Refresh edited choices, then apply the resulting candidate."""

        def _handle_review_result(review_result) -> InteractionOutcome:
            resource_outcome = self._preview_resource_preflight_outcome(
                review_result,
                retry=lambda token: _dispatch(
                    resource_preflight_confirmed=True,
                    resource_preflight_token=token,
                ),
            )
            if resource_outcome is not None:
                return resource_outcome
            if self._result_failed(review_result, "Interpretation review failed"):
                return self._interaction_failure_outcome(
                    review_result,
                    review_result.message,
                )
            try:
                review_state = self._review_state_from_review_result(review_result)
            except (
                ApplicationError,
                ControllerCompatibilityUnavailableError,
            ) as exc:
                QMessageBox.warning(
                    self.panel,
                    "Import review changed",
                    str(exc),
                )
                return InteractionOutcome.blocked(str(exc))
            if str(review_state.decision.get("decision")) == "blocked":
                QMessageBox.critical(
                    self.panel,
                    "Interpretation blocked",
                    self._decision_reason(review_state.decision),
                )
                return InteractionOutcome.blocked(
                    self._decision_reason(review_state.decision)
                )
            return self._apply_interpretation_async(review_state, dialog_result)

        def _dispatch(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome | None:
            return self._execute_interpretation_command_async(
                ReviewInterpretationCommand(
                    source_path=source_path,
                    source_hint=source_hint,
                    label_sources=label_sources,
                    choices=choices,
                    resource_preflight_confirmed=resource_preflight_confirmed,
                    resource_preflight_token=resource_preflight_token,
                ),
                on_result=_handle_review_result,
                error_title="Interpretation review failed",
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_REVIEW
                ),
            )

        return _dispatch()

    def _apply_interpretation_async(
        self,
        review_state: _InterpretationReviewState,
        dialog_result: dict[str, Any],
    ) -> InteractionOutcome:
        """Apply one reviewed candidate and continue to optional recipe saving."""
        candidate_id = (
            self._optional_payload_id(review_state.decision, "candidate_id")
            or review_state.candidate_id
        )

        def _handle_apply_result(apply_result) -> InteractionOutcome:
            resource_preflight = self._resource_preflight_view(apply_result)
            if apply_result.failed and resource_preflight:
                risk_level = resource_preflight.risk_level
                error_type = getattr(
                    getattr(apply_result, "error_type", None),
                    "value",
                    getattr(apply_result, "error_type", None),
                )
                if (
                    error_type == ErrorType.CONFIRMATION_REQUIRED.value
                    and risk_level in {"warning", "unknown"}
                ):
                    challenge = resource_preflight.challenge
                    if challenge is None:
                        message = (
                            "The resource check could not be confirmed safely. "
                            "Retry the import to run a fresh check."
                        )
                        QMessageBox.critical(
                            self.panel,
                            "Dataset Resource Check",
                            message,
                        )
                        return InteractionOutcome.blocked(message)
                    reply = QMessageBox.question(
                        self.panel,
                        "Dataset Resource Check",
                        (resource_preflight.message or apply_result.message)
                        + "\n\nContinue importing this dataset?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return InteractionOutcome.cancelled(
                            "Dataset import was cancelled during the resource check."
                        )

                    continuation = reserve_interaction_continuation()

                    def _resume_confirmed_apply() -> None:
                        if qt_object_deleted(self.panel):
                            if continuation is not None:
                                continuation.fail(
                                    "The dataset surface closed before the confirmed "
                                    "import retry could start."
                                )
                            return

                        def _start_confirmed_apply() -> InteractionOutcome:
                            return _dispatch_apply(
                                resource_preflight_confirmed=True,
                                resource_preflight_token=challenge.challenge_id,
                            )

                        if continuation is not None:
                            continuation.start(_start_confirmed_apply)
                        else:
                            _start_confirmed_apply()

                    try:
                        QTimer.singleShot(0, _resume_confirmed_apply)
                    except Exception:
                        logger.exception("Could not schedule confirmed dataset import")
                        message = (
                            "The confirmed dataset import retry could not be started."
                        )
                        if continuation is not None:
                            continuation.fail(message)
                        return InteractionOutcome.failed(message)
                    return InteractionOutcome.accepted(
                        "Confirmed dataset import was scheduled."
                    )
                if risk_level == "blocking":
                    QMessageBox.critical(
                        self.panel,
                        "Dataset Resource Check",
                        resource_preflight.message or apply_result.message,
                    )
                    return InteractionOutcome.blocked(apply_result.message)
            if self._result_failed(apply_result, "Interpretation apply failed"):
                return self._interaction_failure_outcome(
                    apply_result,
                    apply_result.message,
                )

            def _finish(recipe_message: str = "") -> None:
                self._show_status(
                    " ".join(
                        part for part in [apply_result.message, recipe_message] if part
                    ),
                )

            if bool(dialog_result.get("save_recipe", False)):
                if not self._save_interpretation_recipe(on_complete=_finish):
                    _finish()
                return InteractionOutcome.completed(apply_result.message)
            _finish()
            return InteractionOutcome.completed(apply_result.message)

        def _dispatch_apply(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome:
            apply_command = ApplyInterpretationCommand(
                candidate_id=candidate_id,
                confirmed=dialog_result.get("confirmed") is True,
                resource_preflight_confirmed=resource_preflight_confirmed,
                resource_preflight_token=resource_preflight_token,
            )
            return self._execute_interpretation_command_async(
                apply_command,
                on_result=_handle_apply_result,
                error_title="Interpretation apply failed",
                refresh=True,
                expected_publication_generation=(review_state.publication_generation),
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_APPLY
                ),
            ) or InteractionOutcome.blocked(
                "Data interpretation apply could not be started."
            )

        return _dispatch_apply()

    @staticmethod
    def _resource_preflight_view(result: Any) -> ResourcePreflightView | None:
        """Read resource diagnostics through the shared typed contract."""
        diagnostics = getattr(result, "diagnostics", {})
        try:
            return ResourcePreflightView.from_diagnostics(diagnostics)
        except ResourcePreflightContractError:
            return None

    def _preview_resource_preflight_outcome(
        self,
        result: Any,
        *,
        retry: Callable[[str], Any],
    ) -> InteractionOutcome | None:
        """Handle preview RAM warnings before label payloads are materialized."""
        if not getattr(result, "failed", False):
            return None
        preflight = self._resource_preflight_view(result)
        if not preflight:
            return None
        risk_level = preflight.risk_level
        if risk_level == "blocking":
            message = preflight.message or result.message
            QMessageBox.critical(self.panel, "Dataset Resource Check", message)
            return InteractionOutcome.blocked(message)
        error_type = getattr(
            getattr(result, "error_type", None),
            "value",
            getattr(result, "error_type", None),
        )
        if error_type != ErrorType.CONFIRMATION_REQUIRED.value or risk_level not in {
            "warning",
            "unknown",
        }:
            return None
        challenge = preflight.challenge
        if challenge is None:
            message = (
                "The resource check could not be confirmed safely. "
                "Retry the import to run a fresh check."
            )
            QMessageBox.critical(self.panel, "Dataset Resource Check", message)
            return InteractionOutcome.blocked(message)
        result_command = str(getattr(result, "command_name", "") or "").strip().lower()
        if challenge.command_name.strip().lower() != result_command:
            message = (
                "The resource confirmation did not match this import action. "
                "Retry the import to run a fresh check."
            )
            QMessageBox.critical(self.panel, "Dataset Resource Check", message)
            return InteractionOutcome.blocked(message)
        reply = QMessageBox.question(
            self.panel,
            "Dataset Resource Check",
            (preflight.message or result.message)
            + "\n\nContinue building the import preview?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return InteractionOutcome.cancelled(
                "Dataset import preview was cancelled during the resource check."
            )
        retry_outcome = retry(challenge.challenge_id)
        if isinstance(
            retry_outcome, InteractionOutcome
        ) and retry_outcome.status.value in {"blocked", "failed"}:
            return retry_outcome
        return InteractionOutcome.accepted("Confirmed dataset preview was scheduled.")

    def _review_state_from_review_result(
        self,
        review_result,
    ) -> _InterpretationReviewState:
        candidate = self._diagnostic_payload(review_result, "candidate")
        return self._review_state_from_parts(
            scan=self._diagnostic_payload(review_result, "scan_result"),
            preview=self._diagnostic_payload(review_result, "preview"),
            candidate=candidate,
            decision=self._diagnostic_payload(review_result, "validation_decision"),
        )

    def _review_state_from_parts(
        self,
        *,
        scan: dict[str, Any],
        preview: dict[str, Any],
        candidate: dict[str, Any],
        decision: dict[str, Any],
    ) -> _InterpretationReviewState:
        scan_id = self._optional_payload_id(scan, "scan_id")
        candidate_id = self._optional_payload_id(candidate, "candidate_id")
        if scan_id is None or candidate_id is None:
            raise PreconditionError(
                "The Data Import review identity could not be verified. Refresh the "
                "review and try again.",
                diagnostics={"stale_interpretation_review": True},
            )
        publication = get_application_view_publication(self.panel)
        if publication is None:
            raise ControllerCompatibilityUnavailableError(
                "The Data Import review runtime is unavailable."
            )
        identity = InterpretationReviewIdentity(
            publication_generation=publication.generation,
            scan_id=scan_id,
            candidate_id=candidate_id,
        )
        self._require_interpretation_identity(publication, identity)
        return _InterpretationReviewState(
            scan=scan,
            preview=preview,
            candidate=candidate,
            candidate_id=candidate_id,
            decision=decision,
            publication_generation=identity.publication_generation,
        )

    def _result_failed(self, result, title: str) -> bool:
        if not result.failed:
            return False
        if is_stale_publication_result(result):
            QMessageBox.warning(
                self.panel,
                "Review Data Import Again",
                result.message,
            )
        else:
            QMessageBox.critical(self.panel, title, result.message)
        return True

    @staticmethod
    def _interaction_failure_outcome(result, message: str) -> InteractionOutcome:
        if bool(getattr(result, "recoverable", False)):
            return InteractionOutcome.blocked(message)
        return InteractionOutcome.failed(message)

    @staticmethod
    def _dialog_label_sources(
        dialog_result: dict[str, Any],
        current_sources: list[str],
    ) -> list[str]:
        if not bool(dialog_result.get("label_sources_changed")):
            return list(current_sources)
        raw_sources = dialog_result.get("label_sources")
        if not isinstance(raw_sources, list):
            return list(current_sources)
        result: list[str] = []
        for source in raw_sources:
            text = str(source).strip()
            if text and text not in result:
                result.append(text)
        return result

    def _save_interpretation_recipe(
        self,
        *,
        on_complete: Callable[[str], None] | None = None,
        review_context: CommandReviewContext | None = None,
        review_context_resolved: bool = False,
    ) -> bool:
        """Persist the current recipe and report completion asynchronously."""
        complete = on_complete or (lambda _message: None)
        if not review_context_resolved:
            review_context = get_command_review_context(
                self.panel,
                CommandName.SAVE_INTERPRETATION_RECIPE,
            )
        if review_context is None and has_real_application_context(self.panel):
            QMessageBox.warning(
                self.panel,
                "Recipe Save Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            complete("")
            return True
        save_capability = (
            review_context.capability if review_context is not None else None
        )
        recipe_block_reason = (
            blocked_reason(
                save_capability,
                "Apply an interpretation before saving a recipe.",
            )
            if save_capability is not None and not save_capability.enabled
            else self._recipe_save_block_reason()
            if review_context is None
            else None
        )
        if recipe_block_reason is not None:
            QMessageBox.warning(
                self.panel,
                "Recipe Save Blocked",
                recipe_block_reason,
            )
            complete("")
            return True

        recipe_path, _ = QFileDialog.getSaveFileName(
            self.panel,
            "Save Interpretation Recipe",
            "import_recipe.json",
            "JSON (*.json)",
        )

        def _handle_result(result) -> None:
            if result.failed:
                title = (
                    "Review Recipe Save Again"
                    if is_stale_publication_result(result)
                    else "Recipe not saved"
                )
                QMessageBox.warning(self.panel, title, result.message)
                complete("")
                return
            complete("Recipe saved." if recipe_path else "Recipe kept in this session.")

        outcome = self._execute_interpretation_command_async(
            SaveInterpretationRecipeCommand(recipe_path=recipe_path or None),
            on_result=_handle_result,
            error_title="Recipe save failed",
            expected_publication_generation=(
                review_context.publication_generation
                if review_context is not None
                else None
            ),
            unexpected_error_context=UnexpectedErrorContext.DATA_IMPORT_RECIPE_SAVE,
        )
        return outcome is not None

    def _recipe_save_block_reason(self) -> str | None:
        save_capability = get_command_capability(
            self.panel,
            CommandName.SAVE_INTERPRETATION_RECIPE,
        )
        if save_capability is not None and not save_capability.enabled:
            return blocked_reason(
                save_capability,
                "Apply an interpretation before saving a recipe.",
            )
        return None

    @staticmethod
    def _interpretation_source_and_choices(
        filepaths: list[str],
    ) -> tuple[str, dict[str, Any]]:
        if len(filepaths) == 1:
            return filepaths[0], {}

        parents = [str(Path(path).expanduser().parent) for path in filepaths]
        unique_parents = sorted(set(parents))
        source_path = unique_parents[0] if len(unique_parents) == 1 else filepaths[0]
        return source_path, {"selected_eeg_files": list(filepaths)}

    @staticmethod
    def _merge_interpretation_choices(
        base: dict[str, Any],
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace mutually exclusive label choices while merging metadata edits."""
        merged = dict(base)
        label_choice_keys = (
            "skip_labels",
            "label_carrier",
            "class_map",
            "event_roles",
            "excluded_label_carriers",
            "label_carrier_choices",
            "label_carrier_remap",
        )
        if not any(key in updates for key in label_choice_keys):
            for key, value in updates.items():
                if key == "metadata_overrides" and isinstance(value, dict):
                    previous = merged.get(key)
                    merged[key] = {
                        **(previous if isinstance(previous, dict) else {}),
                        **value,
                    }
                else:
                    merged[key] = value
            return merged

        for key in label_choice_keys:
            merged.pop(key, None)

        skip_labels = bool(updates.get("skip_labels"))
        label_carrier = str(updates.get("label_carrier") or "").strip()
        if skip_labels or label_carrier == "embedded_events":
            for key in (
                "required_label_carriers",
                "label_carrier_choices",
                "label_carrier_remap",
                "excluded_label_carriers",
            ):
                merged.pop(key, None)
        if skip_labels or label_carrier != "embedded_events":
            for key in (
                "internal_event_selection",
                "run_event_mappings",
                "class_map",
                "event_roles",
            ):
                merged.pop(key, None)

        for key, value in updates.items():
            if key == "metadata_overrides" and isinstance(value, dict):
                previous = merged.get(key)
                merged[key] = {
                    **(previous if isinstance(previous, dict) else {}),
                    **value,
                }
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _choices_after_label_source_change(
        choices: dict[str, Any],
    ) -> dict[str, Any]:
        """Invalidate decisions derived from the previous label-carrier set."""
        result = dict(choices)
        for key in (
            "skip_labels",
            "label_carrier",
            "label_sources",
            "required_label_carriers",
            "label_carrier_choices",
            "label_carrier_remap",
            "internal_event_selection",
            "run_event_mappings",
            "class_map",
            "event_roles",
        ):
            result.pop(key, None)
        return result

    @staticmethod
    def _diagnostic_payload(result, key: str) -> dict:
        value = result.diagnostics.get(key, {})
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _optional_payload_id(payload: dict, key: str) -> str | None:
        value = payload.get(key)
        return str(value) if value else None

    @staticmethod
    def _decision_reason(decision: dict) -> str:
        reasons = decision.get("blocked_reasons") or decision.get("reasons") or []
        if reasons:
            return "\n".join(str(reason) for reason in reasons)
        return "This data interpretation cannot be applied."

    def on_import_finished(self, success_count, errors):
        """Handle the import-finished callback from the controller.

        Shows warnings for failures. Successful compatibility imports already emit
        ``data_changed``, and that observer event owns the panel refresh.

        Args:
            success_count: Number of files successfully imported.
            errors: List of error message strings for failed imports.

        """
        if errors:
            error_msg = "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n...and {len(errors) - 10} more errors."
            QMessageBox.warning(
                self.panel,
                "Import Warnings",
                f"Failed files:\n{error_msg}",
            )

    def open_smart_parser(self):
        """Open the smart-parser dialog to auto-extract metadata from filenames.

        Blocked if the dataset is locked or no data is loaded.
        """
        review_context = get_command_review_context(
            self.panel,
            CommandName.APPLY_SMART_PARSE,
        )
        smart_parse_capability = (
            review_context.capability
            if review_context is not None
            else get_command_capability(
                self.panel,
                CommandName.APPLY_SMART_PARSE,
            )
        )
        if smart_parse_capability is not None and not smart_parse_capability.enabled:
            QMessageBox.warning(
                self.panel,
                "Smart Parse Blocked",
                blocked_reason(
                    smart_parse_capability,
                    "Load raw data before applying smart parse.",
                ),
            )
            return

        controller = self.controller
        if controller is None:
            QMessageBox.critical(
                self.panel,
                "Error",
                "Dataset controller unavailable.",
            )
            return

        if smart_parse_capability is None:
            available, is_locked = self._compatibility_controller_value(
                "Smart Parse Blocked",
                lambda: bool(controller.is_locked()),
            )
            if not available:
                return
            if is_locked:
                QMessageBox.warning(self.panel, "Blocked", "Dataset is locked.")
                return

            available, has_data = self._compatibility_controller_value(
                "Smart Parse Blocked",
                lambda: bool(controller.has_data()),
            )
            if not available:
                return
            if not has_data:
                QMessageBox.warning(self.panel, "Warning", "No data loaded.")
                return

        reviewed_generation = (
            review_context.publication_generation
            if review_context is not None
            else None
        )
        filepaths = self._smart_parse_filenames(
            expected_publication_generation=reviewed_generation,
        )
        if filepaths is None:
            return
        if not filepaths:
            QMessageBox.warning(self.panel, "Warning", "No data loaded.")
            return
        dialog_class = _smart_parser_dialog_class()
        dialog = dialog_class(filepaths, self.panel)
        if dialog.exec():
            results = dialog.get_result()
            if reviewed_generation is None:
                result = execute_application_command(
                    self.panel,
                    ApplySmartParseCommand(results=results),
                )
            else:
                result = execute_application_command(
                    self.panel,
                    ApplySmartParseCommand(results=results),
                    expected_publication_generation=reviewed_generation,
                )
            if result is None:
                QMessageBox.warning(
                    self.panel,
                    "Smart Parse Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                if is_stale_publication_result(result):
                    QMessageBox.warning(
                        self.panel,
                        "Review Smart Parse Again",
                        result.message,
                    )
                else:
                    QMessageBox.critical(self.panel, "Error", result.message)
                return
            else:
                count = int(result.diagnostics.get("success_count", 0))
            self._update_panel_after_command_result(result)

            self._show_status(f"Updated {count} files")

    def _smart_parse_filenames(
        self,
        *,
        expected_publication_generation: int | None = None,
    ) -> list[str] | None:
        if expected_publication_generation is None:
            result = execute_application_command(
                self.panel,
                QueryStateCommand(query="state"),
                refresh=False,
            )
        else:
            result = execute_application_command(
                self.panel,
                QueryStateCommand(query="state"),
                refresh=False,
                expected_publication_generation=expected_publication_generation,
            )
        if result is None:
            return self._compatibility_filenames_for_smart_parse()
        if result.failed:
            title = (
                "Review Smart Parse Again"
                if is_stale_publication_result(result)
                else "Smart Parse Blocked"
                if result.recoverable
                else "Smart Parse Failed"
            )
            QMessageBox.warning(
                self.panel,
                title,
                result.message,
            )
            return None
        diagnostics = getattr(result, "diagnostics", {}) or {}
        state = diagnostics.get("state")
        raw = state.get("raw") if isinstance(state, dict) else {}
        files = raw.get("files") if isinstance(raw, dict) else None
        if not isinstance(files, list):
            return []
        return [str(file) for file in files if str(file)]

    def import_label(self):
        """Import external label files and apply them to loaded EEG data.

        Supports single-file, batch, and timestamp-based label mapping.
        Prompts the user for event filtering when applicable.
        """
        review_context = get_command_review_context(
            self.panel,
            CommandName.IMPORT_LABELS,
        )
        if review_context is None and has_real_application_context(self.panel):
            QMessageBox.warning(
                self.panel,
                "Label Import Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return
        label_capability = (
            review_context.capability
            if review_context is not None
            else get_command_capability(
                self.panel,
                CommandName.IMPORT_LABELS,
            )
        )
        if label_capability is not None and not label_capability.enabled:
            QMessageBox.warning(
                self.panel,
                "Label Import Blocked",
                blocked_reason(
                    label_capability,
                    "Label import is not available right now.",
                ),
            )
            return

        target_files = self._get_target_files_for_import()
        if not target_files:
            return

        dialog_class = _import_label_dialog_class()
        if review_context is None:
            dialog = dialog_class(
                self.panel,
                target_files=target_files,
            )
        else:
            dialog = dialog_class(
                self.panel,
                target_files=target_files,
                expected_publication_generation=review_context.publication_generation,
            )
        if not dialog.exec():
            return
        selection, mapping = dialog.get_result()
        if selection is None or mapping is None:
            return

        preview_mode = str(selection.mode or "").lower()
        if preview_mode not in {"sequence", "timestamp"}:
            QMessageBox.critical(
                self.panel,
                "Label Import Failed",
                "Timestamp and sequence label files cannot be mixed in one import.",
            )
            return

        try:
            is_timestamp = preview_mode == "timestamp"
            target_count = selection.target_count

            selected_event_names = None
            if not is_timestamp:
                selected_event_names = self._filter_events_for_import(
                    target_files,
                    target_count,
                )
                if selected_event_names is False:
                    return

            label_paths = list(selection.label_paths)
            if len(label_paths) > 1:  # Batch
                data_paths = [d.get_filepath() for d in target_files]
                dialog_class = _label_mapping_dialog_class()
                map_dlg = dialog_class(
                    self.panel,
                    data_paths,
                    label_paths,
                )
                if not map_dlg.exec():
                    return
                file_map = map_dlg.get_mapping()
                plan = self._build_label_import_plan(
                    selection,
                    mapping,
                    mode="batch",
                    file_mapping=file_map,
                    selected_event_names=selected_event_names,
                )
            elif is_timestamp:  # Compatibility timestamp format
                label_fname = label_paths[0]
                file_map = {d.get_filepath(): label_fname for d in target_files}
                plan = self._build_label_import_plan(
                    selection,
                    mapping,
                    mode="timestamp",
                    file_mapping=file_map,
                    selected_event_names=selected_event_names,
                )
            else:  # Single same-length label file
                label_fname = label_paths[0]
                file_map = {d.get_filepath(): label_fname for d in target_files}
                plan = self._build_label_import_plan(
                    selection,
                    mapping,
                    mode="sequence",
                    file_mapping=file_map,
                    selected_event_names=selected_event_names,
                )
            self._execute_label_import_async(
                plan,
                expected_publication_generation=(
                    review_context.publication_generation
                    if review_context is not None
                    else None
                ),
            )

        except Exception:
            present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.LABEL_IMPORT,
                message_box=QMessageBox,
            )

    def _execute_label_import_async(
        self,
        plan: LabelImportPlan,
        *,
        expected_publication_generation: int | None = None,
    ) -> None:
        """Apply one exact reviewed label plan away from the GUI thread."""

        def _handle_result(result) -> InteractionOutcome:
            if result.failed:
                if is_stale_publication_result(result):
                    QMessageBox.warning(
                        self.panel,
                        "Review Label Import Again",
                        result.message,
                    )
                else:
                    QMessageBox.critical(
                        self.panel,
                        "Label Import Failed",
                        result.message,
                    )
                return self._interaction_failure_outcome(result, result.message)

            count = int(result.diagnostics.get("success_count", 0))
            if count <= 0:
                message = (
                    "No labels were applied. Check whether the label count, event "
                    "selection, or file mapping matches the selected data."
                )
                QMessageBox.warning(self.panel, "No Labels Applied", message)
                return InteractionOutcome.blocked(message)

            self._update_panel_after_command_result(result)

            def _finish_label_import(recipe_message: str = "") -> None:
                self._show_status(
                    " ".join(
                        part
                        for part in [
                            f"Applied to {count} files.",
                            recipe_message,
                        ]
                        if part
                    ),
                )

            recipe_message = self._offer_label_recipe_save(
                result,
                on_complete=_finish_label_import,
            )
            if recipe_message is not None:
                _finish_label_import(recipe_message)
            return InteractionOutcome.completed(f"Applied labels to {count} files.")

        outcome = self._execute_interpretation_command_async(
            ImportLabelsCommand(plan=plan),
            on_result=_handle_result,
            error_title="Label import failed",
            refresh=True,
            expected_publication_generation=expected_publication_generation,
            blocked_title="Label Import Blocked",
            unexpected_error_context=UnexpectedErrorContext.LABEL_IMPORT,
        )
        if outcome is None:
            QMessageBox.warning(
                self.panel,
                "Label Import Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )

    def _offer_label_recipe_save(
        self,
        result,
        *,
        on_complete: Callable[[str], None] | None = None,
    ) -> str | None:
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if not bool(diagnostics.get("recipe_updated")):
            return ""
        review_context = get_command_review_context(
            self.panel,
            CommandName.SAVE_INTERPRETATION_RECIPE,
        )
        if review_context is None and has_real_application_context(self.panel):
            return "Interpretation recipe trace updated in this session."
        save_capability = (
            review_context.capability if review_context is not None else None
        )
        recipe_block_reason = (
            blocked_reason(
                save_capability,
                "Apply an interpretation before saving a recipe.",
            )
            if save_capability is not None and not save_capability.enabled
            else self._recipe_save_block_reason()
            if review_context is None
            else None
        )
        if recipe_block_reason is not None:
            return "Interpretation recipe trace updated in this session."
        reply = QMessageBox.question(
            self.panel,
            "Save Updated Recipe",
            "External labels were added to the current data interpretation "
            "recipe. Save the updated recipe now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            started = self._save_interpretation_recipe(
                on_complete=on_complete,
                review_context=review_context,
                review_context_resolved=True,
            )
            return None if started else "Interpretation recipe trace updated."
        return "Interpretation recipe trace updated."

    def _get_target_files_for_import(self):
        """Determine which data files should receive imported labels.

        If no rows are selected in the table, asks the user whether to
        apply labels to all files.

        Returns:
            list: A list of data objects for the targeted files,
                or an empty list if the operation is cancelled.

        """
        if self.panel.table.rowCount() <= 0:
            QMessageBox.warning(
                self.panel,
                "No Data Loaded",
                "Interpret a data source before adding labels.",
            )
            return []

        selected_rows = sorted(
            {index.row() for index in self.panel.table.selectedIndexes()},
        )
        if not selected_rows:
            reply = QMessageBox.question(
                self.panel,
                "Add Labels to Loaded Data",
                "No files selected. Add labels to all loaded files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                selected_rows = list(range(self.panel.table.rowCount()))
            else:
                return []

        table_targets = self._target_files_from_table_rows(selected_rows)
        if table_targets is not None:
            return table_targets

        return self._compatibility_target_files_from_controller(selected_rows)

    def _target_files_from_table_rows(self, selected_rows):
        target_files = []
        target_indices = []
        for row in selected_rows:
            item = self.panel.table.item(row, 0)
            if not isinstance(item, QTableWidgetItem):
                return None
            data = item.data(Qt.ItemDataRole.UserRole)
            if data is None:
                return None
            target_files.append(data)
            target_indices.append(row)
        self._last_target_file_indices = target_indices
        return target_files

    def _build_label_import_plan(
        self,
        selection,
        mapping,
        mode,
        file_mapping=None,
        selected_event_names=None,
    ):
        selected_names = (
            sorted(selected_event_names)
            if isinstance(selected_event_names, set)
            else selected_event_names
        )
        return LabelImportPlan(
            preview_id=str(selection.preview_id),
            target_indices=list(getattr(self, "_last_target_file_indices", [])),
            label_paths=[str(path) for path in selection.label_paths],
            label_configs={
                str(path): dict(config)
                for path, config in selection.label_configs.items()
            },
            mapping=mapping,
            file_mapping=dict(file_mapping or {}),
            mode=mode,
            selected_event_names=selected_names,
        )

    def _filter_events_for_import(self, target_files, target_count):
        """Show an event filter dialog for selecting which events to relabel.

        Args:
            target_files: List of data objects that contain raw events.
            target_count: Expected number of labels per event category.

        Returns:
            set | None | False: A set of selected event names, ``None`` if
                no filtering is needed, or ``False`` if the user cancelled.

        """
        raw_files = [d for d in target_files if d.is_raw() and d.has_event()]
        if not raw_files:
            return None

        unique = set()
        for d in raw_files:
            _, ev_ids = d.get_raw_event_list()
            unique.update(ev_ids.keys())

        if not unique:
            return None
        sorted_names = sorted(unique)

        # Suggestions?
        suggested = []
        if target_count and raw_files:
            suggested_names: set[str] = set()
            for raw_file in raw_files:
                s_ids = self._smart_filter_suggestions_for_import(
                    raw_file,
                    target_count,
                    target_files,
                )
                _, ev_ids = raw_file.get_raw_event_list()
                id_map = {v: k for k, v in ev_ids.items()}
                suggested_names.update(id_map[i] for i in s_ids if i in id_map)
            suggested = sorted(suggested_names)

        dialog_class = _event_filter_dialog_class()
        dlg = dialog_class(self.panel, sorted_names)
        if suggested:
            dlg.set_selection(suggested)

        if dlg.exec():
            return set(dlg.get_selected_ids())
        return False

    def _smart_filter_suggestions_for_import(
        self,
        raw_file,
        target_count: int,
        target_files,
    ) -> list[int]:
        """Return event-filter suggestions through service query when possible."""
        target_index = self._target_index_for_filter_suggestion(
            raw_file,
            target_files,
        )
        if target_index is not None:
            result = execute_application_command(
                self.panel,
                QueryStateCommand(
                    query="smart_filter_suggestions",
                    params={
                        "target_index": target_index,
                        "target_count": target_count,
                    },
                ),
                refresh=False,
            )
            if result is not None:
                if result.failed:
                    logger.warning(
                        "Smart filter suggestion query failed: %s",
                        result.message,
                    )
                    return []
                suggestions = result.diagnostics.get("suggestions", [])
                if isinstance(suggestions, list):
                    return [int(item) for item in suggestions]
                return []

        return self._compatibility_smart_filter_suggestions(raw_file, target_count)

    def _target_index_for_filter_suggestion(self, raw_file, target_files) -> int | None:
        try:
            target_position = target_files.index(raw_file)
        except ValueError:
            return None
        target_indices = getattr(self, "_last_target_file_indices", None)
        if isinstance(target_indices, list) and target_position < len(target_indices):
            try:
                return int(target_indices[target_position])
            except (TypeError, ValueError):
                return None
        return target_position

    def show_context_menu(self, pos):
        menu = QMenu(self.panel)
        rows = sorted({i.row() for i in self.panel.table.selectedIndexes()})
        if not rows:
            return
        selection = self._capture_table_selection(rows)
        if selection is None:
            self._reject_stale_table_action(
                "Review Dataset Selection Again",
                "change the selected files",
            )
            return

        a_subj = menu.addAction("Set Subject")
        a_sess = menu.addAction("Set Session")
        menu.addSeparator()
        a_rem = menu.addAction("Remove Files")

        action = menu.exec(self.panel.table.mapToGlobal(pos))
        if action == a_subj:
            self._batch_set(selection, "Subject")
        elif action == a_sess:
            self._batch_set(selection, "Session")
        elif action == a_rem:
            self._remove_files(selection)

    def _capture_table_selection(
        self,
        rows: list[int] | tuple[int, ...],
    ) -> DatasetTableSelection | None:
        capture = getattr(self.panel, "capture_table_selection", None)
        if callable(capture):
            selection = capture(list(rows))
            if isinstance(selection, DatasetTableSelection):
                return selection
        if has_real_application_context(self.panel):
            return None
        return DatasetTableSelection(
            publication_generation=None,
            rows=tuple(
                DatasetTableRowIdentity(canonical_filepath="", rendered_row=int(row))
                for row in rows
            ),
        )

    def _coerce_table_selection(
        self,
        rows_or_selection: DatasetTableSelection | list[int] | tuple[int, ...],
    ) -> DatasetTableSelection | None:
        if isinstance(rows_or_selection, DatasetTableSelection):
            return rows_or_selection
        return self._capture_table_selection(rows_or_selection)

    def _resolve_table_selection(
        self,
        selection: DatasetTableSelection,
        *,
        stale_title: str,
        action_description: str,
    ) -> list[int] | None:
        resolve = getattr(self.panel, "resolve_table_selection", None)
        if callable(resolve):
            rows = resolve(
                selection,
                stale_title=stale_title,
                action_description=action_description,
            )
            if isinstance(rows, list) and all(isinstance(row, int) for row in rows):
                return rows
        compatibility_selection = (
            selection.publication_generation is None
            and not has_real_application_context(self.panel)
        )
        if compatibility_selection:
            return [identity.rendered_row for identity in selection.rows]
        self._reject_stale_table_action(stale_title, action_description)
        return None

    def _reject_stale_table_action(
        self,
        title: str,
        action_description: str,
    ) -> None:
        QMessageBox.warning(
            self.panel,
            title,
            "The selected Dataset files changed or could not be verified. "
            f"Refresh Dataset, then {action_description} again.",
        )
        update_panel = getattr(self.panel, "update_panel", None)
        if callable(update_panel):
            update_panel()

    def _batch_set(
        self,
        rows_or_selection: DatasetTableSelection | list[int] | tuple[int, ...],
        attr,
    ):
        review_context = get_command_review_context(
            self.panel,
            CommandName.UPDATE_METADATA,
        )
        metadata_capability = (
            review_context.capability if review_context is not None else None
        )
        if metadata_capability is not None and not metadata_capability.enabled:
            QMessageBox.warning(
                self.panel,
                "Metadata Update Blocked",
                blocked_reason(
                    metadata_capability,
                    "Load raw data before updating metadata.",
                ),
            )
            return

        selection = self._coerce_table_selection(rows_or_selection)
        if selection is None:
            self._reject_stale_table_action(
                "Review Metadata Again",
                "edit metadata",
            )
            return

        text, ok = QInputDialog.getText(self.panel, f"Set {attr}", f"Enter {attr}:")
        if ok and text:
            rows = self._resolve_table_selection(
                selection,
                stale_title="Review Metadata Again",
                action_description="edit metadata",
            )
            if rows is None:
                return
            controller = self.controller
            if controller is None:
                QMessageBox.critical(
                    self.panel,
                    "Error",
                    "Dataset controller unavailable.",
                )
                return

            updates = []
            for row in rows:
                if attr == "Subject":
                    updates.append(MetadataUpdate(index=row, subject=text))
                elif attr == "Session":
                    updates.append(MetadataUpdate(index=row, session=text))
            result = execute_application_command(
                self.panel,
                UpdateMetadataCommand(updates=updates),
                expected_publication_generation=(
                    selection.publication_generation
                    if selection.publication_generation is not None
                    else review_context.publication_generation
                    if review_context is not None
                    else None
                ),
            )
            if result is None:
                QMessageBox.warning(
                    self.panel,
                    "Metadata Update Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                if is_stale_publication_result(result):
                    QMessageBox.warning(
                        self.panel,
                        "Review Metadata Again",
                        result.message,
                    )
                else:
                    QMessageBox.critical(self.panel, "Error", result.message)
                return
            self._update_panel_after_command_result(result)

    def _remove_files(
        self,
        rows_or_selection: DatasetTableSelection | list[int] | tuple[int, ...],
    ):
        review_context = get_command_review_context(
            self.panel,
            CommandName.REMOVE_FILES,
        )
        remove_capability = (
            review_context.capability if review_context is not None else None
        )
        if remove_capability is not None and not remove_capability.enabled:
            QMessageBox.warning(
                self.panel,
                "Remove Files Blocked",
                blocked_reason(
                    remove_capability,
                    "Load raw data before removing files.",
                ),
            )
            return

        selection = self._coerce_table_selection(rows_or_selection)
        if selection is None:
            self._reject_stale_table_action(
                "Review File Removal Again",
                "remove files",
            )
            return

        if (
            QMessageBox.question(
                self.panel,
                "Confirm",
                f"Remove {len(selection.rows)} files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            rows = self._resolve_table_selection(
                selection,
                stale_title="Review File Removal Again",
                action_description="remove files",
            )
            if rows is None:
                return
            result = execute_application_command(
                self.panel,
                RemoveFilesCommand(indices=list(rows)),
                expected_publication_generation=(
                    selection.publication_generation
                    if selection.publication_generation is not None
                    else review_context.publication_generation
                    if review_context is not None
                    else None
                ),
            )
            if result is None:
                QMessageBox.warning(
                    self.panel,
                    "Remove Files Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                if is_stale_publication_result(result):
                    QMessageBox.warning(
                        self.panel,
                        "Review File Removal Again",
                        result.message,
                    )
                else:
                    QMessageBox.critical(self.panel, "Error", result.message)
                return
            self._update_panel_after_command_result(result)
