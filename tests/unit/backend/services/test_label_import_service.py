"""Tests for LabelImportService covering all public methods.

Targets: apply_labels_batch, apply_labels_legacy, apply_labels_to_single_file,
_force_apply_single, get_epoch_count_for_file.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

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
    def test_sequence_mode_no_filter(self, service):
        data = _make_data_mock()
        labels = [1, 2, 3]
        mapping = {1: "A", 2: "B", 3: "C"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            mock_loader = MockLoader.return_value
            service.apply_labels_to_single_file(data, labels, mapping)

            MockLoader.assert_called_once_with(data)
            mock_loader.create_event.assert_called_once_with(
                mapping, selected_event_ids=None
            )
            mock_loader.apply.assert_called_once()
            data.set_labels_imported.assert_called_once_with(True)

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
# apply_labels_batch
# ---------------------------------------------------------------------------


class TestApplyLabelsBatch:
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
            result = service.apply_labels_batch(
                [data1, data2], label_map, file_mapping, mapping
            )
            assert result == 2
            assert mock_apply.call_count == 2

    def test_batch_partial_match(self, service):
        data1 = _make_data_mock("/data/sub01.set")
        data2 = _make_data_mock("/data/sub02.set")

        label_map = {"label1.txt": [1, 2]}
        file_mapping = {"/data/sub01.set": "label1.txt"}
        mapping = {1: "A"}

        with patch.object(service, "apply_labels_to_single_file") as mock_apply:
            result = service.apply_labels_batch(
                [data1, data2], label_map, file_mapping, mapping
            )
            assert result == 1

    def test_batch_error_continues(self, service):
        data1 = _make_data_mock("/data/sub01.set")
        data2 = _make_data_mock("/data/sub02.set")

        label_map = {"l1.txt": [1], "l2.txt": [2]}
        file_mapping = {"/data/sub01.set": "l1.txt", "/data/sub02.set": "l2.txt"}
        mapping = {1: "A", 2: "B"}

        with patch.object(
            service,
            "apply_labels_to_single_file",
            side_effect=[RuntimeError("fail"), None],
        ) as mock_apply:
            result = service.apply_labels_batch(
                [data1, data2], label_map, file_mapping, mapping
            )
            # First fails, second succeeds
            assert result == 1
            assert mock_apply.call_count == 2

    def test_batch_no_match(self, service):
        data1 = _make_data_mock("/data/sub01.set")
        result = service.apply_labels_batch([data1], {}, {}, {})
        assert result == 0

    def test_batch_label_file_not_in_map(self, service):
        data1 = _make_data_mock("/data/sub01.set")
        file_mapping = {"/data/sub01.set": "missing.txt"}
        result = service.apply_labels_batch([data1], {}, file_mapping, {})
        assert result == 0


# ---------------------------------------------------------------------------
# apply_labels_legacy
# ---------------------------------------------------------------------------


class TestApplyLabelsLegacy:
    def test_exact_match(self, service):
        d1 = _make_data_mock("/data/sub01.set")
        d2 = _make_data_mock("/data/sub02.set")
        labels = list(range(6))  # 6 labels total
        mapping = {i: str(i) for i in range(6)}

        # Patch epoch counts: 3 for each file = 6 total
        with (
            patch.object(service, "get_epoch_count_for_file", return_value=3),
            patch.object(service, "apply_labels_to_single_file") as mock_apply,
        ):
            result = service.apply_labels_legacy([d1, d2], labels, mapping)
            assert result == 2
            assert mock_apply.call_count == 2
            # Check first call got labels [0,1,2], second got [3,4,5]
            assert mock_apply.call_args_list[0][0][1] == [0, 1, 2]
            assert mock_apply.call_args_list[1][0][1] == [3, 4, 5]

    def test_mismatch_no_force(self, service):
        d1 = _make_data_mock("/data/sub01.set")
        labels = [1, 2, 3]
        mapping = {1: "A"}

        with patch.object(service, "get_epoch_count_for_file", return_value=10):
            result = service.apply_labels_legacy([d1], labels, mapping)
            assert result == 0

    def test_force_import(self, service):
        d1 = _make_data_mock("/data/sub01.set")
        labels = list(range(5))
        mapping = {i: str(i) for i in range(5)}

        with (
            patch.object(service, "get_epoch_count_for_file", side_effect=[10, 5]),
            patch.object(service, "_force_apply_single") as mock_force,
        ):
            result = service.apply_labels_legacy(
                [d1], labels, mapping, force_import=True
            )
            assert result == 1
            mock_force.assert_called_once()

    def test_force_import_fallback_epochs(self, service):
        d1 = _make_data_mock("/data/sub01.set")
        labels = list(range(200))
        mapping = {i: str(i) for i in range(200)}

        # get_epoch_count_for_file returns 0 for force mode (None filter)
        # so it uses fallback of 100
        with (
            patch.object(service, "get_epoch_count_for_file", side_effect=[0, 0]),
            patch.object(service, "_force_apply_single") as mock_force,
        ):
            result = service.apply_labels_legacy(
                [d1], labels, mapping, force_import=True
            )
            assert result == 1
            # Should use first 100 labels (fallback)
            call_labels = mock_force.call_args[0][1]
            assert len(call_labels) == 100

    def test_force_import_not_enough_labels(self, service):
        d1 = _make_data_mock("/data/sub01.set")
        labels = [1, 2]  # only 2 labels
        mapping = {1: "A", 2: "B"}

        with (
            patch.object(service, "get_epoch_count_for_file", side_effect=[0, 0]),
            patch.object(service, "_force_apply_single") as mock_force,
        ):
            # With fallback=100, current_idx + 100 > 2, so skip
            result = service.apply_labels_legacy(
                [d1], labels, mapping, force_import=True
            )
            assert result == 0
            mock_force.assert_not_called()

    def test_zero_epochs_zero_labels(self, service):
        d1 = _make_data_mock("/data/sub01.set")
        labels = []
        mapping = {}

        with patch.object(service, "get_epoch_count_for_file", return_value=0):
            result = service.apply_labels_legacy([d1], labels, mapping)
            # label_count == total_epochs == 0, but total_epochs > 0 check fails
            assert result == 0

    def test_skip_zero_epoch_files(self, service):
        d1 = _make_data_mock("/data/sub01.set")
        d2 = _make_data_mock("/data/sub02.set")
        labels = [1, 2, 3]
        mapping = {1: "A", 2: "B", 3: "C"}

        # d1 has 0 epochs, d2 has 3 epochs -> total 3 == len(labels)
        with (
            patch.object(service, "get_epoch_count_for_file", side_effect=[0, 3, 0, 3]),
            patch.object(service, "apply_labels_to_single_file") as mock_apply,
        ):
            result = service.apply_labels_legacy([d1, d2], labels, mapping)
            assert result == 2  # Both files processed
            # Only d2 actually calls apply (n > 0)
            assert mock_apply.call_count == 1


# ---------------------------------------------------------------------------
# _force_apply_single
# ---------------------------------------------------------------------------


class TestForceApplySingle:
    def test_basic(self, service):
        data = _make_data_mock()
        labels = [1, 2, 3]
        mapping = {1: "A", 2: "B", 3: "C"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            mock_loader = MockLoader.return_value
            service._force_apply_single(data, labels, mapping)

            mock_loader.create_event.assert_called_once()
            mock_loader.apply.assert_called_once()
            data.set_labels_imported.assert_called_once_with(True)

    def test_with_filter(self, service):
        data = _make_data_mock()
        labels = [1, 2]
        mapping = {1: "A", 2: "B"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            mock_loader = MockLoader.return_value
            service._force_apply_single(data, labels, mapping, {"EventA"})

            call_kwargs = mock_loader.create_event.call_args[1]
            assert call_kwargs["selected_event_ids"] == [1]

    def test_not_raw(self, service):
        data = _make_data_mock(is_raw=False)
        labels = [1, 2]
        mapping = {1: "A", 2: "B"}

        with patch(
            "XBrainLab.backend.services.label_import_service.EventLoader"
        ) as MockLoader:
            mock_loader = MockLoader.return_value
            service._force_apply_single(data, labels, mapping, {"EventA"})

            # Not raw -> selected_ids remains None
            call_kwargs = mock_loader.create_event.call_args[1]
            assert call_kwargs["selected_event_ids"] is None
