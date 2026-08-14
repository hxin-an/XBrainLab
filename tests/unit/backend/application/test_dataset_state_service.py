"""Behavior tests for the Study-owned dataset state application port."""

from __future__ import annotations

from copy import copy
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    QueryStateCommand,
    ResetSessionCommand,
    UpdateMetadataCommand,
)
from XBrainLab.backend.controller.dataset_controller import DatasetController
from XBrainLab.backend.services.dataset_state_service import DatasetStateService
from XBrainLab.backend.study import Study


class _MetadataRow:
    def __init__(
        self,
        subject: str,
        session: str,
        *,
        filepath: str,
        fail_session: str | None = None,
    ) -> None:
        self.subject = subject
        self.session = session
        self.filepath = filepath
        self.fail_session = fail_session

    def __copy__(self) -> _MetadataRow:
        return type(self)(
            self.subject,
            self.session,
            filepath=self.filepath,
            fail_session=self.fail_session,
        )

    def get_filepath(self) -> str:
        return self.filepath

    def set_subject_name(self, value: str) -> None:
        self.subject = value

    def set_session_name(self, value: str) -> None:
        if value == self.fail_session:
            raise RuntimeError("metadata setter failed")
        self.session = value


class _MetadataStudy:
    def __init__(
        self,
        rows: list[_MetadataRow],
        preprocessed: list[object],
        *,
        fail_reset: bool = False,
    ) -> None:
        self.loaded_data_list = rows
        self.preprocessed_data_list = preprocessed
        self.fail_reset = fail_reset
        self.reset_count = 0

    def reset_preprocess(self, *, force_update: bool) -> None:
        assert force_update is True
        self.reset_count += 1
        if self.fail_reset:
            raise RuntimeError("reset failed")
        self.preprocessed_data_list = list(self.loaded_data_list)

    def set_loaded_data_list(
        self,
        rows: list[_MetadataRow],
        *,
        force_update: bool,
    ) -> None:
        assert force_update is True
        self.loaded_data_list = list(rows)
        self.preprocessed_data_list = list(rows)


class _DatasetRaw:
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath

    def get_filepath(self) -> str:
        return self.filepath

    def copy(self) -> _DatasetRaw:
        return _DatasetRaw(self.filepath)


class _LabelTargetRaw(_DatasetRaw):
    def get_filename(self) -> str:
        return self.filepath.rsplit("/", 1)[-1]

    def is_raw(self) -> bool:
        return True

    def get_raw_event_list(self):
        return [[0, 0, 7], [10, 0, 8]], {"768": 7, "769": 8}


class _DatasetStudy:
    def __init__(self) -> None:
        self.loaded_data_list: list[object] = []
        self.preprocessed_data_list: list[object] = []
        self.backup_count = 0
        self.reset_count = 0
        self.cleaned = False
        self.locked = False

    def set_loaded_data_list(
        self,
        rows: list[object],
        *,
        force_update: bool,
    ) -> None:
        assert force_update is True
        self.loaded_data_list = list(rows)
        self.preprocessed_data_list = list(rows)

    def backup_loaded_data(self) -> None:
        self.backup_count += 1

    def lock_dataset(self) -> None:
        self.locked = True

    def reset_preprocess(self, *, force_update: bool) -> None:
        assert force_update is True
        self.reset_count += 1

    def clean_raw_data(self, *, force_update: bool) -> None:
        assert force_update is True
        self.cleaned = True
        self.loaded_data_list = []


class _RawLoader(list[object]):
    def apply(self, study: _DatasetStudy, *, force_update: bool) -> None:
        study.set_loaded_data_list(list(self), force_update=force_update)


class _RawFactory:
    loaded = _DatasetRaw("/data/new.fif")

    @classmethod
    def load(cls, path: str) -> _DatasetRaw:
        assert path == "/data/new.fif"
        return cls.loaded


class _LabelService:
    def apply_labels_batch_checked(self, target_files, *_args) -> int:
        return len(target_files)


class _ChannelSelection:
    def __init__(self, data_list: list[object]) -> None:
        self.data_list = data_list

    def data_preprocess(self, channels: list[str]) -> list[object]:
        assert channels == ["C3", "C4"]
        return ["selected-channel-data"]


def test_dataset_state_metadata_batch_is_atomic_before_commit() -> None:
    first = _MetadataRow("old-1", "run-1", filepath="/data/one.fif")
    second = _MetadataRow(
        "old-2",
        "run-2",
        filepath="/data/two.fif",
        fail_session="bad-run",
    )
    original_rows = [first, second]
    preprocessing_truth = [object()]
    study = _MetadataStudy(original_rows, preprocessing_truth)
    state = DatasetStateService(study)

    with pytest.raises(RuntimeError, match="metadata setter failed"):
        state.update_metadata_batch(
            [
                (0, "new-1", "new-run-1"),
                (1, "new-2", "bad-run"),
            ]
        )

    assert study.loaded_data_list is original_rows
    assert [(row.subject, row.session) for row in original_rows] == [
        ("old-1", "run-1"),
        ("old-2", "run-2"),
    ]
    assert study.preprocessed_data_list is preprocessing_truth
    assert study.reset_count == 0


def test_dataset_state_smart_parse_and_remove_share_study_state_boundary() -> None:
    first = _MetadataRow("old-1", "run-1", filepath="/data/one.fif")
    second = _MetadataRow("old-2", "run-2", filepath="/data/two.fif")
    study = _MetadataStudy([first, second], [first, second])
    state = DatasetStateService(study)

    updated = state.apply_smart_parse(
        {
            "/data/one.fif": ("S01", "session-01"),
            "/data/two.fif": ("-", "session-02"),
        }
    )

    assert updated == 2
    assert [(row.subject, row.session) for row in study.loaded_data_list] == [
        ("S01", "session-01"),
        ("old-2", "session-02"),
    ]
    retained = copy(study.loaded_data_list[1])

    state.remove_files([0])

    assert len(study.loaded_data_list) == 1
    assert study.loaded_data_list[0].subject == retained.subject
    assert study.loaded_data_list[0].session == retained.session


def test_dataset_state_service_owns_import_label_channel_and_reset_mutations() -> None:
    study = _DatasetStudy()
    state = DatasetStateService(
        study,
        raw_loader_provider=lambda: _RawLoader,
        raw_factory_provider=lambda: _RawFactory,
        label_service_provider=lambda: _LabelService,
        channel_selection_provider=lambda: _ChannelSelection,
    )

    count, errors = state.import_files(["/data/new.fif"])
    label_count = state.apply_labels_batch(
        [_RawFactory.loaded],
        {"labels.csv": [1]},
        {"/data/new.fif": "labels.csv"},
        {1: "left"},
        None,
    )
    selected = state.apply_channel_selection(["C3", "C4"])
    state.reset_preprocess()
    state.clean_dataset()

    assert (count, errors) == (1, [])
    assert label_count == 1
    assert selected is True
    assert study.backup_count == 1
    assert study.locked is True
    assert study.reset_count == 2
    assert study.cleaned is True


def test_channel_selection_refuses_missing_backup_owner_before_publication() -> None:
    class _StudyWithoutBackup:
        def __init__(self) -> None:
            self.loaded_data_list = [_DatasetRaw("/data/source.fif")]
            self.published: list[list[object]] = []
            self.locked = False

        def set_loaded_data_list(
            self,
            rows: list[object],
            *,
            force_update: bool,
        ) -> None:
            assert force_update is True
            self.published.append(rows)
            self.loaded_data_list = rows

        def lock_dataset(self) -> None:
            self.locked = True

    study = _StudyWithoutBackup()
    original = study.loaded_data_list
    state = DatasetStateService(
        study,
        channel_selection_provider=lambda: _ChannelSelection,
    )

    with pytest.raises(RuntimeError, match="backup owner is unavailable"):
        state.apply_channel_selection(["C3", "C4"])

    assert study.loaded_data_list is original
    assert study.published == []
    assert study.locked is False


def test_dataset_state_projects_label_targets_without_exposing_live_raw_objects() -> (
    None
):
    study = _DatasetStudy()
    target = _LabelTargetRaw("/data/sub-01_task-mi_raw.fif")
    study.loaded_data_list = [target]
    state = DatasetStateService(study)
    state.get_smart_filter_suggestions = MagicMock(return_value=[8])

    rows = state.get_label_import_target_rows([0], target_count=288)

    assert rows == [
        {
            "index": 0,
            "filepath": "/data/sub-01_task-mi_raw.fif",
            "filename": "sub-01_task-mi_raw.fif",
            "is_raw": True,
            "event_names": ["768", "769"],
            "suggested_event_names": ["769"],
            "event_read_error": None,
        }
    ]
    assert all(value is not target for value in rows[0].values())
    state.get_smart_filter_suggestions.assert_called_once_with(target, 288)


def test_dataset_state_projects_invalid_raw_event_shape_as_detached_error() -> None:
    class InvalidEventTarget(_LabelTargetRaw):
        def get_raw_event_list(self):
            return {"768": 7}

    study = _DatasetStudy()
    study.loaded_data_list = [InvalidEventTarget("/data/invalid-events.fif")]
    state = DatasetStateService(study)

    rows = state.get_label_import_target_rows([0], target_count=1)

    assert rows[0]["event_names"] == []
    assert rows[0]["suggested_event_names"] == []
    assert rows[0]["event_read_error"] == "raw event metadata has an invalid shape"


def test_study_application_and_controller_share_one_dataset_mutation_owner() -> None:
    study = Study()
    service = ApplicationService(study)
    controller = study.get_controller("dataset")

    assert isinstance(controller, DatasetController)
    assert service.dataset is study.dataset_state_service
    assert controller._dataset_state is study.dataset_state_service
    assert service._command_lock is study._application_command_lock
    assert study.dataset_state_service._mutation_lock is study._application_command_lock


def test_application_data_table_and_state_queries_use_study_port_not_controller() -> (
    None
):
    service = ApplicationService(Study())

    assert service.data_table.dataset is service.dataset_state
    assert service.state_snapshot.dataset is service.dataset_state
    assert service.query_state_commands.dataset is service.dataset_state

    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/data/sample.fif"
    raw.get_subject_name.return_value = "S00"
    raw.get_session_name.return_value = "session-00"
    raw.get_nchan.return_value = 2
    raw.get_sfreq.return_value = 100.0
    raw.get_epochs_length.return_value = 0
    raw.get_event_summary.return_value = {
        "available": False,
        "count": 0,
        "labels": [],
        "source": "none",
        "scanned": True,
    }
    raw.get_mne.return_value.ch_names = ["Fz", "Cz"]
    raw.is_raw.return_value = True
    raw.is_labels_imported.return_value = False
    raw.get_filter_range.return_value = (0.5, 40.0)
    raw.get_runtime_signals.return_value = []
    raw.get_gdf_duplicate_channel_detail.return_value = None
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]

    def reset_preprocess(*, force_update: bool) -> None:
        assert force_update is True
        service.study.data_manager.preprocessed_data_list = list(
            service.study.data_manager.loaded_data_list
        )

    service.study.reset_preprocess = MagicMock(side_effect=reset_preprocess)
    original_get_controller = service.study.get_controller

    def guard_dataset_controller(name: str) -> object:
        if name == "dataset":
            raise AssertionError("product read path resolved the dataset controller")
        return original_get_controller(name)

    service.study.get_controller = MagicMock(side_effect=guard_dataset_controller)

    query_result = service.execute(QueryStateCommand(query="data_lists"))
    result = service.execute(UpdateMetadataCommand(index=0, subject="S01"))

    assert query_result.ok is True
    assert query_result.diagnostics["raw_rows"][0] == {
        "filepath": "/data/sample.fif",
        "filename": "sample.fif",
        "subject": "S00",
        "session": "session-00",
        "n_channels": 2,
        "sampling_frequency": 100.0,
        "epochs_length": 0,
        "is_raw": True,
        "labels_imported": False,
        "channels": ["Fz", "Cz"],
        "event": {
            "available": False,
            "count": 0,
            "labels": [],
            "source": "none",
            "scanned": True,
        },
        "tmin": None,
        "epoch_duration_samples": None,
        "highpass": 0.5,
        "lowpass": 40.0,
    }
    assert result.ok is True
    assert all(
        call.args != ("dataset",)
        for call in service.study.get_controller.call_args_list
    )


def test_real_application_reset_does_not_resolve_dataset_controller() -> None:
    study = Study()
    original_get_controller = study.get_controller
    resolved: list[str] = []

    def guard_dataset_controller(name: str) -> object:
        resolved.append(name)
        if name == "dataset":
            raise AssertionError("Dataset product command resolved its UI controller")
        return original_get_controller(name)

    study.get_controller = guard_dataset_controller  # type: ignore[method-assign]
    service = ApplicationService(study)

    result = service.execute(ResetSessionCommand())

    assert result.ok is True
    assert result.message == "Session reset."
    assert "dataset" not in resolved
    assert service.dataset is service.dataset_state
