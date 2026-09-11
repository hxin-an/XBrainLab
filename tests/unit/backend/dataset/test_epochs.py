import json
import re
import warnings
from pathlib import Path

import mne
import numpy as np
import pytest
import scipy.io

import XBrainLab.backend.dataset.epochs as epochs_module
from XBrainLab.backend.dataset import Epochs
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
