from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.controller.dataset_controller import DatasetController
from XBrainLab.backend.exceptions import FileCorruptedError, UnsupportedFormatError


@pytest.fixture
def mock_study():
    study = MagicMock()
    study.loaded_data_list = []
    study.is_locked.return_value = False
    return study


@pytest.fixture
def controller(mock_study):
    return DatasetController(mock_study)


def test_init(controller, mock_study):
    assert controller.study == mock_study
    assert hasattr(controller, "label_service")


def test_get_loaded_data_list(controller, mock_study):
    mock_study.loaded_data_list = ["data1", "data2"]
    assert controller.get_loaded_data_list() == ["data1", "data2"]


def test_is_locked(controller, mock_study):
    mock_study.is_locked.return_value = True
    assert controller.is_locked() is True


def test_has_data(controller, mock_study):
    mock_study.loaded_data_list = []
    assert controller.has_data() is False
    mock_study.loaded_data_list = ["data"]
    assert controller.has_data() is True


def test_import_files_success(controller, mock_study):
    # Mock Factory
    with patch(
        "XBrainLab.backend.controller.dataset_controller.RawDataLoaderFactory"
    ) as MockFactory:
        mock_raw = MagicMock()
        mock_raw.get_filepath.return_value = "test.edf"
        MockFactory.load.return_value = mock_raw

        # Mock RawDataLoader (the list wrapper)
        # Note: In the controller code: loader = RawDataLoader(existing_data)
        # We need to verify that loader.append is called and loader.apply is called.
        with patch(
            "XBrainLab.backend.controller.dataset_controller.RawDataLoader"
        ) as MockLoader:
            loader_instance = MockLoader.return_value
            loader_instance.__iter__.return_value = iter([])  # No duplicates initially

            count, errors = controller.import_files(["test.edf"])

            assert count == 1
            assert len(errors) == 0
            MockFactory.load.assert_called_with("test.edf")
            loader_instance.append.assert_called_with(mock_raw)
            loader_instance.apply.assert_called_with(mock_study, force_update=True)


def test_import_files_duplicate(controller, mock_study):
    # Mock existing data
    mock_existing = MagicMock()
    mock_existing.get_filepath.return_value = "test.edf"
    mock_study.loaded_data_list = [mock_existing]

    with patch(
        "XBrainLab.backend.controller.dataset_controller.RawDataLoader"
    ) as MockLoader:
        loader_instance = MockLoader.return_value
        # The controller iterates over the loader to check duplicates.
        # Since we passed existing_data to constructor, the loader typically holds it.
        # But we mocked the class return value. We need to simulate the
        # loader containing the file.
        # The controller does: if any(d.get_filepath() == path for d in loader):
        mock_item = MagicMock()
        mock_item.get_filepath.return_value = "test.edf"
        loader_instance.__iter__.return_value = iter([mock_item])

        count, errors = controller.import_files(["test.edf"])

        assert count == 0
        assert len(errors) == 0  # Skipped, not error


def test_import_files_errors(controller, mock_study):
    with patch(
        "XBrainLab.backend.controller.dataset_controller.RawDataLoaderFactory"
    ) as MockFactory:
        # 1. UnsupportedFormatError
        MockFactory.load.side_effect = UnsupportedFormatError("Bad format")
        with patch("XBrainLab.backend.controller.dataset_controller.RawDataLoader"):
            count, errors = controller.import_files(["bad.xyz"])
            assert count == 0
            assert "Unsupported format" in errors[0]

        # 2. FileCorruptedError
        MockFactory.load.side_effect = FileCorruptedError("Corrupt")
        with patch("XBrainLab.backend.controller.dataset_controller.RawDataLoader"):
            count, errors = controller.import_files(["corrupt.edf"])
            assert count == 0
            assert "File corrupted" in errors[0]

        # 3. Generic Exception
        MockFactory.load.side_effect = Exception("Unknown")
        with patch("XBrainLab.backend.controller.dataset_controller.RawDataLoader"):
            count, errors = controller.import_files(["error.edf"])
            assert count == 0
            assert "Unknown" in errors[0]

        # 4. None Return
        MockFactory.load.side_effect = None
        MockFactory.load.return_value = None
        with patch("XBrainLab.backend.controller.dataset_controller.RawDataLoader"):
            count, errors = controller.import_files(["none.edf"])
            assert count == 0
            assert "Loader returned None" in errors[0]


def test_clean_dataset(controller, mock_study):
    controller.clean_dataset()
    mock_study.clean_raw_data.assert_called_with(force_update=True)


def test_remove_files(controller, mock_study):
    d1, d2, d3 = MagicMock(), MagicMock(), MagicMock()
    mock_study.loaded_data_list = [d1, d2, d3]

    controller.remove_files([0, 2])

    # Should call set_loaded_data_list with [d2] directly
    mock_study.set_loaded_data_list.assert_called_with([d2], force_update=True)


def test_update_metadata(controller, mock_study):
    d1 = MagicMock()
    mock_study.loaded_data_list = [d1]

    controller.update_metadata(0, subject="Sub1", session="Ses1")

    d1.set_subject_name.assert_called_with("Sub1")
    d1.set_session_name.assert_called_with("Ses1")
    mock_study.reset_preprocess.assert_called_with(force_update=True)


def test_update_metadata_invalid_index(controller, mock_study):
    mock_study.loaded_data_list = []
    # Should not crash
    controller.update_metadata(0, subject="Sub1")
    mock_study.reset_preprocess.assert_not_called()


def test_apply_smart_parse(controller, mock_study):
    d1 = MagicMock()
    d1.get_filepath.return_value = "/path/sub-01.edf"
    d2 = MagicMock()
    d2.get_filepath.return_value = "/path/sub-02.edf"

    mock_study.loaded_data_list = [d1, d2]

    results = {
        "/path/sub-01.edf": ("01", "01"),
        "/path/sub-02.edf": ("02", "-"),  # Session unchanged
    }

    count = controller.apply_smart_parse(results)

    assert count == 2
    d1.set_subject_name.assert_called_with("01")
    d1.set_session_name.assert_called_with("01")
    d2.set_subject_name.assert_called_with("02")
    d2.set_session_name.assert_not_called()

    mock_study.reset_preprocess.assert_called_with(force_update=True)


def test_apply_channel_selection(controller, mock_study):
    with patch(
        "XBrainLab.backend.controller.dataset_controller.preprocessor.ChannelSelection"
    ) as MockCS:
        instance = MockCS.return_value
        instance.data_preprocess.return_value = True

        result = controller.apply_channel_selection(["C3", "C4"])

        assert result is True
        instance.data_preprocess.assert_called_with(["C3", "C4"])


def test_reset_preprocess(controller, mock_study):
    # Setup observer mock
    mock_callback = MagicMock()
    controller.subscribe("data_changed", mock_callback)
    controller.subscribe("dataset_locked", mock_callback)

    controller.reset_preprocess()

    mock_study.reset_preprocess.assert_called_with(force_update=True)
    # Verify events
    # Check if mock_callback was called for both events
    assert mock_callback.call_count >= 2


def test_get_event_info(controller, mock_study):
    # Create mock data with MNE object
    d1 = MagicMock()
    mne1 = MagicMock()
    # Annotations needs to be an object with .description attribute
    # In MNE, raw.annotations is an object that behaves like a list but has properties
    mock_ann1 = MagicMock()
    mock_ann1.__len__.return_value = 3
    mock_ann1.description = ["A", "B", "A"]
    mne1.annotations = mock_ann1
    d1.get_mne.return_value = mne1

    d2 = MagicMock()
    mne2 = MagicMock()
    mock_ann2 = MagicMock()
    mock_ann2.__len__.return_value = 1
    mock_ann2.description = ["C"]
    mne2.annotations = mock_ann2
    d2.get_mne.return_value = mne2

    mock_study.loaded_data_list = [d1, d2]

    info = controller.get_event_info()

    assert info["total"] == 4  # 3 + 1
    assert info["unique_count"] == 3  # A, B, C
    assert "A" in info["unique_labels"]
    assert "B" in info["unique_labels"]
    assert "C" in info["unique_labels"]


def test_run_import_labels(controller, mock_study):
    controller.label_service = MagicMock()
    controller.label_service.apply_labels_batch.return_value = 5  # 5 files updated

    # Mock observer
    mock_callback = MagicMock()
    controller.subscribe("data_changed", mock_callback)

    count = controller.run_import_labels(["files"], "map", "file_map", "mapping")

    assert count == 5
    controller.label_service.apply_labels_batch.assert_called()
    mock_callback.assert_called_once()  # data_changed

    # Test count 0 (no event)
    controller.label_service.apply_labels_batch.return_value = 0
    mock_callback.reset_mock()
    count = controller.run_import_labels(["files"], "map", "file_map", "mapping")
    assert count == 0
    mock_callback.assert_not_called()


def test_get_filename(controller, mock_study):
    d1 = MagicMock()
    d1.get_filepath.return_value = "f1.edf"
    d2 = MagicMock()
    d2.get_filepath.return_value = "f2.edf"
    mock_study.loaded_data_list = [d1, d2]

    assert controller.get_filenames() == ["f1.edf", "f2.edf"]
