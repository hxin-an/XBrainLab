"""Study-owned dataset operations shared by product commands and UI adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import copy
from math import isfinite
from threading import RLock
from typing import Any, Protocol

from XBrainLab.backend.exceptions import FileCorruptedError, UnsupportedFormatError
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.runtime_diagnostics import collect_runtime_diagnostics


class DatasetLoadedDataReadPort(Protocol):
    """Live loaded-data access restricted to application-owned services."""

    def get_loaded_data_list(self) -> list[Any]: ...


class DatasetInterpretationPort(DatasetLoadedDataReadPort, Protocol):
    """Raw import and label operations used by interpretation commands."""

    def import_files(self, filepaths: Sequence[str]) -> tuple[int, list[str]]: ...
    def clean_dataset(self) -> None: ...
    def apply_labels_batch(
        self,
        target_files: Sequence[Any],
        label_map: Mapping[str, Any],
        file_mapping: Mapping[str, str],
        mapping: Mapping[Any, str],
        selected_event_names: Sequence[str] | set[str] | None,
    ) -> int: ...


class DatasetLifecyclePort(Protocol):
    """Dataset reset operations used by lifecycle commands."""

    def clean_dataset(self) -> None: ...
    def reset_preprocess(self) -> None: ...


class DatasetChannelSelectionPort(Protocol):
    """Raw channel-selection mutation used by preprocess commands."""

    def apply_channel_selection(self, selected_channels: Sequence[str]) -> bool: ...


class DatasetTablePort(DatasetLoadedDataReadPort, Protocol):
    """Loaded-data table mutations used by application commands."""

    def remove_files(self, indices: Sequence[int]) -> bool: ...
    def update_metadata_batch(
        self,
        updates: Sequence[tuple[int, str | None, str | None]],
    ) -> int: ...
    def apply_smart_parse(self, results: Mapping[str, Any]) -> int: ...


class DatasetDetachedReadPort(Protocol):
    """Detached Dataset rows used by product query surfaces."""

    def get_loaded_data_rows(self) -> list[dict[str, Any]]: ...
    def get_preprocessed_data_rows(self) -> list[dict[str, Any]]: ...
    def get_label_import_target_rows(
        self,
        target_indices: Sequence[int],
        *,
        target_count: int,
    ) -> list[dict[str, Any]]: ...


class DatasetStateReadPort(DatasetLoadedDataReadPort, Protocol):
    """Dataset state reads used while assembling application snapshots."""

    def get_preprocessed_data_list(self) -> list[Any]: ...
    def get_epoch_data(self) -> Any | None: ...
    def get_event_info(self) -> dict[str, Any]: ...
    def get_runtime_diagnostics(self) -> dict[str, Any]: ...
    def get_smart_filter_suggestions(
        self,
        data: Any,
        target_count: int,
    ) -> list[int]: ...


class DatasetProductPort(
    DatasetInterpretationPort,
    DatasetLifecyclePort,
    DatasetChannelSelectionPort,
    DatasetTablePort,
    DatasetDetachedReadPort,
    DatasetStateReadPort,
    Protocol,
):
    """Complete Dataset command surface implemented by DatasetStateService."""


def _default_raw_loader_provider() -> Any:
    from XBrainLab.backend.load_data.data_loader import RawDataLoader  # noqa: PLC0415

    return RawDataLoader


def _default_raw_factory_provider() -> Any:
    from XBrainLab.backend.load_data.factory import (  # noqa: PLC0415
        RawDataLoaderFactory,
    )

    return RawDataLoaderFactory


def _default_label_service_provider() -> Any:
    from XBrainLab.backend.services.label_import_service import (  # noqa: PLC0415
        LabelImportService,
    )

    return LabelImportService


def _default_channel_selection_provider() -> Any:
    from XBrainLab.backend.preprocessor import ChannelSelection  # noqa: PLC0415

    return ChannelSelection


def _default_event_loader_provider() -> Any:
    from XBrainLab.backend.load_data.event_loader import EventLoader  # noqa: PLC0415

    return EventLoader


class DatasetStateService:
    """Own loaded-data state transitions without resolving a UI controller."""

    def __init__(
        self,
        study: Any,
        *,
        raw_loader_provider: Callable[[], Any] = _default_raw_loader_provider,
        raw_factory_provider: Callable[[], Any] = _default_raw_factory_provider,
        label_service_provider: Callable[[], Any] = _default_label_service_provider,
        channel_selection_provider: Callable[[], Any] = (
            _default_channel_selection_provider
        ),
        event_loader_provider: Callable[[], Any] = _default_event_loader_provider,
    ) -> None:
        self.study = study
        self._raw_loader_provider = raw_loader_provider
        self._raw_factory_provider = raw_factory_provider
        self._label_service_provider = label_service_provider
        self._channel_selection_provider = channel_selection_provider
        self._event_loader_provider = event_loader_provider
        self._mutation_lock = vars(study).get("_application_command_lock") or RLock()
        self._label_service: Any | None = None

    @property
    def label_service(self) -> Any:
        with self._mutation_lock:
            if self._label_service is None:
                self._label_service = self._label_service_provider()()
            return self._label_service

    @label_service.setter
    def label_service(self, value: Any) -> None:
        with self._mutation_lock:
            self._label_service = value

    def get_loaded_data_list(self) -> list[Any]:
        return list(getattr(self.study, "loaded_data_list", []) or [])

    def get_preprocessed_data_list(self) -> list[Any]:
        """Return a shallow collection copy for application-owned readers."""
        return list(getattr(self.study, "preprocessed_data_list", []) or [])

    def get_epoch_data(self) -> Any | None:
        """Return live epoch data only to application-owned domain services."""
        return getattr(self.study, "epoch_data", None)

    def is_locked(self) -> bool:
        return bool(self.study.is_locked())

    def has_data(self) -> bool:
        return bool(getattr(self.study, "loaded_data_list", []))

    def get_loaded_data_rows(self) -> list[dict[str, Any]]:
        """Return detached, JSON-safe rows for product Dataset readers."""
        return [self.project_data_row(data) for data in self.get_loaded_data_list()]

    def get_preprocessed_data_rows(self) -> list[dict[str, Any]]:
        """Return detached, JSON-safe rows for product aggregate readers."""
        return [
            self.project_data_row(data) for data in self.get_preprocessed_data_list()
        ]

    def get_label_import_target_rows(
        self,
        target_indices: Sequence[int],
        *,
        target_count: int,
    ) -> list[dict[str, Any]]:
        """Project selected label targets without exposing mutable EEG objects."""
        if isinstance(target_count, bool) or not isinstance(target_count, int):
            raise ValueError("target_count must be a non-negative integer.")
        if target_count < 0:
            raise ValueError("target_count must be a non-negative integer.")

        data_list = list(self.get_loaded_data_list())
        indices: list[int] = []
        for raw_index in target_indices:
            if isinstance(raw_index, bool):
                raise ValueError("Label target indices must be integers.")
            try:
                index = int(raw_index)
            except (TypeError, ValueError) as exc:
                raise ValueError("Label target indices must be integers.") from exc
            if index < 0 or index >= len(data_list):
                raise IndexError(f"Label target index out of range: {index}")
            indices.append(index)
        if len(indices) != len(set(indices)):
            raise ValueError("Duplicate label target indices are not allowed.")

        return [
            self._project_label_import_target(
                data_list[index],
                index=index,
                target_count=target_count,
            )
            for index in indices
        ]

    def _project_label_import_target(
        self,
        data: Any,
        *,
        index: int,
        target_count: int,
    ) -> dict[str, Any]:
        filepath = self._safe_text_call(data, "get_filepath")
        filename = self._safe_text_call(data, "get_filename")
        if not filename:
            filename = filepath.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        is_raw = self._safe_bool_call(data, "is_raw")
        event_names: list[str] = []
        suggested_event_names: list[str] = []
        event_read_error: str | None = None

        if is_raw:
            try:
                raw_event_ids = self._read_raw_event_ids(data)
            except Exception as exc:
                event_read_error = str(exc) or type(exc).__name__
            else:
                event_names = sorted(str(name) for name in raw_event_ids)
                names_by_code: dict[int, str] = {}
                for name, raw_code in raw_event_ids.items():
                    code = self._event_code_or_none(raw_code)
                    if code is not None:
                        names_by_code[code] = str(name)
                if target_count > 0 and names_by_code:
                    try:
                        suggested_codes = self.get_smart_filter_suggestions(
                            data,
                            target_count,
                        )
                    except Exception:
                        logger.warning(
                            "Could not suggest target events for %s",
                            filepath or filename,
                            exc_info=True,
                        )
                    else:
                        suggested_event_names = sorted(
                            {
                                names_by_code[code]
                                for code in suggested_codes
                                if code in names_by_code
                            }
                        )

        return {
            "index": index,
            "filepath": filepath,
            "filename": filename,
            "is_raw": is_raw,
            "event_names": event_names,
            "suggested_event_names": suggested_event_names,
            "event_read_error": event_read_error,
        }

    @classmethod
    def project_data_row(cls, data: Any) -> dict[str, Any]:
        """Project one mutable EEG wrapper into an immutable read payload."""
        filepath = cls._safe_text_call(data, "get_filepath")
        filename = cls._safe_text_call(data, "get_filename")
        if not filename:
            filename = filepath.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

        is_raw = cls._safe_bool_call(data, "is_raw")
        mne_data = cls._safe_call(data, "get_mne")
        channels = [
            str(channel) for channel in list(getattr(mne_data, "ch_names", []) or [])
        ]
        highpass, lowpass = cls._safe_filter_range(data)
        return {
            "filepath": filepath,
            "filename": filename,
            "subject": cls._safe_text_call(data, "get_subject_name"),
            "session": cls._safe_text_call(data, "get_session_name"),
            "n_channels": cls._safe_int_call(data, "get_nchan"),
            "sampling_frequency": cls._safe_float_call(data, "get_sfreq"),
            "epochs_length": cls._safe_int_call(data, "get_epochs_length"),
            "is_raw": is_raw,
            "labels_imported": cls._safe_bool_call(data, "is_labels_imported"),
            "channels": channels,
            "event": cls._safe_event_summary(data),
            "tmin": None if is_raw else cls._safe_float_call(data, "get_tmin"),
            "epoch_duration_samples": (
                None if is_raw else cls._safe_epoch_sample_count(mne_data)
            ),
            "highpass": highpass,
            "lowpass": lowpass,
        }

    def import_files(
        self,
        filepaths: Sequence[str],
    ) -> tuple[int, list[str]]:
        with self._mutation_lock:
            existing_data = self.get_loaded_data_list()
            try:
                loader = self._raw_loader_provider()(existing_data)
            except Exception as exc:
                raise ValueError(f"Existing dataset inconsistent: {exc}") from exc

            success_count = 0
            errors: list[str] = []
            factory = self._raw_factory_provider()
            for raw_path in filepaths:
                path = str(raw_path)
                if any(data.get_filepath() == path for data in loader):
                    logger.info("Skipping duplicate: %s", path)
                    continue
                try:
                    logger.info("Loading file: %s", path)
                    raw = factory.load(path)
                    if raw is None:
                        errors.append(f"{path}: Loader returned None.")
                        continue
                    loader.append(raw)
                    success_count += 1
                except UnsupportedFormatError:
                    logger.error("Unsupported format: %s", path)
                    errors.append(f"{path}: Unsupported format.")
                except FileCorruptedError:
                    logger.error("File corrupted: %s", path)
                    errors.append(f"{path}: File corrupted.")
                except Exception as exc:
                    logger.error("Error loading %s: %s", path, exc)
                    errors.append(f"{path}: {exc!s}")

            if success_count > 0:
                loader.apply(self.study, force_update=True)
            return success_count, errors

    def clean_dataset(self) -> None:
        with self._mutation_lock:
            self.study.clean_raw_data(force_update=True)

    def reset_preprocess(self) -> None:
        with self._mutation_lock:
            self.study.reset_preprocess(force_update=True)

    def remove_files(self, indices: Sequence[int]) -> bool:
        with self._mutation_lock:
            current = self.get_loaded_data_list()
            retained = list(current)
            changed = False
            for index in sorted({int(item) for item in indices}, reverse=True):
                if 0 <= index < len(retained):
                    del retained[index]
                    changed = True
            if changed:
                self.study.set_loaded_data_list(retained, force_update=True)
            return changed

    def update_metadata_batch(
        self,
        updates: Sequence[tuple[int, str | None, str | None]],
    ) -> int:
        with self._mutation_lock:
            changes = list(updates)
            if not changes:
                return 0

            current = getattr(self.study, "loaded_data_list", [])
            invalid = [
                index
                for index, _subject, _session in changes
                if not 0 <= index < len(current)
            ]
            if invalid:
                raise IndexError(f"Metadata row index out of range: {invalid[0]}")

            working = [copy(data) for data in current]
            for index, subject, session in changes:
                data = working[index]
                if subject is not None:
                    data.set_subject_name(subject)
                if session is not None:
                    data.set_session_name(session)

            self._commit_metadata_rows(working)
            return len(changes)

    def apply_smart_parse(
        self,
        results: Mapping[str, Any],
    ) -> int:
        with self._mutation_lock:
            updates: list[tuple[int, str | None, str | None]] = []
            for index, data in enumerate(self.get_loaded_data_list()):
                path = str(data.get_filepath())
                if path not in results:
                    continue
                value = results[path]
                if isinstance(value, Mapping):
                    subject = str(value.get("subject") or "-")
                    session = str(value.get("session") or "-")
                else:
                    subject, session = value[:2]
                updates.append(
                    (
                        index,
                        None if subject == "-" else str(subject),
                        None if session == "-" else str(session),
                    )
                )
            return self.update_metadata_batch(updates) if updates else 0

    def run_import_labels(
        self,
        target_files: Sequence[Any],
        label_map: Mapping[str, Any],
        file_mapping: Mapping[str, str],
        mapping: Mapping[Any, str],
        selected_event_names: Sequence[str] | set[str] | None = None,
    ) -> int:
        with self._mutation_lock:
            return int(
                self.label_service.apply_labels_batch_checked(
                    target_files,
                    label_map,
                    file_mapping,
                    mapping,
                    selected_event_names,
                )
            )

    def apply_labels_batch(
        self,
        target_files: Sequence[Any],
        label_map: Mapping[str, Any],
        file_mapping: Mapping[str, str],
        mapping: Mapping[Any, str],
        selected_event_names: Sequence[str] | set[str] | None,
    ) -> int:
        with self._mutation_lock:
            count = self.run_import_labels(
                target_files,
                label_map,
                file_mapping,
                mapping,
                selected_event_names,
            )
            if count > 0:
                self.reset_preprocess()
            return count

    def apply_labels_sequence(
        self,
        target_files: Sequence[Any],
        labels: Sequence[Any],
        mapping: Mapping[Any, str],
        selected_event_names: Sequence[str] | set[str] | None,
        *,
        force_import: bool = False,
    ) -> int:
        with self._mutation_lock:
            count = int(
                self.label_service.apply_labels_sequence(
                    list(target_files),
                    labels,
                    dict(mapping),
                    selected_event_names,
                    force_import=force_import,
                )
            )
            if count > 0:
                self.reset_preprocess()
            return count

    def apply_channel_selection(self, selected_channels: Sequence[str]) -> bool:
        with self._mutation_lock:
            process = self._channel_selection_provider()(self.get_loaded_data_list())
            try:
                result = process.data_preprocess(list(selected_channels))
            except Exception as exc:
                logger.error("Channel selection failed: %s", exc)
                raise
            self.study.backup_loaded_data()
            self.study.set_loaded_data_list(result, force_update=True)
            self.study.lock_dataset()
            return True

    def get_filenames(self) -> list[str]:
        return [str(data.get_filepath()) for data in self.get_loaded_data_list()]

    def get_data_at_assignments(self, indices: Sequence[int]) -> list[Any]:
        data_list = self.get_loaded_data_list()
        return [data_list[index] for index in indices if 0 <= index < len(data_list)]

    def get_epoch_count(self, data: Any, event_names: Sequence[str]) -> int:
        return int(self.label_service.get_epoch_count_for_file(data, event_names))

    def get_event_info(self) -> dict[str, Any]:
        total_events = 0
        unique_events: set[str] = set()
        for data in self.get_loaded_data_list():
            mne_data = data.get_mne()
            annotations = getattr(mne_data, "annotations", None)
            if annotations:
                total_events += len(annotations)
                unique_events.update(str(item) for item in annotations.description)
        return {
            "total": total_events,
            "unique_count": len(unique_events),
            "unique_labels": sorted(unique_events),
        }

    def get_runtime_diagnostics(self) -> dict[str, Any]:
        return collect_runtime_diagnostics(self.get_loaded_data_list())

    def get_smart_filter_suggestions(self, data: Any, target_count: int) -> list[int]:
        loader = self._event_loader_provider()(data)
        return [int(item) for item in loader.smart_filter(int(target_count))]

    @staticmethod
    def _read_raw_event_ids(data: Any) -> Mapping[Any, Any]:
        event_reader = getattr(data, "get_raw_event_list", None)
        if not callable(event_reader):
            raise RuntimeError("raw event metadata is unavailable")
        event_result: Any = event_reader()
        if not isinstance(event_result, tuple) or len(event_result) != 2:
            raise RuntimeError("raw event metadata has an invalid shape")
        raw_event_ids = event_result[1]
        if not isinstance(raw_event_ids, Mapping):
            raise RuntimeError("raw event-code mapping is unavailable")
        return raw_event_ids

    @staticmethod
    def _event_code_or_none(raw_code: Any) -> int | None:
        if type(raw_code) is bool:
            return None
        try:
            return int(raw_code)
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _safe_call(data: Any, method_name: str) -> Any | None:
        method = getattr(data, method_name, None)
        if not callable(method):
            return None
        try:
            return method()
        except Exception:
            return None

    @classmethod
    def _safe_text_call(cls, data: Any, method_name: str) -> str:
        value = cls._safe_call(data, method_name)
        return "" if value is None else str(value)

    @classmethod
    def _safe_bool_call(cls, data: Any, method_name: str) -> bool:
        value = cls._safe_call(data, method_name)
        return value if type(value) is bool else False

    @classmethod
    def _safe_int_call(cls, data: Any, method_name: str) -> int | None:
        value = cls._safe_call(data, method_name)
        if value is None or type(value) is bool:
            return None
        try:
            converted = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return converted if converted >= 0 else None

    @classmethod
    def _safe_float_call(cls, data: Any, method_name: str) -> float | None:
        value = cls._safe_call(data, method_name)
        if value is None or type(value) is bool:
            return None
        try:
            converted = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return converted if isfinite(converted) else None

    @classmethod
    def _safe_filter_range(
        cls,
        data: Any,
    ) -> tuple[float | None, float | None]:
        value = cls._safe_call(data, "get_filter_range")
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return None, None
        return cls._finite_float(value[0]), cls._finite_float(value[1])

    @staticmethod
    def _finite_float(value: Any) -> float | None:
        if type(value) is bool:
            return None
        try:
            converted = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return converted if isfinite(converted) else None

    @classmethod
    def _safe_event_summary(cls, data: Any) -> dict[str, Any]:
        method = getattr(data, "get_event_summary", None)
        if not callable(method):
            return {
                "available": False,
                "count": None,
                "labels": [],
                "source": "unavailable",
                "scanned": False,
            }
        try:
            summary = method(allow_scan=False)
        except Exception:
            return {
                "available": False,
                "count": None,
                "labels": [],
                "source": "error",
                "scanned": False,
            }
        if not isinstance(summary, dict):
            return {
                "available": False,
                "count": None,
                "labels": [],
                "source": "unavailable",
                "scanned": False,
            }
        count = summary.get("count")
        if type(count) is bool:
            count = None
        elif count is not None:
            try:
                count = max(0, int(count))
            except (TypeError, ValueError, OverflowError):
                count = None
        labels = summary.get("labels")
        return {
            "available": bool(summary.get("available", False)),
            "count": count,
            "labels": (
                [str(label) for label in labels]
                if isinstance(labels, (list, tuple, set))
                else []
            ),
            "source": str(summary.get("source", "unavailable")),
            "scanned": bool(summary.get("scanned", False)),
        }

    @staticmethod
    def _safe_epoch_sample_count(mne_data: Any) -> int | None:
        times = getattr(mne_data, "times", None)
        if times is None:
            return None
        try:
            return len(times)
        except (TypeError, OverflowError):
            return None

    def _commit_metadata_rows(self, working: list[Any]) -> None:
        original_loaded = self.study.loaded_data_list
        original_preprocessed = self.study.preprocessed_data_list
        manager = vars(self.study).get("data_manager")
        manager_state = None
        if manager is not None:
            manager_state = {
                "loaded_data_list": manager.loaded_data_list,
                "backup_loaded_data_list": manager.backup_loaded_data_list,
                "preprocessed_data_list": manager.preprocessed_data_list,
                "epoch_data": manager.epoch_data,
                "datasets": manager.datasets,
                "dataset_generator": manager.dataset_generator,
                "dataset_locked": manager.dataset_locked,
            }

        try:
            self.study.loaded_data_list = working
            self.study.reset_preprocess(force_update=True)
        except Exception:
            if manager_state is None:
                self.study.loaded_data_list = original_loaded
                self.study.preprocessed_data_list = original_preprocessed
            else:
                for name, value in manager_state.items():
                    setattr(manager, name, value)
            raise
