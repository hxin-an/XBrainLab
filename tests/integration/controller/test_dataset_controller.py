"""
Integration tests for DatasetController using real GDF data.
"""

import os
import shutil

import pytest

from XBrainLab.backend.controller.dataset_controller import (
    DatasetController,
)
from XBrainLab.backend.study import Study

# Locate test data (relative to project root)
TEST_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")


@pytest.fixture
def study():
    return Study()


@pytest.fixture
def dataset_controller(study):
    return DatasetController(study)


@pytest.fixture
def gdf_path():
    if not os.path.exists(GDF_FILE):
        pytest.skip(f"Test data not found at {GDF_FILE}")
    return GDF_FILE


class TestDatasetControllerDataManagement:
    """Test data loading and management functionalities."""

    def test_import_single_file(self, dataset_controller, gdf_path):
        """Test importing one valid GDF file."""
        assert not dataset_controller.has_data()

        success_count, errors = dataset_controller.import_files([gdf_path])

        assert success_count == 1
        assert len(errors) == 0
        assert dataset_controller.has_data()

        loaded = dataset_controller.get_loaded_data_list()
        assert len(loaded) == 1
        assert loaded[0].get_filename() == os.path.basename(gdf_path)

    def test_import_invalid_file(self, dataset_controller, tmp_path):
        """Test importing a non-EEG file."""
        # Create a dummy text file
        bad_file = tmp_path / "bad.txt"
        bad_file.write_text("not an eeg file")

        success_count, errors = dataset_controller.import_files([str(bad_file)])

        assert success_count == 0
        assert len(errors) == 1
        assert not dataset_controller.has_data()

    def test_remove_files_by_index(self, dataset_controller, gdf_path, tmp_path):
        """Test removing files from the dataset."""
        # Create a copy to bypass duplicate detection
        copy_path = tmp_path / "copy.gdf"

        shutil.copy(gdf_path, copy_path)

        # Load two different files
        dataset_controller.import_files([gdf_path, str(copy_path)])
        assert len(dataset_controller.get_loaded_data_list()) == 2

        # Remove first one (index 0)
        dataset_controller.remove_files([0])

        remaining = dataset_controller.get_loaded_data_list()
        assert len(remaining) == 1
        # Removing clears preprocessing too (implied by logic)

        # Remove remaining
        dataset_controller.remove_files([0])
        assert not dataset_controller.has_data()

    def test_metadata_update(self, dataset_controller, gdf_path):
        """Test updating subject and session metadata."""
        dataset_controller.import_files([gdf_path])

        # Update metadata locally (controller doesn't expose strict getter for metadata
        # but modify the Raw object in loaded list)
        dataset_controller.update_metadata(0, subject="Sub001", session="Ses01")

        data = dataset_controller.get_loaded_data_list()[0]
        assert data.get_subject_name() == "Sub001"
        assert data.get_session_name() == "Ses01"

    def test_clean_dataset(self, dataset_controller, gdf_path):
        """Test clearing all data."""
        dataset_controller.import_files([gdf_path])
        assert dataset_controller.has_data()

        dataset_controller.clean_dataset()
        assert not dataset_controller.has_data()
        assert len(dataset_controller.get_loaded_data_list()) == 0


class TestDatasetControllerSmartParse:
    """Test smart parsing integration (mocked behavior mainly)."""

    def test_apply_smart_parse(self, dataset_controller, gdf_path):
        """Test applying a batch of metadata updates."""
        dataset_controller.import_files([gdf_path])
        filename = os.path.basename(gdf_path)

        # Map: filename -> (subject, session)
        # Use abspath to ensure it matches controller's internal storage
        abs_path = os.path.abspath(gdf_path)
        results = {abs_path: ("Sub002", "Ses02")}

        count = dataset_controller.apply_smart_parse(results)
        assert count == 1

        data = dataset_controller.get_loaded_data_list()[0]
        assert data.get_subject_name() == "Sub002"
