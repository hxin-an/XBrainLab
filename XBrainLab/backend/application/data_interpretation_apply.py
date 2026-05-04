"""Apply helpers for reviewed Data Interpretation candidates."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from XBrainLab.backend.load_data.label_loader import load_label_file
from XBrainLab.backend.utils.logger import logger

from .commands import LabelImportPlan
from .data_interpretation import InterpretationCandidate


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
        if (
            not timestamp_applicable
            and not anchored_applicable
            and not sequence_applicable
        ):
            return {
                "status": "skipped",
                "reason": ("No reviewed label carrier is safe to apply automatically."),
            }

        applicable = timestamp_applicable or anchored_applicable or sequence_applicable
        if timestamp_applicable:
            mode = "timestamp"
        elif anchored_applicable:
            mode = "anchored"
        else:
            mode = "legacy"

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
            label_map = self._load_reviewed_label_map(applicable, mode)
            mapping = self._label_import_mapping_from_class_map(candidate.class_map)
            if mode in {"timestamp", "anchored"}:
                count = self.dataset.apply_labels_batch(
                    mapped_target_files,
                    label_map,
                    file_mapping,
                    mapping,
                    None,
                )
            else:
                count = self._apply_reviewed_sequence_label_map(
                    mapped_target_files,
                    label_map,
                    file_mapping,
                    mapping,
                )
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
                selected_event_names=None,
                success_count=count,
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
    def _load_reviewed_label_map(
        label_plans: list[dict[str, Any]],
        mode: str,
    ) -> dict[str, Any]:
        label_map: dict[str, Any] = {}
        for carrier in label_plans:
            carrier_path = str(carrier.get("path") or "").strip()
            label_field = str(carrier.get("selected_label_field") or "").strip()
            anchor = str(carrier.get("selected_anchor") or "").strip()
            if not carrier_path or not label_field or not anchor:
                raise ValueError(
                    "Reviewed label carrier is missing label field or anchor.",
                )
            label_map[carrier_path] = load_label_file(
                carrier_path,
                label_field=label_field,
                anchor=anchor if mode in {"timestamp", "anchored"} else None,
            )
        return label_map

    def _apply_reviewed_sequence_label_map(
        self,
        target_files: list[Any],
        label_map: dict[str, Any],
        file_mapping: dict[str, str],
        mapping: dict[Any, str],
    ) -> int:
        success_count = 0
        for target in target_files:
            data_path = self._data_filepath(target)
            carrier_path = file_mapping.get(data_path)
            if not carrier_path or carrier_path not in label_map:
                continue
            success_count += int(
                self.dataset.apply_labels_legacy(
                    [target],
                    label_map[carrier_path],
                    mapping,
                    None,
                    force_import=False,
                ),
            )
        return success_count

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
        time_model = str(plan.get("time_model") or "").strip().lower()
        return (
            carrier_format in {"BIDS events", "CSV", "TSV"}
            and bool(str(plan.get("selected_label_field") or "").strip())
            and bool(str(plan.get("selected_anchor") or "").strip())
            and time_model in {"seconds", "relative_time"}
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
            carrier_format in {"MAT", "MAT labels", "TXT"}
            and bool(str(plan.get("selected_label_field") or "").strip())
            and time_model == "trial_order"
            and granularity == "trial"
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
