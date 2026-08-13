from threading import Event, Thread

import mne
import numpy as np
import pytest

from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
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
