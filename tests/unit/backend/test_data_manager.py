"""Unit tests for DataManager — data lifecycle management."""

from unittest.mock import MagicMock

import mne
import numpy as np
import pytest

from XBrainLab.backend.data_manager import DataManager
from XBrainLab.backend.load_data import Raw, RawDataLoader
from XBrainLab.backend.preprocessor import PreprocessBase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def dm():
    return DataManager()


@pytest.fixture
def raw_data():
    """A single-element list of Raw wrapping a RawArray."""
    info = mne.create_info(["Cz"], sfreq=256, ch_types="eeg")
    mne_raw = mne.io.RawArray(np.random.randn(1, 256), info)
    return [Raw("test.gdf", mne_raw)]


@pytest.fixture
def epoch_data():
    """A single-element list of Raw wrapping an EpochsArray."""
    info = mne.create_info(["Cz"], sfreq=256, ch_types="eeg")
    data = np.random.randn(3, 1, 256)
    mne_epochs = mne.EpochsArray(data, info)
    return [Raw("test.gdf", mne_epochs)]


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------
class TestInit:
    def test_default_state(self, dm):
        assert dm.loaded_data_list == []
        assert dm.preprocessed_data_list == []
        assert dm.epoch_data is None
        assert dm.datasets == []
        assert dm.dataset_generator is None
        assert dm.dataset_locked is False
        assert dm.backup_loaded_data_list is None

    def test_get_raw_data_loader(self, dm):
        loader = dm.get_raw_data_loader()
        assert isinstance(loader, RawDataLoader)


# ---------------------------------------------------------------------------
# Loading data
# ---------------------------------------------------------------------------
class TestSetLoadedDataList:
    def test_basic_load(self, dm, raw_data):
        dm.set_loaded_data_list(raw_data, force_update=True)
        assert len(dm.loaded_data_list) == 1
        assert len(dm.preprocessed_data_list) == 1

    def test_epoch_data_none_for_raw(self, dm, raw_data):
        dm.set_loaded_data_list(raw_data, force_update=True)
        assert dm.epoch_data is None

    def test_epoch_data_set_for_epochs(self, dm, epoch_data):
        dm.set_loaded_data_list(epoch_data, force_update=True)
        assert dm.epoch_data is not None

    def test_force_update_false_raises_on_existing(self, dm, raw_data):
        dm.set_loaded_data_list(raw_data, force_update=True)
        with pytest.raises(ValueError):
            dm.set_loaded_data_list(raw_data, force_update=False)

    def test_type_validation(self, dm):
        with pytest.raises(TypeError):
            dm.set_loaded_data_list(["not_a_raw"], force_update=True)


# ---------------------------------------------------------------------------
# Backup / restore
# ---------------------------------------------------------------------------
class TestBackup:
    def test_backup_and_reset(self, dm, raw_data):
        dm.set_loaded_data_list(raw_data, force_update=True)
        dm.backup_loaded_data()
        assert dm.backup_loaded_data_list is not None

        dm.reset_preprocess(force_update=True)
        assert dm.backup_loaded_data_list is None
        assert len(dm.loaded_data_list) == 1

    def test_backup_empty_is_none(self, dm):
        dm.backup_loaded_data()
        assert dm.backup_loaded_data_list is None


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------
class TestPreprocess:
    def test_set_preprocessed_data_list(self, dm, raw_data):
        dm.set_preprocessed_data_list(raw_data, force_update=True)
        assert len(dm.preprocessed_data_list) == 1

    def test_preprocess_applies(self, dm, raw_data):
        class RenamePreprocessor(PreprocessBase):
            def get_preprocess_desc(self):
                return "rename"

            def _data_preprocess(self, preprocessed_data):
                preprocessed_data.set_subject_name("modified")

        dm.set_loaded_data_list(raw_data, force_update=True)
        dm.preprocess(RenamePreprocessor)
        assert dm.preprocessed_data_list[0].get_subject_name() == "modified"

    def test_preprocess_validates_subclass(self, dm, raw_data):
        dm.set_loaded_data_list(raw_data, force_update=True)
        with pytest.raises(TypeError):
            dm.preprocess(int)

    def test_reset_preprocess(self, dm, raw_data):
        dm.set_loaded_data_list(raw_data, force_update=True)
        original_filepath = dm.preprocessed_data_list[0].get_filepath()
        dm.reset_preprocess(force_update=True)
        assert dm.preprocessed_data_list[0].get_filepath() == original_filepath


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------
class TestDatasets:
    def test_set_datasets(self, dm):
        dm.set_datasets([], force_update=True)
        assert dm.datasets == []

    def test_has_datasets(self, dm):
        assert dm.has_datasets() is False
        dm.datasets = [MagicMock()]
        assert dm.has_datasets() is True

    def test_has_raw_data(self, dm, raw_data):
        assert dm.has_raw_data() is False
        dm.set_loaded_data_list(raw_data, force_update=True)
        assert dm.has_raw_data() is True


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
class TestCleaning:
    def test_clean_raw_data(self, dm, raw_data):
        dm.set_loaded_data_list(raw_data, force_update=True)
        dm.clean_raw_data(force_update=True)
        assert dm.loaded_data_list == []
        assert dm.preprocessed_data_list == []
        assert dm.epoch_data is None

    def test_clean_datasets(self, dm):
        dm.datasets = [MagicMock()]
        dm.clean_datasets(force_update=True)
        assert dm.datasets == []

    def test_guard_clean_raw_data(self, dm, raw_data):
        dm.set_loaded_data_list(raw_data, force_update=True)
        with pytest.raises(ValueError):
            dm._guard_clean_raw_data()

    def test_guard_clean_datasets(self, dm):
        dm.datasets = [MagicMock()]
        with pytest.raises(ValueError):
            dm._guard_clean_datasets()


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------
class TestLocking:
    def test_lock_unlock(self, dm):
        assert dm.is_locked() is False
        dm.lock_dataset()
        assert dm.is_locked() is True
        dm.unlock_dataset()
        assert dm.is_locked() is False
