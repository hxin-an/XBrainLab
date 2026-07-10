"""Action handler for dataset panel operations.

Provides logic for importing EEG data files, applying labels,
running smart parse, and managing event filtering.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
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
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ControllerCompatibilityUnavailableError,
    blocked_reason,
    execute_application_command,
    execute_application_command_async,
    get_command_capability,
    has_real_application_context,
    run_controller_compatibility_call,
)
from XBrainLab.ui.status import show_status_message

DataInterpretationPreviewDialog: Any | None = None
EventFilterDialog: Any | None = None
ImportLabelDialog: Any | None = None
LabelMappingDialog: Any | None = None
SmartParserDialog: Any | None = None


@dataclass(frozen=True)
class _InterpretationReviewState:
    scan: dict[str, Any]
    preview: dict[str, Any]
    candidate: dict[str, Any]
    candidate_id: str | None
    decision: dict[str, Any]


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

    def _confirm_import_resource_preflight(self, paths: list[str]) -> bool:
        if not paths:
            return True
        from XBrainLab.backend.application.resource_guard import (  # noqa: PLC0415
            RISK_BLOCKING,
            RISK_WARNING,
            ResourceChecker,
        )

        result = ResourceChecker.check_dataset_load_safe(paths)
        if result.risk_level == RISK_BLOCKING:
            QMessageBox.critical(
                self.panel,
                "Dataset Resource Check",
                result.message,
            )
            return False
        if result.risk_level == RISK_WARNING:
            reply = QMessageBox.question(
                self.panel,
                "Dataset Resource Check",
                result.message + "\n\nContinue importing this dataset?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes
        return True

    @staticmethod
    def _interpretation_apply_paths(
        candidate: dict[str, Any],
        preview: dict[str, Any],
        scan: dict[str, Any],
    ) -> list[str]:
        for payload, key in (
            (candidate, "selected_eeg_files"),
            (preview, "selected_eeg_files"),
            (scan, "eeg_files"),
        ):
            values = payload.get(key) if isinstance(payload, dict) else None
            if isinstance(values, list) and values:
                return [str(path) for path in values if str(path).strip()]
        return []

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

    def import_data(self):
        """Scan, preview, validate, and apply an EEG data interpretation."""
        scan_capability = get_command_capability(self.panel, CommandName.SCAN_SOURCE)
        if scan_capability is not None and not scan_capability.enabled:
            QMessageBox.warning(
                self.panel,
                "Interpretation Blocked",
                blocked_reason(
                    scan_capability,
                    "Data interpretation is not available right now.",
                ),
            )
            return

        controller = self.controller
        if controller is None:
            QMessageBox.critical(
                self.panel, "Import failed", "Dataset controller unavailable."
            )
            return

        if scan_capability is None and self._compatibility_locked_preflight_blocked(
            controller,
            blocked_title="Interpretation Blocked",
            locked_message="Dataset is locked. Please clear or reset before importing.",
            block_when_unavailable=False,
        ):
            return

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
        if filepaths:
            try:
                handled = self._run_data_interpretation_import(list(filepaths))
                if not handled:
                    if scan_capability is not None:
                        QMessageBox.critical(
                            self.panel,
                            "Interpretation unavailable",
                            "Data Interpretation command service is unavailable.",
                        )
                        return
                    if has_real_application_context(self.panel):
                        QMessageBox.warning(
                            self.panel,
                            "Interpretation Blocked",
                            CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                        )
                        return
                    if not self._confirm_import_resource_preflight(list(filepaths)):
                        return
                    result = execute_application_command(
                        self.panel,
                        LoadDataCommand(paths=list(filepaths)),
                    )
                    if result is not None and result.failed:
                        QMessageBox.critical(
                            self.panel,
                            "Import failed",
                            result.message,
                        )
                        return
                    if result is None:
                        QMessageBox.warning(
                            self.panel,
                            "Interpretation Blocked",
                            CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                        )
                        return
                    self._show_status(result.message)
                    return
            except Exception as e:
                QMessageBox.critical(self.panel, "Error", f"Import failed: {e}")

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
        except Exception as e:
            QMessageBox.critical(self.panel, "Error", f"Import failed: {e}")

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
        except Exception as e:
            QMessageBox.critical(self.panel, "Error", f"Import failed: {e}")

    def reload_interpretation_recipe(self):
        """Reload a saved import recipe, preview it, and apply after review."""
        if not self._can_start_interpretation(
            CommandName.RELOAD_INTERPRETATION_RECIPE,
            blocked_title="Recipe Reload Blocked",
            fallback_reason="Recipe reload is not available right now.",
        ):
            return
        recipe_path, _ = QFileDialog.getOpenFileName(
            self.panel,
            "Choose Import Recipe",
            "",
            "Import Recipe (*.json);;JSON (*.json)",
        )
        if not recipe_path:
            return

        started = self._execute_interpretation_command_async(
            ReloadInterpretationRecipeCommand(recipe_path=recipe_path),
            on_result=self._continue_reloaded_interpretation_recipe,
            error_title="Recipe reload failed",
        )
        if not started:
            QMessageBox.critical(
                self.panel,
                "Recipe reload unavailable",
                "Data Interpretation command service is unavailable.",
            )

    def _continue_reloaded_interpretation_recipe(self, reload_result) -> None:
        """Open the recipe review after its backend state is ready."""
        if reload_result.failed:
            QMessageBox.critical(
                self.panel,
                "Recipe reload failed",
                reload_result.message,
            )
            return

        scan = self._diagnostic_payload(reload_result, "scan_result")
        preview = self._diagnostic_payload(reload_result, "preview")
        candidate = self._diagnostic_payload(reload_result, "candidate")
        decision = self._diagnostic_payload(
            reload_result,
            "validation_decision",
        )
        dialog_class = _data_interpretation_preview_dialog_class()
        dialog = dialog_class(
            self.panel,
            scan_result=scan,
            preview=preview,
            validation_decision=decision,
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
        candidate_id = self._optional_payload_id(candidate, "candidate_id")
        if str(decision.get("decision")) == "blocked" and not dialog_choices:
            QMessageBox.critical(
                self.panel,
                "Interpretation blocked",
                self._decision_reason(decision),
            )
            return
        if dialog_choices:
            raw_base_choices = candidate.get("choices")
            base_choices: dict[str, Any] = (
                {str(key): value for key, value in raw_base_choices.items()}
                if isinstance(raw_base_choices, dict)
                else {}
            )
            dialog_choices = self._merge_interpretation_choices(
                base_choices,
                dialog_choices,
            )
            started = self._execute_interpretation_command_async(
                PreviewInterpretationCommand(
                    scan_id=self._optional_payload_id(scan, "scan_id"),
                    choices=dialog_choices,
                ),
                on_result=lambda result: self._continue_reloaded_recipe_preview(
                    result,
                    scan=scan,
                    dialog_result=dialog_result,
                ),
                error_title="Interpretation preview failed",
            )
            if not started:
                QMessageBox.critical(
                    self.panel,
                    "Interpretation preview unavailable",
                    "Data Interpretation command service is unavailable.",
                )
            return

        review_state = _InterpretationReviewState(
            scan=scan,
            preview=preview,
            candidate=candidate,
            candidate_id=candidate_id,
            decision=decision,
        )
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
        self._apply_interpretation_async(
            _InterpretationReviewState(
                scan=scan,
                preview=preview,
                candidate=candidate,
                candidate_id=candidate_id,
                decision=decision,
            ),
            dialog_result,
        )

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
    ) -> bool:
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
    ) -> bool:
        dialog_kwargs: dict[str, Any] = {
            "scan_result": review_state.scan,
            "preview": review_state.preview,
            "validation_decision": review_state.decision,
        }
        if initial_step:
            dialog_kwargs["initial_step"] = initial_step
        dialog_class = _data_interpretation_preview_dialog_class()
        dialog = dialog_class(self.panel, **dialog_kwargs)
        if not dialog.exec():
            return True

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
        next_label_sources = self._dialog_label_sources(
            dialog_result,
            label_sources,
        )
        if next_label_sources != label_sources:
            return self._start_interpretation_review_async(
                source_path,
                source_hint,
                choices,
                next_label_sources,
                initial_step=str(dialog_result.get("resume_step") or ""),
            )

        if (
            str(review_state.decision.get("decision")) == "blocked"
            and not dialog_choices
        ):
            QMessageBox.critical(
                self.panel,
                "Interpretation blocked",
                self._decision_reason(review_state.decision),
            )
            return True

        if dialog_choices:
            updated_choices = self._merge_interpretation_choices(
                choices,
                dialog_choices,
            )
            return self._review_interpretation_for_apply_async(
                source_path=source_path,
                source_hint=source_hint,
                choices=updated_choices,
                label_sources=label_sources,
                dialog_result=dialog_result,
            )
        return self._apply_interpretation_async(review_state, dialog_result)

    def _execute_interpretation_command_async(
        self,
        command,
        *,
        on_result: Callable[[Any], None],
        error_title: str,
        refresh: bool = False,
    ) -> bool:
        """Dispatch one wizard command and continue from its Qt result callback."""

        def _handle_error(error: tuple) -> None:
            message = error[1] if len(error) > 1 else error
            QMessageBox.critical(self.panel, error_title, str(message))

        if execute_application_command_async(
            self.panel,
            command,
            on_result=on_result,
            on_error=_handle_error,
            refresh=refresh,
            busy_target=self.panel,
        ):
            return True
        if has_real_application_context(self.panel):
            QMessageBox.warning(
                self.panel,
                "Interpretation Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return True
        result = execute_application_command(self.panel, command)
        if result is None:
            return False
        on_result(result)
        return True

    def _start_interpretation_review_async(
        self,
        source_path: str,
        source_hint: str,
        choices: dict[str, Any],
        label_sources: list[str],
        *,
        initial_step: str = "",
    ) -> bool:
        """Run scan/preview/validate off the Qt thread for real Study-backed UI."""

        def _handle_review_result(review_result) -> None:
            if self._result_failed(
                review_result,
                "Interpretation review failed",
            ):
                return
            review_state = self._review_state_from_review_result(review_result)
            self._continue_data_interpretation_import(
                source_path=source_path,
                source_hint=source_hint,
                choices=dict(choices),
                label_sources=list(label_sources),
                review_state=review_state,
                initial_step=initial_step,
            )

        review_command = ReviewInterpretationCommand(
            source_path=source_path,
            source_hint=source_hint,
            label_sources=label_sources,
            choices=choices,
        )
        return self._execute_interpretation_command_async(
            review_command,
            on_result=_handle_review_result,
            error_title="Interpretation failed",
            refresh=False,
        )

    def _review_interpretation_for_apply_async(
        self,
        *,
        source_path: str,
        source_hint: str,
        choices: dict[str, Any],
        label_sources: list[str],
        dialog_result: dict[str, Any],
    ) -> bool:
        """Refresh edited choices, then apply the resulting candidate."""

        def _handle_review_result(review_result) -> None:
            if self._result_failed(review_result, "Interpretation review failed"):
                return
            review_state = self._review_state_from_review_result(review_result)
            if str(review_state.decision.get("decision")) == "blocked":
                QMessageBox.critical(
                    self.panel,
                    "Interpretation blocked",
                    self._decision_reason(review_state.decision),
                )
                return
            self._apply_interpretation_async(review_state, dialog_result)

        return self._execute_interpretation_command_async(
            ReviewInterpretationCommand(
                source_path=source_path,
                source_hint=source_hint,
                label_sources=label_sources,
                choices=choices,
            ),
            on_result=_handle_review_result,
            error_title="Interpretation review failed",
        )

    def _apply_interpretation_async(
        self,
        review_state: _InterpretationReviewState,
        dialog_result: dict[str, Any],
    ) -> bool:
        """Apply one reviewed candidate and continue to optional recipe saving."""
        apply_paths = self._interpretation_apply_paths(
            review_state.candidate,
            review_state.preview,
            review_state.scan,
        )
        if not self._confirm_import_resource_preflight(apply_paths):
            return True
        apply_command = ApplyInterpretationCommand(
            candidate_id=(
                self._optional_payload_id(review_state.decision, "candidate_id")
                or review_state.candidate_id
            ),
            confirmed=bool(dialog_result.get("confirmed")),
        )

        def _handle_apply_result(apply_result) -> None:
            if self._result_failed(apply_result, "Interpretation apply failed"):
                return

            def _finish(recipe_message: str = "") -> None:
                self._show_status(
                    " ".join(
                        part for part in [apply_result.message, recipe_message] if part
                    ),
                )

            if bool(dialog_result.get("save_recipe", False)):
                if not self._save_interpretation_recipe(on_complete=_finish):
                    _finish()
                return
            _finish()

        return self._execute_interpretation_command_async(
            apply_command,
            on_result=_handle_apply_result,
            error_title="Interpretation apply failed",
            refresh=True,
        )

    def _review_state_from_review_result(
        self,
        review_result,
    ) -> _InterpretationReviewState:
        candidate = self._diagnostic_payload(review_result, "candidate")
        return _InterpretationReviewState(
            scan=self._diagnostic_payload(review_result, "scan_result"),
            preview=self._diagnostic_payload(review_result, "preview"),
            candidate=candidate,
            candidate_id=self._optional_payload_id(candidate, "candidate_id"),
            decision=self._diagnostic_payload(review_result, "validation_decision"),
        )

    def _result_failed(self, result, title: str) -> bool:
        if not result.failed:
            return False
        QMessageBox.critical(self.panel, title, result.message)
        return True

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
    ) -> bool:
        """Persist the current recipe and report completion asynchronously."""
        complete = on_complete or (lambda _message: None)
        recipe_block_reason = self._recipe_save_block_reason()
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
                QMessageBox.warning(
                    self.panel,
                    "Recipe not saved",
                    result.message,
                )
                complete("")
                return
            complete("Recipe saved." if recipe_path else "Recipe kept in this session.")

        return self._execute_interpretation_command_async(
            SaveInterpretationRecipeCommand(recipe_path=recipe_path or None),
            on_result=_handle_result,
            error_title="Recipe save failed",
        )

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
        """Merge dialog review choices into the preview command choices."""
        merged = dict(base)
        for key, value in updates.items():
            if key in {"metadata_overrides", "class_map", "event_roles"} and isinstance(
                value,
                dict,
            ):
                previous = merged.get(key)
                merged[key] = {
                    **(previous if isinstance(previous, dict) else {}),
                    **value,
                }
            else:
                merged[key] = value
        return merged

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
        smart_parse_capability = get_command_capability(
            self.panel,
            CommandName.APPLY_SMART_PARSE,
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

        filepaths = self._smart_parse_filenames()
        if filepaths is None:
            return
        if not filepaths:
            QMessageBox.warning(self.panel, "Warning", "No data loaded.")
            return
        dialog_class = _smart_parser_dialog_class()
        dialog = dialog_class(filepaths, self.panel)
        if dialog.exec():
            results = dialog.get_result()
            result = execute_application_command(
                self.panel,
                ApplySmartParseCommand(results=results),
            )
            if result is None:
                QMessageBox.warning(
                    self.panel,
                    "Smart Parse Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                QMessageBox.critical(self.panel, "Error", result.message)
                return
            else:
                count = int(result.diagnostics.get("success_count", 0))
            self._update_panel_after_command_result(result)

            self._show_status(f"Updated {count} files")

    def _smart_parse_filenames(self) -> list[str] | None:
        result = execute_application_command(
            self.panel,
            QueryStateCommand(query="state"),
            refresh=False,
        )
        if result is None:
            return self._compatibility_filenames_for_smart_parse()
        if result.failed:
            QMessageBox.warning(
                self.panel,
                "Smart Parse Blocked" if result.recoverable else "Smart Parse Failed",
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
        label_capability = get_command_capability(
            self.panel,
            CommandName.IMPORT_LABELS,
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
        dialog = dialog_class(self.panel, target_files=target_files)
        if not dialog.exec():
            return
        label_map, mapping = dialog.get_result()
        if label_map is None:
            return

        try:
            # Determine mapping mode from the whole import set rather than the
            # first file only.
            is_timestamp, target_count = self._analyze_label_map(label_map)

            selected_event_names = None
            if not is_timestamp:
                selected_event_names = self._filter_events_for_import(
                    target_files,
                    target_count,
                )
                if selected_event_names is False:
                    return

            count = 0
            plan = None
            if len(label_map) > 1:  # Batch
                data_paths = [d.get_filepath() for d in target_files]
                dialog_class = _label_mapping_dialog_class()
                map_dlg = dialog_class(
                    self.panel,
                    data_paths,
                    list(label_map.keys()),
                )
                if not map_dlg.exec():
                    return
                file_map = map_dlg.get_mapping()
                plan = self._build_label_import_plan(
                    label_map,
                    mapping,
                    mode="batch",
                    file_mapping=file_map,
                    selected_event_names=selected_event_names,
                )
            elif is_timestamp:  # Compatibility timestamp format
                label_fname = next(iter(label_map.keys()))
                file_map = {d.get_filepath(): label_fname for d in target_files}
                plan = self._build_label_import_plan(
                    label_map,
                    mapping,
                    mode="timestamp",
                    file_mapping=file_map,
                    selected_event_names=selected_event_names,
                )
            else:  # Single same-length label file
                label_fname = next(iter(label_map.keys()))
                file_map = {d.get_filepath(): label_fname for d in target_files}
                plan = self._build_label_import_plan(
                    label_map,
                    mapping,
                    mode="sequence",
                    file_mapping=file_map,
                    selected_event_names=selected_event_names,
                )
            result = execute_application_command(
                self.panel,
                ImportLabelsCommand(plan=plan),
            )
            if result is None:
                QMessageBox.warning(
                    self.panel,
                    "Label Import Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                QMessageBox.critical(self.panel, "Error", result.message)
                return
            else:
                count = int(result.diagnostics.get("success_count", 0))

            if count > 0:
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
            else:
                QMessageBox.warning(
                    self.panel,
                    "No Labels Applied",
                    "No labels were applied. Check whether the label count, "
                    "event selection, or file mapping matches the selected data.",
                )

        except Exception as e:
            logger.error("Import label error: %s", e, exc_info=True)
            QMessageBox.critical(self.panel, "Error", f"Failed: {e}")

    def _offer_label_recipe_save(
        self,
        result,
        *,
        on_complete: Callable[[str], None] | None = None,
    ) -> str | None:
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if not bool(diagnostics.get("recipe_updated")):
            return ""
        if self._recipe_save_block_reason() is not None:
            return "Interpretation recipe trace updated in this session."
        reply = QMessageBox.question(
            self.panel,
            "Save Updated Recipe",
            "External labels were added to the current data interpretation "
            "recipe. Save the updated recipe now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            started = self._save_interpretation_recipe(on_complete=on_complete)
            return None if started else "Interpretation recipe trace updated."
        return "Interpretation recipe trace updated."

    def _analyze_label_map(self, label_map):
        """Classify imported labels and infer a safe smart-filter target count."""
        has_timestamp = False
        has_sequence = False
        sequence_lengths = []

        for labels in label_map.values():
            if self._is_timestamp_labels(labels):
                has_timestamp = True
                continue

            has_sequence = True
            try:
                sequence_lengths.append(len(labels))
            except TypeError:
                logger.warning("Imported labels do not expose length: %r", type(labels))

        if has_timestamp and has_sequence:
            raise ValueError(
                "Cannot mix timestamp-style and sequence-style label files in one "
                "import.",
            )

        if has_timestamp:
            return True, None

        target_count = None
        if sequence_lengths and len(set(sequence_lengths)) == 1:
            target_count = sequence_lengths[0]

        return False, target_count

    @staticmethod
    def _is_timestamp_labels(labels):
        """Return whether loaded labels are in timestamp-annotation format."""
        return (
            isinstance(labels, list) and len(labels) > 0 and isinstance(labels[0], dict)
        )

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
        label_map,
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
            target_indices=list(getattr(self, "_last_target_file_indices", [])),
            label_map=dict(label_map),
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

        a_subj = menu.addAction("Set Subject")
        a_sess = menu.addAction("Set Session")
        menu.addSeparator()
        a_rem = menu.addAction("Remove Files")

        action = menu.exec(self.panel.table.mapToGlobal(pos))
        if action == a_subj:
            self._batch_set(rows, "Subject")
        elif action == a_sess:
            self._batch_set(rows, "Session")
        elif action == a_rem:
            self._remove_files(rows)

    def _batch_set(self, rows, attr):
        metadata_capability = get_command_capability(
            self.panel,
            CommandName.UPDATE_METADATA,
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

        text, ok = QInputDialog.getText(self.panel, f"Set {attr}", f"Enter {attr}:")
        if ok and text:
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
            )
            if result is None:
                QMessageBox.warning(
                    self.panel,
                    "Metadata Update Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                QMessageBox.critical(self.panel, "Error", result.message)
                return
            self._update_panel_after_command_result(result)

    def _remove_files(self, rows):
        remove_capability = get_command_capability(
            self.panel,
            CommandName.REMOVE_FILES,
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

        if (
            QMessageBox.question(
                self.panel,
                "Confirm",
                f"Remove {len(rows)} files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            result = execute_application_command(
                self.panel,
                RemoveFilesCommand(indices=list(rows)),
            )
            if result is None:
                QMessageBox.warning(
                    self.panel,
                    "Remove Files Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                QMessageBox.critical(self.panel, "Error", result.message)
                return
            self._update_panel_after_command_result(result)
