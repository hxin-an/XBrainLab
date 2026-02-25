"""Record key constants for accessing training and evaluation statistics."""


class RecordKey:
    """Key constants for accessing evaluation and testing record statistics.

    Attributes:
        LOSS: Key for loss values.
        ACC: Key for accuracy values.
        AUC: Key for AUC values.
    """

    LOSS = "loss"
    ACC = "accuracy"
    AUC = "auc"

    def __iter__(self):
        """Iterate over all record key values defined as class attributes.

        Returns:
            An iterator over the string values of all non-private attributes.
        """
        keys = dir(self)
        keys = [getattr(self, key) for key in keys if not key.startswith("_")]
        return iter(keys)


class TrainRecordKey(RecordKey):
    """Extended key constants for training record statistics.

    Inherits loss, accuracy, and AUC keys from :class:`RecordKey` and adds
    training-specific keys.

    Attributes:
        TIME: Key for epoch duration values.
        LR: Key for learning rate values.
    """

    TIME = "time"
    LR = "lr"
