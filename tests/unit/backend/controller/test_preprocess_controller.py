from __future__ import annotations

from unittest.mock import MagicMock, patch

import mne
import numpy as np
import pytest

from XBrainLab.backend.controller.preprocess_controller import PreprocessController
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.study import Study


class _PreprocessRow:
    def __init__(self, history: list[str] | None = None) -> None:
        self.history = list(history or [])

    def copy(self) -> _PreprocessRow:
        return _PreprocessRow(self.history)


class _RecordingProcessor:
    def __init__(self, data_list: list[_PreprocessRow]) -> None:
        self.data_list = data_list

    def data_preprocess(self, *_args, **_kwargs) -> list[_PreprocessRow]:
        self.data_list[0].history.append("filter")
        return self.data_list


class _FailingProcessor:
    def __init__(self, data_list: list[_PreprocessRow]) -> None:
        self.data_list = data_list

    def data_preprocess(self, *_args, **_kwargs) -> list[_PreprocessRow]:
        self.data_list[0].history.append("resample")
        raise RuntimeError("resample failed")


def _history_processor(label: str):
    class _HistoryProcessor:
        def __init__(self, data_list: list[_PreprocessRow]) -> None:
            self.data_list = data_list

        def data_preprocess(self, *_args, **_kwargs) -> list[_PreprocessRow]:
            for row in self.data_list:
                row.history.append(label)
            return self.data_list

    return _HistoryProcessor


@pytest.fixture
def mock_study():
    study = MagicMock()
    study.preprocessed_data_list = []
    study.reset_preprocess = MagicMock()
    study.set_preprocessed_data_list = MagicMock()
    study.lock_dataset = MagicMock()
    return study


@pytest.fixture
def controller(mock_study):
    return PreprocessController(mock_study)


def test_init_and_properties(controller, mock_study):
    # Setup
    d1 = MagicMock()
    d1.get_mne.return_value.ch_names = ["C3", "C4"]
    d1.is_raw.return_value = True

    # Test empty
    assert controller.get_preprocessed_data_list() == []
    assert controller.has_data() is False
    assert controller.get_channel_names() == []
    assert controller.get_first_data() is None
    assert controller.is_epoched() is False

    # Test populated
    mock_study.preprocessed_data_list = [d1]
    assert controller.has_data() is True
    assert controller.get_channel_names() == ["C3", "C4"]
    assert controller.get_first_data() == d1
    assert controller.is_epoched() is False  # is_raw is True

    # Test epoched state
    d1.is_raw.return_value = False
    assert controller.is_epoched() is True


def test_reset_preprocess(controller, mock_study):
    controller.reset_preprocess()
    mock_study.reset_preprocess.assert_called_with(force_update=True)


def test_processor_helper_no_data(controller, mock_study):
    # Ensure empty
    mock_study.preprocessed_data_list = []
    with pytest.raises(ValueError, match=r"No data to preprocess"):
        controller.apply_filter(1, 40)


def test_apply_filter(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch(
        "XBrainLab.backend.controller.preprocess_controller.preprocessor.Filtering"
    ) as MockProc:
        instance = MockProc.return_value
        processed_data = [MagicMock()]
        instance.data_preprocess.return_value = processed_data

        result = controller.apply_filter(1.0, 40.0, [50.0])

        assert result is True
        instance.data_preprocess.assert_called_with(1.0, 40.0, notch_freqs=[50.0])
        mock_study.set_preprocessed_data_list.assert_called_with(
            processed_data, force_update=True
        )


def test_apply_resample(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch(
        "XBrainLab.backend.controller.preprocess_controller.preprocessor.Resample"
    ) as MockProc:
        instance = MockProc.return_value
        result = controller.apply_resample(256.0)

        assert result is True
        instance.data_preprocess.assert_called_with(256.0)


def test_apply_rereference(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch(
        "XBrainLab.backend.controller.preprocess_controller.preprocessor.Rereference"
    ) as MockProc:
        instance = MockProc.return_value
        result = controller.apply_rereference(["Cz"])

        assert result is True
        instance.data_preprocess.assert_called_with(ref_channels=["Cz"])


def test_apply_normalization(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch(
        "XBrainLab.backend.controller.preprocess_controller.preprocessor.Normalize"
    ) as MockProc:
        instance = MockProc.return_value
        result = controller.apply_normalization("z-score")

        assert result is True
        instance.data_preprocess.assert_called_with(norm="z-score")


def test_standard_pipeline_failure_does_not_commit_or_notify(
    controller,
    mock_study,
):
    original = _PreprocessRow(["loaded"])
    original_list = [original]
    mock_study.preprocessed_data_list = original_list
    notifications: list[str] = []
    controller.subscribe("preprocess_changed", lambda: notifications.append("changed"))

    with (
        patch(
            "XBrainLab.backend.controller.preprocess_controller.preprocessor.Filtering",
            _RecordingProcessor,
        ),
        patch(
            "XBrainLab.backend.controller.preprocess_controller.preprocessor.Resample",
            _FailingProcessor,
        ),
        pytest.raises(RuntimeError, match="resample failed"),
    ):
        controller.apply_standard_pipeline(
            l_freq=4,
            h_freq=40,
            rate=128,
        )

    assert mock_study.preprocessed_data_list is original_list
    assert original.history == ["loaded"]
    mock_study.set_preprocessed_data_list.assert_not_called()
    assert notifications == []


def test_standard_pipeline_swaps_once_and_notifies_after_complete_success(
    controller,
    mock_study,
):
    original = _PreprocessRow(["loaded"])
    mock_study.preprocessed_data_list = [original]
    notifications: list[str] = []
    controller.subscribe("preprocess_changed", lambda: notifications.append("changed"))

    with (
        patch(
            "XBrainLab.backend.controller.preprocess_controller.preprocessor.Filtering",
            _history_processor("filter"),
        ),
        patch(
            "XBrainLab.backend.controller.preprocess_controller.preprocessor.Resample",
            _history_processor("resample"),
        ),
        patch(
            "XBrainLab.backend.controller.preprocess_controller.preprocessor.Rereference",
            _history_processor("rereference"),
        ),
        patch(
            "XBrainLab.backend.controller.preprocess_controller.preprocessor.Normalize",
            _history_processor("normalize"),
        ),
    ):
        assert controller.apply_standard_pipeline(
            l_freq=4,
            h_freq=40,
            notch_freq=60,
            rate=128,
            ref_channels="average",
            normalization="z score",
        )

    mock_study.set_preprocessed_data_list.assert_called_once()
    committed = mock_study.set_preprocessed_data_list.call_args.args[0]
    assert committed[0].history == [
        "loaded",
        "filter",
        "filter",
        "resample",
        "rereference",
        "normalize",
    ]
    assert original.history == ["loaded"]
    assert notifications == ["changed"]


def test_apply_epoching_and_locking(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch(
        "XBrainLab.backend.controller.preprocess_controller.preprocessor.TimeEpoch"
    ) as MockProc:
        instance = MockProc.return_value
        instance.data_preprocess.return_value = [MagicMock()]  # Success

        result = controller.apply_epoching(None, ["Event1"], -0.2, 0.5)

        assert result is True
        instance.data_preprocess.assert_called_with(None, ["Event1"], -0.2, 0.5, False)
        # Verify dataset is locked
        mock_study.lock_dataset.assert_called_once()


def test_epoching_all_dropped_preserves_original_state_and_lock() -> None:
    sfreq = 100.0
    mne_raw = mne.io.RawArray(
        np.zeros((2, 1_000), dtype=np.float64),
        mne.create_info(["C3", "C4"], sfreq=sfreq, ch_types="eeg"),
        verbose=False,
    )
    mne_raw.set_annotations(
        mne.Annotations(
            onset=[0.0],
            duration=[float(mne_raw.times[-1])],
            description=["BAD_motion"],
        )
    )
    raw = Raw("all-dropped-raw.fif", mne_raw)
    raw.set_event(np.array([[200, 0, 1]], dtype=int), {"Event1": 1})
    study = Study()
    original_preprocessed = [raw]
    study.data_manager.loaded_data_list = [raw]
    study.data_manager.preprocessed_data_list = original_preprocessed
    controller = PreprocessController(study)

    with pytest.raises(ValueError, match=r"No usable epochs remain"):
        controller.apply_epoching(None, ["Event1"], -0.1, 0.5)

    assert study.preprocessed_data_list is original_preprocessed
    assert study.preprocessed_data_list[0] is raw
    assert raw.get_mne() is mne_raw
    assert study.epoch_data is None
    assert study.is_locked() is False


def test_get_unique_events(controller, mock_study):
    d1 = MagicMock()
    d1.get_event_list.return_value = (None, {"EventA": 1, "EventB": 2})
    d2 = MagicMock()
    d2.get_event_list.return_value = (None, {"EventB": 2, "EventC": 3})
    d3 = MagicMock()
    d3.get_event_list.side_effect = Exception("No events")

    mock_study.preprocessed_data_list = [d1, d2, d3]

    events = controller.get_unique_events()
    assert events == ["EventA", "EventB", "EventC"]


def test_get_runtime_diagnostics(controller, mock_study):
    d1 = MagicMock()
    d1.get_runtime_signals.return_value = ["duplicate channels", "note one"]
    d1.get_gdf_duplicate_channel_detail.return_value = {
        "kind": "gdf_duplicate_channel_names",
        "generated_bases": ["EEG"],
        "generated_channels": ["EEG-0", "EEG-1"],
        "message": "detail one",
    }
    d1.get_filename.return_value = "A01T.gdf"

    d2 = MagicMock()
    d2.get_runtime_signals.return_value = ["note one", "note two"]
    d2.get_gdf_duplicate_channel_detail.return_value = None

    mock_study.preprocessed_data_list = [d1, d2]

    diagnostics = controller.get_runtime_diagnostics()

    assert diagnostics["runtime_signals"] == [
        "duplicate channels",
        "note one",
        "note two",
    ]
    assert diagnostics["gdf_duplicate_channel_files"] == ["A01T.gdf"]
    assert diagnostics["gdf_duplicate_channel_details"] == [
        {
            "file": "A01T.gdf",
            "generated_bases": ["EEG"],
            "generated_channels": ["EEG-0", "EEG-1"],
            "message": "detail one",
        },
    ]
