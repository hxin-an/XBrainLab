"""Focused UI workflow owner for importing external EEG labels."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from PyQt6.QtWidgets import QMessageBox

from XBrainLab.backend.application.commands import (
    CommandName,
    ImportLabelsCommand,
    LabelImportPlan,
    QueryStateCommand,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    blocked_reason,
    execute_application_command,
    get_command_capability,
    get_command_review_context,
    has_real_application_context,
    is_stale_publication_result,
)
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.interaction_outcome import InteractionOutcome

_DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE = (
    "Data interpretation availability is unavailable right now."
)


@dataclass(frozen=True, slots=True)
class LabelImportTarget:
    """Immutable target facts reviewed through the ApplicationService boundary."""

    index: int
    filepath: str
    filename: str
    raw: bool
    event_names: tuple[str, ...]
    suggested_event_names: tuple[str, ...]
    event_read_error: str | None
    publication_generation: int

    @classmethod
    def from_payload(
        cls,
        payload: Any,
        *,
        publication_generation: int,
    ) -> LabelImportTarget:
        if not isinstance(payload, dict):
            raise ValueError("Label target payload must be an object.")
        index = payload.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Label target index is invalid.")
        filepath = str(payload.get("filepath") or "").strip()
        filename = str(payload.get("filename") or "").strip()
        if not filepath or not filename:
            raise ValueError("Label target path identity is incomplete.")
        raw = payload.get("is_raw")
        if not isinstance(raw, bool):
            raise ValueError("Label target data kind is invalid.")
        event_names = payload.get("event_names")
        suggested = payload.get("suggested_event_names")
        if not isinstance(event_names, list) or not all(
            isinstance(item, str) and item for item in event_names
        ):
            raise ValueError("Label target event names are invalid.")
        if not isinstance(suggested, list) or not all(
            isinstance(item, str) and item for item in suggested
        ):
            raise ValueError("Label target event suggestions are invalid.")
        raw_error = payload.get("event_read_error")
        if raw_error is not None and not isinstance(raw_error, str):
            raise ValueError("Label target event error is invalid.")
        return cls(
            index=index,
            filepath=filepath,
            filename=filename,
            raw=raw,
            event_names=tuple(event_names),
            suggested_event_names=tuple(suggested),
            event_read_error=raw_error,
            publication_generation=publication_generation,
        )

    def get_filepath(self) -> str:
        return self.filepath

    def get_filename(self) -> str:
        return self.filename


@dataclass(frozen=True, slots=True)
class CompatibilityLabelTargets:
    """Detached compatibility result for mock/controller-only UI contexts."""

    targets: tuple[Any, ...]
    target_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ExternalLabelSelectionSnapshot:
    """Read-only view of the targets used to build the next label plan."""

    target_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ExternalLabelImportBindings:
    """Replaceable UI/application ports resolved by the composition root."""

    message_box: Callable[[], Any]
    get_command_review_context: Callable[..., Any]
    get_command_capability: Callable[..., Any]
    has_real_application_context: Callable[..., bool]
    blocked_reason: Callable[..., str]
    execute_application_command: Callable[..., Any]
    is_stale_publication_result: Callable[[Any], bool]
    present_unexpected_error: Callable[..., Any]


def default_external_label_import_bindings() -> ExternalLabelImportBindings:
    """Build production bindings for direct coordinator use."""
    return ExternalLabelImportBindings(
        message_box=lambda: QMessageBox,
        get_command_review_context=get_command_review_context,
        get_command_capability=get_command_capability,
        has_real_application_context=has_real_application_context,
        blocked_reason=blocked_reason,
        execute_application_command=execute_application_command,
        is_stale_publication_result=is_stale_publication_result,
        present_unexpected_error=present_unexpected_error,
    )


class ExternalLabelImportHost(Protocol):
    """Narrow adapter contract retained by ``DatasetActionHandler``."""

    panel: Any

    def _compatibility_target_files_from_controller(
        self,
        selected_rows: list[int],
    ) -> CompatibilityLabelTargets: ...

    def _compatibility_smart_filter_suggestions(
        self,
        raw_file: Any,
        target_count: int,
    ) -> list[int]: ...

    def _execute_interpretation_command_async(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> InteractionOutcome | None: ...

    def _interaction_failure_outcome(
        self,
        result: Any,
        message: str,
    ) -> InteractionOutcome: ...

    def _recipe_save_block_reason(self) -> str | None: ...

    def _save_interpretation_recipe(self, *args: Any, **kwargs: Any) -> bool: ...

    def _show_status(self, message: str) -> None: ...


class ExternalLabelImportCoordinator:
    """Own external-label review, mapping, filtering, apply, and recipe prompts."""

    def __init__(
        self,
        host: ExternalLabelImportHost,
        *,
        event_filter_dialog_class: Callable[[], type[Any]],
        import_label_dialog_class: Callable[[], type[Any]],
        label_mapping_dialog_class: Callable[[], type[Any]],
        bindings: ExternalLabelImportBindings | None = None,
    ) -> None:
        self._host = host
        self.panel = host.panel
        self._event_filter_dialog_class = event_filter_dialog_class
        self._import_label_dialog_class = import_label_dialog_class
        self._label_mapping_dialog_class = label_mapping_dialog_class
        self._bindings = bindings or default_external_label_import_bindings()
        self._target_file_indices: tuple[int, ...] = ()

    def selection_snapshot(self) -> ExternalLabelSelectionSnapshot:
        """Return immutable target identity for diagnostics and tests."""
        return ExternalLabelSelectionSnapshot(
            target_indices=self._target_file_indices,
        )

    def _remember_target_file_indices(self, target_indices: list[int]) -> None:
        self._target_file_indices = tuple(target_indices)

    def import_label(self) -> None:
        """Review and apply external label files to selected loaded EEG data."""
        bindings = self._bindings
        message_box = bindings.message_box()
        review_context = bindings.get_command_review_context(
            self.panel,
            CommandName.IMPORT_LABELS,
        )
        if review_context is None and bindings.has_real_application_context(self.panel):
            message_box.warning(
                self.panel,
                "Label Import Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return
        label_capability = (
            getattr(review_context, "capability", None)
            if review_context is not None
            else bindings.get_command_capability(
                self.panel,
                CommandName.IMPORT_LABELS,
            )
        )
        if review_context is not None and label_capability is None:
            message_box.warning(
                self.panel,
                "Label Import Blocked",
                _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE,
            )
            return
        if label_capability is not None and not label_capability.enabled:
            message_box.warning(
                self.panel,
                "Label Import Blocked",
                bindings.blocked_reason(
                    label_capability,
                    "Label import is not available right now.",
                ),
            )
            return

        target_files = self.get_target_files_for_import()
        if not target_files:
            return

        dialog_class = self._import_label_dialog_class()
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
            message_box.critical(
                self.panel,
                "Label Import Failed",
                "Timestamp and sequence label files cannot be mixed in one import.",
            )
            return

        try:
            is_timestamp = preview_mode == "timestamp"
            target_count = selection.target_count

            selected_event_names: set[str] | list[str] | None = None
            if not is_timestamp:
                filtered_event_names = self.filter_events_for_import(
                    target_files,
                    target_count,
                )
                if filtered_event_names is False:
                    return
                selected_event_names = filtered_event_names

            label_paths = list(selection.label_paths)
            if len(label_paths) > 1:
                data_paths = [data.get_filepath() for data in target_files]
                mapping_dialog = self._label_mapping_dialog_class()(
                    self.panel,
                    data_paths,
                    label_paths,
                )
                if not mapping_dialog.exec():
                    return
                plan = self.build_label_import_plan(
                    selection,
                    mapping,
                    mode="batch",
                    file_mapping=mapping_dialog.get_mapping(),
                    selected_event_names=selected_event_names,
                )
            else:
                label_filename = label_paths[0]
                file_mapping = {
                    data.get_filepath(): label_filename for data in target_files
                }
                plan = self.build_label_import_plan(
                    selection,
                    mapping,
                    mode="timestamp" if is_timestamp else "sequence",
                    file_mapping=file_mapping,
                    selected_event_names=selected_event_names,
                )
            self.execute_label_import_async(
                plan,
                expected_publication_generation=(
                    review_context.publication_generation
                    if review_context is not None
                    else None
                ),
            )
        except Exception:
            bindings.present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.LABEL_IMPORT,
                message_box=message_box,
            )

    def execute_label_import_async(
        self,
        plan: LabelImportPlan,
        *,
        expected_publication_generation: int | None = None,
    ) -> None:
        """Apply one exact reviewed label plan away from the GUI thread."""
        message_box = self._bindings.message_box()

        def _handle_result(result: Any) -> InteractionOutcome:
            if result.failed:
                if self._bindings.is_stale_publication_result(result):
                    message_box.warning(
                        self.panel,
                        "Review Label Import Again",
                        result.message,
                    )
                else:
                    message_box.critical(
                        self.panel,
                        "Label Import Failed",
                        result.message,
                    )
                return self._host._interaction_failure_outcome(
                    result,
                    result.message,
                )

            count = int(result.diagnostics.get("success_count", 0))
            if count <= 0:
                message = (
                    "No labels were applied. Check whether the label count, event "
                    "selection, or file mapping matches the selected data."
                )
                message_box.warning(self.panel, "No Labels Applied", message)
                return InteractionOutcome.blocked(message)

            def _finish_label_import(recipe_message: str = "") -> None:
                self._host._show_status(
                    " ".join(
                        part
                        for part in [
                            f"Applied to {count} files.",
                            recipe_message,
                        ]
                        if part
                    ),
                )

            recipe_message = self.offer_label_recipe_save(
                result,
                on_complete=_finish_label_import,
            )
            if recipe_message is not None:
                _finish_label_import(recipe_message)
            return InteractionOutcome.completed(f"Applied labels to {count} files.")

        outcome = self._host._execute_interpretation_command_async(
            ImportLabelsCommand(plan=plan),
            on_result=_handle_result,
            error_title="Label import failed",
            expected_publication_generation=expected_publication_generation,
            blocked_title="Label Import Blocked",
            unexpected_error_context=UnexpectedErrorContext.LABEL_IMPORT,
        )
        if outcome is None:
            message_box.warning(
                self.panel,
                "Label Import Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )

    def offer_label_recipe_save(
        self,
        result: Any,
        *,
        on_complete: Callable[[str], None] | None = None,
    ) -> str | None:
        bindings = self._bindings
        message_box = bindings.message_box()
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if not bool(diagnostics.get("recipe_updated")):
            return ""
        review_context = bindings.get_command_review_context(
            self.panel,
            CommandName.SAVE_INTERPRETATION_RECIPE,
        )
        if review_context is None and bindings.has_real_application_context(self.panel):
            return "Interpretation recipe trace updated in this session."
        save_capability = (
            getattr(review_context, "capability", None)
            if review_context is not None
            else None
        )
        if review_context is not None and save_capability is None:
            return "Interpretation recipe trace updated in this session."
        recipe_block_reason = (
            bindings.blocked_reason(
                save_capability,
                "Apply an interpretation before saving a recipe.",
            )
            if save_capability is not None and not save_capability.enabled
            else self._host._recipe_save_block_reason()
            if review_context is None
            else None
        )
        if recipe_block_reason is not None:
            return "Interpretation recipe trace updated in this session."
        reply = message_box.question(
            self.panel,
            "Save Updated Recipe",
            "External labels were added to the current data interpretation "
            "recipe. Save the updated recipe now?",
            message_box.StandardButton.Yes | message_box.StandardButton.No,
        )
        if reply == message_box.StandardButton.Yes:
            started = self._host._save_interpretation_recipe(
                on_complete=on_complete,
                review_context=review_context,
                review_context_resolved=True,
            )
            return None if started else "Interpretation recipe trace updated."
        return "Interpretation recipe trace updated."

    def get_target_files_for_import(self) -> list[Any]:
        """Resolve selected table-backed target files without stale index guesses."""
        self._remember_target_file_indices([])
        message_box = self._bindings.message_box()
        if self.panel.table.rowCount() <= 0:
            message_box.warning(
                self.panel,
                "No Data Loaded",
                "Interpret a data source before adding labels.",
            )
            return []

        selected_rows = sorted(
            {index.row() for index in self.panel.table.selectedIndexes()},
        )
        if not selected_rows:
            reply = message_box.question(
                self.panel,
                "Add Labels to Loaded Data",
                "No files selected. Add labels to all loaded files?",
                message_box.StandardButton.Yes | message_box.StandardButton.No,
            )
            if reply == message_box.StandardButton.Yes:
                selected_rows = list(range(self.panel.table.rowCount()))
            else:
                return []

        table_targets = self.target_files_from_table_rows(selected_rows)
        if table_targets is not None:
            return table_targets
        compatibility_targets = self._host._compatibility_target_files_from_controller(
            selected_rows
        )
        self._remember_target_file_indices(
            list(compatibility_targets.target_indices),
        )
        return list(compatibility_targets.targets)

    def target_files_from_table_rows(
        self,
        selected_rows: list[int],
    ) -> list[Any] | None:
        capture = getattr(self.panel, "capture_table_selection", None)
        resolve = getattr(self.panel, "resolve_table_selection", None)
        if not callable(capture) or not callable(resolve):
            return None
        selection = capture(selected_rows)
        generation = getattr(selection, "publication_generation", None)
        if isinstance(generation, bool) or not isinstance(generation, int):
            return None
        target_indices = resolve(
            selection,
            stale_title="Review Label Targets Again",
            action_description="add labels",
        )
        if not isinstance(target_indices, list) or not all(
            isinstance(index, int) and not isinstance(index, bool)
            for index in target_indices
        ):
            return []
        return self._query_label_import_targets(
            target_indices,
            target_count=0,
            publication_generation=generation,
        )

    def _query_label_import_targets(
        self,
        target_indices: list[int],
        *,
        target_count: int,
        publication_generation: int,
    ) -> list[LabelImportTarget]:
        message_box = self._bindings.message_box()
        result = self._bindings.execute_application_command(
            self.panel,
            QueryStateCommand(
                query="label_import_targets",
                params={
                    "target_indices": list(target_indices),
                    "target_count": target_count,
                },
            ),
            refresh=False,
            expected_publication_generation=publication_generation,
        )
        if result is None:
            message_box.warning(
                self.panel,
                "Label Import Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return []
        if result.failed:
            title = (
                "Review Label Targets Again"
                if self._bindings.is_stale_publication_result(result)
                else "Label Import Blocked"
            )
            message_box.warning(self.panel, title, result.message)
            return []
        diagnostics = getattr(result, "diagnostics", {}) or {}
        payloads = diagnostics.get("targets")
        if diagnostics.get("payload_type") != "label_import_targets" or not isinstance(
            payloads, list
        ):
            message_box.warning(
                self.panel,
                "Label Import Blocked",
                "XBrainLab could not verify the selected EEG label targets.",
            )
            return []
        try:
            targets = [
                LabelImportTarget.from_payload(
                    payload,
                    publication_generation=publication_generation,
                )
                for payload in payloads
            ]
        except ValueError as exc:
            logger.warning("Invalid detached label-target payload: %s", exc)
            message_box.warning(
                self.panel,
                "Label Import Blocked",
                "XBrainLab could not verify the selected EEG label targets.",
            )
            return []
        if [target.index for target in targets] != target_indices:
            message_box.warning(
                self.panel,
                "Review Label Targets Again",
                "The selected EEG files changed while label import was being reviewed.",
            )
            return []
        self._remember_target_file_indices(target_indices)
        return targets

    def build_label_import_plan(
        self,
        selection: Any,
        mapping: Any,
        mode: str,
        file_mapping: dict[str, str] | None = None,
        selected_event_names: set[str] | list[str] | None = None,
    ) -> LabelImportPlan:
        selected_names = (
            sorted(selected_event_names)
            if isinstance(selected_event_names, set)
            else selected_event_names
        )
        return LabelImportPlan(
            preview_id=str(selection.preview_id),
            target_indices=list(self._target_file_indices),
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

    def filter_events_for_import(
        self,
        target_files: list[Any],
        target_count: int,
    ) -> set[str] | None | Literal[False]:
        """Review which raw events receive sequential labels."""
        if target_files and all(
            isinstance(target, LabelImportTarget) for target in target_files
        ):
            return self._filter_detached_events_for_import(
                target_files,
                target_count,
            )

        raw_files = [
            data for data in target_files if data.is_raw() and data.has_event()
        ]
        if not raw_files:
            return None

        unique: set[str] = set()
        for data in raw_files:
            _, event_ids = data.get_raw_event_list()
            unique.update(event_ids.keys())
        if not unique:
            return None

        suggested: list[str] = []
        if target_count:
            suggested_names: set[str] = set()
            for raw_file in raw_files:
                suggested_ids = self.smart_filter_suggestions_for_import(
                    raw_file,
                    target_count,
                    target_files,
                )
                _, event_ids = raw_file.get_raw_event_list()
                id_map = {value: key for key, value in event_ids.items()}
                suggested_names.update(
                    id_map[event_id] for event_id in suggested_ids if event_id in id_map
                )
            suggested = sorted(suggested_names)

        dialog = self._event_filter_dialog_class()(self.panel, sorted(unique))
        if suggested:
            dialog.set_selection(suggested)
        if dialog.exec():
            return set(dialog.get_selected_ids())
        return False

    def _filter_detached_events_for_import(
        self,
        target_files: list[Any],
        target_count: int,
    ) -> set[str] | None | Literal[False]:
        targets = [
            target for target in target_files if isinstance(target, LabelImportTarget)
        ]
        generations = {target.publication_generation for target in targets}
        if len(generations) != 1:
            self._bindings.message_box().warning(
                self.panel,
                "Review Label Targets Again",
                "The selected EEG files do not belong to one reviewed dataset state.",
            )
            return False
        reviewed_targets = self._query_label_import_targets(
            [target.index for target in targets],
            target_count=target_count,
            publication_generation=generations.pop(),
        )
        if not reviewed_targets:
            return False
        target_files[:] = reviewed_targets
        raw_targets = [target for target in reviewed_targets if target.raw]
        if not raw_targets:
            return None
        failed_target = next(
            (target for target in raw_targets if target.event_read_error is not None),
            None,
        )
        if failed_target is not None:
            self._bindings.message_box().warning(
                self.panel,
                "Label Event Review Failed",
                "XBrainLab could not read EEG events from "
                f"{failed_target.filename}. Review the source file before adding "
                "sequence labels.",
            )
            return False

        unique = {
            event_name for target in raw_targets for event_name in target.event_names
        }
        if not unique:
            self._bindings.message_box().warning(
                self.panel,
                "No EEG Events Available",
                "Sequence labels require at least one target EEG event.",
            )
            return False
        suggested = sorted(
            {
                event_name
                for target in raw_targets
                for event_name in target.suggested_event_names
            }
        )
        dialog = self._event_filter_dialog_class()(self.panel, sorted(unique))
        if suggested:
            dialog.set_selection(suggested)
        if dialog.exec():
            return set(dialog.get_selected_ids())
        return False

    def smart_filter_suggestions_for_import(
        self,
        raw_file: Any,
        target_count: int,
        target_files: list[Any],
    ) -> list[int]:
        """Read event-filter suggestions from the command API when possible."""
        target_index = self.target_index_for_filter_suggestion(
            raw_file,
            target_files,
        )
        if target_index is not None:
            result = self._bindings.execute_application_command(
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
        return self._host._compatibility_smart_filter_suggestions(
            raw_file,
            target_count,
        )

    def target_index_for_filter_suggestion(
        self,
        raw_file: Any,
        target_files: list[Any],
    ) -> int | None:
        try:
            target_position = target_files.index(raw_file)
        except ValueError:
            return None
        target_indices = self._target_file_indices
        if target_position < len(target_indices):
            try:
                return int(target_indices[target_position])
            except (TypeError, ValueError):
                return None
        return target_position
