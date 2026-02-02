from .eval import EvalRecord


class ProxyRecord:
    def __init__(self, labels, outputs):
        self.eval_record = EvalRecord(labels, outputs, {}, {}, {}, {}, {})

    def get_confusion_figure(self, fig=None, show_percentage=False):
        # Return None as this is a proxy record without dataset context
        # or implement simple confusion matrix logic if needed.
        # For now, explicit None return to fix the "empty method" issue.
        return None


class PooledRecordWrapper:
    def __init__(self, original, labels, outputs):
        self.original = original
        self.eval_record = EvalRecord(labels, outputs, {}, {}, {}, {}, {})
        self.dataset = original.dataset  # Needed for class names

    def get_confusion_figure(self, fig=None, show_percentage=False):
        # Delegate finding class names etc to original class method
        return self.original.__class__.get_confusion_figure(
            self, fig, show_percentage=show_percentage
        )
