"""Unit tests for Worker and WorkerSignals."""

import logging

from XBrainLab.backend.application.owned_work import OwnedOperationCancelledError
from XBrainLab.ui.core.worker import PythonThreadWorker, Worker, WorkerSignals


class TestWorkerSignals:
    """WorkerSignals declares terminal and result delivery signals."""

    def test_has_finished_signal(self):
        ws = WorkerSignals()
        assert callable(ws.finished.connect)

    def test_has_error_signal(self):
        ws = WorkerSignals()
        assert callable(ws.error.connect)

    def test_has_result_signal(self):
        ws = WorkerSignals()
        assert callable(ws.result.connect)


def test_python_thread_worker_daemon_is_explicit_and_opt_in():
    regular = PythonThreadWorker(lambda: None, name="regular-worker")
    detached = PythonThreadWorker(
        lambda: None,
        name="detached-preview-worker",
        daemon=True,
    )

    assert regular.daemon is False
    assert detached.daemon is True


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
        w.signals.result.connect(results.append)
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
        w.signals.error.connect(errors.append)
        w.signals.finished.connect(lambda: finished.append(True))

        w.run()

        assert len(errors) == 1
        exc_type, exc_value, tb_str = errors[0]
        assert exc_type is ValueError
        assert str(exc_value) == "boom"
        assert "boom" in tb_str
        # finished should still fire
        assert finished == [True]

    def test_run_reports_expected_cancellation_without_error_log(
        self,
        qtbot,
        capture_product_logs,
    ):
        errors = []
        finished = []

        def cancel():
            raise OwnedOperationCancelledError("operation-1", "Preparing result")

        worker = Worker(cancel)
        worker.signals.error.connect(errors.append)
        worker.signals.finished.connect(lambda: finished.append(True))

        with capture_product_logs(level=logging.DEBUG) as caplog:
            worker.run()

        assert len(errors) == 1
        assert errors[0][0] is OwnedOperationCancelledError
        assert finished == [True]
        worker_records = [
            record
            for record in caplog.records
            if record.name == "XBrainLab.ui.core.worker"
        ]
        assert [record.levelno for record in worker_records] == [logging.DEBUG]
        assert all(
            "Worker task failed" not in record.getMessage() for record in worker_records
        )

    def test_run_logs_unexpected_failure_at_error(self, qtbot, capture_product_logs):
        def fail():
            raise ValueError("boom")

        worker = Worker(fail)
        with capture_product_logs(level=logging.DEBUG) as caplog:
            worker.run()

        worker_records = [
            record
            for record in caplog.records
            if record.name == "XBrainLab.ui.core.worker"
        ]
        assert len(worker_records) == 1
        assert worker_records[0].levelno == logging.ERROR
        assert worker_records[0].getMessage().startswith("Worker task failed")

    def test_no_result_on_error(self, qtbot):
        results = []

        def fail():
            raise RuntimeError("err")

        w = Worker(fail)
        w.signals.result.connect(results.append)
        w.run()

        assert results == []

    def test_run_with_kwargs(self, qtbot):
        results = []

        def greet(name="world"):
            return f"hello {name}"

        w = Worker(greet, name="test")
        w.signals.result.connect(results.append)
        w.run()

        assert results == ["hello test"]

    def test_worker_is_qrunnable(self):
        from PyQt6.QtCore import QRunnable

        w = Worker(lambda: None)
        assert isinstance(w, QRunnable)
