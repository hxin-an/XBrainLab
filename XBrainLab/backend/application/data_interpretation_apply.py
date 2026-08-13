"""Apply helpers for reviewed Data Interpretation candidates."""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable, Iterable
from numbers import Real
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np

from XBrainLab.backend.event_semantics import mark_gdf_rejected_trials
from XBrainLab.backend.load_data.raw import (
    SOURCE_CONTENT_IDENTITY_RUNTIME_KEY,
    Raw,
    normalize_source_content_identity,
)
from XBrainLab.backend.services.dataset_state_service import DatasetInterpretationPort
from XBrainLab.backend.services.label_import_errors import (
    AtomicLabelApplyError,
    AtomicLabelStateUnknownError,
)
from XBrainLab.backend.services.label_import_service import (
    LabelImportService,
)
from XBrainLab.backend.utils.logger import logger

from .commands import LabelImportPlan
from .data_interpretation import InterpretationCandidate
from .data_interpretation_bids import prepare_bids_timestamp_rows_for_placement
from .data_interpretation_bids_channels import apply_bids_channel_review
from .data_interpretation_content_identity import assert_review_content_unchanged
from .data_interpretation_event_values import (
    class_map_from_value_decisions,
    filter_kept_label_values,
)
from .data_interpretation_pairing import resolve_label_file_pairing
from .epoch_context import EPOCH_HINT_KEY
from .errors import ApplicationError
from .label_resource_admission import AdmittedLabelResourceSession
from .results import ErrorType


class LabelImportRecorder(Protocol):
    def __call__(
        self,
        *,
        plan: LabelImportPlan,
        mode: str,
        target_files: list[Any],
        file_mapping: dict[str, str],
        selected_event_names: set[str] | None,
        success_count: int,
    ) -> dict[str, Any] | None: ...


class TimestampLabelStateUnknownError(ApplicationError):
    """Non-recoverable application error for incomplete label rollback."""

    state_unknown = True

    def __init__(self, error: AtomicLabelStateUnknownError) -> None:
        rollback_failures = [
            {
                "target_path": failure.target_path,
                "exception_type": failure.exception_type,
                "message": failure.message,
            }
            for failure in error.rollback_failures
        ]
        super().__init__(
            message=str(error),
            error_type=ErrorType.INTERNAL,
            recoverable=False,
            diagnostics={
                "state_unknown": True,
                "retryable": False,
                "command_effect_may_have_applied": True,
                "operation_name": error.operation_name,
                "commit_error": str(error.commit_error),
                "commit_exception_type": type(error.commit_error).__name__,
                "rollback_failures": rollback_failures,
            },
        )


class DataInterpretationApplyService:
    """Apply reviewed metadata and label carriers to loaded EEG data."""

    def __init__(
        self,
        dataset_controller: DatasetInterpretationPort,
        *,
        data_filename: Callable[[Any], str],
        data_filepath: Callable[[Any], str],
        record_label_import: LabelImportRecorder,
    ) -> None:
        self.dataset = dataset_controller
        self._data_filename = data_filename
        self._data_filepath = data_filepath
        self._record_label_import = record_label_import

    def apply_candidate_metadata_to_loaded_data(
        self,
        candidate: InterpretationCandidate,
    ) -> list[dict[str, str]]:
        """Mirror reviewed interpretation metadata onto loaded Raw wrappers."""
        metadata_by_path = {
            self._path_key(item.file): item for item in candidate.metadata
        }
        metadata_by_name = {Path(item.file).name: item for item in candidate.metadata}
        updated: list[dict[str, str]] = []
        for data in list(self.dataset.get_loaded_data_list() or []):
            filepath = self._safe_data_filepath(data)
            metadata = metadata_by_path.get(self._path_key(filepath))
            if metadata is None:
                metadata = metadata_by_name.get(Path(filepath).name)
            if metadata is None:
                continue

            values = {
                "subject": str(metadata.subject.value or ""),
                "session": str(metadata.session.value or ""),
                "task": str(metadata.task.value or ""),
                "run": str(metadata.run.value or ""),
            }
            if values["subject"] and hasattr(data, "set_subject_name"):
                data.set_subject_name(values["subject"])
            if values["session"] and hasattr(data, "set_session_name"):
                data.set_session_name(values["session"])
            if hasattr(data, "set_runtime_detail"):
                data.set_runtime_detail("data_interpretation_metadata", values)
            updated.append({"file": Path(filepath).name, **values})

        return updated

    def detached_copy(
        self,
        dataset_controller: DatasetInterpretationPort,
        *,
        record_label_import: LabelImportRecorder,
    ) -> DataInterpretationApplyService:
        """Create the same apply policy over a detached Dataset holder."""
        return type(self)(
            dataset_controller,
            data_filename=self._data_filename,
            data_filepath=self._data_filepath,
            record_label_import=record_label_import,
        )

    def bind_source_content_identity(
        self,
        candidate: InterpretationCandidate,
    ) -> list[dict[str, Any]]:
        """Attach reviewed EEG byte identities without rereading source files."""
        files = candidate.content_identity.get("files")
        if not isinstance(files, list):
            return []
        selected_paths = {self._path_key(item) for item in candidate.selected_eeg_files}
        identity_by_path: dict[str, dict[str, Any]] = {}
        for item in files:
            if not isinstance(item, dict) or item.get("role") != "selected_eeg":
                continue
            path = self._path_key(str(item.get("path") or ""))
            if not path:
                raise ValueError("Reviewed EEG content identity is invalid.")
            try:
                identity_by_path[path] = normalize_source_content_identity(
                    {
                        "algorithm": "sha256",
                        "sha256": item.get("sha256"),
                        "file_bytes": item.get("file_bytes"),
                    }
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("Reviewed EEG content identity is invalid.") from exc

        bound: list[dict[str, Any]] = []
        for data in list(self.dataset.get_loaded_data_list() or []):
            path = self._path_key(self._safe_data_filepath(data))
            identity = identity_by_path.get(path)
            if identity is None:
                if path in selected_paths:
                    raise ValueError(
                        "Reviewed EEG content identity is missing for a loaded file."
                    )
                continue
            typed_setter = getattr(data, "set_source_content_identity", None)
            if callable(typed_setter):
                typed_setter(identity)
            else:
                setter = getattr(data, "set_runtime_detail", None)
                if not callable(setter):
                    raise TypeError(
                        "Loaded EEG data cannot retain its reviewed content identity."
                    )
                setter(SOURCE_CONTENT_IDENTITY_RUNTIME_KEY, identity)
            bound.append({"file": Path(path).name, **identity})
        return bound

    def apply_bids_channels(
        self,
        candidate: InterpretationCandidate,
    ) -> list[dict[str, Any]]:
        """Apply exact local BIDS channels.tsv types, units, and status."""
        review = candidate.bids.get("channel_review")
        if not isinstance(review, dict):
            return []
        return apply_bids_channel_review(
            review=review,
            loaded_data=list(self.dataset.get_loaded_data_list() or []),
            data_filepath=self._data_filepath,
        )

    def apply_label_carriers(
        self,
        candidate: InterpretationCandidate,
        label_resources: AdmittedLabelResourceSession | None = None,
        *,
        recheck_content_identity: bool = True,
    ) -> dict[str, Any]:
        """Apply reviewed label carriers after interpretation apply."""
        if not candidate.label_carrier_plan:
            return {"status": "not_applicable", "reason": "No label carrier plan."}

        not_ready = self._not_ready_label_plans(candidate.label_carrier_plan)
        if not_ready:
            return {
                "status": "failed",
                "reason": (
                    "Label placement is not ready: "
                    + "; ".join(self._label_plan_name(item) for item in not_ready)
                    + "."
                ),
                "success_count": 0,
            }

        timestamp_applicable = [
            item
            for item in candidate.label_carrier_plan
            if self._is_auto_applicable_timestamp_label_plan(item)
        ]
        anchored_applicable = [
            item
            for item in candidate.label_carrier_plan
            if self._is_auto_applicable_anchored_label_plan(item, candidate.class_map)
        ]
        sequence_applicable = [
            item
            for item in candidate.label_carrier_plan
            if self._is_auto_applicable_sequence_label_plan(item, candidate.class_map)
        ]
        event_code_applicable = [
            item
            for item in candidate.label_carrier_plan
            if self._is_auto_applicable_event_code_label_plan(item, candidate.class_map)
        ]
        if (
            not timestamp_applicable
            and not anchored_applicable
            and not sequence_applicable
            and not event_code_applicable
        ):
            return {
                "status": "failed",
                "reason": ("No reviewed label carrier is safe to apply automatically."),
                "success_count": 0,
            }

        applicable_groups = [
            group
            for group in (
                timestamp_applicable,
                anchored_applicable,
                event_code_applicable,
                sequence_applicable,
            )
            if group
        ]
        if len(applicable_groups) > 1:
            return {
                "status": "failed",
                "reason": (
                    "Reviewed label carriers use mixed placement modes. "
                    "Import one placement mode at a time or remap labels first."
                ),
                "success_count": 0,
            }

        applicable = (
            timestamp_applicable
            or anchored_applicable
            or event_code_applicable
            or sequence_applicable
        )
        if label_resources is None:
            raise ValueError(
                "Reviewed external labels require an admitted bounded reader."
            )
        if timestamp_applicable:
            mode = "timestamp"
        elif anchored_applicable:
            mode = "anchored"
        elif event_code_applicable:
            mode = "event_code"
        else:
            mode = "sequence"

        target_files = list(self.dataset.get_loaded_data_list() or [])
        if not target_files:
            return {
                "status": "skipped",
                "reason": "Automatic label application found no loaded EEG files.",
            }

        file_mapping, reason = self._reviewed_label_file_mapping(
            applicable,
            target_files,
        )
        if reason:
            return {"status": "skipped", "reason": reason}

        carrier_label = ", ".join(
            str(item.get("path") or "").strip() for item in applicable
        )
        mapped_target_files = [
            target
            for target in target_files
            if self._data_filepath(target) in file_mapping
        ]
        if not mapped_target_files:
            return {
                "status": "skipped",
                "reason": "Reviewed label carriers did not map to any loaded EEG file.",
            }

        try:
            if recheck_content_identity:
                self._assert_reviewed_label_content_is_current(candidate)
            bids_placement: list[dict[str, Any]] = []
            mapping = self._label_import_mapping_from_class_map(candidate.class_map)
            if mode == "event_code":
                label_map, count = self._apply_reviewed_event_code_label_map(
                    mapped_target_files,
                    applicable,
                    file_mapping,
                    candidate,
                    label_resources,
                )
                selected_event_names = None
            else:
                label_map = self._load_reviewed_label_map(
                    applicable,
                    mode,
                    label_resources,
                )
                selected_event_names = (
                    self._selected_event_names_for_sequence_plans(applicable)
                    if mode == "sequence"
                    else None
                )
                count = 0
            if mode in {"timestamp", "anchored"}:
                count, bids_placement = self._apply_reviewed_timestamp_label_map(
                    mapped_target_files,
                    applicable,
                    label_map,
                    file_mapping,
                    candidate,
                )
            elif mode == "sequence":
                count = self._apply_reviewed_sequence_label_map(
                    mapped_target_files,
                    applicable,
                    label_map,
                    file_mapping,
                    mapping,
                    selected_event_names,
                    candidate,
                )
            self._ensure_all_mapped_labels_applied(count, len(mapped_target_files))
            plan = LabelImportPlan(
                target_indices=list(range(len(mapped_target_files))),
                label_paths=sorted(label_map),
                mapping=mapping,
                file_mapping=file_mapping,
                mode=mode,
            )
            record = self._record_label_import(
                plan=plan,
                mode=mode,
                target_files=mapped_target_files,
                file_mapping=file_mapping,
                selected_event_names=selected_event_names,
                success_count=count,
            )
            self._record_epoch_hints(
                candidate=candidate,
                label_plans=applicable,
                target_files=mapped_target_files,
                file_mapping=file_mapping,
                label_map=label_map,
                mode=mode,
            )
        except AtomicLabelStateUnknownError as exc:
            raise TimestampLabelStateUnknownError(exc) from exc
        except AtomicLabelApplyError as exc:
            logger.error(
                "Atomic reviewed label application failed during %s.",
                exc.phase,
                exc_info=True,
            )
            return {
                "status": "failed",
                "reason": exc.user_message,
                "success_count": 0,
                "failure": {
                    "code": exc.error_code,
                    "phase": exc.phase,
                    "recoverable": exc.recoverable,
                    "state_unknown": exc.state_unknown,
                },
            }
        except Exception as exc:
            logger.error(
                "Failed to apply reviewed label carrier %s: %s",
                carrier_label,
                exc,
                exc_info=True,
            )
            return {"status": "failed", "reason": str(exc), "success_count": 0}

        if count <= 0:
            return {
                "status": "failed",
                "reason": "Reviewed label carrier did not match any loaded EEG file.",
                "success_count": 0,
            }
        label_carriers = sorted(label_map)
        result = {
            "status": "applied",
            "success_count": int(count),
            "mode": mode,
            "label_import": record or {},
            "label_carrier": label_carriers[0],
            "label_carriers": label_carriers,
        }
        if mode == "timestamp":
            result["bids_placement"] = bids_placement
        return result

    @staticmethod
    def _assert_reviewed_label_content_is_current(
        candidate: InterpretationCandidate,
    ) -> None:
        if not candidate.content_identity:
            return
        assert_review_content_unchanged(
            expected=candidate.content_identity,
            label_carrier_plan=candidate.label_carrier_plan,
            selected_eeg_files=candidate.selected_eeg_files,
            class_map=candidate.class_map,
            event_roles=candidate.event_roles,
            run_event_mappings=candidate.run_event_mappings,
            candidate_id=candidate.candidate_id,
        )

    @classmethod
    def _not_ready_label_plans(
        cls,
        label_plans: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for plan in label_plans:
            review = plan.get("placement_review")
            status = (
                str(review.get("status") or "").strip()
                if isinstance(review, dict)
                else ""
            )
            unresolved_sequence_target = (
                str(plan.get("time_model") or "").strip().lower() == "trial_order"
                and str(plan.get("placement_method") or "").strip().lower()
                in {"", "eeg_event"}
                and not cls._sequence_target_event_names(plan)
            )
            if status != "ready" or unresolved_sequence_target:
                result.append(plan)
        return result

    @staticmethod
    def _label_plan_name(plan: dict[str, Any]) -> str:
        name = str(plan.get("name") or "").strip()
        if name:
            return name
        path = str(plan.get("path") or "").strip()
        return Path(path).name if path else "unnamed label carrier"

    @staticmethod
    def _ensure_all_mapped_labels_applied(count: int, expected: int) -> None:
        if count == expected:
            return
        raise ValueError(
            f"Applied labels to {count}/{expected} mapped EEG file(s).",
        )

    def _apply_reviewed_event_code_label_map(
        self,
        target_files: list[Any],
        label_plans: list[dict[str, Any]],
        file_mapping: dict[str, str],
        candidate: InterpretationCandidate,
        label_resources: AdmittedLabelResourceSession,
    ) -> tuple[dict[str, Any], int]:
        label_map = self._load_event_code_label_map(
            label_plans,
            label_resources,
        )
        plan_by_path = {
            str(plan.get("path") or "").strip(): plan for plan in label_plans
        }
        success_count = 0
        for target in target_files:
            data_path = self._data_filepath(target)
            carrier_path = file_mapping.get(data_path)
            if carrier_path is None:
                continue
            code_rows = label_map.get(carrier_path)
            if not code_rows:
                continue
            mapping = self._mapping_for_target(
                candidate,
                target,
                plan=plan_by_path.get(carrier_path),
            )
            events, _event_id = target.get_event_list()
            remapped_events, remapped_event_id = self._remap_events_by_label_codes(
                events,
                code_rows,
                mapping,
            )
            target.set_event(remapped_events, remapped_event_id)
            setter = getattr(target, "set_labels_imported", None)
            if callable(setter):
                setter(True)
            success_count += 1
        return label_map, success_count

    def _load_event_code_label_map(
        self,
        label_plans: list[dict[str, Any]],
        label_resources: AdmittedLabelResourceSession,
    ) -> dict[str, list[dict[str, str]]]:
        label_map: dict[str, list[dict[str, str]]] = {}
        for carrier in label_plans:
            carrier_path = str(carrier.get("path") or "").strip()
            code_field = str(carrier.get("selected_anchor") or "").strip()
            label_field = str(carrier.get("selected_label_field") or "").strip()
            if not carrier_path or not code_field or not label_field:
                raise ValueError(
                    "Reviewed event-code label carrier is missing code or label field.",
                )
            loaded = label_resources.load(carrier_path)
            if not isinstance(loaded, list) or not all(
                isinstance(row, dict) for row in loaded
            ):
                raise ValueError(
                    "Event-code label carrier did not produce row records."
                )
            rows = []
            for item in loaded:
                code = str(item.get("onset") or "").strip()
                label = str(item.get("label") or "").strip()
                if code and label:
                    rows.append({"event_code": code, "label": label})
            rows = self._filter_reviewed_label_values(rows, carrier)
            if not rows:
                raise ValueError("Event-code label carrier contains no usable rows.")
            label_map[carrier_path] = rows
        return label_map

    @staticmethod
    def _remap_events_by_label_codes(
        events: Any,
        code_rows: list[dict[str, str]],
        mapping: dict[Any, str],
    ) -> tuple[Any, dict[str, int]]:
        code_to_label: dict[str, str] = {}
        for row in code_rows:
            code = str(row.get("event_code") or "").strip()
            label = str(row.get("label") or "").strip()
            if not code or not label:
                continue
            existing = code_to_label.get(code)
            if existing is not None and existing != label:
                raise ValueError(f"Event code {code} maps to multiple labels.")
            code_to_label[code] = label
        event_array = events.copy()
        selected_rows: list[Any] = []
        label_to_code: dict[str, int] = {}
        event_id: dict[str, int] = {}
        for row in event_array:
            event_code = str(row[-1]).strip()
            if event_code not in code_to_label:
                continue
            label_value = code_to_label[event_code]
            display_name = str(mapping.get(label_value, label_value)).strip()
            if display_name not in label_to_code:
                next_code = len(label_to_code) + 1
                label_to_code[display_name] = next_code
                event_id[display_name] = next_code
            updated = row.copy()
            updated[-1] = label_to_code[display_name]
            selected_rows.append(updated)
        if not selected_rows:
            raise ValueError("No EEG events matched reviewed event-code labels.")
        return np.asarray(selected_rows, dtype=event_array.dtype), event_id

    def record_internal_epoch_hints(
        self,
        candidate: InterpretationCandidate,
    ) -> list[dict[str, Any]]:
        """Persist internal-event class choices for later epoch setup."""
        if candidate.label_carrier_plan or not (
            candidate.class_map or candidate.run_event_mappings
        ):
            return []
        if (
            str(candidate.choices.get("label_carrier") or "").strip()
            != "embedded_events"
            and "internal_events" not in candidate.event_roles
        ):
            return []
        selected_events = self._internal_epoch_event_codes(candidate)
        records: list[dict[str, Any]] = []
        for data in list(self.dataset.get_loaded_data_list() or []):
            mark_gdf_rejected_trials(data)
            setter = getattr(data, "set_runtime_detail", None)
            if not callable(setter):
                continue
            class_map = self._class_map_for_target(candidate, data)
            event_label_aliases = {
                event_code: str(class_map.get(event_code) or event_code).strip()
                for event_code in selected_events
                if str(class_map.get(event_code) or event_code).strip()
            }
            hint = {
                "source": "Labels inside EEG files",
                "placement_method": "internal_events",
                "label_field": "Internal event",
                "time_field": "Event onset",
                "duration_field": "",
                "time_model": "sample_index_or_annotation_time",
                "granularity": "trial_or_event",
                "class_map": class_map,
                "event_roles": dict(candidate.event_roles),
                "event_label_aliases": event_label_aliases,
                "recommended_events": selected_events,
            }
            setter(EPOCH_HINT_KEY, hint)
            records.append(
                {"file": self._safe_data_filepath(data), "source": hint["source"]}
            )
        return records

    @staticmethod
    def _internal_epoch_event_codes(candidate: InterpretationCandidate) -> list[str]:
        selection = dict(candidate.internal_event_selection or {})
        values = selection.get("label_event_codes")
        if not isinstance(values, (list, tuple, set)):
            values = [
                code
                for mapping in candidate.run_event_mappings.values()
                for code in mapping
            ] or candidate.class_map.keys()

        def sort_key(value: str) -> tuple[int, int | str]:
            text = str(value).strip()
            return (0, int(text)) if text.isdigit() else (1, text.casefold())

        return sorted(
            {str(item).strip() for item in values if str(item).strip()},
            key=sort_key,
        )

    @staticmethod
    def _load_reviewed_label_map(
        label_plans: list[dict[str, Any]],
        mode: str,
        label_resources: AdmittedLabelResourceSession,
    ) -> dict[str, Any]:
        label_map: dict[str, Any] = {}
        for carrier in label_plans:
            carrier_path = str(carrier.get("path") or "").strip()
            label_field = str(carrier.get("selected_label_field") or "").strip()
            anchor = str(carrier.get("selected_anchor") or "").strip()
            needs_anchor = mode in {"timestamp", "anchored"}
            if not carrier_path or not label_field or (needs_anchor and not anchor):
                raise ValueError(
                    "Reviewed label carrier is missing label field or anchor.",
                )
            labels = label_resources.load(carrier_path)
            label_map[carrier_path] = (
                labels
                if mode == "timestamp"
                else DataInterpretationApplyService._filter_reviewed_label_values(
                    labels,
                    carrier,
                )
            )
        return label_map

    def _apply_reviewed_timestamp_label_map(
        self,
        target_files: list[Any],
        label_plans: list[dict[str, Any]],
        label_map: dict[str, Any],
        file_mapping: dict[str, str],
        candidate: InterpretationCandidate,
    ) -> tuple[int, list[dict[str, Any]]]:
        plan_by_path = {
            str(plan.get("path") or "").strip(): plan for plan in label_plans
        }
        placement_records: list[dict[str, Any]] = []
        prepared: list[tuple[Any, str, str, dict[str, Any], list[dict[str, Any]]]] = []
        for target in target_files:
            data_path = self._data_filepath(target)
            carrier_path = file_mapping.get(data_path)
            if not carrier_path or carrier_path not in label_map:
                continue
            plan = plan_by_path.get(carrier_path, {})
            labels = label_map[carrier_path]
            labels, placement_record = prepare_bids_timestamp_rows_for_placement(
                labels,
                plan,
            )
            labels = self._filter_reviewed_label_values(labels, plan)
            labels = self._timestamp_row_records(labels)
            labels = self._timestamp_rows_with_value_decisions(labels, plan)
            if self._plan_uses_sample_index(plan):
                labels = self._timestamp_rows_from_sample_index(
                    labels,
                    sfreq=self._target_sample_frequency(target),
                    first_samp=self._target_first_sample(target),
                    sample_index_base=str(plan.get("sample_index_base") or ""),
                    sample_index_origin=str(plan.get("sample_index_origin") or ""),
                )
            label_map[carrier_path] = labels
            if placement_record is not None:
                placement_records.append(placement_record)
            prepared.append(
                (
                    target,
                    data_path,
                    carrier_path,
                    self._mapping_for_target(candidate, target, plan=plan),
                    labels,
                )
            )
        success_count = self._apply_timestamp_targets_atomically(prepared)
        return success_count, placement_records

    @staticmethod
    def _plan_uses_sample_index(plan: dict[str, Any]) -> bool:
        return str(plan.get("time_model") or "").strip().lower() == "sample_index"

    @staticmethod
    def _timestamp_rows_from_sample_index(
        labels: Any,
        *,
        sfreq: float,
        first_samp: int,
        sample_index_base: str,
        sample_index_origin: str,
    ) -> list[Any]:
        if sfreq <= 0:
            raise ValueError(
                "EEG sample frequency is required for sample-index labels.",
            )
        if not isinstance(labels, list):
            raise ValueError("Sample-index labels must be timestamp row records.")
        base = str(sample_index_base).strip().lower()
        origin = str(sample_index_origin).strip().lower()
        if base not in {"zero_based", "one_based"} or origin not in {
            "recording_relative",
            "absolute",
        }:
            raise ValueError(
                "Sample-index labels require an explicit zero/one-based and "
                "recording-relative/absolute contract.",
            )
        base_offset = 1 if base == "one_based" else 0
        converted: list[Any] = []
        for row_index, item in enumerate(labels, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Sample-index label row {row_index} is not a record.")
            row = dict(item)
            try:
                raw_sample = float(row["onset"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Sample-index label row has no numeric sample.",
                ) from exc
            if not math.isfinite(raw_sample) or not raw_sample.is_integer():
                raise ValueError(
                    "Sample-index label row must contain a finite integer sample.",
                )
            normalized_sample = int(raw_sample) - base_offset
            absolute_sample = (
                first_samp + normalized_sample
                if origin == "recording_relative"
                else normalized_sample
            )
            row["onset"] = (absolute_sample - first_samp) / sfreq
            if "duration" in row and row["duration"] not in (None, ""):
                try:
                    row["duration"] = float(row["duration"]) / sfreq
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "Sample-index label row has non-numeric duration.",
                    ) from exc
            converted.append(row)
        return converted

    @staticmethod
    def _timestamp_row_records(labels: Any) -> list[dict[str, Any]]:
        if isinstance(labels, list):
            if not all(isinstance(item, dict) for item in labels):
                raise ValueError("Timestamp label payload contains a non-row value.")
            return [dict(item) for item in labels]
        array = np.asarray(labels)
        if array.ndim != 2 or array.shape[1] != 3:
            raise ValueError("Sample-anchored labels are not MNE event rows.")
        return [
            {
                "onset": DataInterpretationApplyService._python_scalar(row[0]),
                "duration": 0.0,
                "label": DataInterpretationApplyService._python_scalar(row[2]),
            }
            for row in array
        ]

    @staticmethod
    def _timestamp_rows_with_value_decisions(
        labels: list[dict[str, Any]],
        plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raw_decisions = plan.get("value_decisions")
        if not isinstance(raw_decisions, dict):
            return [dict(row) for row in labels]
        decisions = {
            DataInterpretationApplyService._label_value_key(key): value
            for key, value in raw_decisions.items()
            if DataInterpretationApplyService._label_value_key(key)
            and isinstance(value, dict)
        }
        enriched: list[dict[str, Any]] = []
        for row_index, item in enumerate(labels, start=1):
            row = dict(item)
            raw_value = DataInterpretationApplyService._label_value_key(
                row.get("label")
            )
            decision = decisions.get(raw_value)
            if not isinstance(decision, dict) or decision.get("decision") != "resolved":
                raise ValueError(
                    f"Timestamp label row {row_index} has no resolved semantic "
                    f"decision for {raw_value or 'an empty value'}.",
                )
            if decision.get("keep_event") is not True:
                raise ValueError(
                    "Timestamp semantic enrichment received an excluded label row.",
                )
            use_as_class = decision.get("use_as_class")
            if not isinstance(use_as_class, bool):
                raise ValueError(
                    f"Timestamp label row {row_index} has no class-use decision.",
                )
            row["role"] = str(decision.get("role") or "unknown")
            row["use_as_class"] = use_as_class
            if use_as_class:
                class_name = str(decision.get("class_name") or "").strip()
                if not class_name:
                    raise ValueError(
                        f"Timestamp label row {row_index} has no reviewed class name.",
                    )
                row["class_name"] = class_name
            enriched.append(row)
        return enriched

    def _apply_timestamp_targets_atomically(
        self,
        prepared: list[tuple[Any, str, str, dict[Any, str], list[dict[str, Any]]]],
    ) -> int:
        if not prepared:
            return 0
        operations = [
            (cast(Raw, target), labels, mapping)
            for target, _data_path, _carrier_path, mapping, labels in prepared
        ]
        return LabelImportService().apply_timestamp_labels_atomically(operations)

    @staticmethod
    def _python_scalar(value: Any) -> Any:
        return value.item() if isinstance(value, np.generic) else value

    @staticmethod
    def _label_value_key(value: Any) -> str:
        value = DataInterpretationApplyService._python_scalar(value)
        if isinstance(value, Real) and not isinstance(value, bool):
            numeric = float(value)
            if not math.isfinite(numeric):
                return ""
            return str(int(numeric)) if numeric.is_integer() else str(value).strip()
        return str(value or "").strip()

    @staticmethod
    def _target_sample_frequency(target: Any) -> float:
        getter = getattr(target, "get_sfreq", None)
        if callable(getter):
            value = getter()
            if value:
                return float(cast(Any, value))
        get_mne = getattr(target, "get_mne", None)
        if callable(get_mne):
            mne_obj = get_mne()
            info = getattr(mne_obj, "info", {}) or {}
            value = info.get("sfreq") if isinstance(info, dict) else None
            if value:
                return float(cast(Any, value))
        raise ValueError("EEG sample frequency is required for sample-index labels.")

    @staticmethod
    def _target_first_sample(target: Any) -> int:
        get_mne = getattr(target, "get_mne", None)
        if not callable(get_mne):
            return 0
        mne_obj = get_mne()
        value = getattr(mne_obj, "first_samp", 0)
        if isinstance(value, int):
            return value
        if isinstance(value, np.integer):
            return int(value)
        return 0

    def _record_epoch_hints(
        self,
        *,
        candidate: InterpretationCandidate,
        label_plans: list[dict[str, Any]],
        target_files: list[Any],
        file_mapping: dict[str, str],
        label_map: dict[str, Any],
        mode: str,
    ) -> None:
        plan_by_path = {
            str(plan.get("path") or "").strip(): plan for plan in label_plans
        }
        for target in target_files:
            setter = getattr(target, "set_runtime_detail", None)
            if not callable(setter):
                continue
            carrier_path = file_mapping.get(self._data_filepath(target), "")
            plan = plan_by_path.get(carrier_path)
            if not plan:
                continue
            setter(
                EPOCH_HINT_KEY,
                self._epoch_hint_from_label_plan(
                    plan,
                    candidate=candidate,
                    class_map=self._class_map_for_target(
                        candidate,
                        target,
                        plan=plan,
                    ),
                    labels=label_map.get(carrier_path),
                    mode=mode,
                ),
            )

    def _epoch_hint_from_label_plan(
        self,
        plan: dict[str, Any],
        *,
        candidate: InterpretationCandidate,
        class_map: dict[str, str],
        labels: Any,
        mode: str,
    ) -> dict[str, Any]:
        bids_duration_evidence = self._bids_duration_epoch_evidence(plan)
        bids_duration_stats = (
            None
            if bids_duration_evidence is None
            else bids_duration_evidence["duration_stats"]
        )
        hint: dict[str, Any] = {
            "source": self._epoch_hint_source(plan, candidate=candidate),
            "placement_method": str(plan.get("placement_method") or "").strip(),
            "label_field": str(plan.get("selected_label_field") or "").strip(),
            "time_field": str(plan.get("selected_anchor") or "").strip(),
            "duration_field": str(plan.get("selected_duration_field") or "").strip(),
            "time_model": str(plan.get("time_model") or "").strip(),
            "granularity": str(plan.get("granularity") or "").strip(),
            "class_map": class_map,
            "event_roles": dict(candidate.event_roles),
            "recommended_events": [str(value) for value in class_map.values()],
            "duration_stats": (
                bids_duration_stats
                if bids_duration_stats is not None
                else self._duration_stats_from_loaded_labels(labels)
                or dict(plan.get("selected_duration_stats") or {})
            ),
            "label_import_mode": mode,
        }
        bids_review = plan.get("bids_event_review")
        if not isinstance(bids_review, dict):
            return hint
        placement = bids_review.get("placement")
        if not isinstance(placement, dict):
            return hint
        if bids_duration_evidence is not None:
            hint.update(bids_duration_evidence)
        hint["excluded_event_count"] = int(placement.get("excluded_event_count", 0))
        return hint

    @staticmethod
    def _epoch_hint_source(
        plan: dict[str, Any],
        *,
        candidate: InterpretationCandidate,
    ) -> str:
        if (
            candidate.source_kind == "bids"
            and str(plan.get("format") or "") == "BIDS events"
        ):
            return "BIDS events.tsv"
        return "Loaded label file"

    @staticmethod
    def _duration_stats_from_loaded_labels(labels: Any) -> dict[str, Any]:
        if not isinstance(labels, list):
            return {}
        values: list[float] = []
        for item in labels:
            if not isinstance(item, dict) or "duration" not in item:
                continue
            try:
                value = float(item["duration"])
            except (TypeError, ValueError):
                continue
            values.append(value)
        return DataInterpretationApplyService._duration_stats_from_values(values)

    @staticmethod
    def _duration_stats_from_bids_review(
        plan: dict[str, Any],
    ) -> dict[str, Any] | None:
        evidence = DataInterpretationApplyService._bids_duration_epoch_evidence(plan)
        return None if evidence is None else evidence["duration_stats"]

    @staticmethod
    def _bids_duration_epoch_evidence(
        plan: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Build internally consistent duration evidence for selected class rows."""
        review = plan.get("bids_event_review")
        if not isinstance(review, dict):
            return None
        row_evidence = review.get("row_evidence")
        if not isinstance(row_evidence, list):
            return {
                "duration_stats": {},
                "placement_event_count": 0,
                "unknown_duration_count": 0,
                "unknown_duration_rows": [],
            }
        values: list[float] = []
        selected_rows: list[dict[str, Any]] = []
        unknown_rows: list[int] = []
        for row in row_evidence:
            if not isinstance(row, dict) or row.get("placement_status") != "usable":
                continue
            value_decision = row.get("value_decision")
            if (
                not isinstance(value_decision, dict)
                or value_decision.get("use_as_class") is not True
            ):
                continue
            selected_rows.append(row)
            if row.get("duration_provenance") != "known":
                if row.get("row") is not None:
                    unknown_rows.append(int(row["row"]))
                continue
            raw_duration = row.get("raw_duration")
            if raw_duration is None:
                if row.get("row") is not None:
                    unknown_rows.append(int(row["row"]))
                continue
            try:
                value = float(cast(Any, raw_duration))
            except (TypeError, ValueError):
                if row.get("row") is not None:
                    unknown_rows.append(int(row["row"]))
                continue
            if np.isfinite(value):
                values.append(value)
            elif row.get("row") is not None:
                unknown_rows.append(int(row["row"]))
        return {
            "duration_stats": (
                DataInterpretationApplyService._duration_stats_from_values(values)
            ),
            "placement_event_count": len(selected_rows),
            "unknown_duration_count": len(selected_rows) - len(values),
            "unknown_duration_rows": unknown_rows,
        }

    @staticmethod
    def _duration_stats_from_values(values: list[float]) -> dict[str, Any]:
        if not values:
            return {}
        counts: dict[str, int] = {}
        for value in values:
            key = f"{value:g}"
            counts[key] = counts.get(key, 0) + 1
        return {
            "row_count": len(values),
            "value_counts": dict(sorted(counts.items())),
            "numeric_count": len(values),
            "min": min(values),
            "max": max(values),
        }

    def _apply_reviewed_sequence_label_map(
        self,
        target_files: list[Any],
        label_plans: list[dict[str, Any]],
        label_map: dict[str, Any],
        file_mapping: dict[str, str],
        mapping: dict[Any, str],
        selected_event_names: set[str] | None,
        candidate: InterpretationCandidate,
    ) -> int:
        return self._apply_reviewed_mapped_label_map(
            target_files=target_files,
            label_plans=label_plans,
            label_map=label_map,
            file_mapping=file_mapping,
            default_mapping=mapping,
            selected_event_names=selected_event_names,
            candidate=candidate,
        )

    def _apply_reviewed_mapped_label_map(
        self,
        *,
        target_files: list[Any],
        label_plans: list[dict[str, Any]],
        label_map: dict[str, Any],
        file_mapping: dict[str, str],
        default_mapping: dict[Any, str],
        selected_event_names: set[str] | None,
        candidate: InterpretationCandidate,
    ) -> int:
        applicable_file_mapping: dict[str, str] = {}
        for target in target_files:
            data_path = self._data_filepath(target)
            carrier_path = file_mapping.get(data_path)
            if carrier_path and carrier_path in label_map:
                applicable_file_mapping[data_path] = carrier_path
        applicable_label_map = {
            carrier_path: label_map[carrier_path]
            for carrier_path in applicable_file_mapping.values()
        }
        applicable_targets = [
            target
            for target in target_files
            if self._data_filepath(target) in applicable_file_mapping
        ]
        if not applicable_targets:
            return 0
        if self._has_per_run_mapping(candidate, label_plans):
            plan_by_path = {
                str(plan.get("path") or "").strip(): plan for plan in label_plans
            }
            count = 0
            for target in applicable_targets:
                data_path = self._data_filepath(target)
                carrier_path = applicable_file_mapping[data_path]
                plan = plan_by_path.get(carrier_path, {})
                count += int(
                    self.dataset.apply_labels_batch(
                        [target],
                        {carrier_path: label_map[carrier_path]},
                        {data_path: carrier_path},
                        self._mapping_for_target(candidate, target, plan=plan),
                        selected_event_names,
                    )
                )
            return count
        return int(
            self.dataset.apply_labels_batch(
                applicable_targets,
                applicable_label_map,
                applicable_file_mapping,
                default_mapping,
                selected_event_names,
            ),
        )

    def _mapping_for_target(
        self,
        candidate: InterpretationCandidate,
        target: Any,
        *,
        plan: dict[str, Any] | None = None,
    ) -> dict[Any, str]:
        class_map = self._class_map_for_target(
            candidate,
            target,
            plan=plan,
        )
        return self._label_import_mapping_from_class_map(class_map)

    def _class_map_for_target(
        self,
        candidate: InterpretationCandidate,
        target: Any,
        *,
        plan: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        if isinstance(plan, dict) and isinstance(plan.get("value_decisions"), dict):
            return class_map_from_value_decisions(plan["value_decisions"])
        run_mapping = self._run_mapping_for_target(candidate, target, plan=plan)
        if plan is None and candidate.internal_event_preview.get(
            "run_dependent_semantics"
        ):
            return {
                code: run_mapping.get(code) or code
                for code in self._internal_epoch_event_codes(candidate)
            }
        result = dict(candidate.class_map)
        if isinstance(plan, dict):
            plan_mapping = plan.get("run_class_map")
            if isinstance(plan_mapping, dict):
                reviewed_mapping = {
                    str(key): str(value)
                    for key, value in plan_mapping.items()
                    if str(key).strip() and str(value).strip()
                }
                if isinstance(plan.get("bids_event_review"), dict):
                    result = reviewed_mapping
                else:
                    result.update(reviewed_mapping)
        result.update(run_mapping)
        return result

    @staticmethod
    def _filter_reviewed_label_values(
        labels: Any,
        plan: dict[str, Any],
    ) -> Any:
        decisions = plan.get("value_decisions")
        if not isinstance(decisions, dict):
            return labels

        def is_kept(item: Any) -> bool:
            raw_value: Any = item
            if isinstance(item, dict):
                raw_value = item.get("label")
            elif isinstance(item, (list, tuple, np.ndarray)):
                if len(item) == 0:
                    raise ValueError("Reviewed label row is empty.")
                raw_value = item[-1]
            return bool(filter_kept_label_values([raw_value], decisions))

        if isinstance(labels, np.ndarray):
            if labels.ndim == 0:
                return labels if is_kept(labels.item()) else labels.reshape(-1)[:0]
            mask = np.asarray([is_kept(item) for item in labels], dtype=bool)
            return labels[mask]
        if isinstance(labels, list):
            return [item for item in labels if is_kept(item)]
        if isinstance(labels, tuple):
            return tuple(item for item in labels if is_kept(item))
        raise ValueError("Reviewed label payload has an unsupported value shape.")

    def _run_mapping_for_target(
        self,
        candidate: InterpretationCandidate,
        target: Any,
        *,
        plan: dict[str, Any] | None,
    ) -> dict[str, str]:
        target_path = self._data_filepath(target)
        keys = [target_path, Path(target_path).name]
        if isinstance(plan, dict):
            carrier_path = str(plan.get("path") or "").strip()
            keys.extend([carrier_path, Path(carrier_path).name if carrier_path else ""])
        run_values = [
            str(metadata.run.value or "").strip()
            for metadata in candidate.metadata
            if str(metadata.run.value or "").strip()
        ]
        for metadata in candidate.metadata:
            if self._path_key(metadata.file) != self._path_key(target_path) and (
                Path(metadata.file).name != Path(target_path).name
            ):
                continue
            run = str(metadata.run.value or "").strip()
            if run and run_values.count(run) == 1:
                keys.extend([run, f"run-{run}"])
            break
        for key in keys:
            mapping = candidate.run_event_mappings.get(key)
            if isinstance(mapping, dict):
                return {
                    str(code): str(label)
                    for code, label in mapping.items()
                    if str(code).strip() and str(label).strip()
                }
        return {}

    @staticmethod
    def _has_per_run_mapping(
        candidate: InterpretationCandidate,
        label_plans: list[dict[str, Any]],
    ) -> bool:
        if candidate.run_event_mappings:
            return True
        signatures = {
            tuple(sorted((str(key), str(value)) for key, value in mapping.items()))
            for plan in label_plans
            if isinstance((mapping := plan.get("run_class_map")), dict) and mapping
        }
        return len(signatures) > 1

    @staticmethod
    def _selected_event_names_for_sequence_plans(
        label_plans: list[dict[str, Any]],
    ) -> set[str] | None:
        selected: list[str] = []
        for carrier in label_plans:
            if str(carrier.get("placement_method") or "").strip() not in {
                "",
                "eeg_event",
            }:
                continue
            target_events = DataInterpretationApplyService._sequence_target_event_names(
                carrier,
            )
            if not target_events:
                return None
            for event_name in sorted(target_events):
                if event_name not in selected:
                    selected.append(event_name)
        return set(selected) if selected else None

    @staticmethod
    def _sequence_target_event_names(plan: dict[str, Any]) -> set[str]:
        raw_values = plan.get("selected_target_event_codes")
        if isinstance(raw_values, str):
            values: Iterable[Any] = raw_values.split(",")
        elif isinstance(raw_values, (list, tuple, set)):
            values = raw_values
        else:
            values = []
        selected = {
            text
            for value in values
            if (text := str(value).strip()) and text != "trial order"
        }
        if selected:
            return selected
        anchor = str(plan.get("selected_anchor") or "").strip()
        return {anchor} if anchor and anchor != "trial order" else set()

    def _reviewed_label_file_mapping(
        self,
        label_plans: list[dict[str, Any]],
        target_files: list[Any],
    ) -> tuple[dict[str, str], str | None]:
        target_paths = [self._data_filepath(target) for target in target_files]
        pairing = resolve_label_file_pairing(label_plans, target_paths)
        return (
            dict(pairing.file_mapping),
            None if pairing.complete else pairing.blocking_reason(),
        )

    def _safe_data_filepath(self, data: Any) -> str:
        with contextlib.suppress(Exception):
            return str(self._data_filepath(data))
        return str(getattr(data, "filepath", ""))

    @staticmethod
    def _path_key(path: str) -> str:
        if not path:
            return ""
        with contextlib.suppress(Exception):
            return str(Path(path).resolve())
        return str(path)

    @staticmethod
    def _is_auto_applicable_timestamp_label_plan(plan: dict[str, Any]) -> bool:
        carrier_format = str(plan.get("format") or "").strip()
        placement_method = str(plan.get("placement_method") or "").strip().lower()
        time_model = str(plan.get("time_model") or "").strip().lower()
        return (
            carrier_format in {"BIDS events", "CSV", "TSV"}
            and placement_method != "event_code"
            and bool(str(plan.get("selected_label_field") or "").strip())
            and bool(str(plan.get("selected_anchor") or "").strip())
            and time_model in {"seconds", "relative_time", "sample_index"}
        )

    @staticmethod
    def _is_auto_applicable_anchored_label_plan(
        plan: dict[str, Any],
        class_map: dict[str, str],
    ) -> bool:
        carrier_format = str(plan.get("format") or "").strip()
        time_model = str(plan.get("time_model") or "").strip().lower()
        granularity = str(plan.get("granularity") or "").strip().lower()
        return (
            carrier_format in {"MAT", "MAT labels"}
            and bool(str(plan.get("selected_label_field") or "").strip())
            and bool(str(plan.get("selected_anchor") or "").strip())
            and time_model == "sample_index"
            and granularity == "trial"
            and bool(class_map)
        )

    @staticmethod
    def _is_auto_applicable_sequence_label_plan(
        plan: dict[str, Any],
        class_map: dict[str, str],
    ) -> bool:
        carrier_format = str(plan.get("format") or "").strip()
        placement_method = str(plan.get("placement_method") or "").strip().lower()
        time_model = str(plan.get("time_model") or "").strip().lower()
        granularity = str(plan.get("granularity") or "").strip().lower()
        return (
            carrier_format in {"MAT", "MAT labels", "TXT", "CSV", "TSV", "BIDS events"}
            and placement_method in {"", "eeg_event"}
            and bool(str(plan.get("selected_label_field") or "").strip())
            and time_model == "trial_order"
            and granularity == "trial"
            and bool(DataInterpretationApplyService._sequence_target_event_names(plan))
            and bool(class_map)
        )

    @staticmethod
    def _is_auto_applicable_event_code_label_plan(
        plan: dict[str, Any],
        class_map: dict[str, str],
    ) -> bool:
        carrier_format = str(plan.get("format") or "").strip()
        placement_method = str(plan.get("placement_method") or "").strip().lower()
        return (
            carrier_format in {"CSV", "TSV", "BIDS events"}
            and placement_method == "event_code"
            and bool(str(plan.get("selected_label_field") or "").strip())
            and bool(str(plan.get("selected_anchor") or "").strip())
            and bool(class_map)
        )

    @staticmethod
    def _label_import_mapping_from_class_map(
        class_map: dict[str, str],
    ) -> dict[Any, str]:
        mapping: dict[Any, str] = {}
        for key, value in class_map.items():
            normalized_key: Any = key
            with contextlib.suppress(ValueError):
                normalized_key = int(key)
            mapping[normalized_key] = str(value)
        return mapping
