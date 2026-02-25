"""Unit tests for training/record/key — RecordKey and TrainRecordKey."""

from XBrainLab.backend.training.record.key import RecordKey, TrainRecordKey


class TestRecordKey:
    def test_constants(self):
        assert RecordKey.LOSS == "loss"
        assert RecordKey.ACC == "accuracy"
        assert RecordKey.AUC == "auc"

    def test_iterable(self):
        keys = list(RecordKey())
        assert "loss" in keys
        assert "accuracy" in keys
        assert "auc" in keys
        assert len(keys) == 3

    def test_iteration_skips_private(self):
        for key in RecordKey():
            assert not key.startswith("_")


class TestTrainRecordKey:
    def test_inherits_record_key(self):
        assert issubclass(TrainRecordKey, RecordKey)

    def test_extra_constants(self):
        assert TrainRecordKey.TIME == "time"
        assert TrainRecordKey.LR == "lr"

    def test_iterable_includes_inherited(self):
        keys = list(TrainRecordKey())
        assert "loss" in keys
        assert "accuracy" in keys
        assert "auc" in keys
        assert "time" in keys
        assert "lr" in keys
        assert len(keys) == 5
