"""Extended tests for BackendFacade to cover uncovered paths.

Covers: attach_labels, set_montage (fuzzy matching), generate_dataset
(all split strategies), stop_training, is_training, get_latest_results.
"""

import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from XBrainLab.backend.facade import BackendFacade

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_facade():
    """Create a BackendFacade with a mocked Study."""
    with patch("XBrainLab.backend.facade.Study") as MockStudy:
        mock_study = MockStudy.return_value
        facade = BackendFacade()
    return facade, mock_study


def _make_raw_mock(filepath, filename=None):
    """Create a mock Raw object."""
    raw = MagicMock()
    raw.filepath = filepath
    raw.get_filepath = MagicMock(return_value=filepath)
    raw.get_filename = MagicMock(return_value=filename or os.path.basename(filepath))
    raw.get_mne.return_value.info = {"ch_names": ["Fp1", "Fp2", "Cz"]}
    return raw


# ---------------------------------------------------------------------------
# attach_labels
# ---------------------------------------------------------------------------


class TestAttachLabels:
    def test_attach_labels_success(self):
        facade, _ = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

        fake_labels = np.array([1, 2, 1, 2])
        with patch(
            "XBrainLab.backend.facade.load_label_file", return_value=fake_labels
        ):
            result = facade.attach_labels({"sub01.set": "/labels/sub01.txt"})

        assert result == 1
        raw.set_event.assert_called_once()
        raw.set_labels_imported.assert_called_once_with(True)
        facade.dataset.notify.assert_called_once_with("data_changed")

    def test_attach_labels_no_match(self):
        facade, _ = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

        result = facade.attach_labels({"other_file.set": "/labels/other.txt"})
        assert result == 0
        raw.set_event.assert_not_called()
        facade.dataset.notify.assert_not_called()

    def test_attach_labels_exception(self):
        facade, _ = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

        with patch(
            "XBrainLab.backend.facade.load_label_file",
            side_effect=ValueError("bad file"),
        ):
            result = facade.attach_labels({"sub01.set": "/labels/sub01.txt"})

        assert result == 0
        raw.set_event.assert_not_called()

    def test_attach_labels_events_format(self):
        """Verify the events array shape and event_id dict are correct."""
        facade, _ = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

        fake_labels = np.array([0, 1, 2, 1, 0])
        with patch(
            "XBrainLab.backend.facade.load_label_file", return_value=fake_labels
        ):
            facade.attach_labels({"sub01.set": "/labels/sub01.txt"})

        call_args = raw.set_event.call_args[0]
        events = call_args[0]
        event_id = call_args[1]

        assert events.shape == (5, 3)
        assert np.array_equal(events[:, 2], fake_labels)
        assert event_id == {"0": 0, "1": 1, "2": 2}

    def test_attach_labels_multiple_files(self):
        """Test batch labelling of multiple files."""
        facade, _ = _make_facade()
        raw1 = _make_raw_mock("/data/sub01.set")
        raw2 = _make_raw_mock("/data/sub02.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw1, raw2])

        fake_labels = np.array([1, 2])
        with patch(
            "XBrainLab.backend.facade.load_label_file", return_value=fake_labels
        ):
            result = facade.attach_labels(
                {
                    "sub01.set": "/labels/sub01.txt",
                    "sub02.set": "/labels/sub02.txt",
                }
            )

        assert result == 2


# ---------------------------------------------------------------------------
# set_montage
# ---------------------------------------------------------------------------


class TestSetMontage:
    def test_no_data_loaded(self):
        facade, _ = _make_facade()
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[])
        facade.training.has_epoch_data = MagicMock(return_value=False)

        result = facade.set_montage("standard_1020")
        assert "Error" in result

    def test_full_match(self):
        facade, mock_study = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
        facade.training.has_epoch_data = MagicMock(return_value=False)

        positions = {
            "ch_pos": {
                "Fp1": (0.1, 0.2, 0.3),
                "Fp2": (0.4, 0.5, 0.6),
                "Cz": (0.7, 0.8, 0.9),
            }
        }
        with patch(
            "XBrainLab.backend.facade.get_montage_positions",
            return_value=positions,
        ):
            result = facade.set_montage("standard_1020")

        assert "Matched 3" in result
        mock_study.set_channels.assert_called_once()

    def test_partial_match(self):
        facade, mock_study = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
        facade.training.has_epoch_data = MagicMock(return_value=False)

        # Only 2 of 3 channels match
        positions = {
            "ch_pos": {
                "Fp1": (0.1, 0.2, 0.3),
                "Fp2": (0.4, 0.5, 0.6),
            }
        }
        with patch(
            "XBrainLab.backend.facade.get_montage_positions",
            return_value=positions,
        ):
            result = facade.set_montage("standard_1020")

        assert "Only 2/3" in result
        mock_study.set_channels.assert_not_called()

    def test_no_match(self):
        facade, _mock_study = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
        facade.training.has_epoch_data = MagicMock(return_value=False)

        positions = {"ch_pos": {"O1": (0.1, 0.2, 0.3)}}
        with patch(
            "XBrainLab.backend.facade.get_montage_positions",
            return_value=positions,
        ):
            result = facade.set_montage("standard_1020")

        assert "Verify Montage" in result

    def test_fuzzy_matching_eeg_prefix(self):
        """Channels like 'EEGFp1' should fuzzy-match to 'Fp1'."""
        facade, mock_study = _make_facade()
        raw = MagicMock()
        raw.get_mne.return_value.info = {"ch_names": ["EEGFp1", "EEGFp2", "EEGCz"]}
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
        facade.training.has_epoch_data = MagicMock(return_value=False)

        positions = {
            "ch_pos": {
                "Fp1": (0.1, 0.2, 0.3),
                "Fp2": (0.4, 0.5, 0.6),
                "Cz": (0.7, 0.8, 0.9),
            }
        }
        with patch(
            "XBrainLab.backend.facade.get_montage_positions",
            return_value=positions,
        ):
            result = facade.set_montage("standard_1020")

        assert "Matched 3" in result
        mock_study.set_channels.assert_called_once()

    def test_empty_montage_positions(self):
        facade, _ = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
        facade.training.has_epoch_data = MagicMock(return_value=False)

        with patch(
            "XBrainLab.backend.facade.get_montage_positions",
            return_value=None,
        ):
            result = facade.set_montage("nonexistent_montage")

        assert "Error" in result or "Failed" in result

    def test_exception_handling(self):
        facade, _ = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
        facade.training.has_epoch_data = MagicMock(return_value=False)

        with patch(
            "XBrainLab.backend.facade.get_montage_positions",
            side_effect=RuntimeError("boom"),
        ):
            result = facade.set_montage("standard_1020")

        assert "failed" in result.lower()

    def test_epoch_data_info_used(self):
        """When epoch data exists, use its info instead of raw data."""
        facade, _mock_study = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

        epoch_mock = MagicMock()
        epoch_mock.get_mne.return_value.info = {"ch_names": ["Fp1"]}
        facade.training.has_epoch_data = MagicMock(return_value=True)
        facade.training.get_epoch_data = MagicMock(return_value=epoch_mock)

        positions = {"ch_pos": {"Fp1": (0.1, 0.2, 0.3)}}
        with patch(
            "XBrainLab.backend.facade.get_montage_positions",
            return_value=positions,
        ):
            result = facade.set_montage("standard_1020")

        assert "Matched 1" in result


# ---------------------------------------------------------------------------
# generate_dataset
# ---------------------------------------------------------------------------


class TestGenerateDataset:
    @pytest.mark.parametrize(
        "strategy, expected_split_type",
        [
            ("trial", "TRIAL"),
            ("session", "SESSION"),
            ("subject", "SUBJECT"),
        ],
    )
    def test_split_strategies(self, strategy, expected_split_type):
        facade, mock_study = _make_facade()
        mock_generator = MagicMock()
        mock_study.get_datasets_generator = MagicMock(return_value=mock_generator)

        with patch("XBrainLab.backend.facade.DataSplittingConfig") as MockConfig:
            facade.generate_dataset(
                test_ratio=0.2,
                val_ratio=0.1,
                split_strategy=strategy,
            )

            MockConfig.assert_called_once()
            call_kwargs = MockConfig.call_args[1]
            # The train_type should be IND by default
            assert call_kwargs["is_cross_validation"] is False
            facade.training.apply_data_splitting.assert_called_once_with(mock_generator)

    @pytest.mark.parametrize(
        "mode, expected_type_name",
        [
            ("individual", "IND"),
            ("group", "FULL"),
        ],
    )
    def test_training_modes(self, mode, expected_type_name):
        facade, mock_study = _make_facade()
        mock_generator = MagicMock()
        mock_study.get_datasets_generator = MagicMock(return_value=mock_generator)

        with patch("XBrainLab.backend.facade.DataSplittingConfig") as MockConfig:
            facade.generate_dataset(training_mode=mode)
            MockConfig.assert_called_once()
            call_kwargs = MockConfig.call_args[1]
            assert call_kwargs["train_type"].name == expected_type_name


# ---------------------------------------------------------------------------
# Training control
# ---------------------------------------------------------------------------


class TestTrainingControl:
    def test_stop_training(self):
        facade, _ = _make_facade()
        facade.training.stop_training = MagicMock()
        facade.stop_training()
        facade.training.stop_training.assert_called_once()

    def test_is_training(self):
        facade, _ = _make_facade()
        facade.training.is_training = MagicMock(return_value=True)
        assert facade.is_training() is True

        facade.training.is_training = MagicMock(return_value=False)
        assert facade.is_training() is False


# ---------------------------------------------------------------------------
# get_latest_results
# ---------------------------------------------------------------------------


class TestGetLatestResults:
    def test_no_plans(self):
        facade, _ = _make_facade()
        facade.evaluation.get_plans = MagicMock(return_value=[])
        result = facade.get_latest_results()
        assert result == {"status": "no_plans"}

    def test_with_plans(self):
        facade, _ = _make_facade()

        run1 = MagicMock()
        run1.is_finished.return_value = True
        run2 = MagicMock()
        run2.is_finished.return_value = False

        plan = MagicMock()
        plan.get_plans.return_value = [run1, run2]

        facade.evaluation.get_plans = MagicMock(return_value=[plan])
        facade.training.is_training = MagicMock(return_value=True)

        result = facade.get_latest_results()

        assert result["total_plans"] == 1
        assert result["total_runs"] == 2
        assert result["finished_runs"] == 1
        assert result["training_active"] is True

    def test_multiple_plans_all_finished(self):
        facade, _ = _make_facade()

        run1 = MagicMock()
        run1.is_finished.return_value = True

        plan1 = MagicMock()
        plan1.get_plans.return_value = [run1]
        plan2 = MagicMock()
        plan2.get_plans.return_value = [run1]

        facade.evaluation.get_plans = MagicMock(return_value=[plan1, plan2])
        facade.training.is_training = MagicMock(return_value=False)

        result = facade.get_latest_results()

        assert result["total_plans"] == 2
        assert result["finished_runs"] == 2
        assert result["training_active"] is False


# ---------------------------------------------------------------------------
# Other delegation methods
# ---------------------------------------------------------------------------


class TestDelegation:
    def test_get_data_summary_with_event_info(self):
        facade, _ = _make_facade()
        raw = _make_raw_mock("/data/sub01.set")
        facade.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
        facade.dataset.get_event_info = MagicMock(
            return_value={"events": 100, "classes": 2}
        )

        summary = facade.get_data_summary()
        assert summary["count"] == 1
        assert summary["files"] == ["sub01.set"]
        assert summary["events"] == 100

    def test_set_reference_average(self):
        facade, _ = _make_facade()
        facade.preprocess.apply_rereference = MagicMock()
        facade.set_reference("average")
        facade.preprocess.apply_rereference.assert_called_once_with("average")

    def test_set_reference_channel(self):
        facade, _ = _make_facade()
        facade.preprocess.apply_rereference = MagicMock()
        facade.set_reference("Cz")
        facade.preprocess.apply_rereference.assert_called_once_with(["Cz"])

    def test_apply_notch_filter(self):
        facade, _ = _make_facade()
        facade.preprocess.apply_filter = MagicMock()
        facade.apply_notch_filter(60.0)
        facade.preprocess.apply_filter.assert_called_once_with(None, None, [60.0])

    def test_resample_data(self):
        facade, _ = _make_facade()
        facade.preprocess.apply_resample = MagicMock()
        facade.resample_data(256)
        facade.preprocess.apply_resample.assert_called_once_with(256)

    def test_normalize_data(self):
        facade, _ = _make_facade()
        facade.preprocess.apply_normalization = MagicMock()
        facade.normalize_data("zscore")
        facade.preprocess.apply_normalization.assert_called_once_with("zscore")

    def test_select_channels(self):
        facade, _ = _make_facade()
        facade.dataset.apply_channel_selection = MagicMock()
        facade.select_channels(["Fp1", "Fp2"])
        facade.dataset.apply_channel_selection.assert_called_once_with(["Fp1", "Fp2"])

    def test_epoch_data(self):
        facade, _ = _make_facade()
        facade.preprocess.apply_epoching = MagicMock()
        facade.epoch_data(-0.2, 0.5, baseline=[None, 0], event_ids=["left", "right"])
        facade.preprocess.apply_epoching.assert_called_once_with(
            [None, 0], ["left", "right"], -0.2, 0.5
        )

    def test_set_model_unknown(self):
        facade, _ = _make_facade()
        with pytest.raises(ValueError, match="Unknown model"):
            facade.set_model("nonexistent_model")

    def test_set_model_case_insensitive(self):
        facade, _ = _make_facade()
        facade.training.set_model_holder = MagicMock()
        with patch("XBrainLab.backend.facade.ModelHolder") as MockMH:
            facade.set_model("EEGNET")
            MockMH.assert_called_once()

    def test_configure_training_cpu(self):
        facade, _ = _make_facade()
        facade.training.set_training_option = MagicMock()
        with patch("XBrainLab.backend.facade.TrainingOption") as MockTO:
            facade.configure_training(10, 32, 0.001, device="cpu")
            call_kwargs = MockTO.call_args[1]
            assert call_kwargs["use_cpu"] is True
            assert call_kwargs["gpu_idx"] is None

    def test_configure_training_auto(self):
        facade, _ = _make_facade()
        facade.training.set_training_option = MagicMock()
        with patch("XBrainLab.backend.facade.TrainingOption") as MockTO:
            facade.configure_training(10, 32, 0.001, device="auto")
            call_kwargs = MockTO.call_args[1]
            assert call_kwargs["use_cpu"] is False
            assert call_kwargs["gpu_idx"] == 0

    def test_configure_training_adamw(self):
        facade, _ = _make_facade()
        facade.training.set_training_option = MagicMock()
        with patch("XBrainLab.backend.facade.TrainingOption") as MockTO:
            facade.configure_training(10, 32, 0.001, optimizer="adamw")
            call_kwargs = MockTO.call_args[1]
            assert call_kwargs["optim"] == torch.optim.AdamW

    def test_clear_data(self):
        facade, _ = _make_facade()
        facade.dataset.clean_dataset = MagicMock()
        facade.clear_data()
        facade.dataset.clean_dataset.assert_called_once()
