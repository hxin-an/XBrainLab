"""Action handler for dataset panel operations.

Provides logic for importing EEG data files, applying labels,
running smart parse, and managing event filtering.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMenu,
)

from XBrainLab.backend.application.commands import (
    ApplySmartParseCommand,
    CommandName,
    LabelImportPlan,
    MetadataUpdate,
    QueryStateCommand,
    RemoveFilesCommand,
    UpdateMetadataCommand,
)
from XBrainLab.backend.application.view_publication import InterpretationReviewIdentity
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    CommandReviewContext,
    ControllerCompatibilityUnavailableError,
    application_ui_runtime,
    blocked_reason,
    cancel_application_operation,
    execute_application_command,
    execute_application_command_async,
    get_application_operation,
    get_application_view_publication,
    get_command_capability,
    get_command_review_context,
    has_real_application_context,
    is_stale_publication_result,
    run_controller_compatibility_call,
)
from XBrainLab.ui.async_command_runner import qt_object_deleted
from XBrainLab.ui.components.modal_presentation import (
    AlertSeverity,
    ask_confirmation,
    show_error,
    show_warning,
)
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.interaction_outcome import (
    InteractionOutcome,
    reserve_interaction_continuation,
)
from XBrainLab.ui.panels.dataset.data_interpretation_action_coordinator import (
    DataInterpretationActionBindings,
    DataInterpretationActionCoordinator,
)
from XBrainLab.ui.panels.dataset.external_label_import_coordinator import (
    CompatibilityLabelTargets,
    ExternalLabelImportBindings,
    ExternalLabelImportCoordinator,
)
from XBrainLab.ui.status import show_status_message

DataInterpretationPreviewDialog: Any | None = None
BidsSubjectSelectionDialog: Any | None = None
EegSourceChooserDialog: Any | None = None
EventFilterDialog: Any | None = None
ImportLabelDialog: Any | None = None
LabelMappingDialog: Any | None = None
SmartParserDialog: Any | None = None

_DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE = (
    "Data interpretation availability is unavailable right now."
)


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


def _data_interpretation_preview_dialog_class():
    patched = globals()["DataInterpretationPreviewDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (  # noqa: PLC0415
        DataInterpretationPreviewDialog,
    )

    return DataInterpretationPreviewDialog


def _bids_subject_selection_dialog_class():
    patched = globals()["BidsSubjectSelectionDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.bids_subject_selection_dialog import (  # noqa: PLC0415
        BidsSubjectSelectionDialog,
    )

    return BidsSubjectSelectionDialog


def _eeg_source_chooser_dialog_class():
    patched = globals()["EegSourceChooserDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (  # noqa: PLC0415
        EegSourceChooserDialog,
    )

    return EegSourceChooserDialog


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
        self._data_interpretation = DataInterpretationActionCoordinator(
            self,
            source_chooser_dialog_class=_eeg_source_chooser_dialog_class,
            preview_dialog_class=_data_interpretation_preview_dialog_class,
            bids_subject_dialog_class=_bids_subject_selection_dialog_class,
            bindings=DataInterpretationActionBindings(
                show_warning=lambda *args, **kwargs: show_warning(*args, **kwargs),
                show_error=lambda *args, **kwargs: show_error(*args, **kwargs),
                ask_confirmation=lambda *args, **kwargs: ask_confirmation(
                    *args, **kwargs
                ),
                file_dialog=lambda: QFileDialog,
                single_shot=lambda *args, **kwargs: QTimer.singleShot(
                    *args,
                    **kwargs,
                ),
                application_ui_runtime=lambda *args, **kwargs: (
                    application_ui_runtime(*args, **kwargs)
                ),
                blocked_reason=lambda *args, **kwargs: blocked_reason(
                    *args,
                    **kwargs,
                ),
                cancel_application_operation=lambda *args, **kwargs: (
                    cancel_application_operation(*args, **kwargs)
                ),
                execute_application_command=lambda *args, **kwargs: (
                    execute_application_command(*args, **kwargs)
                ),
                execute_application_command_async=lambda *args, **kwargs: (
                    execute_application_command_async(*args, **kwargs)
                ),
                get_application_operation=lambda *args, **kwargs: (
                    get_application_operation(*args, **kwargs)
                ),
                get_application_view_publication=lambda *args, **kwargs: (
                    get_application_view_publication(*args, **kwargs)
                ),
                get_command_capability=lambda *args, **kwargs: (
                    get_command_capability(*args, **kwargs)
                ),
                get_command_review_context=lambda *args, **kwargs: (
                    get_command_review_context(*args, **kwargs)
                ),
                has_real_application_context=lambda *args, **kwargs: (
                    has_real_application_context(*args, **kwargs)
                ),
                is_stale_publication_result=lambda result: (
                    is_stale_publication_result(result)
                ),
                present_unexpected_error=lambda *args, **kwargs: (
                    present_unexpected_error(*args, **kwargs)
                ),
                qt_object_deleted=lambda obj: qt_object_deleted(obj),
                reserve_interaction_continuation=lambda: (
                    reserve_interaction_continuation()
                ),
            ),
        )
        self._external_label_import = ExternalLabelImportCoordinator(
            self,
            event_filter_dialog_class=_event_filter_dialog_class,
            import_label_dialog_class=_import_label_dialog_class,
            label_mapping_dialog_class=_label_mapping_dialog_class,
            bindings=ExternalLabelImportBindings(
                show_warning=lambda *args, **kwargs: show_warning(*args, **kwargs),
                show_error=lambda *args, **kwargs: show_error(*args, **kwargs),
                ask_confirmation=lambda *args, **kwargs: ask_confirmation(
                    *args, **kwargs
                ),
                get_command_review_context=lambda *args, **kwargs: (
                    get_command_review_context(*args, **kwargs)
                ),
                get_command_capability=lambda *args, **kwargs: (
                    get_command_capability(*args, **kwargs)
                ),
                has_real_application_context=lambda *args, **kwargs: (
                    has_real_application_context(*args, **kwargs)
                ),
                blocked_reason=lambda *args, **kwargs: blocked_reason(
                    *args,
                    **kwargs,
                ),
                execute_application_command=lambda *args, **kwargs: (
                    execute_application_command(*args, **kwargs)
                ),
                is_stale_publication_result=lambda result: (
                    is_stale_publication_result(result)
                ),
                present_unexpected_error=lambda *args, **kwargs: (
                    present_unexpected_error(*args, **kwargs)
                ),
            ),
        )

    @property
    def controller(self):
        """DatasetController: The dataset controller from the parent panel."""
        return getattr(self.panel, "controller", None)

    @property
    def main_window(self):
        """QMainWindow: The application main window reference."""
        return getattr(self.panel, "main_window", None)

    def _show_status(self, message: str, timeout_ms: int = 7000) -> None:
        show_status_message(self.panel, message, timeout_ms)

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
                show_warning(self.panel, blocked_title, str(exc))
            return False, None

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

    def _compatibility_target_files_from_controller(
        self,
        selected_rows: list[int],
    ) -> CompatibilityLabelTargets:
        controller = self.controller
        if controller is None:
            show_warning(
                self.panel,
                "Add Labels Blocked",
                "Dataset controller unavailable.",
            )
            return CompatibilityLabelTargets(targets=(), target_indices=())
        available, data_list = self._compatibility_controller_value(
            "Add Labels Blocked",
            controller.get_loaded_data_list,
        )
        if not available:
            return CompatibilityLabelTargets(targets=(), target_indices=())
        target_indices = tuple(i for i in selected_rows if i < len(data_list))
        return CompatibilityLabelTargets(
            targets=tuple(data_list[i] for i in target_indices),
            target_indices=target_indices,
        )

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
        return self._data_interpretation.import_data()

    def review_current_import(
        self,
        *,
        initial_step: str = "Review and Import",
        expected_identity: InterpretationReviewIdentity | None = None,
    ) -> InteractionOutcome:
        return self._data_interpretation.review_current_import(
            initial_step=initial_step,
            expected_identity=expected_identity,
        )

    def import_folder_source(self):
        return self._data_interpretation.import_folder_source()

    def import_bids_source(self):
        return self._data_interpretation.import_bids_source()

    def reload_interpretation_recipe(self):
        return self._data_interpretation.reload_interpretation_recipe()

    def _execute_interpretation_command_async(
        self,
        command,
        *,
        on_result: Callable[[Any], InteractionOutcome | None],
        error_title: str,
        expected_publication_generation: int | None = None,
        blocked_title: str = "Interpretation Blocked",
        unexpected_error_context: UnexpectedErrorContext = (
            UnexpectedErrorContext.DATA_INTERPRETATION_REVIEW
        ),
    ) -> InteractionOutcome | None:
        return self._data_interpretation._execute_interpretation_command_async(
            command,
            on_result=on_result,
            error_title=error_title,
            expected_publication_generation=expected_publication_generation,
            blocked_title=blocked_title,
            unexpected_error_context=unexpected_error_context,
        )

    def _interaction_failure_outcome(
        self,
        result,
        message: str,
    ) -> InteractionOutcome:
        return self._data_interpretation._interaction_failure_outcome(result, message)

    def _save_interpretation_recipe(
        self,
        *,
        on_complete: Callable[[str], None] | None = None,
        review_context: CommandReviewContext | None = None,
        review_context_resolved: bool = False,
    ) -> bool:
        return self._data_interpretation._save_interpretation_recipe(
            on_complete=on_complete,
            review_context=review_context,
            review_context_resolved=review_context_resolved,
        )

    def _recipe_save_block_reason(self) -> str | None:
        return self._data_interpretation._recipe_save_block_reason()

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
            show_warning(
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
        if review_context is None and has_real_application_context(self.panel):
            show_warning(
                self.panel,
                "Smart Parse Blocked",
                _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE,
            )
            return
        smart_parse_capability = (
            getattr(review_context, "capability", None)
            if review_context is not None
            else get_command_capability(
                self.panel,
                CommandName.APPLY_SMART_PARSE,
            )
        )
        if review_context is not None and smart_parse_capability is None:
            show_warning(
                self.panel,
                "Smart Parse Blocked",
                _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE,
            )
            return
        if smart_parse_capability is not None and not smart_parse_capability.enabled:
            show_warning(
                self.panel,
                "Smart Parse Blocked",
                blocked_reason(
                    smart_parse_capability,
                    "Load raw data before applying smart parse.",
                ),
            )
            return

        if smart_parse_capability is None:
            controller = self.controller
            if controller is None:
                show_error(
                    self.panel,
                    "Error",
                    "Dataset controller unavailable.",
                )
                return
            available, is_locked = self._compatibility_controller_value(
                "Smart Parse Blocked",
                lambda: bool(controller.is_locked()),
            )
            if not available:
                return
            if is_locked:
                show_warning(self.panel, "Blocked", "Dataset is locked.")
                return

            available, has_data = self._compatibility_controller_value(
                "Smart Parse Blocked",
                lambda: bool(controller.has_data()),
            )
            if not available:
                return
            if not has_data:
                show_warning(self.panel, "Warning", "No data loaded.")
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
            show_warning(self.panel, "Warning", "No data loaded.")
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
                show_warning(
                    self.panel,
                    "Smart Parse Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                if is_stale_publication_result(result):
                    show_warning(
                        self.panel,
                        "Review Smart Parse Again",
                        result.message,
                    )
                else:
                    show_error(self.panel, "Error", result.message)
                return
            else:
                count = int(result.diagnostics.get("success_count", 0))
            self._show_status(f"Updated {count} files")

    def _smart_parse_filenames(
        self,
        *,
        expected_publication_generation: int | None = None,
    ) -> list[str] | None:
        if expected_publication_generation is None:
            result = execute_application_command(
                self.panel,
                QueryStateCommand(query="data_lists"),
                refresh=False,
            )
        else:
            result = execute_application_command(
                self.panel,
                QueryStateCommand(query="data_lists"),
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
            show_warning(
                self.panel,
                title,
                result.message,
            )
            return None
        diagnostics = getattr(result, "diagnostics", {}) or {}
        rows = diagnostics.get("raw_rows")
        if not isinstance(rows, list):
            return []
        filepaths: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                return []
            filepath = str(row.get("filepath") or "").strip()
            if not filepath:
                return []
            filepaths.append(filepath)
        return filepaths

    def import_label(self) -> None:
        """Delegate the external-label workflow to its focused state owner."""
        self._external_label_import.import_label()

    def _execute_label_import_async(
        self,
        plan: LabelImportPlan,
        *,
        expected_publication_generation: int | None = None,
    ) -> None:
        self._external_label_import.execute_label_import_async(
            plan,
            expected_publication_generation=expected_publication_generation,
        )

    def _offer_label_recipe_save(
        self,
        result: Any,
        *,
        on_complete: Callable[[str], None] | None = None,
    ) -> str | None:
        return self._external_label_import.offer_label_recipe_save(
            result,
            on_complete=on_complete,
        )

    def _get_target_files_for_import(self) -> list[Any]:
        return self._external_label_import.get_target_files_for_import()

    def _target_files_from_table_rows(
        self,
        selected_rows: list[int],
    ) -> list[Any] | None:
        return self._external_label_import.target_files_from_table_rows(selected_rows)

    def _build_label_import_plan(
        self,
        selection: Any,
        mapping: Any,
        mode: str,
        file_mapping: dict[str, str] | None = None,
        selected_event_names: set[str] | list[str] | None = None,
    ) -> LabelImportPlan:
        return self._external_label_import.build_label_import_plan(
            selection,
            mapping,
            mode,
            file_mapping=file_mapping,
            selected_event_names=selected_event_names,
        )

    def _filter_events_for_import(
        self,
        target_files: list[Any],
        target_count: int,
    ) -> set[str] | None | Literal[False]:
        return self._external_label_import.filter_events_for_import(
            target_files,
            target_count,
        )

    def _smart_filter_suggestions_for_import(
        self,
        raw_file: Any,
        target_count: int,
        target_files: list[Any],
    ) -> list[int]:
        return self._external_label_import.smart_filter_suggestions_for_import(
            raw_file,
            target_count,
            target_files,
        )

    def _target_index_for_filter_suggestion(
        self,
        raw_file: Any,
        target_files: list[Any],
    ) -> int | None:
        return self._external_label_import.target_index_for_filter_suggestion(
            raw_file,
            target_files,
        )

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
        show_warning(
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
        if review_context is None and has_real_application_context(self.panel):
            show_warning(
                self.panel,
                "Metadata Update Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return
        metadata_capability = (
            getattr(review_context, "capability", None)
            if review_context is not None
            else None
        )
        if review_context is not None and metadata_capability is None:
            show_warning(
                self.panel,
                "Metadata Update Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return
        if metadata_capability is not None and not metadata_capability.enabled:
            show_warning(
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
                show_warning(
                    self.panel,
                    "Metadata Update Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                if is_stale_publication_result(result):
                    show_warning(
                        self.panel,
                        "Review Metadata Again",
                        result.message,
                    )
                else:
                    show_error(self.panel, "Error", result.message)
                return

    def _remove_files(
        self,
        rows_or_selection: DatasetTableSelection | list[int] | tuple[int, ...],
    ):
        review_context = get_command_review_context(
            self.panel,
            CommandName.REMOVE_FILES,
        )
        if review_context is None and has_real_application_context(self.panel):
            show_warning(
                self.panel,
                "Remove Files Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return
        remove_capability = (
            getattr(review_context, "capability", None)
            if review_context is not None
            else None
        )
        if review_context is not None and remove_capability is None:
            show_warning(
                self.panel,
                "Remove Files Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return
        if remove_capability is not None and not remove_capability.enabled:
            show_warning(
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

        if ask_confirmation(
            self.panel,
            severity=AlertSeverity.WARNING,
            title="Confirm",
            message=f"Remove {len(selection.rows)} files?",
            confirm_text="Remove files",
            cancel_text="Cancel",
            destructive=True,
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
                show_warning(
                    self.panel,
                    "Remove Files Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif result.failed:
                if is_stale_publication_result(result):
                    show_warning(
                        self.panel,
                        "Review File Removal Again",
                        result.message,
                    )
                else:
                    show_error(self.panel, "Error", result.message)
                return
