class RecordKey:
    "Utility class for accessing the statistics of the testing record"

    LOSS = "loss"
    ACC = "accuracy"
    AUC = "auc"

    def __iter__(self):
        keys = dir(self)
        keys = [getattr(self, key) for key in keys if not key.startswith("_")]
        return iter(keys)


class TrainRecordKey(RecordKey):
    "Utility class for accessing the statistics of the training record"

    TIME = "time"
    LR = "lr"
