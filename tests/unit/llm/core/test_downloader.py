import multiprocessing
import queue as stdlib_queue
import threading
import time
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.downloader import (
    PROCESS_JOIN_TIMEOUT_SEC,
    PROCESS_KILL_JOIN_TIMEOUT_SEC,
    PROCESS_TERMINATE_JOIN_TIMEOUT_SEC,
    DownloadWorker,
    ModelDownloader,
    ModelDownloadOutcome,
    ModelDownloadStatus,
    ProcessCleanupPhase,
    run_download_task,
)

PRIMARY_MODEL_ID = "microsoft/Phi-4-mini-instruct"
PRIMARY_MODEL_REVISION = (
    "cfbefacb99257ffa30c83adab238a50856ac3083"  # pragma: allowlist secret
)
VALID_TEST_WEIGHT_BYTES = 300_000_000


def _spawn_wait_for_parent_cleanup(started) -> None:
    """Picklable spawn target that waits until its parent terminates it."""
    started.set()
    while True:
        time.sleep(0.1)


def _write_hf_snapshot(
    cache_dir: Path,
    *,
    repo_id: str = PRIMARY_MODEL_ID,
    revision: str = PRIMARY_MODEL_REVISION,
    weight_bytes: int = VALID_TEST_WEIGHT_BYTES,
) -> Path:
    snapshot = (
        cache_dir / f"models--{repo_id.replace('/', '--')}" / "snapshots" / revision
    )
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    with (snapshot / "model.safetensors").open("wb") as stream:
        stream.truncate(weight_bytes)
    return snapshot


def _patch_download_process_context(process, result_queue):
    context = MagicMock()
    context.Process.return_value = process
    context.Queue.return_value = result_queue
    return patch(
        "XBrainLab.llm.core.downloader.multiprocessing.get_context",
        return_value=context,
    )


class _AmbiguousStartProcess:
    """Reliable fake for a child created before parent-side start failure."""

    pid = 4242

    def __init__(self) -> None:
        self.child_alive = True
        self.allow_cleanup = False
        self.joined = False
        self.close_calls = 0
        self.terminate_calls = 0

    def start(self) -> None:
        raise OSError("parent bootstrap failed after child creation")

    def is_alive(self) -> bool:
        return self.child_alive

    def terminate(self) -> None:
        self.terminate_calls += 1
        if not self.allow_cleanup:
            raise PermissionError("parent cannot terminate child")
        self.child_alive = False

    def kill(self) -> None:
        self.terminate()

    def join(self, _timeout: float) -> None:
        if not self.allow_cleanup:
            raise PermissionError("parent cannot join child")
        self.joined = True

    def close(self) -> None:
        self.close_calls += 1
        if self.child_alive:
            raise ValueError("cannot close a running process")


def _drain_queue(q, timeout=2.0, poll=0.05):
    """Drain all items from a multiprocessing.Queue with timeout.

    On Windows, the feeder thread may not have flushed yet when
    ``get_nowait`` is called immediately after ``put``.
    """
    messages = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            messages.append(q.get_nowait())
        except Exception:  # noqa: PERF203
            if messages:
                # Got at least one; try once more after short sleep
                time.sleep(poll)
                try:
                    messages.append(q.get_nowait())
                except Exception:
                    break
            else:
                time.sleep(poll)
    return messages


# Mock multiprocessing.Process AND Queue
@pytest.fixture
def mock_multiprocessing():
    with patch("XBrainLab.llm.core.downloader.multiprocessing") as mock_mp:
        mock_context = MagicMock()
        mock_mp.get_context.return_value = mock_context
        mock_mp.Process = mock_context.Process
        mock_mp.Queue = mock_context.Queue
        mock_process = MagicMock()
        mock_process.is_alive.side_effect = lambda: not mock_process.kill.called
        mock_context.Process.return_value = mock_process

        mock_queue = MagicMock()
        mock_queue.get_nowait.side_effect = list

        mock_context.Queue.return_value = mock_queue

        yield mock_mp, mock_process, mock_queue


class TestModelDownloader:
    def test_download_success(self, mock_multiprocessing, qtbot):
        """Test successful download signal emission via queue."""
        mock_mp, mock_process, mock_queue = mock_multiprocessing

        messages = [("progress", (50, "Halfway")), ("finished", "/path/to/model")]

        def get_msg():
            if messages:
                return messages.pop(0)
            raise stdlib_queue.Empty

        mock_queue.get_nowait.side_effect = get_msg

        downloader = ModelDownloader()

        with qtbot.waitSignal(downloader.finished, timeout=1000) as blocker:
            downloader.start_download("repo/id", "/cache")

        outcome = blocker.args[0]
        assert isinstance(outcome, ModelDownloadOutcome)
        assert outcome.status is ModelDownloadStatus.SUCCEEDED
        assert outcome.target.repo_id == "repo/id"
        assert outcome.target.cache_dir == "/cache"
        assert outcome.model_path == "/path/to/model"
        mock_mp.Process.assert_called_once()
        mock_process.start.assert_called_once()

    def test_download_failure(self, mock_multiprocessing, qtbot):
        """Test failure signal emission."""
        _, _, mock_queue = mock_multiprocessing

        messages = [("error", "Network Error")]

        def get_msg():
            if messages:
                return messages.pop(0)
            raise stdlib_queue.Empty

        mock_queue.get_nowait.side_effect = get_msg

        downloader = ModelDownloader()

        with qtbot.waitSignal(downloader.failed, timeout=1000) as blocker:
            downloader.start_download("repo/id", "/cache")

        outcome = blocker.args[0]
        assert isinstance(outcome, ModelDownloadOutcome)
        assert outcome.status is ModelDownloadStatus.FAILED
        assert outcome.target.repo_id == "repo/id"
        assert "Network Error" in outcome.diagnostic_message
        assert "Network Error" not in outcome.message

    def test_cancellation(self, mock_multiprocessing, qtbot):
        """Test that cancel() calls process.terminate()."""
        _, mock_process, mock_queue = mock_multiprocessing

        mock_queue.get_nowait.side_effect = stdlib_queue.Empty

        downloader = ModelDownloader()
        downloader.start_download("repo/id", "/cache")

        qtbot.wait(100)

        with qtbot.waitSignal(downloader.failed, timeout=1000) as blocker:
            downloader.cancel_download()

        outcome = blocker.args[0]
        assert isinstance(outcome, ModelDownloadOutcome)
        assert outcome.status is ModelDownloadStatus.CANCELLED
        assert outcome.target.repo_id == "repo/id"
        mock_process.terminate.assert_called_once()
        mock_process.join.assert_any_call(PROCESS_TERMINATE_JOIN_TIMEOUT_SEC)
        mock_process.join.assert_any_call(PROCESS_KILL_JOIN_TIMEOUT_SEC)

    def test_start_download_ignores_if_running(self, mock_multiprocessing, qtbot):
        """If a download thread is already running, start_download is a no-op."""
        mock_mp, _, mock_queue = mock_multiprocessing
        mock_queue.get_nowait.side_effect = stdlib_queue.Empty

        downloader = ModelDownloader()
        assert downloader.start_download("repo/id", "/cache") is True
        qtbot.waitUntil(lambda: mock_mp.Process.call_count == 1, timeout=1000)

        assert downloader.start_download("repo/other", "/cache") is False

        mock_mp.Process.assert_called_once()
        with qtbot.waitSignal(downloader.terminal, timeout=1000):
            downloader.cancel_download()

    def test_qthread_start_failure_releases_ownership_and_publishes_failure(self):
        downloader = ModelDownloader()
        failed: list[ModelDownloadOutcome] = []
        terminal: list[ModelDownloadOutcome] = []
        downloader.failed.connect(failed.append)
        downloader.terminal.connect(terminal.append)

        with patch(
            "XBrainLab.llm.core.downloader.QThread.start",
            side_effect=RuntimeError("native thread start failed"),
        ):
            assert downloader.start_download("repo/id", "/cache") is False

        assert downloader.is_idle() is True
        assert downloader.worker is None
        assert downloader.active_target is None
        assert len(failed) == 1
        assert terminal == failed
        assert failed[0].status is ModelDownloadStatus.FAILED
        assert "native thread start failed" not in failed[0].message
        assert "native thread start failed" in failed[0].diagnostic_message

    def test_deleted_thread_wrapper_does_not_manufacture_idle(self):
        """Unknown QThread state must retain ownership and reject new work."""
        downloader = ModelDownloader()
        mock_thread = MagicMock()
        mock_thread.isRunning.side_effect = RuntimeError(
            "Wrapped C++ object has been deleted"
        )
        downloader._thread = mock_thread

        assert downloader.is_idle() is False
        assert downloader.start_download("repo/id", "/cache") is False
        assert downloader._thread is mock_thread

    def test_cancel_no_worker_keeps_thread_state(self):
        """cancel_download only delegates to an active worker."""
        downloader = ModelDownloader()
        thread = MagicMock()
        downloader.worker = None
        downloader._thread = thread

        downloader.cancel_download()

        assert downloader.worker is None
        assert downloader._thread is thread
        thread.quit.assert_not_called()
        thread.wait.assert_not_called()

    def test_shutdown_requests_cancel_without_blocking_gui_thread(self):
        """Shutdown must leave terminal ownership intact for a later retry."""
        downloader = ModelDownloader()
        downloader.worker = MagicMock()
        thread = MagicMock()
        thread.isRunning.return_value = True
        downloader._thread = thread

        started_at = time.monotonic()
        assert downloader.shutdown() is False
        elapsed = time.monotonic() - started_at

        assert elapsed < 0.05
        downloader.worker.cancel.assert_called_once()
        thread.quit.assert_not_called()
        thread.wait.assert_not_called()
        assert downloader._thread is thread

    def test_terminal_signal_is_emitted_after_subprocess_is_reaped(
        self,
        mock_multiprocessing,
        qtbot,
    ):
        """Terminal means both the worker thread and child process are gone."""
        _, mock_process, mock_queue = mock_multiprocessing
        messages = [("finished", "/path/to/model")]

        def get_msg():
            if messages:
                return messages.pop(0)
            raise stdlib_queue.Empty

        mock_queue.get_nowait.side_effect = get_msg
        mock_process.is_alive.side_effect = [True, False, False]
        downloader = ModelDownloader()

        with qtbot.waitSignal(downloader.terminal, timeout=1000) as blocker:
            downloader.start_download("repo/id", "/cache")

        outcome = blocker.args[0]
        assert isinstance(outcome, ModelDownloadOutcome)
        assert outcome.status is ModelDownloadStatus.SUCCEEDED
        assert outcome.target.repo_id == "repo/id"
        mock_process.join.assert_called()
        assert downloader.is_idle() is True
        assert downloader._thread is None

    def test_terminate_permission_error_retains_ownership_until_retry_terminal(
        self,
        qtbot,
    ):
        """A failed cleanup attempt cannot manufacture terminal or idle."""
        allow_terminate = threading.Event()
        process_alive = True
        mock_process = MagicMock()

        def terminate() -> None:
            nonlocal process_alive
            if not allow_terminate.is_set():
                raise PermissionError("process access denied")
            process_alive = False

        mock_process.terminate.side_effect = terminate
        mock_process.is_alive.side_effect = lambda: process_alive
        mock_queue = MagicMock()
        mock_queue.get_nowait.side_effect = stdlib_queue.Empty
        downloader = ModelDownloader()
        terminal_outcomes: list[ModelDownloadOutcome] = []
        cleanup_phases: list[ProcessCleanupPhase] = []
        downloader.terminal.connect(terminal_outcomes.append)
        downloader.cleanup_state_changed.connect(
            lambda snapshot: cleanup_phases.append(snapshot.phase)
        )

        with _patch_download_process_context(mock_process, mock_queue):
            assert downloader.start_download("repo/id", "/cache") is True
            qtbot.waitUntil(lambda: mock_process.start.called, timeout=1000)
            downloader.cancel_download()
            qtbot.waitUntil(
                lambda: ProcessCleanupPhase.RETRY_PENDING in cleanup_phases,
                timeout=1000,
            )

            assert terminal_outcomes == []
            assert downloader.is_idle() is False
            assert downloader.worker is not None
            assert downloader.worker._process is mock_process

            allow_terminate.set()
            downloader.request_cleanup_retry()
            qtbot.waitUntil(lambda: bool(terminal_outcomes), timeout=2000)

        assert terminal_outcomes[0].status is ModelDownloadStatus.CANCELLED
        assert terminal_outcomes[0].target.repo_id == "repo/id"
        assert downloader.is_idle() is True
        mock_process.kill.assert_not_called()

    def test_permanent_cleanup_error_is_bounded_and_keeps_gui_responsive(
        self,
        qtbot,
    ):
        """A retained child enters recovery without terminal or a busy loop."""
        process = _AmbiguousStartProcess()
        start_mock = MagicMock()
        process.start = cast(Any, start_mock)
        queue = MagicMock()
        queue.get_nowait.side_effect = stdlib_queue.Empty
        downloader = ModelDownloader()
        terminal_outcomes: list[ModelDownloadOutcome] = []
        cleanup_phases: list[ProcessCleanupPhase] = []
        heartbeat: list[bool] = []
        downloader.terminal.connect(terminal_outcomes.append)
        downloader.cleanup_state_changed.connect(
            lambda snapshot: cleanup_phases.append(snapshot.phase)
        )

        with _patch_download_process_context(process, queue):
            try:
                assert downloader.start_download("repo/id", "/cache") is True
                qtbot.waitUntil(lambda: start_mock.called, timeout=1000)
                downloader.cancel_download()
                qtbot.waitUntil(
                    lambda: ProcessCleanupPhase.RECOVERY_REQUIRED in cleanup_phases,
                    timeout=2000,
                )

                attempts_after_recovery = process.terminate_calls
                qtbot.wait(150)
                assert process.terminate_calls == attempts_after_recovery
                assert terminal_outcomes == []
                assert downloader.is_idle() is False
                assert downloader.worker is not None
                assert downloader.worker._process is process

                from PyQt6.QtCore import QTimer

                QTimer.singleShot(0, lambda: heartbeat.append(True))
                qtbot.waitUntil(lambda: heartbeat == [True], timeout=1000)

                process.allow_cleanup = True
                downloader.request_cleanup_retry()
                qtbot.waitUntil(lambda: bool(terminal_outcomes), timeout=2000)
            finally:
                process.allow_cleanup = True
                retry = getattr(downloader, "request_cleanup_retry", None)
                if callable(retry):
                    retry()
                else:
                    downloader.cancel_download()
                qtbot.waitUntil(downloader.is_idle, timeout=2000)

        assert terminal_outcomes[0].status is ModelDownloadStatus.CANCELLED
        assert process.joined is True
        assert process.child_alive is False
        assert downloader.is_idle() is True


class TestRunDownloadTask:
    def test_success_uses_pinned_revision_and_validates_snapshot(
        self,
        tmp_path: Path,
    ):
        q = multiprocessing.Queue()
        cache_dir = tmp_path / "models"
        snapshot = _write_hf_snapshot(cache_dir)
        with patch(
            "XBrainLab.llm.core.downloader.snapshot_download",
            return_value=str(snapshot),
        ) as download:
            run_download_task(PRIMARY_MODEL_ID, str(cache_dir), q)

        messages = _drain_queue(q)

        types = [m[0] for m in messages]
        assert "progress" in types
        assert "finished" in types
        assert messages[-1] == ("finished", str(snapshot))
        assert download.call_args.kwargs["revision"] == PRIMARY_MODEL_REVISION

    def test_invalid_snapshot_never_emits_success(self, tmp_path: Path) -> None:
        q = multiprocessing.Queue()
        cache_dir = tmp_path / "models"
        snapshot = _write_hf_snapshot(cache_dir, weight_bytes=1)

        with patch(
            "XBrainLab.llm.core.downloader.snapshot_download",
            return_value=str(snapshot),
        ):
            run_download_task(PRIMARY_MODEL_ID, str(cache_dir), q)

        messages = _drain_queue(q)

        assert any(kind == "error" for kind, _payload in messages)
        assert all(kind != "finished" for kind, _payload in messages)

    def test_unpinned_snapshot_revision_never_emits_success(
        self,
        tmp_path: Path,
    ) -> None:
        q = multiprocessing.Queue()
        cache_dir = tmp_path / "models"
        snapshot = _write_hf_snapshot(
            cache_dir,
            revision="0" * 40,
        )

        with patch(
            "XBrainLab.llm.core.downloader.snapshot_download",
            return_value=str(snapshot),
        ):
            run_download_task(PRIMARY_MODEL_ID, str(cache_dir), q)

        messages = _drain_queue(q)

        assert any(
            "pinned local runtime revision" in str(payload) for _, payload in messages
        )
        assert all(kind != "finished" for kind, _payload in messages)

    def test_post_download_single_model_limit_is_enforced(
        self,
        tmp_path: Path,
    ) -> None:
        q = multiprocessing.Queue()
        cache_dir = tmp_path / "models"

        def download_snapshot(**_kwargs) -> str:
            return str(_write_hf_snapshot(cache_dir, weight_bytes=10_100_000_000))

        with patch(
            "XBrainLab.llm.core.downloader.snapshot_download",
            side_effect=download_snapshot,
        ):
            run_download_task(PRIMARY_MODEL_ID, str(cache_dir), q)

        messages = _drain_queue(q)

        assert any("per-model limit" in str(payload) for _, payload in messages)
        assert all(kind != "finished" for kind, _payload in messages)

    def test_post_download_total_cache_limit_is_enforced(
        self,
        tmp_path: Path,
    ) -> None:
        q = multiprocessing.Queue()
        cache_dir = tmp_path / "models"

        def download_snapshot(**_kwargs) -> str:
            other = cache_dir / "unrelated-cache.bin"
            other.parent.mkdir(parents=True, exist_ok=True)
            with other.open("wb") as stream:
                stream.truncate(20_100_000_000)
            return str(_write_hf_snapshot(cache_dir))

        with patch(
            "XBrainLab.llm.core.downloader.snapshot_download",
            side_effect=download_snapshot,
        ):
            run_download_task(PRIMARY_MODEL_ID, str(cache_dir), q)

        messages = _drain_queue(q)

        assert any("total cache limit" in str(payload) for _, payload in messages)
        assert all(kind != "finished" for kind, _payload in messages)

    def test_post_download_disk_reserve_is_enforced(
        self,
        tmp_path: Path,
    ) -> None:
        q = multiprocessing.Queue()
        cache_dir = tmp_path / "models"

        def download_snapshot(**_kwargs) -> str:
            return str(_write_hf_snapshot(cache_dir))

        with (
            patch(
                "XBrainLab.llm.core.downloader.snapshot_download",
                side_effect=download_snapshot,
            ),
            patch(
                "XBrainLab.llm.core.model_catalog.available_disk_bytes",
                side_effect=[50_000_000_000, 4_000_000_000],
            ),
        ):
            run_download_task(PRIMARY_MODEL_ID, str(cache_dir), q)

        messages = _drain_queue(q)

        assert any("free disk reserve" in str(payload) for _, payload in messages)
        assert all(kind != "finished" for kind, _payload in messages)

    def test_missing_library(self):
        q = multiprocessing.Queue()
        import XBrainLab.llm.core.downloader as _dl_mod

        original = _dl_mod.snapshot_download
        try:
            _dl_mod.snapshot_download = None  # type: ignore[assignment]
            run_download_task("microsoft/Phi-4-mini-instruct", "/cache", q)
        finally:
            _dl_mod.snapshot_download = original

        messages = _drain_queue(q)
        assert len(messages) == 1
        assert messages[0][0] == "error"
        assert "Missing" in messages[0][1]

    def test_exception_during_download(self):
        q = multiprocessing.Queue()
        with patch(
            "XBrainLab.llm.core.downloader.snapshot_download",
            side_effect=OSError("disk full"),
        ):
            run_download_task("microsoft/Phi-4-mini-instruct", "/cache", q)

        messages = _drain_queue(q)
        # Should have progress then error
        errors = [m for m in messages if m[0] == "error"]
        assert len(errors) == 1
        assert "disk full" in errors[0][1]


class TestDownloadWorker:
    def test_worker_uses_explicit_spawn_context(self, mock_multiprocessing) -> None:
        mock_mp, mock_process, mock_queue = mock_multiprocessing
        mock_process.is_alive.side_effect = [True, False, False]
        mock_queue.get_nowait.side_effect = [
            ("error", "stop after context assertion"),
        ]
        worker = DownloadWorker("repo/id", "/cache")

        worker.run()

        mock_mp.get_context.assert_called_once_with("spawn")
        mock_mp.Process.assert_called_once()
        mock_mp.Queue.assert_called_once()

    @pytest.mark.skipif(
        not hasattr(multiprocessing, "get_context"),
        reason="spawn context is unavailable",
    )
    def test_product_worker_runs_real_spawn_child_without_default_fork(
        self,
        tmp_path: Path,
    ) -> None:
        worker = DownloadWorker("unsupported/repo", str(tmp_path / "models"))
        failures: list[str] = []
        worker.download_failed.connect(failures.append)

        worker.run()

        assert len(failures) == 1
        assert "not in the supported product catalog" in failures[0]
        assert worker._process is None
        assert worker._queue is None

    def test_process_start_failure_is_reported_and_releases_native_owners(self):
        worker = DownloadWorker("repo/id", "/cache")
        failures: list[str] = []
        worker.download_failed.connect(failures.append)

        mock_process = MagicMock()
        mock_process.start.side_effect = OSError("cannot start child")
        mock_process.is_alive.return_value = False
        mock_process.pid = None
        mock_process._popen = None
        mock_queue = MagicMock()

        with _patch_download_process_context(mock_process, mock_queue):
            worker.run()

        assert failures == ["Model download could not start: cannot start child"]
        assert worker._process is None
        assert worker._queue is None
        mock_queue.close.assert_called_once()
        mock_queue.join_thread.assert_called_once()

    def test_start_failure_after_child_creation_retains_handle_until_retry(self):
        """A parent-side start exception cannot orphan an already-live child."""
        worker = DownloadWorker("repo/id", "/cache")
        failures: list[str] = []
        cleanup_phases: list[ProcessCleanupPhase] = []
        worker.download_failed.connect(failures.append)
        worker.cleanup_state_changed.connect(
            lambda snapshot: cleanup_phases.append(snapshot.phase)
        )
        process = _AmbiguousStartProcess()
        queue = MagicMock()

        with _patch_download_process_context(process, queue):
            started_at = time.monotonic()
            worker.run()
            elapsed = time.monotonic() - started_at

        assert elapsed < 1.0
        assert failures == []
        assert process.child_alive is True
        assert worker._process is process
        assert process.close_calls == 0
        assert ProcessCleanupPhase.RECOVERY_REQUIRED in cleanup_phases

        process.allow_cleanup = True
        worker.retry_cleanup()

        assert failures == [
            "Model download could not start: "
            "parent bootstrap failed after child creation"
        ]
        assert process.joined is True
        assert process.child_alive is False
        assert worker._process is None
        assert process.close_calls == 1

    def test_check_queue_empty(self):
        worker = DownloadWorker("repo/id", "/cache")
        worker._queue = MagicMock()
        worker._queue.get_nowait.side_effect = stdlib_queue.Empty
        assert worker._check_queue() is False

    def test_check_queue_progress(self):
        worker = DownloadWorker("repo/id", "/cache")
        worker._queue = MagicMock()
        progress = MagicMock()
        worker.progress_update.connect(progress)
        items = [("progress", (50, "half"))]

        def side_effect():
            if items:
                return items.pop(0)
            raise stdlib_queue.Empty

        worker._queue.get_nowait.side_effect = side_effect
        assert worker._check_queue() is False
        progress.assert_called_once_with(50, "half")

    def test_check_queue_finished(self):
        worker = DownloadWorker("repo/id", "/cache")
        worker._queue = MagicMock()
        items = [("finished", "/path")]

        def side_effect():
            if items:
                return items.pop(0)
            raise stdlib_queue.Empty

        worker._queue.get_nowait.side_effect = side_effect
        assert worker._check_queue() is True
        assert worker._pending_terminal_kind == "finished"
        assert worker._pending_terminal_payload == "/path"

    def test_check_queue_error(self):
        worker = DownloadWorker("repo/id", "/cache")
        worker._queue = MagicMock()
        items = [("error", "boom")]

        def side_effect():
            if items:
                return items.pop(0)
            raise stdlib_queue.Empty

        worker._queue.get_nowait.side_effect = side_effect
        assert worker._check_queue() is True
        assert worker._pending_terminal_kind == "failed"
        assert worker._pending_terminal_payload == "boom"

    def test_check_queue_none(self):
        worker = DownloadWorker("repo/id", "/cache")
        worker._queue = None
        assert worker._check_queue() is False

    def test_terminate_process_alive(self):
        worker = DownloadWorker("repo/id", "/cache")
        process = MagicMock()
        process.is_alive.side_effect = [True, True, False]
        worker._process = process
        assert worker._terminate_process() is True
        process.terminate.assert_called_once()
        process.join.assert_any_call(PROCESS_TERMINATE_JOIN_TIMEOUT_SEC)
        process.join.assert_any_call(PROCESS_KILL_JOIN_TIMEOUT_SEC)
        assert worker._process is None

    def test_terminate_process_retains_ownership_when_kill_times_out(self):
        worker = DownloadWorker("repo/id", "/cache")
        process = MagicMock()
        process.is_alive.return_value = True
        worker._process = process

        assert worker._terminate_process() is False

        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        assert worker._process is process

    def test_is_alive_error_retains_process_ownership(self):
        worker = DownloadWorker("repo/id", "/cache")
        process = MagicMock()
        process.is_alive.side_effect = PermissionError("cannot inspect child")
        worker._process = process

        assert worker._terminate_process() is False

        assert worker._process is process
        process.terminate.assert_not_called()

    def test_terminate_process_not_alive(self):
        worker = DownloadWorker("repo/id", "/cache")
        process = MagicMock()
        process.is_alive.return_value = False
        worker._process = process
        worker._child_start_confirmed = True
        assert worker._terminate_process() is True
        process.terminate.assert_not_called()
        process.join.assert_called_once_with(PROCESS_JOIN_TIMEOUT_SEC)
        assert worker._process is None

    def test_close_failure_retains_reaped_handle_until_retry_terminal(self):
        """A refused close cannot manufacture terminal ownership release."""
        worker = DownloadWorker("repo/id", "/cache")
        process = MagicMock()
        process.is_alive.return_value = False
        process.close.side_effect = ValueError(
            "cannot close while child may still be alive"
        )
        worker._process = process
        worker._child_start_confirmed = True
        worker._record_pending_failure("start failed")
        failures: list[str] = []
        worker.download_failed.connect(failures.append)

        assert worker._finish_or_defer_terminal() is False
        assert failures == []
        assert worker._process is process
        assert worker.cleanup_snapshot.phase is ProcessCleanupPhase.RECOVERY_REQUIRED

        process.close.side_effect = None
        worker.retry_cleanup()

        assert failures == ["start failed"]
        assert worker._process is None

    def test_cancel_sets_flag(self):
        worker = DownloadWorker("repo/id", "/cache")
        worker.cancel()
        assert worker._is_cancelled is True

    def test_run_joins_download_process_after_finished_message(self):
        """Finished queue messages should still reap the subprocess."""
        worker = DownloadWorker("repo/id", "/cache")
        finished_paths: list[str] = []
        worker.download_finished.connect(finished_paths.append)

        mock_process = MagicMock()
        mock_process.is_alive.side_effect = [True, False, False]
        mock_queue = MagicMock()
        messages = [("finished", "/model/path")]

        def get_message():
            if messages:
                return messages.pop(0)
            raise stdlib_queue.Empty

        mock_queue.get_nowait.side_effect = get_message

        with _patch_download_process_context(mock_process, mock_queue):
            worker.run()

        assert finished_paths == ["/model/path"]
        mock_process.join.assert_called()
        mock_process.terminate.assert_not_called()

    @pytest.mark.skipif(
        not hasattr(multiprocessing, "get_context"),
        reason="spawn context is unavailable",
    )
    def test_reaps_a_real_spawn_child_without_hf_download(self):
        """Exercise Process APIs with a real spawn-compatible child."""
        context = multiprocessing.get_context("spawn")
        started = context.Event()
        process = context.Process(
            target=_spawn_wait_for_parent_cleanup,
            args=(started,),
        )
        process.start()
        assert started.wait(timeout=5.0)
        worker = DownloadWorker("repo/id", "/cache")
        worker._process = process
        worker._child_start_confirmed = True

        try:
            assert worker._terminate_process() is True
            assert worker._process is None
            assert getattr(process, "_closed", False) is True
        finally:
            try:
                alive = process.is_alive()
            except ValueError:
                alive = False
            if alive:
                process.terminate()
                process.join(timeout=2.0)
