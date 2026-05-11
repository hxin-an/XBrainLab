"""Legacy data/label compatibility handlers for the application command spine."""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from XBrainLab.backend.load_data.label_loader import load_label_file
from XBrainLab.backend.utils.logger import logger

from .commands import (
    AttachLabelsCommand,
    Command,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
)
from .errors import ApplicationError, PreconditionError
from .results import ErrorType

HandlerResult = str | tuple[str, dict[str, Any]]


class DataCompatibilityCommandService:
    """Handle legacy data loading and post-load label compatibility commands."""

    def __init__(
        self,
        *,
        dataset: Any,
        interpretation: Any,
    ) -> None:
        self.dataset = dataset
        self.interpretation = interpretation

    def handle_load_data(self, command: Command) -> HandlerResult:
        if not isinstance(command, LoadDataCommand):
            raise TypeError("Invalid command for load_data")
        if not command.paths:
            raise PreconditionError("paths list cannot be empty.")
        count, errors = self.dataset.import_files(command.paths)
        if count == 0 and errors:
            error_text = "; ".join(str(error) for error in errors)
            error_type = ErrorType.RUNTIME
            if "Unsupported format" in error_text:
                error_type = ErrorType.UNSUPPORTED_FORMAT
            elif "File corrupted" in error_text:
                error_type = ErrorType.FILE_CORRUPTED
            raise ApplicationError(
                message=f"Failed to load data: {errors}",
                error_type=error_type,
                recoverable=True,
                diagnostics={"success_count": 0, "errors": errors},
            )
        if errors:
            return (
                f"Loaded {count} file(s) with errors: {errors}",
                {"success_count": count, "errors": errors},
            )
        return f"Loaded {count} file(s).", {"success_count": count, "errors": []}

    def handle_attach_labels(self, command: Command) -> HandlerResult:
        if not isinstance(command, AttachLabelsCommand):
            raise TypeError("Invalid command for attach_labels")
        if not command.mapping:
            raise PreconditionError("mapping is required.")

        data_list = self.dataset.get_loaded_data_list()
        label_map: dict[str, Any] = {}
        file_mapping: dict[str, str] = {}
        target_files: list[Any] = []
        errors: list[str] = []

        for raw in data_list:
            label_path = self._resolve_label_attachment_path(raw, command.mapping)
            if not label_path:
                continue
            try:
                if label_path not in label_map:
                    label_map[label_path] = load_label_file(label_path)
                target_files.append(raw)
                file_mapping[raw.get_filepath()] = label_path
            except Exception as exc:
                filename = self._data_filename(raw)
                errors.append(f"{filename}: {exc!s}")
                logger.error(
                    "Failed to attach label for %s: %s",
                    filename,
                    exc,
                    exc_info=True,
                )

        if not target_files:
            return (
                "No labels attached. Check file name mapping.",
                {"success_count": 0, "errors": errors},
            )

        event_name_map = self._build_default_label_name_map(label_map)
        count = self.dataset.apply_labels_batch(
            target_files,
            label_map,
            file_mapping,
            event_name_map,
            None,
        )
        return (
            f"Attached labels to {count} file(s).",
            {"success_count": count, "errors": errors},
        )

    def handle_import_labels(self, command: Command) -> HandlerResult:
        if not isinstance(command, ImportLabelsCommand):
            raise TypeError("Invalid command for import_labels")

        plan = command.plan
        if not plan.label_map:
            raise PreconditionError("label_map is required.")

        target_files = self._target_files_for_label_plan(plan)
        if not target_files:
            raise PreconditionError("No target files were selected for label import.")

        selected_event_names = self._selected_event_names(plan.selected_event_names)
        mode = str(plan.mode or "batch").lower()
        file_mapping: dict[str, str] = {}
        if mode in {"batch", "timestamp"}:
            file_mapping = dict(plan.file_mapping)
            if not file_mapping and len(plan.label_map) == 1:
                label_name = next(iter(plan.label_map))
                file_mapping = {
                    target.get_filepath(): label_name for target in target_files
                }
            if not file_mapping:
                raise PreconditionError(
                    "file_mapping is required for batch label import.",
                )
            count = self.dataset.apply_labels_batch(
                target_files,
                dict(plan.label_map),
                file_mapping,
                plan.mapping,
                selected_event_names,
            )
        elif mode == "legacy":
            labels = next(iter(plan.label_map.values()), None)
            if labels is None:
                raise PreconditionError("labels are required for legacy import.")
            label_name = next(iter(plan.label_map), "")
            file_mapping = {
                self._data_filepath(target): str(label_name)
                for target in target_files
                if label_name
            }
            count = self.dataset.apply_labels_legacy(
                target_files,
                labels,
                plan.mapping,
                selected_event_names,
                force_import=plan.force_import,
            )
        else:
            raise ValueError(f"Unknown label import mode: {plan.mode}")

        label_import = self.interpretation.record_label_import_for_recipe(
            plan=plan,
            mode=mode,
            target_files=target_files,
            file_mapping=file_mapping,
            selected_event_names=selected_event_names,
            success_count=count,
        )
        return (
            f"Imported labels for {count} file(s).",
            {
                "success_count": count,
                "mode": mode,
                "target_count": len(target_files),
                "recipe_updated": label_import is not None,
                "label_import": label_import or {},
            },
        )

    def _target_files_for_label_plan(self, plan: LabelImportPlan) -> list[Any]:
        data_list = list(self.dataset.get_loaded_data_list() or [])
        if not plan.target_indices:
            return data_list
        return [
            data_list[int(index)]
            for index in plan.target_indices
            if 0 <= int(index) < len(data_list)
        ]

    @staticmethod
    def _selected_event_names(
        values: list[str] | tuple[str, ...] | set[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None
        return [str(value) for value in values if str(value)]

    @staticmethod
    def _resolve_label_attachment_path(raw: Any, mapping: dict[str, str]) -> str | None:
        filepath = raw.get_filepath()
        filename = raw.get_filename()
        return (
            mapping.get(filepath)
            or mapping.get(filename)
            or mapping.get(os.path.basename(filepath))
        )

    @staticmethod
    def _build_default_label_name_map(label_map: dict[str, Any]) -> dict[Any, str]:
        event_name_map: dict[Any, str] = {}
        for labels in label_map.values():
            if (
                isinstance(labels, list)
                and len(labels) > 0
                and isinstance(labels[0], dict)
            ):
                continue
            for label in np.array(labels).flatten():
                normalized = label.item() if isinstance(label, np.generic) else label
                event_name_map.setdefault(normalized, str(normalized))
        return event_name_map

    @staticmethod
    def _data_filename(data: Any) -> str:
        try:
            return str(data.get_filename())
        except Exception:
            return str(data)

    @staticmethod
    def _data_filepath(data: Any) -> str:
        try:
            return str(data.get_filepath())
        except Exception:
            return ""
