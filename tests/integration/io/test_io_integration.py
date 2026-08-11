import os
from threading import Event
from typing import Any

import pytest
from mne.io.constants import FIFF

from XBrainLab.backend.application import (
    ApplicationService,
    LoadDataCommand,
    QueryStateCommand,
)
from XBrainLab.backend.application.data_interpretation_bids_channels import (
    apply_bids_channel_review,
    review_bids_channel_sidecars,
)
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.load_data.raw_data_loader import (
    load_edf_file,
    load_gdf_file,
    load_raw_data,
)

# Path to the small real-data fixtures stored under tests/fixtures/data
TEST_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "data"),
)
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")
MULTIFORMAT_DIR = os.path.join(TEST_DATA_DIR, "multiformat")
PUBLIC_DATA_DIR = os.path.join(TEST_DATA_DIR, "public")
REAL_DATA_FIXTURES = [
    GDF_FILE,
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real_raw.fif"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real_raw.fif.gz"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real.edf"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real.bdf"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real.vhdr"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real.set"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real-epo.fif"),
]
PUBLIC_REAL_DATA_FIXTURES = [
    os.path.join(PUBLIC_DATA_DIR, "physionet-eegmmidb-S008R01.edf"),
    os.path.join(PUBLIC_DATA_DIR, "bbci-competition-iii-O3VR.gdf"),
    os.path.join(PUBLIC_DATA_DIR, "sccn-eeglab_data.set"),
    os.path.join(PUBLIC_DATA_DIR, "scan41_short.cnt"),
    os.path.join(PUBLIC_DATA_DIR, "test_NO.vhdr"),
]
OPENNEURO_P300_EEG = os.path.join(
    PUBLIC_DATA_DIR,
    "openneuro-ds003061-p300",
    "sub-001",
    "eeg",
    "sub-001_task-P300_run-1_eeg.set",
)
OPENNEURO_P300_CHANNELS = os.path.join(
    PUBLIC_DATA_DIR,
    "openneuro-ds003061-p300",
    "sub-001",
    "eeg",
    "sub-001_task-P300_run-1_channels.tsv",
)
SLEEP_EDFX_PSG = os.path.join(
    PUBLIC_DATA_DIR,
    "sleep-edfx-st7011",
    "ST7011J0-PSG.edf",
)
CHBMIT_EDF = os.path.join(
    PUBLIC_DATA_DIR,
    "chbmit-chb01",
    "chb01_03.edf",
)


def _assert_raw(value: object) -> Raw:
    assert isinstance(value, Raw)
    return value


def _mne_data(raw: Raw) -> Any:
    return raw.get_mne().get_data()


def _assert_real_data_shape(raw: Raw) -> Any:
    data = _mne_data(raw)
    assert data.ndim in (2, 3)
    assert data.size > 0
    if data.ndim == 2:
        assert data.shape[0] == raw.get_nchan()
        assert data.shape[1] > 0
    else:
        assert data.shape[0] > 0
        assert data.shape[1] == raw.get_nchan()
        assert data.shape[2] > 0
    return data


class TestIOIntegration:
    """
    Integration tests for data loading module.
    Verifies that we can actually load real files from disk.
    """

    def test_load_gdf_file_success(self):
        """Test loading a valid GDF file."""
        # Ensure the test file exists before trying to load
        if not os.path.exists(GDF_FILE):
            pytest.skip(f"Test data not found at {GDF_FILE}")

        raw = _assert_raw(load_gdf_file(GDF_FILE))

        # 1. Verify return type
        assert isinstance(raw, Raw)

        # 2. Verify metadata
        assert raw.get_nchan() > 0
        assert raw.get_sfreq() > 0
        assert raw.get_filepath() == GDF_FILE

        # 3. Verify data access (preload=False by default now)
        # Use get_data() instead of private _data
        data = _assert_real_data_shape(raw)

        # 4. Check shape
        n_channels = raw.get_nchan()
        # n_times might vary if not preloaded vs preloaded,
        # but get_data() returns full array
        assert data.shape[0] == n_channels
        assert data.shape[1] > 0

    def test_load_gdf_file_restores_known_graz_channel_names(self):
        """Known Graz fixtures should restore canonical labels after MNE auto-rename."""
        if not os.path.exists(GDF_FILE):
            pytest.skip(f"Test data not found at {GDF_FILE}")

        raw = _assert_raw(load_gdf_file(GDF_FILE))

        assert raw.has_runtime_signals() is False
        assert raw.get_mne().ch_names[0:7] == [
            "EEG-Fz",
            "EEG-FC3",
            "EEG-FC1",
            "EEG-FCz",
            "EEG-FC2",
            "EEG-FC4",
            "EEG-C5",
        ]
        assert raw.get_mne().ch_names[18:22] == [
            "EEG-P1",
            "EEG-Pz",
            "EEG-P2",
            "EEG-POz",
        ]
        assert raw.has_runtime_detail("gdf_duplicate_channel_names")
        assert raw.has_gdf_duplicate_channel_detail()

        detail = raw.get_gdf_duplicate_channel_detail()
        assert isinstance(detail, dict)
        assert detail["kind"] == "gdf_duplicate_channel_names"
        assert detail["filepath"] == GDF_FILE
        assert detail["resolved"] is True
        assert "EEG" in detail["generated_bases"]
        assert "EEG-0" in detail["generated_channels"]
        assert "EEG-FC3" in detail["normalized_channels"]

    @pytest.mark.parametrize("filepath", REAL_DATA_FIXTURES)
    def test_load_supported_real_formats(self, filepath):
        """Load compact real-data fixtures across several supported extensions."""
        if not os.path.exists(filepath):
            pytest.skip(f"Test data not found at {filepath}")

        raw = _assert_raw(load_raw_data(filepath))

        assert isinstance(raw, Raw)
        assert raw.get_filepath() == filepath
        assert raw.get_nchan() > 0
        assert raw.get_sfreq() > 0

        _assert_real_data_shape(raw)

    @pytest.mark.parametrize("filepath", REAL_DATA_FIXTURES)
    def test_application_service_import_supported_real_formats(self, filepath):
        """Exercise the product command import entrypoint across multiple formats."""
        if not os.path.exists(filepath):
            pytest.skip(f"Test data not found at {filepath}")

        service = ApplicationService()
        load_result = service.execute(LoadDataCommand(paths=[filepath]))

        assert load_result.ok is True
        assert load_result.diagnostics["success_count"] == 1
        assert load_result.diagnostics["errors"] == []

        summary_result = service.execute(QueryStateCommand(query="data_summary"))
        assert summary_result.ok is True
        summary = summary_result.diagnostics
        assert summary["count"] == 1
        assert summary["files"] == [os.path.basename(filepath)]

    def test_application_service_summary_excludes_resolved_gdf_channel_normalization(
        self,
    ):
        """Do not keep resolved Graz normalization in unresolved ambiguity summaries."""
        if not os.path.exists(GDF_FILE):
            pytest.skip(f"Test data not found at {GDF_FILE}")

        service = ApplicationService()
        load_result = service.execute(LoadDataCommand(paths=[GDF_FILE]))

        assert load_result.ok is True
        assert load_result.diagnostics["success_count"] == 1
        assert load_result.diagnostics["errors"] == []

        summary_result = service.execute(QueryStateCommand(query="data_summary"))
        assert summary_result.ok is True
        summary = summary_result.diagnostics
        assert summary["gdf_duplicate_channel_files"] == []
        assert summary["gdf_duplicate_channel_details"] == []

    def test_data_summary_stays_available_during_optional_montage_commit(self):
        """A background montage publication must not hide committed inventory."""
        if not os.path.exists(GDF_FILE):
            pytest.skip(f"Test data not found at {GDF_FILE}")

        service = ApplicationService()
        commit_entered = Event()
        release_commit = Event()
        original_commit = service.bids_montage_preparation._commit_publication
        assert original_commit is not None

        def block_optional_commit(work, snapshot) -> None:
            with service._command_lock:
                commit_entered.set()
                assert release_commit.wait(timeout=5.0)
            original_commit(work, snapshot)

        service.bids_montage_preparation._commit_publication = block_optional_commit
        try:
            load_result = service.execute(LoadDataCommand(paths=[GDF_FILE]))

            assert load_result.ok is True
            assert commit_entered.wait(timeout=5.0)
            committed_during_load = service.get_view_publication()

            summary_result = service.execute(QueryStateCommand(query="data_summary"))
            mutable_result = service.execute(QueryStateCommand(query="data_lists"))

            assert summary_result.ok is True
            assert summary_result.state == committed_during_load.state
            assert "application_busy" not in summary_result.diagnostics
            assert summary_result.diagnostics["count"] == 1
            assert summary_result.diagnostics["files"] == ["A01T.gdf"]
            assert mutable_result.failed is True
            assert mutable_result.error_type is ErrorType.PRECONDITION
            assert mutable_result.recoverable is True
            assert mutable_result.diagnostics["application_busy"] is True

            release_commit.set()
            assert service.bids_montage_preparation.wait_for_idle(timeout=5.0)

            final_publication = service.get_view_publication()
            assert final_publication.usable is True
            assert final_publication.revision > committed_during_load.revision
            stale_result = service.execute(
                QueryStateCommand(query="data_summary"),
                expected_publication_generation=committed_during_load.generation,
            )
            current_result = service.execute(
                QueryStateCommand(query="data_summary"),
                expected_publication_generation=final_publication.generation,
            )
            assert stale_result.failed is True
            assert stale_result.diagnostics["stale_publication"] is True
            assert current_result.ok is True
            assert current_result.diagnostics["count"] == 1
            assert current_result.diagnostics["files"] == ["A01T.gdf"]
        finally:
            release_commit.set()
            service.bids_montage_preparation.wait_for_idle(timeout=5.0)
            service.close()

    @pytest.mark.optional_public_fixture
    @pytest.mark.parametrize("filepath", PUBLIC_REAL_DATA_FIXTURES)
    def test_load_public_real_formats(self, filepath):
        """Load small public EEG fixtures from different sources and formats."""
        if not os.path.exists(filepath):
            pytest.skip(f"Public test data not found at {filepath}")

        raw = _assert_raw(load_raw_data(filepath))

        assert isinstance(raw, Raw)
        assert raw.get_filepath() == filepath
        assert raw.get_nchan() > 0
        assert raw.get_sfreq() > 0

        _assert_real_data_shape(raw)

    @pytest.mark.optional_public_fixture
    def test_openneuro_bids_channels_apply_to_real_mne_raw(self):
        """Real BIDS sidecar semantics must survive the product load/apply helpers."""
        if not os.path.exists(OPENNEURO_P300_EEG):
            pytest.skip(
                "OpenNeuro teacher fixture not downloaded; run the "
                "teacher-preflight fixture fetch first."
            )

        raw = _assert_raw(load_raw_data(OPENNEURO_P300_EEG))
        review = review_bids_channel_sidecars(
            bids={
                "is_bids": True,
                "layout": [
                    {
                        "file": OPENNEURO_P300_EEG,
                        "channels_file": OPENNEURO_P300_CHANNELS,
                    }
                ],
            },
            selected_eeg_files=[OPENNEURO_P300_EEG],
        )
        applied = apply_bids_channel_review(
            review=review,
            loaded_data=[raw],
            data_filepath=lambda item: item.get_filepath(),
        )

        mne_raw = raw.get_mne()
        types_by_name = dict(
            zip(mne_raw.ch_names, mne_raw.get_channel_types(), strict=True)
        )
        assert types_by_name["EXG1"] == "misc"
        assert types_by_name["GSR1"] == "gsr"
        assert types_by_name["Resp"] == "resp"
        assert types_by_name["Temp"] == "temperature"
        temp_index = mne_raw.ch_names.index("Temp")
        assert mne_raw.info["chs"][temp_index]["unit"] == FIFF.FIFF_UNIT_CEL
        assert applied[0]["channel_units"]["Temp"] == "n/a"
        assert "Temp" in applied[0]["unmapped_unit_channels"]

    @pytest.mark.optional_public_fixture
    def test_sleep_edf_infers_prefixed_types_without_renaming_channels(self):
        """MNE EDF prefix inference must not change the product channel identity."""
        if not os.path.exists(SLEEP_EDFX_PSG):
            pytest.skip(
                "Sleep-EDF teacher fixture not downloaded; run the "
                "teacher-preflight fixture fetch first."
            )

        raw = _assert_raw(load_edf_file(SLEEP_EDFX_PSG))

        assert raw.get_mne().ch_names == [
            "EEG Fpz-Cz",
            "EEG Pz-Oz",
            "EOG horizontal",
            "EMG submental",
            "Marker",
        ]
        assert raw.get_mne().get_channel_types() == [
            "eeg",
            "eeg",
            "eog",
            "emg",
            "eeg",
        ]
        detail = raw.get_runtime_detail("edf_channel_type_inference")
        assert detail["method"] == "mne_edf_infer_types"
        assert detail["defaulted_to_eeg_channels"] == ["Marker"]

    @pytest.mark.optional_public_fixture
    def test_chbmit_duplicate_channel_names_keep_mne_unique_identity(self):
        """EDF inference must retain MNE's duplicate-name compatibility."""
        if not os.path.exists(CHBMIT_EDF):
            pytest.skip(
                "CHB-MIT teacher fixture not downloaded; run the "
                "teacher-preflight fixture fetch first."
            )

        raw = _assert_raw(load_edf_file(CHBMIT_EDF))

        assert raw.get_mne().ch_names.count("T8-P8-0") == 1
        assert raw.get_mne().ch_names.count("T8-P8-1") == 1
        assert "T8-P8" not in raw.get_mne().ch_names
        assert len(raw.get_mne().ch_names) == len(set(raw.get_mne().ch_names))

    @pytest.mark.optional_public_fixture
    @pytest.mark.parametrize("filepath", PUBLIC_REAL_DATA_FIXTURES)
    def test_application_service_import_public_real_formats(self, filepath):
        """Exercise the command import entrypoint across downloaded public EEG fixtures."""
        if not os.path.exists(filepath):
            pytest.skip(f"Public test data not found at {filepath}")

        service = ApplicationService()
        load_result = service.execute(LoadDataCommand(paths=[filepath]))

        assert load_result.ok is True
        assert load_result.diagnostics["success_count"] == 1
        assert load_result.diagnostics["errors"] == []

        summary_result = service.execute(QueryStateCommand(query="data_summary"))
        assert summary_result.ok is True
        summary = summary_result.diagnostics
        assert summary["count"] == 1
        assert summary["files"] == [os.path.basename(filepath)]

    def test_load_non_existent_file(self):
        """Test loading a file that does not exist."""
        fake_path = os.path.join(TEST_DATA_DIR, "non_existent.gdf")
        with pytest.raises((FileCorruptedError, FileNotFoundError)):
            load_gdf_file(fake_path)

    def test_load_invalid_extension(self, tmp_path):
        """Test loading a file with wrong extension."""
        dummy_path = str(tmp_path / "dummy.txt")
        with open(dummy_path, "w") as f:
            f.write("This is not a GDF file.")

        with pytest.raises((FileCorruptedError, FileNotFoundError, ValueError)):
            load_gdf_file(dummy_path)
