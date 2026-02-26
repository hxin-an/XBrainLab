"""Coverage tests for DatasetController uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.controller.dataset_controller import DatasetController


def _make_ctrl():
    study = MagicMock()
    study.loaded_data_list = []
    return DatasetController(study), study


class TestImportFiles:
    def test_import_raises_on_inconsistent_dataset(self):
        ctrl, study = _make_ctrl()
        study.loaded_data_list = [MagicMock()]
        with (
            patch(
                "XBrainLab.backend.controller.dataset_controller.RawDataLoader",
                side_effect=ValueError("bad"),
            ),
            pytest.raises(ValueError, match="inconsistent"),
        ):
            ctrl.import_files(["a.edf"])


class TestRemoveFiles:
    def test_remove_noop_no_data(self):
        ctrl, study = _make_ctrl()
        study.loaded_data_list = None
        ctrl.remove_files([0])
        study.set_loaded_data_list.assert_not_called()


class TestApplySmartParse:
    def test_smart_parse_updates_metadata(self):
        ctrl, study = _make_ctrl()
        d1 = MagicMock()
        d1.get_filepath.return_value = "/a.edf"
        study.loaded_data_list = [d1]
        count = ctrl.apply_smart_parse({"/a.edf": ("S01", "001")})
        assert count == 1
        d1.set_subject_name.assert_called_once_with("S01")
        d1.set_session_name.assert_called_once_with("001")

    def test_smart_parse_skips_dash(self):
        ctrl, study = _make_ctrl()
        d1 = MagicMock()
        d1.get_filepath.return_value = "/a.edf"
        study.loaded_data_list = [d1]
        ctrl.apply_smart_parse({"/a.edf": ("-", "-")})
        d1.set_subject_name.assert_not_called()
        d1.set_session_name.assert_not_called()


class TestApplyChannelSelection:
    def test_channel_selection_success(self):
        ctrl, study = _make_ctrl()
        study.loaded_data_list = [MagicMock()]
        with patch(
            "XBrainLab.backend.controller.dataset_controller.preprocessor"
        ) as mock_pp:
            process = MagicMock()
            process.data_preprocess.return_value = ["result"]
            mock_pp.ChannelSelection.return_value = process
            result = ctrl.apply_channel_selection(["Cz", "Fz"])
        assert result is True
        study.backup_loaded_data.assert_called_once()
        study.lock_dataset.assert_called_once()

    def test_channel_selection_failure_raises(self):
        ctrl, study = _make_ctrl()
        study.loaded_data_list = [MagicMock()]
        with patch(
            "XBrainLab.backend.controller.dataset_controller.preprocessor"
        ) as mock_pp:
            process = MagicMock()
            process.data_preprocess.side_effect = RuntimeError("fail")
            mock_pp.ChannelSelection.return_value = process
            with pytest.raises(RuntimeError):
                ctrl.apply_channel_selection(["Cz"])


class TestGetFilenames:
    def test_returns_filepaths(self):
        ctrl, study = _make_ctrl()
        d1 = MagicMock()
        d1.get_filepath.return_value = "/a.edf"
        study.loaded_data_list = [d1]
        assert ctrl.get_filenames() == ["/a.edf"]


class TestResetPreprocess:
    def test_notifies(self):
        ctrl, study = _make_ctrl()
        events = []
        ctrl.subscribe("data_changed", lambda: events.append("dc"))
        ctrl.subscribe("dataset_locked", lambda v: events.append(("dl", v)))
        ctrl.reset_preprocess()
        study.reset_preprocess.assert_called_once()
        assert "dc" in events


class TestLabelWrappers:
    def test_get_data_at_assignments(self):
        ctrl, study = _make_ctrl()
        study.loaded_data_list = ["a", "b", "c"]
        assert ctrl.get_data_at_assignments([0, 2]) == ["a", "c"]
        assert ctrl.get_data_at_assignments([5]) == []

    def test_apply_labels_batch(self):
        ctrl, _study = _make_ctrl()
        ctrl.label_service = MagicMock()
        ctrl.label_service.apply_labels_batch.return_value = 2
        count = ctrl.apply_labels_batch([], {}, {}, {}, None)
        assert count == 2

    def test_apply_labels_legacy(self):
        ctrl, _study = _make_ctrl()
        ctrl.label_service = MagicMock()
        ctrl.label_service.apply_labels_legacy.return_value = 1
        count = ctrl.apply_labels_legacy([], [], {}, None, force_import=True)
        assert count == 1

    def test_get_epoch_count(self):
        ctrl, _study = _make_ctrl()
        ctrl.label_service = MagicMock()
        ctrl.label_service.get_epoch_count_for_file.return_value = 42
        assert ctrl.get_epoch_count(MagicMock(), ["ev1"]) == 42

    def test_get_smart_filter_suggestions(self):
        ctrl, _study = _make_ctrl()
        with patch(
            "XBrainLab.backend.controller.dataset_controller.EventLoader"
        ) as MockEL:
            loader = MagicMock()
            loader.smart_filter.return_value = [1, 2]
            MockEL.return_value = loader
            result = ctrl.get_smart_filter_suggestions(MagicMock(), 10)
            assert result == [1, 2]
