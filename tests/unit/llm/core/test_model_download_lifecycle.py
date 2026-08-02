"""Application-owned model download and cache-cleanup lifecycle contracts."""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from XBrainLab.llm.core.downloader import (
    ModelDownloadOutcome,
    ModelDownloadStatus,
    ModelDownloadTarget,
)
from XBrainLab.llm.core.model_download_lifecycle import (
    ModelCacheCleanupReason,
    ModelCacheCleanupRequest,
    ModelCacheCleanupResult,
    ModelDownloadLifecycle,
    ModelStatusInspectionRequest,
    ModelStatusInspectionResult,
    _ModelCacheCleanupWorker,
)

PRIMARY_MODEL_ID = "ibm-granite/granite-3.3-2b-instruct"
PRIMARY_MODEL_REVISION = (
    "707f574c62054322f6b5b04b6d075f0a8f05e0f0"  # pragma: allowlist secret
)
VALID_TEST_WEIGHT_BYTES = 300_000_000


def _write_complete_model_cache(cache_dir: Path) -> Path:
    model_root = cache_dir / f"models--{PRIMARY_MODEL_ID.replace('/', '--')}"
    snapshot = model_root / "snapshots" / PRIMARY_MODEL_REVISION
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    with (snapshot / "model.safetensors").open("wb") as stream:
        stream.truncate(VALID_TEST_WEIGHT_BYTES)
    return model_root


class _FakeDownloader(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(object)
    terminal = pyqtSignal(object)
    cleanup_state_changed = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.idle = True
        self.cancel_requests = 0
        self.target: ModelDownloadTarget | None = None

    def start_download(self, repo_id: str, cache_dir: str) -> bool:
        if not self.idle:
            return False
        self.idle = False
        self.target = ModelDownloadTarget.create(repo_id, cache_dir)
        return True

    def cancel_download(self) -> None:
        self.cancel_requests += 1

    def shutdown(self) -> bool:
        self.cancel_download()
        return self.idle

    def is_idle(self) -> bool:
        return self.idle

    @property
    def active_target(self) -> ModelDownloadTarget | None:
        return self.target

    def complete(
        self,
        *,
        status: ModelDownloadStatus,
        message: str,
        model_path: str | None = None,
    ) -> ModelDownloadOutcome:
        assert self.target is not None
        outcome = ModelDownloadOutcome(
            target=self.target,
            status=status,
            message=message,
            model_path=model_path,
        )
        self.idle = True
        self.terminal.emit(outcome)
        if outcome.ok:
            self.finished.emit(outcome)
        else:
            self.failed.emit(outcome)
        return outcome


def test_cancel_timeout_retains_app_ownership_through_partial_cleanup(
    qtbot,
    tmp_path,
) -> None:
    downloader = _FakeDownloader()
    lifecycle = ModelDownloadLifecycle(downloader=downloader)
    assert lifecycle.start_download("repo/id", str(tmp_path)) is True
    assert downloader.target is not None
    partial_path = Path(downloader.target.cache_candidates[0])
    partial_path.mkdir()
    (partial_path / "partial.bin").write_bytes(b"partial")

    assert lifecycle.request_cancel() is False
    assert lifecycle.is_idle() is False
    assert downloader.cancel_requests == 1

    with qtbot.waitSignal(lifecycle.terminal, timeout=2000) as blocker:
        downloader.complete(
            status=ModelDownloadStatus.CANCELLED,
            message="Cancelled by user",
        )

    assert blocker.args[0] is False
    assert lifecycle.is_idle() is True
    assert partial_path.exists() is False


def test_success_path_forwards_one_target_aware_terminal_outcome(qtbot) -> None:
    downloader = _FakeDownloader()
    lifecycle = ModelDownloadLifecycle(downloader=downloader)
    terminal_events: list[tuple[bool, str]] = []
    finished_outcomes: list[ModelDownloadOutcome] = []
    lifecycle.terminal.connect(
        lambda ok, message: terminal_events.append((ok, message))
    )
    lifecycle.finished.connect(finished_outcomes.append)

    assert lifecycle.start_download("repo/id", "/cache") is True
    downloader.complete(
        status=ModelDownloadStatus.SUCCEEDED,
        message="/cache/model",
        model_path="/cache/model",
    )
    qtbot.waitUntil(lifecycle.is_idle, timeout=1000)

    assert terminal_events == [(True, "/cache/model")]
    assert len(finished_outcomes) == 1
    assert finished_outcomes[0].target.repo_id == "repo/id"
    assert finished_outcomes[0].model_path == "/cache/model"


def test_app_shutdown_rejects_new_downloads_after_terminal(tmp_path, qtbot) -> None:
    downloader = _FakeDownloader()
    lifecycle = ModelDownloadLifecycle(downloader=downloader)
    assert lifecycle.start_download("repo/id", str(tmp_path)) is True

    assert lifecycle.request_shutdown() is False
    with qtbot.waitSignal(lifecycle.terminal, timeout=2000):
        downloader.complete(
            status=ModelDownloadStatus.CANCELLED,
            message="Cancelled by user",
        )

    assert lifecycle.is_idle() is True
    assert lifecycle.start_download("repo/other", str(tmp_path)) is False


def test_recursive_cache_cleanup_is_background_owned_and_in_close_fence(
    qtbot,
    tmp_path,
) -> None:
    lifecycle = ModelDownloadLifecycle(downloader=_FakeDownloader())
    target = ModelDownloadTarget.create("repo/id", str(tmp_path))
    partial_path = Path(target.cache_candidates[0])
    partial_path.mkdir()
    entered_cleanup = threading.Event()
    release_cleanup = threading.Event()
    heartbeat: list[bool] = []

    def slow_rmtree(path: str) -> None:
        assert Path(path) == partial_path
        entered_cleanup.set()
        release_cleanup.wait(timeout=2.0)

    with patch(
        "XBrainLab.llm.core.model_download_lifecycle.shutil.rmtree",
        side_effect=slow_rmtree,
    ):
        started_at = time.monotonic()
        assert lifecycle.request_cache_removal(
            "repo/id",
            str(tmp_path),
            reason=ModelCacheCleanupReason.USER_DELETE,
        )
        elapsed = time.monotonic() - started_at

        assert elapsed < 0.05
        qtbot.waitUntil(entered_cleanup.is_set, timeout=1000)
        assert lifecycle.is_idle() is False
        assert lifecycle.request_shutdown() is False

        QTimer.singleShot(0, lambda: heartbeat.append(True))
        qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

        release_cleanup.set()
        qtbot.waitUntil(lifecycle.is_idle, timeout=2000)


def test_cancel_cleanup_uses_immutable_target_and_preserves_other_model(
    qtbot,
    tmp_path,
) -> None:
    downloader = _FakeDownloader()
    lifecycle = ModelDownloadLifecycle(downloader=downloader)
    assert lifecycle.start_download("vendor/model-a", str(tmp_path)) is True
    assert downloader.target is not None
    model_a_path = Path(downloader.target.cache_candidates[0])
    model_a_path.mkdir()
    (model_a_path / "partial.bin").write_bytes(b"partial")

    model_b_target = ModelDownloadTarget.create("vendor/model-b", str(tmp_path))
    model_b_path = Path(model_b_target.cache_candidates[0])
    model_b_path.mkdir()
    (model_b_path / "model.bin").write_bytes(b"installed")

    with qtbot.waitSignal(lifecycle.terminal, timeout=2000):
        downloader.complete(
            status=ModelDownloadStatus.CANCELLED,
            message="Cancelled by user",
        )

    assert model_a_path.exists() is False
    assert model_b_path.exists() is True
    assert (model_b_path / "model.bin").read_bytes() == b"installed"


def test_failed_download_cleans_only_target_before_terminal_publication(
    qtbot,
    tmp_path,
) -> None:
    downloader = _FakeDownloader()
    lifecycle = ModelDownloadLifecycle(downloader=downloader)
    terminals: list[tuple[bool, str]] = []
    cleanup_results: list[ModelCacheCleanupResult] = []
    lifecycle.terminal.connect(lambda ok, message: terminals.append((ok, message)))
    lifecycle.cache_cleanup_finished.connect(cleanup_results.append)
    assert lifecycle.start_download(PRIMARY_MODEL_ID, str(tmp_path)) is True
    assert downloader.target is not None
    target_path = Path(downloader.target.cache_candidates[0])
    target_path.mkdir()
    (target_path / "model.safetensors.incomplete").write_bytes(b"partial")
    unrelated_path = tmp_path / "models--vendor--other"
    unrelated_path.mkdir()
    (unrelated_path / "keep.bin").write_bytes(b"keep")

    entered_cleanup = threading.Event()
    release_cleanup = threading.Event()
    original_rmtree = shutil.rmtree

    def slow_rmtree(path: str) -> None:
        assert Path(path) == target_path
        entered_cleanup.set()
        release_cleanup.wait(timeout=2.0)
        original_rmtree(path)

    with patch(
        "XBrainLab.llm.core.model_download_lifecycle.shutil.rmtree",
        side_effect=slow_rmtree,
    ):
        downloader.complete(
            status=ModelDownloadStatus.FAILED,
            message="Model download failed.",
        )
        qtbot.waitUntil(entered_cleanup.is_set, timeout=1000)

        assert terminals == []
        assert lifecycle.is_idle() is False
        assert target_path.exists() is True

        release_cleanup.set()
        qtbot.waitUntil(lambda: bool(terminals), timeout=2000)

    assert terminals == [(False, "Model download failed.")]
    assert len(cleanup_results) == 1
    assert cleanup_results[0].reason is ModelCacheCleanupReason.FAILED_DOWNLOAD
    assert target_path.exists() is False
    assert (unrelated_path / "keep.bin").read_bytes() == b"keep"


@pytest.mark.parametrize(
    "status",
    [ModelDownloadStatus.FAILED, ModelDownloadStatus.CANCELLED],
)
def test_unsuccessful_download_preserves_complete_cache_present_at_admission(
    qtbot,
    tmp_path,
    status: ModelDownloadStatus,
) -> None:
    model_root = _write_complete_model_cache(tmp_path)
    downloader = _FakeDownloader()
    lifecycle = ModelDownloadLifecycle(downloader=downloader)
    cleanup_results: list[ModelCacheCleanupResult] = []
    lifecycle.cache_cleanup_finished.connect(cleanup_results.append)

    assert lifecycle.start_download(PRIMARY_MODEL_ID, str(tmp_path)) is True
    assert downloader.target is not None
    assert downloader.target.complete_cache_at_start is True

    with qtbot.waitSignal(lifecycle.terminal, timeout=1000) as blocker:
        downloader.complete(
            status=status,
            message="Model download failed.",
        )

    assert blocker.args == [False, "Model download failed."]
    assert cleanup_results == []
    assert model_root.exists() is True
    assert (
        model_root / "snapshots" / PRIMARY_MODEL_REVISION / "model.safetensors"
    ).stat().st_size == VALID_TEST_WEIGHT_BYTES


def test_cache_root_resolve_failure_emits_exactly_once_and_thread_terminates(
    qtbot,
    tmp_path,
) -> None:
    lifecycle = ModelDownloadLifecycle(downloader=_FakeDownloader())
    results: list[ModelCacheCleanupResult] = []
    terminals: list[tuple[bool, str]] = []
    lifecycle.cache_cleanup_finished.connect(results.append)
    lifecycle.terminal.connect(lambda ok, message: terminals.append((ok, message)))
    sensitive = (
        r"RuntimeError: symlink loop at \\server\private\model "
        r"C:\Users\alice\.cache token=hf_secret"
    )

    with patch.object(Path, "resolve", side_effect=RuntimeError(sensitive)):
        try:
            assert lifecycle.request_cache_removal(
                "repo/id",
                str(tmp_path),
                reason=ModelCacheCleanupReason.USER_DELETE,
            )
            qtbot.waitUntil(lambda: bool(terminals), timeout=2000)
        finally:
            thread = lifecycle._cleanup_thread
            if thread is not None:
                thread.quit()
                qtbot.waitUntil(lambda: not thread.isRunning(), timeout=2000)

    assert len(results) == 1
    assert results[0].ok is False
    assert results[0].diagnostic_errors
    assert sensitive in results[0].diagnostic_errors[0]
    assert sensitive not in results[0].public_message
    assert terminals == [(False, results[0].public_message)]
    assert lifecycle.is_idle() is True


def test_cleanup_worker_preloop_failure_emits_one_result() -> None:
    target = ModelDownloadTarget.create("repo/id", "/cache")
    request = ModelCacheCleanupRequest(
        target=target,
        reason=ModelCacheCleanupReason.USER_DELETE,
    )
    worker = _ModelCacheCleanupWorker(request)
    results: list[ModelCacheCleanupResult] = []
    worker.completed.connect(results.append)

    with patch.object(Path, "resolve", side_effect=RuntimeError("symlink loop")):
        worker.run()

    assert len(results) == 1
    assert results[0].ok is False


def test_cleanup_thread_start_failure_is_terminal_and_releases_qobjects(
    qtbot,
    tmp_path,
) -> None:
    created_threads: list[QThread] = []
    created_workers: list[_ModelCacheCleanupWorker] = []

    class _FailingThread(QThread):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            created_threads.append(self)

        def start(self, priority=QThread.Priority.InheritPriority) -> None:
            del priority
            raise RuntimeError("fault injection: QThread.start failed")

    original_worker = _ModelCacheCleanupWorker

    def capture_worker(request):
        worker = original_worker(request)
        created_workers.append(worker)
        return worker

    lifecycle = ModelDownloadLifecycle(downloader=_FakeDownloader())
    terminals: list[tuple[bool, str]] = []
    lifecycle.terminal.connect(lambda ok, message: terminals.append((ok, message)))

    with (
        patch(
            "XBrainLab.llm.core.model_download_lifecycle.QThread",
            _FailingThread,
        ),
        patch(
            "XBrainLab.llm.core.model_download_lifecycle._ModelCacheCleanupWorker",
            side_effect=capture_worker,
        ),
    ):
        started = lifecycle.request_cache_removal(
            "repo/id",
            str(tmp_path),
            reason=ModelCacheCleanupReason.USER_DELETE,
        )

    assert started is False
    assert terminals == [
        (
            False,
            "Model cleanup could not start. Check the application log and try again.",
        )
    ]
    assert lifecycle.is_idle() is True
    assert lifecycle.active_target is None
    assert lifecycle._cleanup_thread is None
    assert lifecycle._cleanup_worker is None
    assert len(created_threads) == 1
    assert len(created_workers) == 1
    assert sip.isdeleted(created_workers[0])
    assert sip.isdeleted(created_threads[0])
    qtbot.wait(0)


def test_download_thread_start_failure_releases_worker_and_is_terminal(
    qtbot,
    tmp_path,
) -> None:
    created_threads: list[QThread] = []
    created_workers: list[QObject] = []

    class _FailingThread(QThread):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            created_threads.append(self)

        def start(self, priority=QThread.Priority.InheritPriority) -> None:
            del priority
            raise RuntimeError("fault injection: download QThread.start failed")

    from XBrainLab.llm.core.downloader import DownloadWorker

    def capture_worker(*args, **kwargs):
        worker = DownloadWorker(*args, **kwargs)
        created_workers.append(worker)
        return worker

    lifecycle = ModelDownloadLifecycle()
    terminals: list[tuple[bool, str]] = []
    lifecycle.terminal.connect(lambda ok, message: terminals.append((ok, message)))

    with (
        patch("XBrainLab.llm.core.downloader.QThread", _FailingThread),
        patch(
            "XBrainLab.llm.core.downloader.DownloadWorker",
            side_effect=capture_worker,
        ),
    ):
        started = lifecycle.start_download("repo/id", str(tmp_path))

    assert started is False
    assert lifecycle.is_idle() is True
    assert lifecycle.active_target is None
    assert len(terminals) == 1
    assert terminals[0][0] is False
    assert len(created_threads) == 1
    assert len(created_workers) == 1
    assert sip.isdeleted(created_workers[0])
    assert sip.isdeleted(created_threads[0])
    qtbot.wait(0)


def test_cleanup_unlinks_broken_cache_symlink_without_following_target(
    tmp_path,
) -> None:
    target = ModelDownloadTarget.create("repo/id", str(tmp_path))
    cache_link = Path(target.cache_candidates[0])
    outside_target = tmp_path.parent / "missing-external-model-cache"
    cache_link.symlink_to(outside_target, target_is_directory=True)
    request = ModelCacheCleanupRequest(
        target=target,
        reason=ModelCacheCleanupReason.USER_DELETE,
    )
    worker = _ModelCacheCleanupWorker(request)
    results: list[ModelCacheCleanupResult] = []
    worker.completed.connect(results.append)

    worker.run()

    assert len(results) == 1
    assert results[0].ok is True
    assert results[0].removed_paths == (str(cache_link),)
    assert cache_link.is_symlink() is False
    assert outside_target.exists() is False


def test_model_status_inspection_runs_outside_gui_thread(
    qtbot,
    tmp_path,
) -> None:
    lifecycle = ModelDownloadLifecycle(downloader=_FakeDownloader())
    request = ModelStatusInspectionRequest(
        request_id=7,
        model_name="microsoft/Phi-4-mini-instruct",
        cache_dir=str(tmp_path),
        device="cpu",
        load_in_4bit=False,
    )
    entered = threading.Event()
    release = threading.Event()
    heartbeat: list[bool] = []
    result = ModelStatusInspectionResult.unavailable(
        request,
        "Model status could not be checked.",
    )

    def inspect(_request):
        entered.set()
        release.wait(timeout=2.0)
        return result

    outcomes: list[ModelStatusInspectionResult] = []
    lifecycle.inspection_finished.connect(outcomes.append)

    with patch(
        "XBrainLab.llm.core.model_download_lifecycle.inspect_model_status",
        side_effect=inspect,
    ):
        started_at = time.monotonic()
        assert lifecycle.request_model_inspection(request) is True
        elapsed = time.monotonic() - started_at
        assert elapsed < 0.05
        qtbot.waitUntil(entered.is_set, timeout=1000)
        assert lifecycle._inspection_thread is not None
        inspection_thread_name = lifecycle._inspection_thread.objectName()

        QTimer.singleShot(0, lambda: heartbeat.append(True))
        qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)
        release.set()
        qtbot.waitUntil(lambda: bool(outcomes), timeout=2000)

    assert outcomes == [result]
    assert inspection_thread_name == "ModelStatusProbe"
    assert lifecycle.is_idle() is True


def test_model_status_thread_start_failure_releases_qobjects_and_reports_once(
    tmp_path,
) -> None:
    created_threads: list[QThread] = []
    created_workers: list[QObject] = []

    class _FailingThread(QThread):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            created_threads.append(self)

        def start(self, priority=QThread.Priority.InheritPriority) -> None:
            del priority
            raise RuntimeError("fault injection: inspection QThread.start failed")

    from XBrainLab.llm.core.model_download_lifecycle import (
        _ModelStatusInspectionWorker,
    )

    def capture_worker(request):
        worker = _ModelStatusInspectionWorker(request)
        created_workers.append(worker)
        return worker

    lifecycle = ModelDownloadLifecycle(downloader=_FakeDownloader())
    request = ModelStatusInspectionRequest(
        request_id=11,
        model_name="microsoft/Phi-4-mini-instruct",
        cache_dir=str(tmp_path),
        device="cpu",
        load_in_4bit=False,
    )
    outcomes: list[ModelStatusInspectionResult] = []
    lifecycle.inspection_finished.connect(outcomes.append)

    with (
        patch(
            "XBrainLab.llm.core.model_download_lifecycle.QThread",
            _FailingThread,
        ),
        patch(
            "XBrainLab.llm.core.model_download_lifecycle._ModelStatusInspectionWorker",
            side_effect=capture_worker,
        ),
    ):
        started = lifecycle.request_model_inspection(request)

    assert started is False
    assert lifecycle.is_idle() is True
    assert len(outcomes) == 1
    assert outcomes[0].request == request
    assert outcomes[0].runtime_ready is False
    assert outcomes[0].diagnostic_message
    assert len(created_threads) == 1
    assert len(created_workers) == 1
    assert sip.isdeleted(created_workers[0])
    assert sip.isdeleted(created_threads[0])
