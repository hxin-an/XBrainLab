"""Apply helpers for reviewed Data Interpretation candidates."""

from __future__ import annotations

import contextlib
import csv
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np

from XBrainLab.backend.load_data.label_loader import load_label_file
from XBrainLab.backend.utils.logger import logger

from .commands import LabelImportPlan
from .data_interpretation import InterpretationCandidate
from .epoch_context import EPOCH_HINT_KEY


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


class DataInterpretationApplyService:
    """Apply reviewed metadata and label carriers to loaded EEG data."""

    def __init__(
        self,
        dataset_controller: Any,
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

        if updated:
            with contextlib.suppress(Exception):
                self.dataset.notify("data_changed")
        return updated

    def apply_label_carriers(
        self,
        candidate: InterpretationCandidate,
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

        if len(applicable) == 1 and len(target_files) == 1:
            carrier_path = str(applicable[0].get("path") or "").strip()
            file_mapping = {self._data_filepath(target_files[0]): carrier_path}
        else:
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
            mapping = self._label_import_mapping_from_class_map(candidate.class_map)
            if mode == "event_code":
                label_map, count = self._apply_reviewed_event_code_label_map(
                    mapped_target_files,
                    applicable,
                    file_mapping,
                    mapping,
                )
                selected_event_names = None
            else:
                label_map = self._load_reviewed_label_map(applicable, mode)
                selected_event_names = (
                    self._selected_event_names_for_sequence_plans(applicable)
                    if mode == "sequence"
                    else None
                )
                count = 0
            if mode == "timestamp":
                count = self._apply_reviewed_timestamp_label_map(
                    mapped_target_files,
                    applicable,
                    label_map,
                    file_mapping,
                    mapping,
                )
            elif mode == "anchored":
                count = self.dataset.apply_labels_batch(
                    mapped_target_files,
                    label_map,
                    file_mapping,
                    mapping,
                    None,
                )
            elif mode == "sequence":
                count = self._apply_reviewed_sequence_label_map(
                    mapped_target_files,
                    label_map,
                    file_mapping,
                    mapping,
                    selected_event_names,
                )
            self._ensure_all_mapped_labels_applied(count, len(mapped_target_files))
            plan = LabelImportPlan(
                target_indices=list(range(len(mapped_target_files))),
                label_map=label_map,
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
        return {
            "status": "applied",
            "success_count": int(count),
            "mode": mode,
            "label_import": record or {},
            "label_carrier": label_carriers[0],
            "label_carriers": label_carriers,
        }

    @staticmethod
    def _not_ready_label_plans(
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
            if status != "ready":
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
        mapping: dict[Any, str],
    ) -> tuple[dict[str, Any], int]:
        label_map = self._load_event_code_label_map(label_plans)
        success_count = 0
        for target in target_files:
            data_path = self._data_filepath(target)
            carrier_path = file_mapping.get(data_path)
            if carrier_path is None:
                continue
            code_rows = label_map.get(carrier_path)
            if not code_rows:
                continue
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
            delimiter = "\t" if Path(carrier_path).suffix.lower() == ".tsv" else ","
            rows: list[dict[str, str]] = []
            with Path(carrier_path).open(
                "r", encoding="utf-8-sig", newline=""
            ) as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                if not reader.fieldnames:
                    raise ValueError("Event-code label carrier has no header row.")
                normalized = {
                    field.lower().strip(): field for field in reader.fieldnames
                }
                code_column = normalized.get(code_field.lower())
                label_column = normalized.get(label_field.lower())
                if code_column is None or label_column is None:
                    raise ValueError(
                        "Event-code label carrier is missing selected columns.",
                    )
                for row in reader:
                    code = str(row.get(code_column) or "").strip()
                    label = str(row.get(label_column) or "").strip()
                    if code and label:
                        rows.append({"event_code": code, "label": label})
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
        if candidate.label_carrier_plan or not candidate.class_map:
            return []
        if (
            str(candidate.choices.get("label_carrier") or "").strip()
            != "embedded_events"
            and "internal_events" not in candidate.event_roles
        ):
            return []
        selected_events = self._internal_epoch_event_codes(candidate)
        event_label_aliases = {
            event_code: str(candidate.class_map.get(event_code) or event_code).strip()
            for event_code in selected_events
            if str(candidate.class_map.get(event_code) or event_code).strip()
        }
        records: list[dict[str, Any]] = []
        hint = {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "label_field": "Internal event",
            "time_field": "Event onset",
            "duration_field": "",
            "time_model": "sample_index_or_annotation_time",
            "granularity": "trial_or_event",
            "class_map": dict(candidate.class_map),
            "event_roles": dict(candidate.event_roles),
            "event_label_aliases": event_label_aliases,
            "recommended_events": selected_events,
        }
        for data in list(self.dataset.get_loaded_data_list() or []):
            setter = getattr(data, "set_runtime_detail", None)
            if not callable(setter):
                continue
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
            values = candidate.class_map.keys()

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
            label_map[carrier_path] = load_label_file(
                carrier_path,
                label_field=label_field,
                anchor=anchor if mode in {"timestamp", "anchored"} else None,
                duration_field=str(carrier.get("selected_duration_field") or "").strip()
                or None,
                sequence_only=mode == "sequence",
            )
        return label_map

    def _apply_reviewed_timestamp_label_map(
        self,
        target_files: list[Any],
        label_plans: list[dict[str, Any]],
        label_map: dict[str, Any],
        file_mapping: dict[str, str],
        mapping: dict[Any, str],
    ) -> int:
        plan_by_path = {
            str(plan.get("path") or "").strip(): plan for plan in label_plans
        }
        success_count = 0
        for target in target_files:
            data_path = self._data_filepath(target)
            carrier_path = file_mapping.get(data_path)
            if not carrier_path or carrier_path not in label_map:
                continue
            plan = plan_by_path.get(carrier_path, {})
            labels = label_map[carrier_path]
            if self._plan_uses_sample_index(plan):
                labels = self._timestamp_rows_from_sample_index(
                    labels,
                    sfreq=self._target_sample_frequency(target),
                )
            success_count += int(
                self.dataset.apply_labels_batch(
                    [target],
                    {carrier_path: labels},
                    {data_path: carrier_path},
                    mapping,
                    None,
                )
            )
        return success_count

    @staticmethod
    def _plan_uses_sample_index(plan: dict[str, Any]) -> bool:
        return str(plan.get("time_model") or "").strip().lower() == "sample_index"

    @staticmethod
    def _timestamp_rows_from_sample_index(labels: Any, *, sfreq: float) -> list[Any]:
        if sfreq <= 0:
            raise ValueError(
                "EEG sample frequency is required for sample-index labels.",
            )
        if not isinstance(labels, list):
            return labels
        converted: list[Any] = []
        for item in labels:
            if not isinstance(item, dict):
                converted.append(item)
                continue
            row = dict(item)
            try:
                row["onset"] = float(row["onset"]) / sfreq
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Sample-index label row has no numeric sample.",
                ) from exc
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
                    labels=label_map.get(carrier_path),
                    mode=mode,
                ),
            )

    def _epoch_hint_from_label_plan(
        self,
        plan: dict[str, Any],
        *,
        candidate: InterpretationCandidate,
        labels: Any,
        mode: str,
    ) -> dict[str, Any]:
        class_map = dict(candidate.class_map)
        return {
            "source": self._epoch_hint_source(plan),
            "placement_method": str(plan.get("placement_method") or "").strip(),
            "label_field": str(plan.get("selected_label_field") or "").strip(),
            "time_field": str(plan.get("selected_anchor") or "").strip(),
            "duration_field": str(plan.get("selected_duration_field") or "").strip(),
            "time_model": str(plan.get("time_model") or "").strip(),
            "granularity": str(plan.get("granularity") or "").strip(),
            "class_map": class_map,
            "event_roles": dict(candidate.event_roles),
            "recommended_events": [str(value) for value in class_map.values()],
            "duration_stats": self._duration_stats_from_loaded_labels(labels)
            or dict(plan.get("selected_duration_stats") or {}),
            "label_import_mode": mode,
        }

    @staticmethod
    def _epoch_hint_source(plan: dict[str, Any]) -> str:
        if str(plan.get("format") or "") == "BIDS events":
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
        label_map: dict[str, Any],
        file_mapping: dict[str, str],
        mapping: dict[Any, str],
        selected_event_names: set[str] | None,
    ) -> int:
        success_count = 0
        for target in target_files:
            data_path = self._data_filepath(target)
            carrier_path = file_mapping.get(data_path)
            if not carrier_path or carrier_path not in label_map:
                continue
            success_count += int(
                self.dataset.apply_labels_batch(
                    [target],
                    {carrier_path: label_map[carrier_path]},
                    {data_path: carrier_path},
                    mapping,
                    selected_event_names,
                ),
            )
        return success_count

    @staticmethod
    def _selected_event_names_for_sequence_plans(
        label_plans: list[dict[str, Any]],
    ) -> set[str] | None:
        selected: list[str] = []
        for carrier in label_plans:
            if str(carrier.get("placement_method") or "").strip() != "eeg_event":
                continue
            raw_values = carrier.get("selected_target_event_codes")
            if isinstance(raw_values, str):
                values = raw_values.split(",")
            elif isinstance(raw_values, (list, tuple, set)):
                values = raw_values
            else:
                anchor = str(carrier.get("selected_anchor") or "").strip()
                values = [anchor] if anchor and anchor != "trial order" else []
            for value in values:
                text = str(value).strip()
                if text and text != "trial order" and text not in selected:
                    selected.append(text)
        return set(selected) if selected else None

    def _reviewed_label_file_mapping(
        self,
        label_plans: list[dict[str, Any]],
        target_files: list[Any],
    ) -> tuple[dict[str, str], str | None]:
        manual_mapping_requested = any(
            str(carrier.get("selected_target_file") or "").strip()
            for carrier in label_plans
        )
        file_mapping: dict[str, str] = {}
        used_carriers: set[str] = set()
        remaining_plans: list[dict[str, Any]] = []
        for carrier in label_plans:
            carrier_path = str(carrier.get("path") or "").strip()
            selected_target = str(carrier.get("selected_target_file") or "").strip()
            if not selected_target:
                remaining_plans.append(carrier)
                continue
            target = self._target_file_for_reviewed_label_choice(
                target_files,
                selected_target,
            )
            if target is None:
                return (
                    {},
                    (
                        "Reviewed label carrier target file does not match a "
                        f"loaded EEG file: {selected_target}."
                    ),
                )
            data_path = self._data_filepath(target)
            if data_path in file_mapping:
                return (
                    {},
                    "Multiple reviewed label carriers target the same EEG file.",
                )
            if not carrier_path:
                return {}, "Reviewed label carrier is missing a usable path."
            file_mapping[data_path] = carrier_path
            used_carriers.add(carrier_path)

        carrier_by_key: dict[str, str] = {}
        for carrier in remaining_plans:
            carrier_path = str(carrier.get("path") or "").strip()
            key = self._label_mapping_key(carrier_path)
            if not carrier_path or not key:
                return {}, "Reviewed label carrier is missing a usable path."
            if key in carrier_by_key:
                return (
                    {},
                    "Multiple reviewed label carriers match the same EEG file stem.",
                )
            carrier_by_key[key] = carrier_path

        for target in target_files:
            data_path = self._data_filepath(target)
            if data_path in file_mapping:
                continue
            key = self._label_mapping_key(data_path)
            carrier_path = carrier_by_key.get(key)
            if not carrier_path:
                if manual_mapping_requested:
                    continue
                return (
                    {},
                    (
                        "No reviewed label carrier uniquely matches loaded EEG "
                        f"file {Path(data_path).name}."
                    ),
                )
            file_mapping[data_path] = carrier_path
            used_carriers.add(carrier_path)

        unused = sorted(set(carrier_by_key.values()) - used_carriers)
        if unused:
            return (
                {},
                "Reviewed label carriers did not all match loaded EEG files.",
            )
        return file_mapping, None

    def _target_file_for_reviewed_label_choice(
        self,
        target_files: list[Any],
        selected_target: str,
    ) -> Any | None:
        selected = selected_target.strip()
        for target in target_files:
            data_path = self._data_filepath(target)
            filename = self._data_filename(target)
            if selected in {data_path, filename, Path(data_path).name}:
                return target
        return None

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
    def _label_mapping_key(path: str) -> str:
        name = Path(path).name
        lowered = name.lower()
        if lowered.endswith(".fif.gz"):
            stem = name[: -len(".fif.gz")]
        else:
            stem = Path(name).stem
        normalized = stem.lower()
        for suffix in (
            "_events",
            "-events",
            "_labels",
            "-labels",
            "_label",
            "-label",
            "_raw",
            "-raw",
            "_eeg",
            "-eeg",
        ):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized.strip()

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
        time_model = str(plan.get("time_model") or "").strip().lower()
        granularity = str(plan.get("granularity") or "").strip().lower()
        return (
            carrier_format in {"MAT", "MAT labels", "TXT", "CSV", "TSV", "BIDS events"}
            and bool(str(plan.get("selected_label_field") or "").strip())
            and time_model == "trial_order"
            and granularity == "trial"
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
