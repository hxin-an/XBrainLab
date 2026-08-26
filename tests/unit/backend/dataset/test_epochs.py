import json
import re
import warnings
from pathlib import Path
from unittest.mock import patch

import mne
import numpy as np
import pytest
import scipy.io

import XBrainLab.backend.dataset.epochs as epochs_module
from XBrainLab.backend.dataset import Epochs, SplitUnit
from XBrainLab.backend.load_data import Raw

epoch_duration = 3
n_class = 2
n_trial = 3
fs = 5
block_size = n_class * n_trial
subject_list = ["1", "2", "3"]
session_list = ["1", "2"]
event_id = {"c1": 0, "c2": 1}
ch_names = ["O1", "O2"]


@pytest.fixture
def preprocessed_data_list():
    events = np.zeros((n_class * n_trial, 3), dtype=int)
    events[:, 0] = np.arange(events.shape[0])
    events[:, 2] = np.arange(n_class).repeat(n_trial)

    ch_types = "eeg"

    result = []
    for subject in subject_list:
        for session in session_list:
            base = int(subject) * 100000 + int(session) * 1000
            info = mne.create_info(ch_names=ch_names, sfreq=fs, ch_types=ch_types)
            data = np.zeros((len(events), len(ch_names), epoch_duration * fs))
            for i in range(len(events)):
                data[i, :, :] = base + events[i, 0]
            epochs = mne.EpochsArray(
                data, info, events=events, tmin=0, event_id=event_id
            )
            raw = Raw(f"test/sub-{subject}_ses-{session}.fif", epochs)
            raw.set_subject_name(subject)
            raw.set_session_name(session)
            result.append(raw)
    return result


@pytest.fixture
def epochs(preprocessed_data_list):
    return Epochs(preprocessed_data_list)


@pytest.fixture
def full_filter_preview_mask(epochs):
    mask = np.ones(block_size * len(subject_list) * len(session_list), dtype=bool)
    filter_preview_mask = epochs._generate_mask_target(mask)
    return filter_preview_mask


def test_epochs_args_error():
    info = mne.create_info(ch_names=ch_names, sfreq=fs, ch_types="eeg")
    data = np.zeros((2, 5))
    raw = Raw("test/sub-01_ses-01_task-rest_eeg.fif", mne.io.RawArray(data, info))
    with pytest.raises(ValueError, match=r".*of type epoch."):
        Epochs([raw])


def test_epochs_subject_attributes(epochs):
    for subject in range(len(subject_list)):
        for session in range(len(session_list)):
            i = subject * len(session_list) + session
            assert (
                epochs.get_subject_list()[i * block_size : (i + 1) * block_size]
                == subject
            ).all()
    assert set(epochs.get_subject_map().values()) == set(subject_list)
    assert epochs.get_subject_index_list() == list(range(len(subject_list)))


def test_epochs_session_attributes(epochs):
    for subject in range(len(subject_list)):
        for session in range(len(session_list)):
            i = subject * len(session_list) + session
            assert (
                epochs.get_session_list()[i * block_size : (i + 1) * block_size]
                == session
            ).all()
    assert set(epochs.get_session_map().values()) == set(session_list)


def test_epochs_label_attributes(epochs):
    for subject in range(len(subject_list)):
        for session in range(len(session_list)):
            i = subject * len(session_list) + session
            assert (
                epochs.get_label_list()[i * block_size : (i + 1) * block_size]
                == np.arange(n_class).repeat(n_trial)
            ).all()
    assert set(epochs.get_label_map().values()) == set(event_id.keys())


def test_epochs_remaps_each_file_by_event_name_not_numeric_shape() -> None:
    info = mne.create_info(ch_names=["C3", "C4"], sfreq=10, ch_types="eeg")
    data = np.zeros((2, 2, 10))
    first = mne.EpochsArray(
        data,
        info,
        events=np.asarray([[0, 0, 0], [10, 0, 1]]),
        event_id={"left": 0, "right": 1},
        verbose=False,
    )
    second = mne.EpochsArray(
        data,
        info,
        events=np.asarray([[0, 0, 1], [10, 0, 0]]),
        event_id={"left": 1, "right": 0},
        verbose=False,
    )

    merged = Epochs([Raw("first-epo.fif", first), Raw("second-epo.fif", second)])

    assert merged.event_id == {"left": 0, "right": 1}
    assert merged.label.tolist() == [0, 1, 0, 1]
    assert merged.label_map == {0: "left", 1: "right"}


def test_epochs_rejects_channel_order_mismatch_before_concatenation() -> None:
    reference_info = mne.create_info(
        ch_names=["C3", "C4"],
        sfreq=10,
        ch_types="eeg",
    )
    swapped_info = mne.create_info(
        ch_names=["C4", "C3"],
        sfreq=10,
        ch_types="eeg",
    )
    events = np.asarray([[0, 0, 1]])
    reference = mne.EpochsArray(
        np.zeros((1, 2, 10)),
        reference_info,
        events=events,
        event_id={"class": 1},
        verbose=False,
    )
    swapped = mne.EpochsArray(
        np.zeros((1, 2, 10)),
        swapped_info,
        events=events,
        event_id={"class": 1},
        verbose=False,
    )

    with pytest.raises(ValueError, match="channel names or order"):
        Epochs([Raw("reference-epo.fif", reference), Raw("swapped-epo.fif", swapped)])


def test_epochs_copy(epochs):
    epochs_copy = epochs.copy()
    old_sfreq = epochs.sfreq
    epochs_copy.sfreq = -1
    assert epochs.sfreq == old_sfreq


def test_epochs_preserve_multi_file_source_window_provenance():
    info = mne.create_info(ch_names=["Cz"], sfreq=10.0, ch_types="eeg")

    def make_epochs(event_samples):
        events = np.column_stack(
            (
                np.asarray(event_samples),
                np.zeros(len(event_samples), dtype=int),
                np.ones(len(event_samples), dtype=int),
            ),
        )
        return mne.EpochsArray(
            np.zeros((len(event_samples), 1, 20)),
            info,
            events=events,
            event_id={"event": 1},
            tmin=-0.2,
            verbose=False,
        )

    source_a = "recordings/source-a-epo.fif"
    source_b = "recordings/source-b-epo.fif"
    epoch_data = Epochs(
        [
            Raw(source_a, make_epochs([100, 200])),
            Raw(source_b, make_epochs([100])),
        ],
    )

    provenance = epoch_data.get_epoch_window_provenance()

    assert len(provenance) == 3
    assert re.fullmatch(
        r"path-sha256:[0-9a-f]{64}",
        provenance[0].source_recording_id,
    )
    assert provenance[1].source_recording_id == provenance[0].source_recording_id
    assert provenance[2].source_recording_id != provenance[0].source_recording_id
    for item in provenance:
        assert str(Path(source_a).resolve()) not in item.source_recording_id
        assert Path(source_a).name not in item.source_recording_id
        assert Path(source_b).name not in item.source_recording_id
    assert [item.event_sample for item in provenance] == [100, 200, 100]
    assert [item.window_start_sample for item in provenance] == [98, 198, 98]
    assert [item.window_end_sample_exclusive for item in provenance] == [118, 218, 118]
    assert provenance[0].source_sfreq == 10.0
    assert provenance[0].epoch_sfreq == 10.0
    assert provenance[0].tmin_seconds == -0.2
    assert provenance[0].tmax_seconds == 1.7
    assert provenance[0].source_coordinates_verified is False


def test_epochs_array_fif_reload_does_not_upgrade_unknown_coordinates(
    tmp_path,
) -> None:
    info = mne.create_info(ch_names=["Cz"], sfreq=100.0, ch_types="eeg")
    events = np.column_stack(
        (
            np.asarray([100, 250, 400, 550, 700, 850]),
            np.zeros(6, dtype=int),
            np.asarray([1, 2, 1, 2, 1, 2]),
        ),
    )
    source_epochs = mne.EpochsArray(
        np.zeros((6, 1, 100)),
        info,
        events=events,
        event_id={"left": 1, "right": 2},
        verbose=False,
    )
    before = Epochs(
        [Raw(str(tmp_path / "source-array-epo.fif"), source_epochs)],
    ).get_epoch_window_provenance()
    saved_path = tmp_path / "reloaded-array-epo.fif"
    source_epochs.save(saved_path, overwrite=True, verbose=False)

    reloaded = mne.read_epochs(saved_path, preload=True, verbose=False)
    after = Epochs([Raw(str(saved_path), reloaded)]).get_epoch_window_provenance()

    assert len(set(source_epochs.events[:, 2])) == 2
    assert all(not item.source_coordinates_verified for item in before)
    assert all(not item.source_coordinates_verified for item in after)


def test_eeglab_imported_epochs_without_provenance_are_unknown(
    tmp_path,
) -> None:
    epoch_count = 6
    channel_count = 2
    sample_count = 20
    labels = ["left", "right", "left", "right", "left", "right"]
    epoch_rows = np.empty(epoch_count, dtype=object)
    event_rows = np.empty(epoch_count, dtype=object)
    for index, label in enumerate(labels):
        epoch_rows[index] = {"eventtype": label}
        event_rows[index] = {
            "latency": float(index * sample_count + 1),
            "type": label,
        }
    set_path = tmp_path / "imported-epochs.set"
    scipy.io.savemat(
        set_path,
        {
            "EEG": {
                "data": np.zeros(
                    (channel_count, sample_count, epoch_count),
                    dtype=np.float32,
                ),
                "trials": epoch_count,
                "nbchan": channel_count,
                "pnts": sample_count,
                "srate": 100.0,
                "xmin": 0.0,
                "xmax": (sample_count - 1) / 100.0,
                "chanlocs": np.asarray([], dtype=object),
                "epoch": epoch_rows,
                "event": event_rows,
            },
        },
    )

    imported = mne.io.read_epochs_eeglab(set_path, verbose=False)
    provenance = Epochs(
        [Raw(str(set_path), imported)],
    ).get_epoch_window_provenance()

    assert len(imported.event_id) == 2
    assert len(provenance) == epoch_count
    assert all(not item.source_coordinates_verified for item in provenance)


def test_explicit_xbrainlab_raw_event_provenance_survives_fif_reload(
    tmp_path,
) -> None:
    info = mne.create_info(ch_names=["Cz"], sfreq=100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, 1_000)), info, verbose=False)
    events = np.column_stack(
        (
            np.asarray([100, 250, 400, 550, 700, 850]),
            np.zeros(6, dtype=int),
            np.asarray([1, 2, 1, 2, 1, 2]),
        ),
    )
    source_epochs = mne.Epochs(
        raw,
        events,
        event_id={"left": 1, "right": 2},
        tmin=-0.1,
        tmax=0.89,
        baseline=None,
        preload=True,
        verbose=False,
    )
    source = Raw("/recordings/reviewed-source.fif", source_epochs)
    source.set_source_content_identity(
        {
            "algorithm": "sha256",
            "sha256": "d" * 64,
            "file_bytes": 80_000,
        },
    )
    source.add_preprocess("Epoching -0.1 ~ 0.89 by event (None baseline)")
    before = Epochs([source]).get_epoch_window_provenance()
    saved_path = tmp_path / "verified-source-epo.fif"
    source_epochs.save(saved_path, overwrite=True, verbose=False)

    reloaded = mne.read_epochs(saved_path, preload=True, verbose=False)
    after = Epochs([Raw(str(saved_path), reloaded)]).get_epoch_window_provenance()

    assert all(item.source_coordinates_verified for item in before)
    assert all(item.source_coordinates_verified for item in after)
    assert after == before


def test_stale_serialized_provenance_fails_closed_after_reload(
    tmp_path,
) -> None:
    info = mne.create_info(ch_names=["Cz"], sfreq=100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, 500)), info, verbose=False)
    mne_epochs = mne.Epochs(
        raw,
        np.asarray([[100, 0, 1], [300, 0, 2]]),
        event_id={"left": 1, "right": 2},
        tmin=0.0,
        tmax=0.99,
        baseline=None,
        preload=True,
        verbose=False,
    )
    source = Raw("/recordings/source.fif", mne_epochs)
    source.add_preprocess("Epoching 0.0 ~ 0.99 by event (None baseline)")
    assert all(
        item.source_coordinates_verified
        for item in Epochs([source]).get_epoch_window_provenance()
    )
    saved_path = tmp_path / "marked-source-epo.fif"
    mne_epochs.save(saved_path, overwrite=True, verbose=False)
    reloaded = mne.read_epochs(saved_path, preload=True, verbose=False)
    metadata = reloaded.metadata
    assert metadata is not None
    marker_column = epochs_module.EPOCH_SOURCE_PROVENANCE_METADATA_COLUMN
    payload = json.loads(metadata.loc[0, marker_column])
    payload["event_sample"] = 101
    metadata.loc[0, marker_column] = json.dumps(payload)
    reloaded.metadata = metadata

    provenance = Epochs(
        [Raw(str(saved_path), reloaded)],
    ).get_epoch_window_provenance()

    assert all(not item.source_coordinates_verified for item in provenance)


def test_epoch_source_identity_uses_the_canonical_path_fingerprint(
    tmp_path,
    monkeypatch,
):
    info = mne.create_info(ch_names=["Cz"], sfreq=10.0, ch_types="eeg")

    def make_epochs(event_sample):
        events = np.asarray([[event_sample, 0, 1]])
        return mne.EpochsArray(
            np.zeros((1, 1, 10)),
            info,
            events=events,
            event_id={"event": 1},
            verbose=False,
        )

    source_path = tmp_path / "participant-secret-source.fif"
    other_path = tmp_path / "participant-secret-source-copy.fif"
    monkeypatch.chdir(tmp_path)
    epoch_data = Epochs(
        [
            Raw(source_path.name, make_epochs(100)),
            Raw(str(source_path), make_epochs(200)),
            Raw(str(other_path), make_epochs(300)),
        ],
    )

    source_ids = [
        item.source_recording_id for item in epoch_data.get_epoch_window_provenance()
    ]

    assert source_ids[0] == source_ids[1]
    assert source_ids[2] != source_ids[0]
    assert all(re.fullmatch(r"path-sha256:[0-9a-f]{64}", value) for value in source_ids)
    assert source_path.name not in "".join(source_ids)
    assert str(tmp_path) not in "".join(source_ids)


def test_epoch_source_identity_prefers_reviewed_content_over_copy_path() -> None:
    info = mne.create_info(ch_names=["Cz"], sfreq=10.0, ch_types="eeg")

    def make_epochs(event_sample: int) -> mne.BaseEpochs:
        raw = mne.io.RawArray(np.zeros((1, 500)), info, verbose=False)
        return mne.Epochs(
            raw,
            np.asarray([[event_sample, 0, 1]]),
            event_id={"event": 1},
            tmin=0.0,
            tmax=0.9,
            baseline=None,
            preload=True,
            verbose=False,
        )

    shared_digest = "a" * 64
    original = Raw("/recordings/original.fif", make_epochs(100))
    copied = Raw("/other/location/copied.fif", make_epochs(100))
    different = Raw("/recordings/different.fif", make_epochs(100))
    for raw in (original, copied):
        raw.set_source_content_identity(
            {"algorithm": "sha256", "sha256": shared_digest, "file_bytes": 42},
        )
    different.set_source_content_identity(
        {"algorithm": "sha256", "sha256": "b" * 64, "file_bytes": 42},
    )
    for source in (original, copied, different):
        epochs_module.mark_xbrainlab_raw_event_source_epochs(source)

    provenance = Epochs(
        [original, copied, different],
    ).get_epoch_window_provenance()

    assert provenance[0].source_recording_id == f"content-sha256:{shared_digest}"
    assert provenance[1].source_recording_id == provenance[0].source_recording_id
    assert provenance[2].source_recording_id == f"content-sha256:{'b' * 64}"
    assert all(item.source_coordinates_verified for item in provenance)


@pytest.mark.parametrize(
    "identity",
    [
        {"algorithm": "md5", "sha256": "a" * 64, "file_bytes": 10},
        {"algorithm": "sha256", "sha256": "not-a-digest", "file_bytes": 10},
        {"algorithm": "sha256", "sha256": "a" * 64, "file_bytes": -1},
        {"algorithm": "sha256", "sha256": "a" * 64, "file_bytes": True},
    ],
)
def test_raw_rejects_malformed_reviewed_content_identity(identity) -> None:
    info = mne.create_info(ch_names=["Cz"], sfreq=10.0, ch_types="eeg")
    raw = Raw(
        "identity.edf",
        mne.io.RawArray(np.zeros((1, 100)), info, verbose=False),
    )

    with pytest.raises((TypeError, ValueError), match="Source content identity"):
        raw.set_source_content_identity(identity)


def test_malformed_runtime_source_identity_fails_closed() -> None:
    info = mne.create_info(ch_names=["Cz"], sfreq=10.0, ch_types="eeg")
    mne_raw = mne.io.RawArray(np.zeros((1, 500)), info, verbose=False)
    mne_epochs = mne.Epochs(
        mne_raw,
        np.asarray([[100, 0, 1]]),
        event_id={"event": 1},
        tmin=0.0,
        tmax=0.9,
        baseline=None,
        preload=True,
        verbose=False,
    )
    source = Raw(
        "/recordings/source.fif",
        mne_epochs,
    )
    source.set_runtime_detail(
        "source_content_identity",
        {"algorithm": "sha256", "sha256": "broken", "file_bytes": 42},
    )

    provenance = Epochs([source]).get_epoch_window_provenance()

    assert provenance[0].source_recording_id.startswith("unverified-wrapper-sha256:")
    assert provenance[0].source_coordinates_verified is False


def test_blank_and_invalid_source_paths_are_unverified_and_do_not_merge():
    info = mne.create_info(ch_names=["Cz"], sfreq=100.0, ch_types="eeg")

    def make_epochs(event_sample):
        raw = mne.io.RawArray(np.zeros((1, 500)), info, verbose=False)
        return mne.Epochs(
            raw,
            np.asarray([[event_sample, 0, 1]]),
            event_id={"event": 1},
            tmin=0.0,
            tmax=0.99,
            baseline=None,
            preload=True,
            verbose=False,
        )

    epoch_data = Epochs(
        [
            Raw("", make_epochs(100)),
            Raw("   ", make_epochs(120)),
            Raw("\x00", make_epochs(140)),
        ],
    )

    provenance = epoch_data.get_epoch_window_provenance()
    source_ids = [item.source_recording_id for item in provenance]

    assert all(not item.source_coordinates_verified for item in provenance)
    assert len(set(source_ids)) == 3
    assert all(
        re.fullmatch(r"unverified-wrapper-sha256:[0-9a-f]{64}", value)
        for value in source_ids
    )
    assert len(set(epoch_data.get_trial_group_list().tolist())) == 3


def test_epochs_use_mne_source_sfreq_after_epoch_resampling():
    info = mne.create_info(ch_names=["Cz"], sfreq=100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, 500)), info, verbose=False)
    mne_epochs = mne.Epochs(
        raw,
        np.asarray([[100, 0, 1]]),
        event_id={"event": 1},
        tmin=-0.1,
        tmax=0.89,
        baseline=None,
        preload=True,
        verbose=False,
    )
    mne_epochs.resample(50.0)

    source = Raw("recordings/resampled-source.fif", mne_epochs)
    epochs_module.mark_xbrainlab_raw_event_source_epochs(source)
    provenance = Epochs([source]).get_epoch_window_provenance()[0]

    assert provenance.event_sample == 100
    assert provenance.source_sfreq == 100.0
    assert provenance.epoch_sfreq == 50.0
    assert provenance.source_coordinates_verified is True
    assert provenance.window_start_sample == 90
    assert provenance.window_end_sample_exclusive == 190


def test_epochs_accept_mne_array_source_sfreq_without_deprecation_warning():
    info = mne.create_info(ch_names=["Cz"], sfreq=100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, 500)), info, verbose=False)
    mne_epochs = mne.Epochs(
        raw,
        np.asarray([[100, 0, 1]]),
        event_id={"event": 1},
        tmin=0.0,
        tmax=0.99,
        baseline=None,
        preload=True,
        verbose=False,
    )
    mne_epochs._raw_sfreq = np.asarray([100.0])

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        provenance = Epochs(
            [Raw("recordings/array-sfreq-source.fif", mne_epochs)],
        ).get_epoch_window_provenance()[0]

    assert provenance.source_sfreq == 100.0


def test_epochs_get_by_mask(epochs):
    mask = np.zeros(block_size * len(subject_list) * len(session_list), dtype=bool)
    mask[block_size : block_size * 2] = True
    assert np.allclose(
        epochs.get_subject_list_by_mask(mask), np.array([0] * block_size)
    )
    assert np.allclose(
        epochs.get_session_list_by_mask(mask), np.array([1] * block_size)
    )
    assert np.allclose(
        epochs.get_label_list_by_mask(mask), np.arange(n_class).repeat(n_trial)
    )
    assert np.allclose(epochs.get_idx_list_by_mask(mask), np.arange(block_size))

    mask &= False
    count = block_size * len(session_list)
    mask[count : count + block_size * len(session_list)] = True
    assert (epochs.pick_subject_mask_by_idx(1) == mask).all()


def test_epochs_get_by_index(epochs):
    for idx, name in enumerate(subject_list):
        assert epochs.get_subject_name(idx) == name

    for idx, name in enumerate(session_list):
        assert epochs.get_session_name(idx) == name

    for idx, name in enumerate(event_id):
        assert epochs.get_label_name(idx) == name


def test_epochs_info(epochs):
    assert epochs.get_data_length() == block_size * len(subject_list) * len(
        session_list
    )
    model_args = epochs.get_model_args()
    chs_info = model_args.pop("chs_info")
    assert model_args == {
        "n_classes": len(event_id),
        "channels": len(ch_names),
        "samples": epoch_duration * fs,
        "sfreq": fs,
    }
    assert [channel["ch_name"] for channel in chs_info] == ch_names
    assert all(len(channel["loc"]) == 12 for channel in chs_info)
    assert epochs.get_data().shape == (
        block_size * len(subject_list) * len(session_list),
        len(ch_names),
        epoch_duration * fs,
    )
    # Verify data content (not just shape)
    # The data was initialized with base + events[i, 0]
    # We can check if the first epoch's data is consistent
    assert (
        epochs.get_data()[0, 0, 0] == 101000 + 0
    )  # subject 1 (idx 0) * 100000 + session 1 (idx 0) * 1000 + event 0

    assert epochs.get_label_number() == len(event_id)
    assert epochs.get_channel_names() == ch_names
    assert np.isclose(epochs.get_epoch_duration(), epoch_duration)


def test_epochs_set_channel(epochs):
    original_data = epochs.get_data().copy()
    new_ch_names = ["O2"]
    channel_position = np.random.rand(1, 3).tolist()
    epochs.set_channels(new_ch_names, channel_position)
    assert epochs.get_channel_names() == new_ch_names
    np.testing.assert_array_equal(epochs.get_montage_position(), channel_position)
    np.testing.assert_array_equal(epochs.get_data(), original_data[:, [1], :])


def test_epochs_set_channels_reorders_data_with_channel_identity(epochs):
    epochs.data[:, 0, :] = 1.0
    epochs.data[:, 1, :] = 2.0
    original_data = epochs.get_data().copy()
    positions = [(0.1, 0.2, 0.3), (0.4, 0.5, 0.6)]

    epochs.set_channels(["O2", "O1"], positions)

    assert epochs.get_channel_names() == ["O2", "O1"]
    assert epochs.get_montage_position() == positions
    np.testing.assert_array_equal(epochs.get_data(), original_data[:, [1, 0], :])


def test_epochs_set_channel_positions_preserves_channel_axis_for_partial_layout(epochs):
    """A layout annotates existing channels; it must never select/reorder them."""
    original_names = list(epochs.get_channel_names())
    original_data = epochs.get_data().copy()

    epochs.set_channel_positions({"O2": (0.1, 0.2, 0.3)})

    assert epochs.get_channel_names() == original_names
    np.testing.assert_array_equal(epochs.get_data(), original_data)
    assert epochs.get_montage_position() == [None, (0.1, 0.2, 0.3)]


def test_epochs_partial_layout_keeps_model_context_unpositioned_channels(epochs):
    epochs.set_channel_positions({"O2": (0.1, 0.2, 0.3)})

    channel_info = epochs.get_model_args()["chs_info"]

    assert channel_info[0]["ch_name"] == "O1"
    assert np.isnan(channel_info[0]["loc"][:3]).all()
    np.testing.assert_allclose(channel_info[1]["loc"][:3], (0.1, 0.2, 0.3))


@pytest.mark.parametrize(
    ("channels", "positions", "message"),
    [
        (["missing"], [(0.0, 0.0, 0.0)], "unknown channel"),
        (["O1", "O1"], [(0.0, 0.0, 0.0)] * 2, "unique"),
        (["O1"], [], "equal length"),
        (["O1"], [(0.0, float("nan"), 0.0)], "finite"),
    ],
)
def test_epochs_set_channels_fails_atomically(
    epochs,
    channels,
    positions,
    message,
):
    original_names = list(epochs.get_channel_names())
    original_data = epochs.get_data().copy()
    original_positions = epochs.get_montage_position()

    with pytest.raises(ValueError, match=message):
        epochs.set_channels(channels, positions)

    assert epochs.get_channel_names() == original_names
    assert epochs.get_montage_position() == original_positions
    np.testing.assert_array_equal(epochs.get_data(), original_data)


def test_epochs_generate_mask_target(full_filter_preview_mask):
    for label_idx in range(len(event_id)):
        assert label_idx in full_filter_preview_mask
        for subject_idx in range(len(subject_list)):
            assert subject_idx in full_filter_preview_mask[label_idx]
            for session_idx in range(len(session_list)):
                assert session_idx in full_filter_preview_mask[label_idx][subject_idx]
                target_filter_mask, counter = full_filter_preview_mask[label_idx][
                    subject_idx
                ][session_idx]
                assert counter == 0
                assert target_filter_mask.shape == (
                    block_size * len(session_list) * len(subject_list),
                )
                assert sum(target_filter_mask) == n_trial


def test_epochs_generate_mask_target_partial(epochs):
    mask = np.ones(block_size * len(subject_list) * len(session_list), dtype=bool)
    mask[: block_size * len(session_list)] = False
    filter_preview_mask = epochs._generate_mask_target(mask)
    for label_idx in range(len(event_id)):
        assert label_idx in filter_preview_mask
        for subject_idx in range(len(subject_list)):
            assert subject_idx in filter_preview_mask[label_idx]
            for session_idx in range(len(session_list)):
                assert session_idx in filter_preview_mask[label_idx][subject_idx]
                target_filter_mask, counter = filter_preview_mask[label_idx][
                    subject_idx
                ][session_idx]
                assert counter == 0
                assert target_filter_mask.shape == (
                    block_size * len(session_list) * len(subject_list),
                )
                if subject_idx == 0:
                    assert sum(target_filter_mask) == 0
                else:
                    assert sum(target_filter_mask) == n_trial


def test_epochs_get_filtered_mask_pair(epochs, full_filter_preview_mask):
    for label_idx in range(len(event_id)):
        for subject_idx in range(len(subject_list)):
            for session_idx in range(len(session_list)):
                full_filter_preview_mask[label_idx][subject_idx][session_idx][1] = 1
    target_session = 1
    target_label = 0
    target_subject = 2
    full_filter_preview_mask[target_label][target_subject][target_session][1] = 0
    expect = full_filter_preview_mask[target_label][target_subject][target_session]
    result = epochs._get_filtered_mask_pair(full_filter_preview_mask)
    assert (expect[0] == result[0]).all()
    assert expect[1] == result[1]


def test_epochs_update_mask_target(epochs, full_filter_preview_mask):
    pos = np.zeros(block_size * len(subject_list) * len(session_list), dtype=bool)
    pos[: block_size * len(session_list)] = True
    epochs._update_mask_target(full_filter_preview_mask, pos)
    for label_idx in range(len(event_id)):
        for subject_idx in range(len(subject_list)):
            for session_idx in range(len(session_list)):
                target = full_filter_preview_mask[label_idx][subject_idx][session_idx]
                if subject_idx == 0:
                    assert target[1] == n_trial
                    assert sum(target[0]) == 0
                else:
                    assert target[1] == 0
                    assert sum(target[0]) == n_trial


def _test_epochs_get_real_num_param():
    params = [
        (1, SplitUnit.NUMBER, 1),
        (4, SplitUnit.NUMBER, 4),
        (200, SplitUnit.NUMBER, 4),
    ]
    params += [(i, SplitUnit.RATIO, int(i * 4)) for i in np.arange(0, 1, 0.1)]
    return params


@pytest.mark.parametrize(
    "value, split_unit, expected", _test_epochs_get_real_num_param()
)
@pytest.mark.parametrize(
    "mask, clean_mask",
    [
        (np.ones(16, dtype=bool), None),
        (np.zeros(16, dtype=bool), np.ones(16, dtype=bool)),
    ],
)
def test_epochs_get_real_num(epochs, value, split_unit, expected, mask, clean_mask):
    target_type = np.arange(4).repeat(4)
    group_idx = 0
    assert expected == epochs._get_real_num(
        target_type, value, split_unit, mask, clean_mask, group_idx
    )


def _test_epochs_get_real_num_partial_param():
    params = [
        (1, SplitUnit.NUMBER, 1),
        (4, SplitUnit.NUMBER, 3),
        (200, SplitUnit.NUMBER, 3),
    ]
    params += [(i, SplitUnit.RATIO, int(i * 3)) for i in np.arange(0, 1, 0.1)]
    return params


@pytest.mark.parametrize(
    "value, split_unit, expected", _test_epochs_get_real_num_partial_param()
)
def test_epochs_get_real_num_partial(epochs, value, split_unit, expected):
    target_type = np.arange(4).repeat(4)
    group_idx = 0
    mask = np.ones(16, dtype=bool)
    clean_mask = None
    mask[:4] = False
    assert expected == epochs._get_real_num(
        target_type, value, split_unit, mask, clean_mask, group_idx
    )


@pytest.mark.parametrize(
    "value, group_idx, expected, is_partial",
    [
        (1, 0, 4, 0),
        (2, 0, 2, 0),
        (2, 1, 2, 0),
        (3, 0, 2, 0),
        (3, 1, 1, 0),
        (3, 2, 1, 0),
        (1, 0, 3, 1),
        (2, 0, 2, 1),
        (2, 1, 1, 1),
        (3, 0, 1, 1),
        (3, 1, 1, 1),
        (3, 2, 1, 1),
    ],
)
def test_epochs_get_real_num_k_fold(epochs, value, group_idx, expected, is_partial):
    target_type = np.arange(4).repeat(4)
    split_unit = SplitUnit.KFOLD
    mask = np.ones(16, dtype=bool)
    if is_partial:
        mask[:4] = False
    clean_mask = None

    assert expected == epochs._get_real_num(
        target_type, value, split_unit, mask, clean_mask, group_idx
    )


def test_epochs_get_real_num_not_implemented(epochs):
    with pytest.raises(NotImplementedError):
        epochs._get_real_num(np.arange(4), 1, "test", np.ones(4, dtype=bool), None, 0)


@pytest.mark.parametrize("selected_num", np.arange(block_size + 2))
@pytest.mark.parametrize("is_partial", [False, True])
def test_epochs_pick(epochs, selected_num, is_partial):
    target_type = np.arange(block_size).repeat(len(subject_list) * len(session_list))
    mask = np.ones(len(target_type), dtype=bool)
    real_block_size = block_size
    if is_partial:
        mask[:block_size] = False
        real_block_size -= 1
    old_mask = mask.copy()
    clean_mask = None
    value = 0
    split_unit = 0
    group_idx = 0

    with patch.object(epochs, "_get_real_num", return_value=selected_num):
        ret, new_mask = epochs._pick(
            target_type, mask, clean_mask, value, split_unit, group_idx
        )

    assert (new_mask == mask).all()
    if is_partial:
        assert sum(ret) == sum(old_mask & ret)
    selected = target_type[ret]
    non_selected = target_type[np.logical_not(ret)]

    selected_idx_list = np.unique(selected)
    non_selected_idx_list = np.unique(non_selected)
    if selected_num > real_block_size:
        assert len(selected_idx_list) == real_block_size
    else:
        assert len(selected_idx_list) == selected_num

    assert len(set(selected_idx_list).intersection(set(non_selected_idx_list))) == 0


def test_epochs_pick_manual(epochs):
    target_type = np.arange(block_size).repeat(len(subject_list) * len(session_list))
    mask = np.ones(len(target_type), dtype=bool)
    value = [3, 5]
    result, new_mask = epochs._pick_manual(target_type, mask, value)

    assert (new_mask == mask).all()
    selected = target_type[result]
    non_selected = target_type[np.logical_not(result)]
    selected_idx_list = np.unique(selected)
    non_selected_idx_list = np.unique(non_selected)

    assert set(selected_idx_list) == set(value)
    assert len(set(selected_idx_list).intersection(set(non_selected_idx_list))) == 0


@pytest.mark.parametrize(
    "func_name, target_type_name",
    [("pick_subject", "get_subject_list"), ("pick_session", "get_session_list")],
)
@pytest.mark.parametrize(
    "split_unit, is_manual",
    [
        (SplitUnit.MANUAL, True),
        (SplitUnit.NUMBER, False),
        (SplitUnit.KFOLD, False),
        (SplitUnit.RATIO, False),
    ],
)
def test_epochs_pick_by_wrapper(
    epochs, func_name, split_unit, is_manual, target_type_name
):
    with (
        patch.object(epochs, "_pick") as pick_mock,
        patch.object(epochs, "_pick_manual") as manual_mock,
    ):
        target_type = getattr(epochs, target_type_name)()
        mask = np.random.randint(0, 2, size=len(target_type), dtype=bool)
        clean_mask = None
        group_idx = 5
        value = [1, 2, 3]
        # call func_name of epochs
        func = getattr(epochs, func_name)

        func(mask, clean_mask, value, split_unit, group_idx)
        if is_manual:
            manual_mock.assert_called_once()
            pick_mock.assert_not_called()
            (_target_type, _mask, _value), _ = manual_mock.call_args
            assert (_target_type == target_type).all()
            assert (_mask == mask).all()
            assert _value == value
        else:
            pick_mock.assert_called_once()
            manual_mock.assert_not_called()
            (
                (_target_type, _mask, _clean_mask, _value, _split_unit, _group_idx),
                _,
            ) = pick_mock.call_args
            assert (_target_type == target_type).all()
            assert (_mask == mask).all()
            assert _clean_mask == clean_mask
            assert _value == value
            assert _split_unit == split_unit
            assert _group_idx == group_idx


def test_epochs_pick_manual_trial(epochs):
    mask = np.ones(block_size * len(subject_list) * len(session_list), dtype=bool)
    clean_mask = None
    value = np.random.randint(
        0, 2, size=block_size * len(subject_list) * len(session_list), dtype=bool
    )

    # Convert boolean mask to list of indices where True
    value_indices = np.where(value)[0].tolist()
    result, _ = epochs.pick_trial(mask, clean_mask, value_indices, SplitUnit.MANUAL, 0)
    assert (result == value).all()


def _generate_expected_epochs_pick_by_trial_param(count, is_partial):
    expected = np.zeros(block_size * len(subject_list) * len(session_list), dtype=bool)
    for repeat in range(n_trial):
        for sess in range(len(session_list)):
            for sub in range(len(subject_list)):
                for label in range(n_class):
                    if count <= 0:
                        break
                    if is_partial and sub == 0:
                        continue
                    expected[
                        (n_trial - repeat - 1)
                        + label * n_trial
                        + sess * block_size
                        + sub * block_size * len(session_list)
                    ] = True
                    count -= 1
    return expected


def _test_epochs_pick_by_trial_partial_param():
    is_partial = True
    total_count = block_size * (len(subject_list) - 1) * len(session_list)
    params = [
        (
            SplitUnit.NUMBER,
            i,
            _generate_expected_epochs_pick_by_trial_param(i, is_partial),
            0,
            is_partial,
        )
        for i in range(block_size * len(subject_list) * len(session_list) + 2)
    ]
    params += [
        (
            SplitUnit.KFOLD,
            1,
            _generate_expected_epochs_pick_by_trial_param(total_count, is_partial),
            0,
            is_partial,
        )
    ]
    for i in range(4):
        params.append(
            (
                SplitUnit.KFOLD,
                10,
                _generate_expected_epochs_pick_by_trial_param(3, is_partial),
                i,
                is_partial,
            )
        )
    for i in range(2):
        params.append(
            (
                SplitUnit.KFOLD,
                10,
                _generate_expected_epochs_pick_by_trial_param(2, is_partial),
                4 + i,
                is_partial,
            ),
        )

    for i in np.arange(0, 1, 0.1):
        count = int(i * total_count)
        expected = _generate_expected_epochs_pick_by_trial_param(count, is_partial)
        params.append((SplitUnit.RATIO, i, expected, 0, is_partial))
    return params


def _test_epochs_pick_by_trial_param():
    params = []
    is_partial = False
    total_count = block_size * len(subject_list) * len(session_list)
    params += [
        (
            SplitUnit.NUMBER,
            i,
            _generate_expected_epochs_pick_by_trial_param(i, is_partial),
            0,
            is_partial,
        )
        for i in range(block_size * len(subject_list) * len(session_list) + 2)
    ]
    params += [
        (
            SplitUnit.KFOLD,
            1,
            _generate_expected_epochs_pick_by_trial_param(total_count, is_partial),
            0,
            is_partial,
        ),
        (
            SplitUnit.KFOLD,
            10,
            _generate_expected_epochs_pick_by_trial_param(4, is_partial),
            0,
            is_partial,
        ),
        (
            SplitUnit.KFOLD,
            10,
            _generate_expected_epochs_pick_by_trial_param(4, is_partial),
            1,
            is_partial,
        ),
        (
            SplitUnit.KFOLD,
            10,
            _generate_expected_epochs_pick_by_trial_param(4, is_partial),
            2,
            is_partial,
        ),
        (
            SplitUnit.KFOLD,
            10,
            _generate_expected_epochs_pick_by_trial_param(3, is_partial),
            6,
            is_partial,
        ),
    ]
    for i in np.arange(0, 1, 0.1):
        count = int(i * total_count)
        expected = _generate_expected_epochs_pick_by_trial_param(count, is_partial)
        params.append((SplitUnit.RATIO, i, expected, 0, is_partial))
    params += _test_epochs_pick_by_trial_partial_param()
    return params


@pytest.mark.parametrize(
    "split_unit, value, expected, group_idx, is_partial",
    _test_epochs_pick_by_trial_param(),
)
@pytest.mark.parametrize(
    "clean_mask",
    [None, np.ones(block_size * len(subject_list) * len(session_list), dtype=bool)],
)
def test_epochs_pick_by_trial(
    epochs, clean_mask, split_unit, value, expected, group_idx, is_partial
):
    mask = np.ones(block_size * len(subject_list) * len(session_list), dtype=bool)
    if is_partial:
        if clean_mask is not None:
            clean_mask[: block_size * len(session_list)] = False
        mask[: block_size * len(session_list)] = False
    result, new_mask = epochs.pick_trial(mask, clean_mask, value, split_unit, group_idx)
    assert (new_mask == mask).all()
    assert sum(result) == sum(expected)
    assert (result == expected).all()


def test_epochs_pick_by_trial_not_implemented(epochs):
    with pytest.raises(NotImplementedError):
        epochs.pick_trial(np.arange(4), None, 1, "test", 0)


def test_epochs_pick_subject(epochs):
    # Test picking subjects without mocks
    mask = np.ones(epochs.get_data_length(), dtype=bool)
    clean_mask = None

    # Pick 1 subject
    selected_mask, remaining_mask = epochs.pick_subject(
        mask, clean_mask, 1, SplitUnit.NUMBER, 0
    )

    # Verify selection
    selected_subjects = epochs.get_subject_list()[selected_mask]
    unique_selected = np.unique(selected_subjects)
    assert len(unique_selected) == 1
    assert sum(selected_mask) == block_size * len(
        session_list
    )  # 1 subject * sessions * trials

    # Check that selected and remaining cover the original mask (which was all True)
    # Note: mask might be modified in-place inside pick_subject depending on
    # implementation, so we check if their union is all True.
    assert (selected_mask | remaining_mask).all()
    assert not (selected_mask & remaining_mask).any()

    # Pick 50% subjects (Ratio 0.5) -> Should pick 1 out of 3 (int(3*0.5)=1)
    mask = np.ones(epochs.get_data_length(), dtype=bool)
    selected_mask, remaining_mask = epochs.pick_subject(
        mask, clean_mask, 0.5, SplitUnit.RATIO, 0
    )
    selected_subjects = epochs.get_subject_list()[selected_mask]
    unique_selected = np.unique(selected_subjects)
    assert len(unique_selected) == 1


def test_epochs_pick_session(epochs):
    # Test picking sessions without mocks
    mask = np.ones(epochs.get_data_length(), dtype=bool)
    clean_mask = None

    # Pick 1 session
    selected_mask, _remaining_mask = epochs.pick_session(
        mask, clean_mask, 1, SplitUnit.NUMBER, 0
    )

    # Verify selection
    selected_sessions = epochs.get_session_list()[selected_mask]
    unique_selected = np.unique(selected_sessions)
    assert len(unique_selected) == 1
    assert sum(selected_mask) == block_size * len(
        subject_list
    )  # 1 session * subjects * trials

    # Pick specific session manually
    mask = np.ones(epochs.get_data_length(), dtype=bool)
    # Session list is [0, 1] mapped from ['1', '2']
    # Let's pick session index 0
    selected_mask, _remaining_mask = epochs.pick_session(
        mask, clean_mask, [0], SplitUnit.MANUAL, 0
    )
    selected_sessions = epochs.get_session_list()[selected_mask]
    assert np.all(selected_sessions == 0)
