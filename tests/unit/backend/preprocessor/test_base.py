from threading import Event, Thread, current_thread

import mne
import numpy as np
import pytest

from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
    current_owned_operation_id,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor.base import PreprocessBase

base_fs = 500
base_duration = 10


def _generate_mne(fs, ch_names, ch_types, length=base_duration):
    info = mne.create_info(ch_names=ch_names, sfreq=fs, ch_types=ch_types)
    data = np.random.RandomState(0).randn(len(ch_names), fs * length)
    return mne.io.RawArray(data, info)


# raw without event
@pytest.fixture
def raw():
    mne_raw = _generate_mne(base_fs, ["Fp1", "Fp2", "F3", "F4"], "eeg")
    return Raw("tests/test_data/sub-01_ses-01_task-rest_eeg.fif", mne_raw)


def test_base(raw):
    with pytest.raises(ValueError):
        PreprocessBase([])

    base = PreprocessBase([raw])
    assert len(base.get_preprocessed_data_list()) == 1

    with pytest.raises(NotImplementedError):
        base.get_preprocess_desc()

    with pytest.raises(NotImplementedError):
        base._data_preprocess(None)


def test_inherit(raw):
    class InheritedPreprocessor(PreprocessBase):
        def get_preprocess_desc(self, *args, **kwargs):
            return "test desc " + str(args[0])

        def _data_preprocess(self, preprocessed_data, *args, **kwargs):
            preprocessed_data.set_subject_name("test_inherit")

    preprocessor = InheritedPreprocessor([raw])
    preprocessor.data_preprocess(1)

    result = preprocessor.get_preprocessed_data_list()[0]

    assert result.get_subject_name() == "test_inherit"
    assert result.get_preprocess_history() == ["test desc 1"]


def test_multi_recording_preprocess_reports_progress_and_stops_at_checkpoint(raw):
    entered_second_recording = Event()
    release_second_recording = Event()
    processed_subjects: list[str] = []

    class CancellablePreprocessor(PreprocessBase):
        def get_preprocess_desc(self, *_args, **_kwargs):
            return "cancellable preprocess"

        def _data_preprocess(self, preprocessed_data, *_args, **_kwargs):
            processed_subjects.append(preprocessed_data.get_subject_name())
            if len(processed_subjects) == 2:
                entered_second_recording.set()
                assert release_second_recording.wait(timeout=2.0)

    rows = [raw, raw.copy(), raw.copy()]
    for index, row in enumerate(rows):
        row.set_subject_name(str(index))
    registry = OwnedWorkRegistry()
    operation = registry.begin(OwnedWorkKind.PREPROCESS, cancellable=True)
    cancellation_errors: list[OwnedOperationCancelledError] = []
    thread_errors: list[BaseException] = []

    def run_preprocess() -> None:
        try:
            with registry.bind(operation.operation_id):
                registry.start(operation.operation_id)
                CancellablePreprocessor(rows).data_preprocess()
        except OwnedOperationCancelledError as exc:
            cancellation_errors.append(exc)
        except BaseException as exc:
            thread_errors.append(exc)

    worker = Thread(target=run_preprocess, daemon=True)
    worker.start()
    assert entered_second_recording.wait(timeout=2.0)

    active = registry.snapshot(operation.operation_id)
    assert active.stage == "Preprocessing EEG recordings"
    assert active.completed == 1
    assert active.total == 3
    assert active.indeterminate is False

    assert registry.cancel(operation.operation_id) is True
    release_second_recording.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert thread_errors == []
    assert len(cancellation_errors) == 1
    assert registry.snapshot(operation.operation_id).phase is OwnedWorkPhase.CANCELLED
    assert processed_subjects == ["0", "1"]
    assert all(row.get_preprocess_history() == [] for row in rows)


def test_independent_recordings_use_at_most_two_workers_and_keep_order(raw):
    entered_two_workers = Event()
    release_workers = Event()
    started_subjects: list[str] = []
    worker_operation_ids: list[str | None] = []

    class ParallelPreprocessor(PreprocessBase):
        max_parallel_recordings = 2

        def get_preprocess_desc(self, *_args, **_kwargs):
            return "parallel preprocess"

        def _data_preprocess(self, preprocessed_data, *_args, **_kwargs):
            started_subjects.append(preprocessed_data.get_subject_name())
            worker_operation_ids.append(current_owned_operation_id())
            if len(started_subjects) == 2:
                entered_two_workers.set()
            assert release_workers.wait(timeout=2.0)

    rows = [raw, raw.copy(), raw.copy()]
    for index, row in enumerate(rows):
        row.set_subject_name(str(index))
    registry = OwnedWorkRegistry()
    operation = registry.begin(OwnedWorkKind.PREPROCESS, cancellable=True)
    errors: list[BaseException] = []
    result: list[Raw] = []

    def run_preprocess() -> None:
        try:
            with registry.bind(operation.operation_id):
                registry.start(operation.operation_id)
                result.extend(ParallelPreprocessor(rows).data_preprocess())
                registry.complete(operation.operation_id)
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=run_preprocess, daemon=True)
    worker.start()
    assert entered_two_workers.wait(timeout=2.0)
    assert len(started_subjects) == 2
    release_workers.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert errors == []
    assert [row.get_subject_name() for row in result] == ["0", "1", "2"]
    assert all(
        operation_id == operation.operation_id for operation_id in worker_operation_ids
    )
    assert registry.snapshot(operation.operation_id).phase is OwnedWorkPhase.COMPLETED


def test_parallel_preprocess_cancellation_stops_unscheduled_recordings(raw):
    entered_two_workers = Event()
    release_workers = Event()
    started_subjects: list[str] = []

    class ParallelPreprocessor(PreprocessBase):
        max_parallel_recordings = 2

        def get_preprocess_desc(self, *_args, **_kwargs):
            return "parallel preprocess"

        def _data_preprocess(self, preprocessed_data, *_args, **_kwargs):
            started_subjects.append(preprocessed_data.get_subject_name())
            if len(started_subjects) == 2:
                entered_two_workers.set()
            assert release_workers.wait(timeout=2.0)

    rows = [raw, raw.copy(), raw.copy()]
    for index, row in enumerate(rows):
        row.set_subject_name(str(index))
    registry = OwnedWorkRegistry()
    operation = registry.begin(OwnedWorkKind.PREPROCESS, cancellable=True)
    errors: list[BaseException] = []

    def run_preprocess() -> None:
        try:
            with registry.bind(operation.operation_id):
                registry.start(operation.operation_id)
                ParallelPreprocessor(rows).data_preprocess()
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=run_preprocess, daemon=True)
    worker.start()
    assert entered_two_workers.wait(timeout=2.0)
    assert registry.cancel(operation.operation_id) is True
    release_workers.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], OwnedOperationCancelledError)
    assert len(started_subjects) == 2
    assert set(started_subjects) == {"0", "1"}
    assert registry.snapshot(operation.operation_id).phase is OwnedWorkPhase.CANCELLED
    assert all(row.get_preprocess_history() == [] for row in rows)


def test_parallel_preprocess_falls_back_when_detached_rows_share_one_buffer(raw):
    execution_threads: list[str] = []

    class ParallelPreprocessor(PreprocessBase):
        max_parallel_recordings = 2

        def get_preprocess_desc(self, *_args, **_kwargs):
            return "parallel preprocess"

        def _data_preprocess(self, _preprocessed_data, *_args, **_kwargs):
            execution_threads.append(current_thread().name)

    processor = ParallelPreprocessor([raw, raw])

    processor.data_preprocess()

    assert processor._has_distinct_mne_instances() is False
    assert execution_threads == ["MainThread", "MainThread"]
