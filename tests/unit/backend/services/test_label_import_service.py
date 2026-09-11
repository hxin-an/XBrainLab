"""Tests for LabelImportService's retained label-application boundaries.

Targets: apply_labels_batch_checked, apply_labels_to_single_file, and
get_epoch_count_for_file.
"""

from unittest.mock import MagicMock, patch

import mne
import numpy as np
import pytest

from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.services.label_import_errors import AtomicLabelApplyError
from XBrainLab.backend.services.label_import_service import LabelImportService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_data_mock(filepath="/data/sub01.set", is_raw=True, epoch_length=0):
    """Create a mock data (Raw) object."""
    data = MagicMock()
    data.get_filepath.return_value = filepath
    data.get_filename.return_value = filepath.split("/")[-1]
    data.is_raw.return_value = is_raw
    data.get_epochs_length.return_value = epoch_length
    data.get_event_list.return_value = (
        np.array([[0, 0, 1], [1, 0, 2], [2, 0, 1]]),
        {"EventA": 1, "EventB": 2},
    )
    return data


@pytest.fixture
def service():
    return LabelImportService()


# ---------------------------------------------------------------------------
# get_epoch_count_for_file
# ---------------------------------------------------------------------------


class TestGetEpochCountForFile:
    def test_raw_no_filter(self, service):
        data = _make_data_mock()
        count = service.get_epoch_count_for_file(data, None)
        assert count == 3  # 3 events

    def test_raw_with_filter(self, service):
        data = _make_data_mock()
        count = service.get_epoch_count_for_file(data, {"EventA"})
        assert count == 2  # EventA has id=1, appears twice

    def test_raw_filter_matches_numeric_alias_from_event_name(self, service):
        data = _make_data_mock()
        data.get_event_list.return_value = (
            np.array([[0, 0, 1], [1, 0, 2], [2, 0, 1]]),
            {"Stimulus/S 768": 1, "Stimulus/S 769": 2},
        )

        count = service.get_epoch_count_for_file(data, {"768"})

        assert count == 2

    def test_raw_filter_no_match(self, service):
        data = _make_data_mock()
        count = service.get_epoch_count_for_file(data, {"NoMatch"})
        assert count == 0

    def test_epochs_not_raw(self, service):
        data = _make_data_mock(is_raw=False, epoch_length=50)
        count = service.get_epoch_count_for_file(data, None)
        assert count == 50

    def test_raw_empty_event_id_map(self, service):
        data = _make_data_mock()
        data.get_event_list.return_value = (np.array([[0, 0, 1]]), {})
        count = service.get_epoch_count_for_file(data, {"EventA"})
        assert count == 1  # Falls through to len(events)


# ---------------------------------------------------------------------------
# apply_labels_to_single_file
# ---------------------------------------------------------------------------


class TestApplyLabelsToSingleFile:
    def test_sequence_mode_blocks_ambiguous_balanced_groups_without_target(
        self,
        service,
    ):
        data = _make_data_mock()
        data.get_event_list.return_value = (
            np.asarray(
                [[index, 0, event_id] for event_id in (1, 2) for index in range(5)]
                + [
                    [100 + index, 0, event_id]
                    for event_id in (3, 4, 5, 6, 7)
                    for index in range(2)
                ],
            ),
            {
                "trial/start-a": 1,
                "trial/start-b": 2,
                "cue/a": 3,
                "cue/b": 4,
                "cue/c": 5,
                "cue/d": 6,
                "cue/e": 7,
            },
        )
        labels = [1, 2] * 5
        mapping = {1: "A", 2: "B"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            mock_loader = MockLoader.return_value
            with pytest.raises(ValueError, match="explicit target EEG event"):
                service.apply_labels_to_single_file(data, labels, mapping)

            MockLoader.assert_not_called()
            mock_loader.create_event.assert_not_called()
            mock_loader.apply.assert_not_called()
            data.set_labels_imported.assert_not_called()

    def test_sequence_mode_with_filter(self, service):
        data = _make_data_mock()
        labels = [1, 2, 3]
        mapping = {1: "A", 2: "B", 3: "C"}
        selected = {"EventA"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            mock_loader = MockLoader.return_value
            service.apply_labels_to_single_file(data, labels, mapping, selected)

            mock_loader.create_event.assert_called_once()
            call_kwargs = mock_loader.create_event.call_args[1]
            assert call_kwargs["selected_event_ids"] == [1]

    def test_sequence_mode_with_numeric_event_alias_filter(self, service):
        data = _make_data_mock()
        data.get_event_list.return_value = (
            np.array([[0, 0, 1], [1, 0, 2], [2, 0, 1]]),
            {"Stimulus/S 768": 1, "Stimulus/S 769": 2},
        )
        labels = [1, 2]
        mapping = {1: "A", 2: "B"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            mock_loader = MockLoader.return_value
            service.apply_labels_to_single_file(data, labels, mapping, {"768"})

            call_kwargs = mock_loader.create_event.call_args[1]
            assert call_kwargs["selected_event_ids"] == [1]

    def test_sequence_mode_rejects_partially_unresolved_target_scope(self, service):
        data = _make_data_mock()
        labels = [1, 2, 3]
        mapping = {1: "A", 2: "B", 3: "C"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            with pytest.raises(ValueError, match=r"not found.*MissingEvent"):
                service.apply_labels_to_single_file(
                    data,
                    labels,
                    mapping,
                    {"EventA", "MissingEvent"},
                )

            MockLoader.assert_not_called()
            data.set_labels_imported.assert_not_called()

    def test_sequence_mode_rejects_ambiguous_target_alias(self, service):
        data = _make_data_mock()
        data.get_event_list.return_value = (
            np.array([[0, 0, 1], [1, 0, 2]]),
            {"Stimulus/S 769": 1, "769": 2},
        )

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            with pytest.raises(ValueError, match=r"ambiguous.*769"):
                service.apply_labels_to_single_file(
                    data,
                    [1, 2],
                    {1: "A", 2: "B"},
                    {"769"},
                )

            MockLoader.assert_not_called()
            data.set_labels_imported.assert_not_called()

    def test_timestamp_mode(self, service):
        data = _make_data_mock()
        labels = [
            {"onset": 1.0, "label": "A", "duration": 0.5},
            {"onset": 2.0, "label": "B", "duration": 0.5},
        ]
        mapping = {1: "A", 2: "B"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            mock_loader = MockLoader.return_value
            service.apply_labels_to_single_file(data, labels, mapping)

            # Timestamp mode: create_event called without selected_event_ids
            mock_loader.create_event.assert_called_once_with(mapping)
            mock_loader.apply.assert_called_once()

    def test_sequence_mode_not_raw(self, service):
        data = _make_data_mock(is_raw=False)
        labels = [1, 2]
        mapping = {1: "A", 2: "B"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            mock_loader = MockLoader.return_value
            service.apply_labels_to_single_file(data, labels, mapping, {"EventA"})

            # Not raw -> selected_ids stays None
            mock_loader.create_event.assert_called_once_with(
                mapping, selected_event_ids=None
            )


# ---------------------------------------------------------------------------
# apply_labels_batch_checked
# ---------------------------------------------------------------------------


class TestApplyLabelsBatchChecked:
    def test_timestamp_batch_rolls_back_all_files_when_late_row_fails(
        self,
        service,
    ):
        info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
        first = Raw(
            "/data/first.fif",
            mne.io.RawArray(np.zeros((1, 300)), info, verbose=False),
        )
        second = Raw(
            "/data/second.fif",
            mne.io.RawArray(np.zeros((1, 300)), info, verbose=False),
        )
        for raw in (first, second):
            raw.get_mne().set_annotations(
                mne.Annotations([0.25], [0.1], ["acquisition"])
            )
            raw.set_event(np.array([[25, 0, 9]]), {"original": 9})

        with pytest.raises(AtomicLabelApplyError) as raised:
            service.apply_labels_batch_checked(
                [first, second],
                {
                    "first.csv": [{"onset": 1.0, "duration": 0.0, "label": "left"}],
                    "second.csv": [
                        {"onset": 1.0, "duration": 0.0, "label": "left"},
                        {"onset": 3.0, "duration": 0.0, "label": "left"},
                    ],
                },
                {
                    first.get_filepath(): "first.csv",
                    second.get_filepath(): "second.csv",
                },
                {"left": "Left hand"},
            )

        assert raised.value.phase == "preparation"
        assert isinstance(raised.value.cause, ValueError)
        for raw in (first, second):
            assert raw.is_labels_imported() is False
            assert raw.get_mne().annotations.description.tolist() == ["acquisition"]
            events, event_id = raw.get_event_list()
            np.testing.assert_array_equal(events, np.array([[25, 0, 9]]))
            assert event_id == {"original": 9}

    def test_batch_rejects_mixed_timestamp_and_sequence_without_mutation(
        self,
        service,
    ):
        info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
        first = Raw(
            "/data/first.fif",
            mne.io.RawArray(np.zeros((1, 300)), info, verbose=False),
        )
        second = Raw(
            "/data/second.fif",
            mne.io.RawArray(np.zeros((1, 300)), info, verbose=False),
        )
        for raw in (first, second):
            raw.get_mne().set_annotations(
                mne.Annotations([0.25], [0.1], ["acquisition"])
            )
            raw.set_event(np.array([[25, 0, 9]]), {"original": 9})

        with pytest.raises(AtomicLabelApplyError) as raised:
            service.apply_labels_batch_checked(
                [first, second],
                {
                    "first.csv": [{"onset": 1.0, "duration": 0.0, "label": "left"}],
                    "second.mat": [1],
                },
                {
                    first.get_filepath(): "first.csv",
                    second.get_filepath(): "second.mat",
                },
                {"left": "Left", 1: "Right"},
            )

        assert raised.value.phase == "preparation"
        assert isinstance(raised.value.cause, ValueError)
        for raw in (first, second):
            assert raw.is_labels_imported() is False
            assert raw.get_mne().annotations.description.tolist() == ["acquisition"]
            events, event_id = raw.get_event_list()
            np.testing.assert_array_equal(events, np.array([[25, 0, 9]]))
            assert event_id == {"original": 9}

    def test_batch_success(self, service):
        data1 = _make_data_mock("/data/sub01.set")
        data2 = _make_data_mock("/data/sub02.set")

        label_map = {
            "label1.txt": [1, 2, 3],
            "label2.txt": [4, 5, 6],
        }
        file_mapping = {
            "/data/sub01.set": "label1.txt",
            "/data/sub02.set": "label2.txt",
        }
        mapping = {1: "A", 2: "B"}

        with patch.object(service, "apply_labels_to_single_file") as mock_apply:
            result = service.apply_labels_batch_checked(
                [data1, data2], label_map, file_mapping, mapping
            )
            assert result == 2
            assert mock_apply.call_count == 2

    def test_batch_accepts_numpy_sequence_labels(self, service):
        data = _make_data_mock("/data/sub01.gdf")

        with patch.object(service, "apply_labels_to_single_file") as mock_apply:
            result = service.apply_labels_batch_checked(
                [data],
                {"labels.mat": np.asarray([1, 2, 1])},
                {"/data/sub01.gdf": "labels.mat"},
                {1: "Left", 2: "Right"},
            )

        assert result == 1
        mock_apply.assert_called_once()

    def test_batch_partial_match_fails_without_applying_any_target(self, service):
        data1 = _make_data_mock("/data/sub01.set")
        data2 = _make_data_mock("/data/sub02.set")

        label_map = {"label1.txt": [1, 2]}
        file_mapping = {"/data/sub01.set": "label1.txt"}
        mapping = {1: "A"}

        with patch.object(service, "apply_labels_to_single_file") as mock_apply:
            with pytest.raises(AtomicLabelApplyError) as raised:
                service.apply_labels_batch_checked(
                    [data1, data2], label_map, file_mapping, mapping
                )
            mock_apply.assert_not_called()

        assert raised.value.phase == "preparation"
        assert isinstance(raised.value.cause, ValueError)

    def test_batch_late_preparation_error_rolls_back_the_whole_batch(self, service):
        data1 = _make_data_mock("/data/sub01.set")
        data2 = _make_data_mock("/data/sub02.set")

        label_map = {"l1.txt": [1], "l2.txt": [2]}
        file_mapping = {"/data/sub01.set": "l1.txt", "/data/sub02.set": "l2.txt"}
        mapping = {1: "A", 2: "B"}

        with patch.object(
            service,
            "apply_labels_to_single_file",
            side_effect=[None, RuntimeError("fail")],
        ) as mock_apply:
            with pytest.raises(AtomicLabelApplyError) as raised:
                service.apply_labels_batch_checked(
                    [data1, data2], label_map, file_mapping, mapping
                )
            assert mock_apply.call_count == 2

        assert raised.value.phase == "preparation"
        assert isinstance(raised.value.cause, RuntimeError)
        assert str(raised.value.cause) == "fail"

    def test_batch_commit_failure_restores_every_target(self, service):
        info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
        targets = [
            Raw(
                f"/data/target-{index}.fif",
                mne.io.RawArray(np.zeros((1, 200)), info, verbose=False),
            )
            for index in range(2)
        ]
        for target in targets:
            target.set_event(np.array([[25, 0, 1]]), {"original": 1})

        def prepare(staged, *_args):
            staged.set_event(np.array([[75, 0, 9]]), {"changed": 9})
            staged.set_labels_imported(True)

        original_replace = service._replace_raw_label_state
        commit_calls = 0

        def fail_second_commit(target, source):
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls == 2:
                raise RuntimeError("second commit failed")
            original_replace(target, source)

        with (
            patch.object(service, "apply_labels_to_single_file", side_effect=prepare),
            patch.object(
                service,
                "_replace_raw_label_state",
                side_effect=fail_second_commit,
            ),
            pytest.raises(AtomicLabelApplyError) as raised,
        ):
            service.apply_labels_batch_checked(
                targets,
                {"first.mat": [1], "second.mat": [2]},
                {
                    targets[0].get_filepath(): "first.mat",
                    targets[1].get_filepath(): "second.mat",
                },
                {1: "left", 2: "right"},
            )

        assert raised.value.phase == "commit"
        assert isinstance(raised.value.cause, RuntimeError)
        assert str(raised.value.cause) == "second commit failed"
        assert commit_calls == 4
        for target in targets:
            assert target.is_labels_imported() is False
            events, event_id = target.get_event_list()
            np.testing.assert_array_equal(events, np.array([[25, 0, 1]]))
            assert event_id == {"original": 1}

    def test_batch_no_match(self, service):
        data1 = _make_data_mock("/data/sub01.set")
        with pytest.raises(AtomicLabelApplyError) as raised:
            service.apply_labels_batch_checked([data1], {}, {}, {})

        assert raised.value.phase == "preparation"
        assert isinstance(raised.value.cause, ValueError)

    def test_batch_label_file_not_in_map(self, service):
        data1 = _make_data_mock("/data/sub01.set")
        file_mapping = {"/data/sub01.set": "missing.txt"}
        with pytest.raises(AtomicLabelApplyError) as raised:
            service.apply_labels_batch_checked([data1], {}, file_mapping, {})

        assert raised.value.phase == "preparation"
        assert isinstance(raised.value.cause, ValueError)
