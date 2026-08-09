"""Legacy data/label compatibility handlers for the application command spine."""

from __future__ import annotations

import copy
import os
from typing import Any

from XBrainLab.backend.services.dataset_state_service import DatasetInterpretationPort

from .commands import (
    AttachLabelsCommand,
    Command,
    CommandName,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    PreviewLabelImportCommand,
)
from .data_interpretation_path_identity import (
    deduplicate_resolved_paths,
    resolved_path_identity,
    resolved_path_value,
)
from .data_load_resource_receipt import DataLoadResourceReceiptAuthority
from .errors import ApplicationError, PreconditionError
from .label_import_policy import materialize_reviewed_label_map
from .label_import_preview import (
    LabelImportPreviewService,
    LabelPreviewTargetIdentity,
)
from .label_resource_admission import (
    LabelResourceAdmissionService,
    specs_from_paths,
)
from .resource_guard import check_import_resource_preflight
from .results import ErrorType

HandlerResult = str | tuple[str, dict[str, Any]]


class DataCompatibilityCommandService:
    """Handle legacy data loading and post-load label compatibility commands."""

    def __init__(
        self,
        *,
        dataset: DatasetInterpretationPort,
        interpretation: Any,
        pipeline_transaction: Any,
    ) -> None:
        self.dataset = dataset
        self.interpretation = interpretation
        self._pipeline_transaction = pipeline_transaction
        self._load_resource_receipts = DataLoadResourceReceiptAuthority()
        self._attach_label_resources = LabelResourceAdmissionService(
            command_name=CommandName.ATTACH_LABELS.value,
        )
        self._label_import_previews = LabelImportPreviewService(
            command_name=CommandName.IMPORT_LABELS.value,
        )

    def handle_load_data(self, command: Command) -> HandlerResult:
        if not isinstance(command, LoadDataCommand):
            raise TypeError("Invalid command for load_data")
        if not command.paths:
            raise PreconditionError("paths list cannot be empty.")
        preflight = self._load_resource_receipts.annotate(
            command,
            check_import_resource_preflight(command.paths),
        )
        preflight = self._load_resource_receipts.authorize(command, preflight)
        import_paths, duplicate_count = self._new_import_paths(command)
        if not import_paths:
            return (
                "No new files loaded; the selected files are already present.",
                {
                    "success_count": 0,
                    "errors": [],
                    "allow_append": command.allow_append,
                    "skipped_duplicate_count": duplicate_count,
                    "resource_preflight": preflight.to_diagnostics(),
                },
            )

        training_boundary = self._pipeline_transaction.begin_raw_replacement()
        snapshot = self._pipeline_transaction.capture()
        try:
            if not command.allow_append:
                self._pipeline_transaction.prepare_raw_replacement()
            count, errors = self.dataset.import_files(import_paths)
            expected_count = len(import_paths)
            self._ensure_complete_batch(
                count=count,
                expected_count=expected_count,
                errors=errors,
                allow_append=command.allow_append,
                resource_preflight=preflight.to_diagnostics(),
            )
            trainer_retired = self._pipeline_transaction.commit_pipeline_invalidation(
                training_boundary,
            )
        except Exception:
            self._pipeline_transaction.restore(snapshot)
            raise
        return (
            f"Loaded {count} file(s).",
            {
                "success_count": count,
                "errors": [],
                "allow_append": command.allow_append,
                "trainer_retired": trainer_retired,
                "skipped_duplicate_count": duplicate_count,
                "resource_preflight": preflight.to_diagnostics(),
            },
        )

    def _new_import_paths(self, command: LoadDataCommand) -> tuple[list[str], int]:
        """Return one ordered import batch and the number of skipped duplicates."""
        unique_paths = list(dict.fromkeys(str(path) for path in command.paths))
        duplicate_count = len(command.paths) - len(unique_paths)
        if not command.allow_append:
            return unique_paths, duplicate_count

        existing_paths = {
            str(raw.get_filepath())
            for raw in list(self.dataset.get_loaded_data_list() or [])
            if callable(getattr(raw, "get_filepath", None))
        }
        import_paths = [path for path in unique_paths if path not in existing_paths]
        duplicate_count += len(unique_paths) - len(import_paths)
        return import_paths, duplicate_count

    @staticmethod
    def _ensure_complete_batch(
        *,
        count: int,
        expected_count: int,
        errors: list[str],
        allow_append: bool,
        resource_preflight: dict[str, Any],
    ) -> None:
        """Reject an incomplete batch before its temporary state can commit."""
        if not errors and count == expected_count:
            return
        error_text = "; ".join(str(error) for error in errors)
        error_type = ErrorType.RUNTIME
        if "Unsupported format" in error_text:
            error_type = ErrorType.UNSUPPORTED_FORMAT
        elif "File corrupted" in error_text:
            error_type = ErrorType.FILE_CORRUPTED
        raise ApplicationError(
            message=(
                "Failed to load all selected EEG files; the active dataset was "
                f"restored ({count}/{expected_count} files read successfully)."
            ),
            error_type=error_type,
            recoverable=True,
            diagnostics={
                "success_count": 0,
                "attempted_success_count": count,
                "expected_count": expected_count,
                "errors": list(errors),
                "allow_append": allow_append,
                "rolled_back": True,
                "resource_preflight": resource_preflight,
            },
        )

    def handle_attach_labels(self, command: Command) -> HandlerResult:
        if not isinstance(command, AttachLabelsCommand):
            raise TypeError("Invalid command for attach_labels")
        if not command.mapping:
            raise PreconditionError("mapping is required.")
        label_paths = self._validated_attach_label_paths(command)

        target_files, file_mapping = self._resolve_requested_label_attachments(
            list(self.dataset.get_loaded_data_list() or []),
            command.mapping,
            label_paths=label_paths,
        )

        session = self._attach_label_resources.admit(
            specs_from_paths(label_paths),
            confirmed=command.resource_preflight_confirmed,
            token=command.resource_preflight_token,
            configuration={
                "mapping": {
                    str(key): self._path_key(value)
                    for key, value in command.mapping.items()
                },
                "label_format": str(command.label_format or "").strip().lower(),
                "selected_event_names": sorted(
                    self._selected_event_names(command.selected_event_names) or []
                ),
            },
        )
        # Review each parser result before loading the next declared resource.
        label_map, review = materialize_reviewed_label_map(
            label_paths,
            load=session.load,
            error_code="label_mapping_cardinality_exceeded",
            normalize_value=self._normalize_label_value,
        )
        event_name_map = {label: str(label) for label in review.unique_labels}
        selected_event_names = self._selected_event_names(command.selected_event_names)
        count = self.dataset.apply_labels_batch(
            target_files,
            label_map,
            file_mapping,
            event_name_map,
            selected_event_names,
        )
        self._ensure_complete_label_batch(
            count=count,
            expected_count=len(target_files),
            mode="attach",
        )
        return (
            f"Attached labels to {count} file(s).",
            {
                "success_count": count,
                "errors": [],
                "resource_preflight": session.resource_preflight,
            },
        )

    def handle_import_labels(self, command: Command) -> HandlerResult:
        if isinstance(command, PreviewLabelImportCommand):
            return self._handle_preview_label_import(command)
        if not isinstance(command, ImportLabelsCommand):
            raise TypeError("Invalid command for import_labels")

        plan = command.plan
        label_paths = self._validated_import_label_paths(plan)

        preview_materialized = (
            self._label_import_previews.materialize(
                plan=plan,
                confirmed=command.resource_preflight_confirmed,
                token=command.resource_preflight_token,
                configuration={"purpose": "consume_label_import_preview"},
                target_identity=self._label_preview_target_identity(),
            )
            if plan.preview_id
            else None
        )

        target_files = self._target_files_for_label_plan(plan)
        if not target_files:
            raise PreconditionError("No target files were selected for label import.")

        selected_event_names = self._selected_event_names(plan.selected_event_names)
        mode = str(plan.mode or "").strip()
        file_mapping: dict[str, str] = {}
        if mode in {"batch", "timestamp", "sequence"}:
            file_mapping = {
                str(data_path): self._admitted_label_path(label_path, label_paths)
                for data_path, label_path in plan.file_mapping.items()
            }
            if not file_mapping and len(label_paths) == 1:
                label_name = label_paths[0]
                file_mapping = {
                    target.get_filepath(): label_name for target in target_files
                }
            if not file_mapping:
                raise PreconditionError(
                    "file_mapping is required for batch label import.",
                )
            self._ensure_file_mapping_uses_admitted_paths(
                file_mapping,
                label_paths=label_paths,
            )
            self._ensure_file_mapping_covers_targets(
                file_mapping,
                target_files=target_files,
            )
            materialized = preview_materialized
            if materialized is None:
                materialized = self._label_import_previews.materialize(
                    plan=plan,
                    confirmed=command.resource_preflight_confirmed,
                    token=command.resource_preflight_token,
                    configuration={
                        "target_indices": list(plan.target_indices),
                        "file_mapping": file_mapping,
                        "mapping": plan.mapping,
                        "mode": mode,
                        "selected_event_names": selected_event_names,
                        "force_import": bool(plan.force_import),
                    },
                    target_identity=self._label_preview_target_identity(),
                )
            label_map = materialized.label_map
        else:
            raise ValueError(f"Unknown label import mode: {plan.mode}")

        pipeline_snapshot = self._pipeline_transaction.capture()
        raw_label_snapshots = self._capture_raw_label_states(target_files)
        try:
            count = self.dataset.apply_labels_batch(
                target_files,
                label_map,
                file_mapping,
                plan.mapping,
                selected_event_names,
            )
            self._ensure_complete_label_batch(
                count=count,
                expected_count=len(target_files),
                mode=mode,
            )
            label_import = self.interpretation.record_label_import_for_recipe(
                plan=plan,
                mode=mode,
                target_files=target_files,
                file_mapping=file_mapping,
                selected_event_names=selected_event_names,
                success_count=count,
            )
        except Exception as exc:
            rollback_errors = self._rollback_label_import(
                pipeline_snapshot=pipeline_snapshot,
                raw_label_snapshots=raw_label_snapshots,
            )
            diagnostics = (
                dict(exc.diagnostics) if isinstance(exc, ApplicationError) else {}
            )
            diagnostics.update(
                {
                    "success_count": 0,
                    "expected_count": len(target_files),
                    "mode": mode,
                    "rolled_back": not rollback_errors,
                    "rollback_errors": rollback_errors,
                }
            )
            raise ApplicationError(
                message=(
                    "Label import failed; raw events and interpretation state "
                    "were restored."
                    if not rollback_errors
                    else "Label import failed and rollback was incomplete."
                ),
                error_type=(
                    exc.error_type
                    if isinstance(exc, ApplicationError)
                    else ErrorType.INTERNAL
                ),
                recoverable=not rollback_errors,
                diagnostics=diagnostics,
            ) from exc
        return (
            f"Imported labels for {count} file(s).",
            {
                "success_count": count,
                "mode": mode,
                "target_count": len(target_files),
                "recipe_updated": label_import is not None,
                "label_import": label_import or {},
                "resource_preflight": materialized.resource_preflight,
            },
        )

    @staticmethod
    def _capture_raw_label_states(target_files: list[Any]) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for target in target_files:
            get_mne = getattr(target, "get_mne", None)
            mne_data = get_mne() if callable(get_mne) else None
            copy_mne_data = getattr(mne_data, "copy", None)
            is_labels_imported = getattr(target, "is_labels_imported", None)
            snapshots.append(
                {
                    "target": target,
                    "mne_data": (copy_mne_data() if callable(copy_mne_data) else None),
                    "raw_events": copy.deepcopy(getattr(target, "raw_events", None)),
                    "raw_event_id": copy.deepcopy(
                        getattr(target, "raw_event_id", None)
                    ),
                    "labels_imported": (
                        bool(is_labels_imported())
                        if callable(is_labels_imported)
                        else copy.deepcopy(getattr(target, "labels_imported", None))
                    ),
                    "detected_events_cache": copy.deepcopy(
                        getattr(target, "_detected_events_cache", None)
                    ),
                }
            )
        return snapshots

    def _rollback_label_import(
        self,
        *,
        pipeline_snapshot: Any,
        raw_label_snapshots: list[dict[str, Any]],
    ) -> list[str]:
        errors: list[str] = []
        for snapshot in raw_label_snapshots:
            error = self._restore_raw_label_state_error(snapshot)
            if error:
                errors.append(error)
        try:
            self._pipeline_transaction.restore(pipeline_snapshot)
        except Exception as exc:  # pragma: no cover - defensive corruption path
            errors.append(f"pipeline: {type(exc).__name__}: {exc}")
        return errors

    def _restore_raw_label_state_error(
        self,
        snapshot: dict[str, Any],
    ) -> str:
        try:
            self._restore_raw_label_state(snapshot)
        except Exception as exc:  # pragma: no cover - defensive corruption path
            return (
                f"{self._data_filepath(snapshot['target'])}: "
                f"{type(exc).__name__}: {exc}"
            )
        return ""

    @staticmethod
    def _restore_raw_label_state(snapshot: dict[str, Any]) -> None:
        target = snapshot["target"]
        mne_data = snapshot["mne_data"]
        if mne_data is not None:
            target.raw_events = None
            target.raw_event_id = None
            target.set_mne(mne_data.copy())
        if hasattr(target, "raw_events"):
            target.raw_events = copy.deepcopy(snapshot["raw_events"])
        if hasattr(target, "raw_event_id"):
            target.raw_event_id = copy.deepcopy(snapshot["raw_event_id"])
        set_labels_imported = getattr(target, "set_labels_imported", None)
        if callable(set_labels_imported):
            set_labels_imported(bool(snapshot["labels_imported"]))
        elif hasattr(target, "labels_imported"):
            target.labels_imported = copy.deepcopy(snapshot["labels_imported"])
        if hasattr(target, "_detected_events_cache"):
            target._detected_events_cache = copy.deepcopy(
                snapshot["detected_events_cache"]
            )

    def _handle_preview_label_import(
        self,
        command: PreviewLabelImportCommand,
    ) -> HandlerResult:
        label_paths = self._normalized_label_paths(command.label_paths)
        if not label_paths:
            raise PreconditionError("label_paths is required for label preview.")
        summary, resource_preflight = self._label_import_previews.preview(
            label_paths=label_paths,
            label_configs=command.label_configs,
            confirmed=command.resource_preflight_confirmed,
            token=command.resource_preflight_token,
            target_identity=self._label_preview_target_identity(),
        )
        return (
            f"Reviewed {len(label_paths)} label file(s).",
            {
                "payload_type": "label_import_preview",
                "label_preview": summary,
                "resource_preflight": resource_preflight,
            },
        )

    def _label_preview_target_identity(self) -> LabelPreviewTargetIdentity:
        raw_targets = tuple(self.dataset.get_loaded_data_list() or ())
        return LabelPreviewTargetIdentity(
            dataset=self.dataset,
            raw_targets=raw_targets,
            raw_paths=tuple(self._data_filepath(target) for target in raw_targets),
        )

    @classmethod
    def _validated_attach_label_paths(
        cls,
        command: AttachLabelsCommand,
    ) -> list[str]:
        declared = cls._normalized_label_paths(command.label_paths)
        mapped = cls._normalized_label_paths(command.mapping.values())
        if not declared:
            raise PreconditionError("label_paths is required for label attachment.")
        if {cls._path_key(path) for path in declared} != {
            cls._path_key(path) for path in mapped
        }:
            raise PreconditionError(
                "label_paths must exactly match the paths in attachment mapping.",
                diagnostics={
                    "code": "label_resource_scope_mismatch",
                    "declared_paths": declared,
                    "mapped_paths": mapped,
                },
            )
        return declared

    @classmethod
    def _validated_import_label_paths(cls, plan: LabelImportPlan) -> list[str]:
        paths = cls._normalized_label_paths(plan.label_paths)
        if not paths:
            raise PreconditionError("label_paths is required for label import.")
        return paths

    @classmethod
    def _ensure_file_mapping_uses_admitted_paths(
        cls,
        file_mapping: dict[str, str],
        *,
        label_paths: list[str],
    ) -> None:
        mapped_paths = list(file_mapping.values())
        mapped_identities = {cls._path_key(path) for path in mapped_paths}
        declared_identities = {cls._path_key(path) for path in label_paths}
        if mapped_identities != declared_identities:
            raise PreconditionError(
                "file_mapping must use every and only the admitted label_paths.",
                diagnostics={
                    "code": "label_resource_scope_mismatch",
                    "declared_paths": label_paths,
                    "mapped_paths": sorted(mapped_paths),
                },
            )

    @classmethod
    def _ensure_file_mapping_covers_targets(
        cls,
        file_mapping: dict[str, str],
        *,
        target_files: list[Any],
    ) -> None:
        expected = {cls._data_filepath(target) for target in target_files}
        observed = set(file_mapping)
        if observed == expected:
            return
        raise PreconditionError(
            "file_mapping must provide exactly one label for every selected target.",
            diagnostics={
                "code": "label_target_mapping_incomplete",
                "missing_targets": sorted(expected - observed),
                "unexpected_targets": sorted(observed - expected),
            },
        )

    @classmethod
    def _normalized_label_paths(cls, paths: Any) -> list[str]:
        return deduplicate_resolved_paths(paths)

    @staticmethod
    def _path_key(path: Any) -> str:
        return resolved_path_identity(path)

    @staticmethod
    def _path_value(path: Any) -> str:
        return resolved_path_value(path)

    @classmethod
    def _admitted_label_path(cls, path: Any, label_paths: list[str]) -> str:
        identity = cls._path_key(path)
        for admitted_path in label_paths:
            if cls._path_key(admitted_path) == identity:
                return admitted_path
        return cls._path_value(path)

    @staticmethod
    def _ensure_complete_label_batch(
        *,
        count: int,
        expected_count: int,
        mode: str,
        errors: list[str] | None = None,
    ) -> None:
        """Reject any label batch that did not atomically update every target."""
        if count == expected_count:
            return
        raise ApplicationError(
            message=(
                "Failed to apply labels to all selected EEG files; no label "
                f"changes were committed ({count}/{expected_count} targets reported)."
            ),
            error_type=ErrorType.RUNTIME,
            recoverable=True,
            diagnostics={
                "success_count": 0,
                "attempted_success_count": count,
                "expected_count": expected_count,
                "mode": mode,
                "errors": list(errors or []),
                "rolled_back": True,
            },
        )

    def _target_files_for_label_plan(self, plan: LabelImportPlan) -> list[Any]:
        data_list = list(self.dataset.get_loaded_data_list() or [])
        if not plan.target_indices:
            return data_list
        indices: list[int] = []
        for raw_index in plan.target_indices:
            try:
                index = int(raw_index)
            except (TypeError, ValueError) as exc:
                raise PreconditionError(
                    f"Invalid label target index: {raw_index!r}.",
                    diagnostics={"code": "label_target_index_invalid"},
                ) from exc
            if index < 0 or index >= len(data_list):
                raise PreconditionError(
                    f"Invalid label target index {index}; no target was changed.",
                    diagnostics={
                        "code": "label_target_index_invalid",
                        "target_index": index,
                        "target_count": len(data_list),
                    },
                )
            indices.append(index)
        if len(set(indices)) != len(indices):
            raise PreconditionError(
                "Duplicate label target indices are not allowed.",
                diagnostics={"code": "label_target_index_duplicate"},
            )
        return [data_list[index] for index in indices]

    @classmethod
    def _resolve_requested_label_attachments(
        cls,
        data_list: list[Any],
        mapping: dict[str, str],
        *,
        label_paths: list[str],
    ) -> tuple[list[Any], dict[str, str]]:
        requested = {str(key): value for key, value in mapping.items()}
        consumed: set[str] = set()
        targets: list[Any] = []
        file_mapping: dict[str, str] = {}
        for raw in data_list:
            filepath = cls._data_filepath(raw)
            candidates = (filepath, cls._data_filename(raw), os.path.basename(filepath))
            matched_keys = [
                key for key in dict.fromkeys(candidates) if key in requested
            ]
            if len(matched_keys) > 1:
                raise PreconditionError(
                    f"Multiple label mappings refer to requested target {filepath}.",
                    diagnostics={"code": "label_target_mapping_ambiguous"},
                )
            if not matched_keys:
                continue
            key = matched_keys[0]
            consumed.add(key)
            targets.append(raw)
            file_mapping[filepath] = cls._admitted_label_path(
                requested[key],
                label_paths,
            )
        missing = sorted(set(requested) - consumed)
        if missing:
            raise PreconditionError(
                "A requested target for label attachment is not loaded.",
                diagnostics={
                    "code": "label_target_missing",
                    "missing_targets": missing,
                },
            )
        if not targets:
            raise PreconditionError(
                "No requested target files were selected for label attachment.",
                diagnostics={"code": "label_target_missing"},
            )
        return targets, file_mapping

    @staticmethod
    def _selected_event_names(
        values: list[str] | tuple[str, ...] | set[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None
        normalized = sorted(
            {str(value).strip() for value in values if str(value).strip()},
            key=lambda value: (value.casefold(), value),
        )
        return normalized or None

    @staticmethod
    def _normalize_label_value(value: Any) -> Any:
        item = getattr(value, "item", None)
        return item() if callable(item) else value

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
