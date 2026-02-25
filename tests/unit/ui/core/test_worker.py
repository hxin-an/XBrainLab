"""Unit tests for Worker and WorkerSignals."""

from XBrainLab.ui.core.worker import Worker, WorkerSignals


class TestWorkerSignals:
    """WorkerSignals should declare four pyqtSignals."""

    def test_has_finished_signal(self):
        ws = WorkerSignals()
        assert hasattr(ws, "finished")

    def test_has_error_signal(self):
        ws = WorkerSignals()
        assert hasattr(ws, "error")

    def test_has_result_signal(self):
        ws = WorkerSignals()
        assert hasattr(ws, "result")

    def test_has_progress_signal(self):
        ws = WorkerSignals()
        assert hasattr(ws, "progress")


class TestWorker:
    """Worker wraps a callable and emits signals when run."""

    def test_stores_function_and_args(self):
        def fn(x, y):
            return x + y

        w = Worker(fn, 1, 2, key="val")
        assert w.fn is fn
        assert w.args == (1, 2)
        assert w.kwargs == {"key": "val"}

    def test_run_emits_result_and_finished(self, qtbot):
        results = []
        finished = []

        def add(a, b):
            return a + b

        w = Worker(add, 3, 4)
        w.signals.result.connect(lambda r: results.append(r))
        w.signals.finished.connect(lambda: finished.append(True))

        w.run()

        assert results == [7]
        assert finished == [True]

    def test_run_emits_error_on_exception(self, qtbot):
        errors = []
        finished = []

        def fail():
            raise ValueError("boom")

        w = Worker(fail)
        w.signals.error.connect(lambda e: errors.append(e))
        w.signals.finished.connect(lambda: finished.append(True))

        w.run()

        assert len(errors) == 1
        exc_type, exc_value, tb_str = errors[0]
        assert exc_type is ValueError
        assert str(exc_value) == "boom"
        assert "boom" in tb_str
        # finished should still fire
        assert finished == [True]

    def test_no_result_on_error(self, qtbot):
        results = []

        def fail():
            raise RuntimeError("err")

        w = Worker(fail)
        w.signals.result.connect(lambda r: results.append(r))
        w.run()

        assert results == []

    def test_run_with_kwargs(self, qtbot):
        results = []

        def greet(name="world"):
            return f"hello {name}"

        w = Worker(greet, name="test")
        w.signals.result.connect(lambda r: results.append(r))
        w.run()

        assert results == ["hello test"]

    def test_worker_is_qrunnable(self):
        from PyQt6.QtCore import QRunnable

        w = Worker(lambda: None)
        assert isinstance(w, QRunnable)

    def test_progress_signal_emits(self, qtbot):
        """progress signal can be emitted and received externally."""
        values = []
        w = Worker(lambda: None)
        w.signals.progress.connect(lambda v: values.append(v))
        w.signals.progress.emit(50)
        assert values == [50]
