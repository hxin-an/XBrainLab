import mne
import numpy as np
import pytest

from XBrainLab.backend.exceptions import DataMismatchError
from XBrainLab.backend.load_data import Raw, RawDataLoader
from XBrainLab.backend.study import Study

from .test_raw import _generate_mne, _set_event


def test_raw_data_loader():
    raw = Raw("tests/0.fif", _generate_mne(500, ["Fp1", "Fp2", "F3", "F4"], "eeg"))
    assert len(RawDataLoader()) == 0
    # no event check removed
    # with pytest.raises(ValueError):
    #     RawDataLoader([raw])
    # with event
    _set_event(raw)
    assert len(RawDataLoader([raw])) == 1
    # check empty list creation
    assert len(RawDataLoader()) == 0


def test_raw_data_loader_validate():
    with pytest.raises(ValueError):
        assert RawDataLoader().validate()


def _generate_epoch(name, raw_mne, duration):
    events = np.array([[1, 0, 1], [2, 0, 2], [3, 0, 3], [4, 0, 4]])
    event_id = {"a": 1, "b": 2, "c": 3, "d": 4}
    return Raw(
        f"tests/{name}.fif",
        mne.Epochs(
            raw_mne,
            events,
            event_id,
            tmin=0,
            tmax=duration,
            baseline=None,
            preload=True,
        ),
    )


def test_raw_data_loader_append():
    raw_mne = _generate_mne(500, ["Fp1", "Fp2", "F3", "F4"], "eeg")
    raw_1 = _generate_epoch("1", raw_mne, 0.1)
    raw_2 = _generate_epoch(
        "2", _generate_mne(500, ["Fp1", "Fp2", "F3", "F4"], "eeg"), 0.1
    )

    _set_event(raw_1)
    _set_event(raw_2)

    raw_data_loader = RawDataLoader()

    raw_data_loader.append(raw_1)
    assert len(raw_data_loader) == 1
    raw_data_loader.append(raw_2)
    assert len(raw_data_loader) == 2

    assert raw_data_loader.get_loaded_raw("empty") is None
    assert raw_data_loader.get_loaded_raw("tests/1.fif") == raw_1
    assert raw_data_loader.get_loaded_raw("tests/2.fif") == raw_2


def test_raw_data_loader_allows_mixed_sampling_rates_before_resampling() -> None:
    raw_100_hz = Raw(
        "tests/raw-100.fif",
        _generate_mne(100, ["Fp1", "Fp2", "F3", "F4"], "eeg"),
    )
    raw_256_hz = Raw(
        "tests/raw-256.fif",
        _generate_mne(256, ["Fp1", "Fp2", "F3", "F4"], "eeg"),
    )

    loader = RawDataLoader([raw_100_hz])
    loader.append(raw_256_hz)

    assert [item.get_sfreq() for item in loader] == [100.0, 256.0]


def test_raw_data_loader_append_error():
    raw_mne = _generate_mne(500, ["Fp1", "Fp2", "F3", "F4"], "eeg")
    raw_1 = _generate_epoch("1", raw_mne, 0.1)

    _set_event(raw_1)

    raw_miss_channel = _generate_epoch(
        "mc", _generate_mne(500, ["Fp1", "Fp2", "F3"], "eeg"), 0.1
    )
    raw_miss_sf = _generate_epoch(
        "ms", _generate_mne(5, ["Fp1", "Fp2", "F3", "F4"], "eeg"), 0.1
    )
    raw_miss_duration = _generate_epoch("ms", raw_mne, 0.2)
    raw_miss_type = Raw("test/mt.fif", raw_mne)

    raw_data_loader = RawDataLoader()
    raw_data_loader.append(raw_1)

    assert len(raw_data_loader) == 1

    with pytest.raises(DataMismatchError, match=r".*channel numbers inconsistent.*"):
        raw_data_loader.append(raw_miss_channel)

    with pytest.raises(DataMismatchError, match=r".*sample frequency inconsistent.*"):
        raw_data_loader.append(raw_miss_sf)

    with pytest.raises(DataMismatchError, match=r".*type inconsistent.*"):
        raw_data_loader.append(raw_miss_type)

    with pytest.raises(DataMismatchError, match=r".*duration inconsistent.*"):
        raw_data_loader.append(raw_miss_duration)


def test_raw_data_loader_rejects_swapped_channel_identity() -> None:
    reference = Raw(
        "tests/reference.fif",
        _generate_mne(500, ["C3", "C4"], "eeg"),
    )
    swapped = Raw(
        "tests/swapped.fif",
        _generate_mne(500, ["C4", "C3"], "eeg"),
    )

    loader = RawDataLoader([reference])

    with pytest.raises(DataMismatchError, match="channel names or order"):
        loader.append(swapped)


def test_raw_data_loader_rejects_changed_channel_types() -> None:
    reference = Raw(
        "tests/reference.fif",
        _generate_mne(500, ["C3", "EOG"], ["eeg", "eog"]),
    )
    changed_type = Raw(
        "tests/changed-type.fif",
        _generate_mne(500, ["C3", "EOG"], ["eeg", "eeg"]),
    )

    loader = RawDataLoader([reference])

    with pytest.raises(DataMismatchError, match="channel types"):
        loader.append(changed_type)


def test_apply():
    raw_mne = _generate_mne(500, ["Fp1", "Fp2", "F3", "F4"], "eeg")
    raw = Raw("test/mt.fif", raw_mne)
    _set_event(raw)

    lab = Study()
    RawDataLoader([raw]).apply(lab)
