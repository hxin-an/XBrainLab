"""Extended tests for TrainRecord: export_checkpoint, load, get_model_output.

Covers: export_checkpoint round-trip, load from disk, get_model_output,
resume/pause, confusion figure with percentage.
"""

import os
from unittest.mock import patch

import numpy as np
import pytest
from matplotlib import pyplot as plt

from tests.unit.backend.training.test_training_plan import (
    CLASS_NUM,
    dataset,  # noqa: F401
    epochs,  # noqa: F401
    export_mocker,  # noqa: F401
    model_holder,  # noqa: F401
    preprocessed_data_list,  # noqa: F401
    training_option,  # noqa: F401
    y,  # noqa: F401
)
from XBrainLab.backend.training.record import (
    EvalRecord,
    RecordKey,
    TrainRecord,
)
from XBrainLab.backend.utils import set_seed


@pytest.fixture
def train_record(export_mocker, dataset, training_option, model_holder):  # noqa: F811
    repeat = 0
    seed = set_seed(0)
    model = model_holder.get_model({})
    record = TrainRecord(repeat, dataset, model, training_option, seed)
    return record


# ---------------------------------------------------------------------------
# get_model_output
# ---------------------------------------------------------------------------


class TestGetModelOutput:
    def test_with_training_data(self, train_record):
        """After some epochs, get_model_output returns formatted summary."""
        for i in range(3):
            train_record.update_train(
                {RecordKey.LOSS: 0.5 - i * 0.1, RecordKey.ACC: 50 + i * 10}
            )
            train_record.update_eval(
                {RecordKey.LOSS: 0.6 - i * 0.1, RecordKey.ACC: 45 + i * 10}
            )
            train_record.step()

        output = train_record.get_model_output()
        assert "Training Summary" in output
        assert "Total Epochs: 3" in output
        assert "Best Performance" in output
        assert "Last Epoch" in output
        assert "Train Loss" in output

    def test_no_training_data(self, train_record):
        """Before any training, shows 'No training data'."""
        output = train_record.get_model_output()
        assert "Total Epochs: 0" in output
        assert "No training data" in output


# ---------------------------------------------------------------------------
# resume / pause
# ---------------------------------------------------------------------------


class TestResumePause:
    def test_resume_sets_start_timestamp(self, train_record):
        assert train_record.start_timestamp is None
        train_record.resume()
        assert train_record.start_timestamp is not None

    def test_resume_does_not_overwrite_timestamp(self, train_record):
        train_record.resume()
        first = train_record.start_timestamp
        train_record.resume()
        # Second resume should NOT overwrite
        assert train_record.start_timestamp == first

    def test_pause_saves_state(self, train_record):
        train_record.resume()
        train_record.pause()
        assert train_record.end_timestamp is not None


# ---------------------------------------------------------------------------
# Confusion figure with percentage
# ---------------------------------------------------------------------------


class TestConfusionFigure:
    def test_confusion_percentage_mode(self, train_record):
        label = np.arange(CLASS_NUM).repeat(CLASS_NUM)
        output = np.zeros((CLASS_NUM * CLASS_NUM, CLASS_NUM))
        for i in range(CLASS_NUM):
            output[i * CLASS_NUM : (i + 1) * CLASS_NUM, i] = 1
        eval_record = EvalRecord(label, output, {}, {}, {}, {}, {})
        train_record.set_eval_record(eval_record)

        fig = train_record.get_confusion_figure(show_percentage=True)
        assert fig is not None
        plt.close("all")


# ---------------------------------------------------------------------------
# Export / Load round-trip (real disk)
# ---------------------------------------------------------------------------


class TestExportLoadRoundTrip:
    def test_export_and_load(self, tmp_path, dataset, training_option, model_holder):  # noqa: F811
        seed = set_seed(42)
        model = model_holder.get_model({})

        # Override target_path to tmp_path
        with patch.object(TrainRecord, "init_dir"):
            record = TrainRecord(0, dataset, model, training_option, seed)
            record.target_path = str(tmp_path)

        # Simulate training
        for i in range(5):
            record.update_train(
                {RecordKey.LOSS: 1.0 / (i + 1), RecordKey.ACC: i * 20.0}
            )
            record.update_eval({RecordKey.LOSS: 1.1 / (i + 1), RecordKey.ACC: i * 18.0})
            record.update_test({RecordKey.LOSS: 1.2 / (i + 1), RecordKey.ACC: i * 15.0})
            record.step()

        record.export_checkpoint()

        # Load back
        with patch.object(TrainRecord, "init_dir"):
            record2 = TrainRecord(0, dataset, model, training_option, seed)
            record2.target_path = str(tmp_path)
            record2.load()

        assert record2.epoch == 5
        assert record2.seed == 42
        assert len(record2.train[RecordKey.LOSS]) == 5
        assert len(record2.val[RecordKey.LOSS]) == 5

    def test_load_nonexistent_path(self, train_record):
        """Loading from nonexistent path should be a no-op."""
        train_record.target_path = "/nonexistent/path"
        # Should not raise
        train_record.load()

    def test_load_no_target_path(self, train_record):
        """Loading with None target_path should be a no-op."""
        train_record.target_path = None
        train_record.load()

    def test_export_no_target_path(self, train_record):
        """Exporting with None target_path should be a no-op."""
        train_record.target_path = None
        # Should not raise, just return early
        train_record.export_checkpoint()

    def test_export_with_eval_record(
        self,
        tmp_path,
        dataset,  # noqa: F811
        training_option,  # noqa: F811
        model_holder,  # noqa: F811
    ):
        seed = set_seed(0)
        model = model_holder.get_model({})

        with patch.object(TrainRecord, "init_dir"):
            record = TrainRecord(0, dataset, model, training_option, seed)
            record.target_path = str(tmp_path)

        label = np.array([0, 1])
        output = np.array([[1.0, 0.0], [0.0, 1.0]])
        eval_rec = EvalRecord(label, output, {}, {}, {}, {}, {})
        record.set_eval_record(eval_rec)
        record.export_checkpoint()

        # Verify eval file exists
        assert os.path.exists(os.path.join(str(tmp_path), "eval"))
