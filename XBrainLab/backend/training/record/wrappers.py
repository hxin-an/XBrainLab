"""Wrapper classes for creating proxy and pooled evaluation records."""

from .eval import EvalRecord


class ProxyRecord:
    """Lightweight proxy wrapping labels and outputs into an :class:`EvalRecord`.

    Used when only basic evaluation metrics are needed without full saliency data.

    Attributes:
        eval_record: An :class:`EvalRecord` with empty saliency dictionaries.

    """

    def __init__(self, labels, outputs):
        """Initialize the proxy record.

        Args:
            labels: Ground truth label array.
            outputs: Model output array.

        """
        self.eval_record = EvalRecord(labels, outputs, {}, {}, {}, {}, {})

    def get_confusion_figure(self, fig=None, show_percentage=False):
        """Return ``None`` as proxy records lack dataset context for visualization.

        Args:
            fig: Unused. Present for interface compatibility.
            show_percentage: Unused. Present for interface compatibility.

        Returns:
            ``None``.

        """
        return


class PooledRecordWrapper:
    """Wrapper combining an original record with pooled evaluation data.

    Wraps an original :class:`TrainRecord` and replaces its evaluation data
    with pooled (aggregated) labels and outputs, while retaining the original
    dataset reference for class name resolution.

    Attributes:
        original: The original :class:`TrainRecord` instance.
        eval_record: An :class:`EvalRecord` with the pooled data.
        dataset: The dataset from the original record (for class names).

    """

    def __init__(self, original, labels, outputs):
        """Initialize the pooled record wrapper.

        Args:
            original: The original :class:`TrainRecord` to wrap.
            labels: Pooled ground truth label array.
            outputs: Pooled model output array.

        """
        self.original = original
        self.eval_record = EvalRecord(labels, outputs, {}, {}, {}, {}, {})
        self.dataset = original.dataset  # Needed for class names

    def get_confusion_figure(self, fig=None, show_percentage=False):
        """Generate a confusion matrix figure using the original record's method.

        Args:
            fig: Existing figure to plot on, or ``None`` to create a new one.
            show_percentage: If ``True``, display row-normalized percentages.

        Returns:
            A matplotlib :class:`~matplotlib.figure.Figure`, or ``None``.

        """
        return self.original.__class__.get_confusion_figure(
            self,
            fig,
            show_percentage=show_percentage,
        )
