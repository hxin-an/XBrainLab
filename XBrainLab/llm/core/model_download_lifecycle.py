"""Application-owned lifecycle for model downloads and cache cleanup."""

from __future__ import annotations

import contextlib
import shutil
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.downloader import (
    ModelDownloader,
    ModelDownloadOutcome,
    ModelDownloadStatus,
    ModelDownloadTarget,
)
from XBrainLab.llm.core.model_catalog import model_snapshot_path, plan_model_download

MODEL_STATUS_PROBE_THREAD_NAME = "ModelStatusProbe"


class _Downloader(Protocol):
    @property
    def progress(self) -> Any: ...

    @property
    def terminal(self) -> Any: ...

    @property
    def cleanup_state_changed(self) -> Any: ...

    @property
    def active_target(self) -> ModelDownloadTarget | None: ...

    def start_download(self, repo_id: str, cache_dir: str) -> bool: ...

    def cancel_download(self) -> None: ...

    def shutdown(self) -> bool: ...

    def is_idle(self) -> bool: ...


class ModelCacheCleanupReason(str, Enum):
    """Why one model cache target is being removed."""

    USER_DELETE = "user_delete"


@dataclass(frozen=True)
class ModelCacheCleanupRequest:
    """Immutable cache cleanup request."""

    target: ModelDownloadTarget
    reason: ModelCacheCleanupReason


@dataclass(frozen=True)
class ModelCacheCleanupResult:
    """Terminal result of one app-owned recursive cache cleanup."""

    request: ModelCacheCleanupRequest
    removed_paths: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def target(self) -> ModelDownloadTarget:
        return self.request.target

    @property
    def reason(self) -> ModelCacheCleanupReason:
        return self.request.reason

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def diagnostic_errors(self) -> tuple[str, ...]:
        """Return technical details that must remain out of user dialogs."""
        return self.errors

    @property
    def public_message(self) -> str:
        """Return stable recovery guidance without paths or raw exceptions."""
        if self.errors:
            return (
                "Model files could not be removed. Close other programs that may "
                "be using the model, then try again."
            )
        if self.removed_paths:
            return "Model files were removed."
        return "No model files needed removal."

    @property
    def message(self) -> str:
        """Compatibility alias for the safe public message."""
        return self.public_message


@dataclass(frozen=True)
class ModelStatusInspectionRequest:
    """Immutable inputs for one background model-cache/runtime inspection."""

    request_id: int
    model_name: str
    cache_dir: str
    device: str
    load_in_4bit: bool
    load_persisted_config: bool = False


@dataclass(frozen=True)
class ModelStatusInspectionResult:
    """One coherent model status snapshot produced outside the GUI thread."""

    request: ModelStatusInspectionRequest
    installed: bool
    runtime_ready: bool
    runtime_message: str
    estimated_download_bytes: int
    current_cache_bytes: int
    projected_cache_bytes: int
    available_disk_bytes: int
    preflight_ok: bool
    preflight_message: str
    cleanup_candidates: tuple[str, ...] = ()
    diagnostic_message: str = ""
    resolved_config: LLMConfig | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    @classmethod
    def unavailable(
        cls,
        request: ModelStatusInspectionRequest,
        message: str,
        *,
        diagnostic_message: str = "",
    ) -> ModelStatusInspectionResult:
        """Build a fail-closed result with product-safe visible language."""
        return cls(
            request=request,
            installed=False,
            runtime_ready=False,
            runtime_message=message,
            estimated_download_bytes=0,
            current_cache_bytes=0,
            projected_cache_bytes=0,
            available_disk_bytes=0,
            preflight_ok=False,
            preflight_message=message,
            diagnostic_message=diagnostic_message,
        )


def inspect_model_status(
    request: ModelStatusInspectionRequest,
) -> ModelStatusInspectionResult:
    """Inspect cache and runtime readiness without touching the GUI thread."""
    try:
        if request.load_persisted_config:
            config = LLMConfig.load_from_file() or LLMConfig(device="cpu")
            effective_request = replace(
                request,
                model_name=config.model_name,
                cache_dir=config.cache_dir,
                device=str(config.device),
                load_in_4bit=bool(config.load_in_4bit),
                load_persisted_config=False,
            )
        else:
            config = LLMConfig(
                model_name=request.model_name,
                cache_dir=request.cache_dir,
                device=request.device,
                load_in_4bit=request.load_in_4bit,
            )
            effective_request = request
        preflight = plan_model_download(
            effective_request.model_name,
            effective_request.cache_dir,
        )
        installed = config.has_local_model_cache(effective_request.model_name)
        runtime_ready = config.local_backend_ready(
            model_name=effective_request.model_name
        )
        runtime_message = config.local_backend_status_message(
            model_name=effective_request.model_name
        )
    except Exception as exc:
        diagnostic = f"{type(exc).__name__}: {exc}"
        logger.error(
            "Local model status inspection failed for %s: %s",
            request.model_name,
            diagnostic,
        )
        return ModelStatusInspectionResult.unavailable(
            request,
            "Model status could not be checked. Try again.",
            diagnostic_message=diagnostic,
        )

    return ModelStatusInspectionResult(
        request=effective_request,
        installed=installed,
        runtime_ready=runtime_ready,
        runtime_message=runtime_message,
        estimated_download_bytes=preflight.estimated_download_bytes,
        current_cache_bytes=preflight.current_cache_bytes,
        projected_cache_bytes=preflight.projected_cache_bytes,
        available_disk_bytes=preflight.available_disk_bytes,
        preflight_ok=preflight.ok,
        preflight_message=preflight.message,
        cleanup_candidates=preflight.cleanup_candidates,
        resolved_config=config,
    )


def _delete_unstarted_qobject(obj: QObject | None) -> None:
    """Synchronously destroy a QObject whose target thread never started."""
    if obj is None:
        return
    with contextlib.suppress(RuntimeError):
        if not sip.isdeleted(obj):
            sip.delete(obj)


class _ApplicationOwnedModelDownloader(ModelDownloader):
    """Harden the base downloader's never-started QThread cleanup."""

    def _publish_thread_start_failure(
        self,
        *,
        target: ModelDownloadTarget,
        thread: QThread,
        worker: Any,
        exc: Exception,
    ) -> None:
        super()._publish_thread_start_failure(
            target=target,
            thread=thread,
            worker=worker,
            exc=exc,
        )
        _delete_unstarted_qobject(worker)
        _delete_unstarted_qobject(thread)


class _ModelCacheCleanupWorker(QObject):
    """Run recursive deletion outside the GUI thread."""

    completed = pyqtSignal(object)

    def __init__(self, request: ModelCacheCleanupRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        removed: list[str] = []
        errors: list[str] = []
        try:
            cache_root = Path(self.request.target.cache_dir).resolve(strict=False)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        else:
            for raw_path in self.request.target.cache_candidates:
                candidate = Path(raw_path)
                try:
                    candidate_parent = candidate.parent.resolve(strict=False)
                    if candidate_parent != cache_root:
                        errors.append(
                            f"Refused cache path outside target root: {candidate}"
                        )
                        continue
                    try:
                        candidate.lstat()
                    except FileNotFoundError:
                        continue
                    if candidate.is_symlink():
                        candidate.unlink()
                    else:
                        resolved = candidate.resolve(strict=False)
                        if resolved.parent != cache_root:
                            errors.append(
                                f"Refused cache path outside target root: {candidate}"
                            )
                            continue
                        shutil.rmtree(str(candidate))
                    removed.append(str(candidate))
                except Exception as exc:
                    errors.append(f"{candidate}: {type(exc).__name__}: {exc}")

        result = ModelCacheCleanupResult(
            request=self.request,
            removed_paths=tuple(removed),
            errors=tuple(errors),
        )
        if result.errors:
            logger.error(
                "Model cache cleanup failed for %s: %s",
                result.target.repo_id,
                "; ".join(result.errors),
            )
        self.completed.emit(result)


class _ModelStatusInspectionWorker(QObject):
    """Collect one model status snapshot outside the GUI thread."""

    completed = pyqtSignal(object)

    def __init__(self, request: ModelStatusInspectionRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        self.completed.emit(inspect_model_status(self.request))


class ModelDownloadLifecycleContract(Protocol):
    """UI-facing contract for an application-owned download lifecycle."""

    @property
    def progress(self) -> Any: ...

    @property
    def finished(self) -> Any: ...

    @property
    def failed(self) -> Any: ...

    @property
    def terminal(self) -> Any: ...

    @property
    def cache_cleanup_finished(self) -> Any: ...

    @property
    def inspection_finished(self) -> Any: ...

    @property
    def active_target(self) -> ModelDownloadTarget | None: ...

    def start_download(self, repo_id: str, cache_dir: str) -> bool: ...

    def ensure_download(self, repo_id: str, cache_dir: str) -> bool: ...

    def request_cancel(self) -> bool: ...

    def request_shutdown(self) -> bool: ...

    def request_cache_removal(
        self,
        repo_id: str,
        cache_dir: str,
        *,
        reason: ModelCacheCleanupReason,
    ) -> bool: ...

    def request_model_inspection(
        self,
        request: ModelStatusInspectionRequest,
    ) -> bool: ...

    def is_idle(self) -> bool: ...


class ModelDownloadLifecycle(QObject):
    """Retain download and recursive-cleanup ownership at application scope."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(object)
    terminal = pyqtSignal(bool, str)
    cleanup_state_changed = pyqtSignal(object)
    cache_cleanup_finished = pyqtSignal(object)
    inspection_finished = pyqtSignal(object)

    def __init__(
        self,
        *,
        downloader: _Downloader | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._downloader = downloader or _ApplicationOwnedModelDownloader(self)
        self._shutdown_requested = False
        self._active_target: ModelDownloadTarget | None = None
        self._cleanup_thread: QThread | None = None
        self._cleanup_worker: _ModelCacheCleanupWorker | None = None
        self._pending_cleanup_request: ModelCacheCleanupRequest | None = None
        self._pending_cleanup_result: ModelCacheCleanupResult | None = None
        self._inspection_thread: QThread | None = None
        self._inspection_worker: _ModelStatusInspectionWorker | None = None
        self._pending_inspection_request: ModelStatusInspectionRequest | None = None
        self._pending_inspection_result: ModelStatusInspectionResult | None = None
        self._queued_inspection_request: ModelStatusInspectionRequest | None = None
        self._downloader.progress.connect(self.progress.emit)
        self._downloader.terminal.connect(self._on_download_terminal)
        self._downloader.cleanup_state_changed.connect(self.cleanup_state_changed.emit)

    @property
    def active_target(self) -> ModelDownloadTarget | None:
        """Return immutable identity for the currently owned operation."""
        return self._active_target

    def start_download(self, repo_id: str, cache_dir: str) -> bool:
        """Start one download unless cleanup or application shutdown is active."""
        if self._shutdown_requested or not self.is_idle():
            return False
        started = bool(self._downloader.start_download(repo_id, cache_dir))
        if started:
            self._active_target = self._downloader.active_target or (
                ModelDownloadTarget.create(repo_id, cache_dir)
            )
        return started

    def ensure_download(self, repo_id: str, cache_dir: str) -> bool:
        """Reuse a complete pinned snapshot or start the owned download path."""
        if self._shutdown_requested or not self.is_idle():
            return False
        target = ModelDownloadTarget.create(repo_id, cache_dir)
        if not target.complete_cache_at_start:
            return self.start_download(repo_id, cache_dir)
        snapshot = model_snapshot_path(cache_dir, repo_id)
        if snapshot is None:
            return False
        self._active_target = target
        self._publish_download_outcome(
            ModelDownloadOutcome(
                target=target,
                status=ModelDownloadStatus.SUCCEEDED,
                message="Model is already downloaded.",
                model_path=str(snapshot),
            )
        )
        return True

    def request_cancel(self) -> bool:
        """Request cancellation while retaining download and cleanup ownership."""
        self._downloader.cancel_download()
        return self.is_idle()

    def request_shutdown(self) -> bool:
        """Fence new work and request non-blocking terminal cleanup."""
        self._shutdown_requested = True
        self._queued_inspection_request = None
        self._downloader.shutdown()
        return self.is_idle()

    def request_cache_removal(
        self,
        repo_id: str,
        cache_dir: str,
        *,
        reason: ModelCacheCleanupReason,
    ) -> bool:
        """Start app-owned recursive cleanup for one immutable model target."""
        if self._shutdown_requested or not self.is_idle():
            return False
        request = ModelCacheCleanupRequest(
            target=ModelDownloadTarget.create(repo_id, cache_dir),
            reason=reason,
        )
        self._active_target = request.target
        return self._start_cache_cleanup(request)

    def request_model_inspection(
        self,
        request: ModelStatusInspectionRequest,
    ) -> bool:
        """Run or coalesce one background cache/runtime status inspection."""
        if self._shutdown_requested:
            return False
        if self._inspection_thread is not None:
            self._queued_inspection_request = request
            return True
        return self._start_model_inspection(request)

    def is_idle(self) -> bool:
        """Return true only after all download/cache inspection work is terminal."""
        return (
            self._downloader.is_idle()
            and self._cleanup_thread is None
            and self._inspection_thread is None
        )

    def _on_download_terminal(self, outcome: object) -> None:
        if not isinstance(outcome, ModelDownloadOutcome):
            return
        self._active_target = outcome.target
        self._publish_download_outcome(outcome)

    def _start_cache_cleanup(self, request: ModelCacheCleanupRequest) -> bool:
        if self._cleanup_thread is not None:
            return False
        self._pending_cleanup_request = request
        self._pending_cleanup_result = None
        thread = QThread(self)
        worker = _ModelCacheCleanupWorker(request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._record_cleanup_result)
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._on_cleanup_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._cleanup_thread = thread
        self._cleanup_worker = worker
        try:
            thread.start()
        except Exception as exc:
            self._publish_cleanup_start_failure(
                request=request,
                thread=thread,
                worker=worker,
                exc=exc,
            )
            return False
        return True

    def _publish_cleanup_start_failure(
        self,
        *,
        request: ModelCacheCleanupRequest,
        thread: QThread,
        worker: _ModelCacheCleanupWorker,
        exc: Exception,
    ) -> None:
        """Release never-started cleanup ownership and publish one terminal."""
        diagnostic = (
            f"Cache cleanup QThread could not start: {type(exc).__name__}: {exc}"
        )
        logger.error(
            "Model cache cleanup thread start failed for %s: %s",
            request.target.repo_id,
            diagnostic,
        )
        self._cleanup_thread = None
        self._cleanup_worker = None
        self._pending_cleanup_request = None
        self._pending_cleanup_result = None
        self._active_target = None
        _delete_unstarted_qobject(worker)
        _delete_unstarted_qobject(thread)

        self.terminal.emit(
            False,
            "Model cleanup could not start. Check the application log and try again.",
        )

    def _record_cleanup_result(self, result: object) -> None:
        if isinstance(result, ModelCacheCleanupResult):
            self._pending_cleanup_result = result

    def _on_cleanup_thread_finished(self) -> None:
        request = self._pending_cleanup_request
        result = self._pending_cleanup_result
        self._cleanup_thread = None
        self._cleanup_worker = None
        self._pending_cleanup_request = None
        self._pending_cleanup_result = None
        if result is None and request is not None:
            result = ModelCacheCleanupResult(
                request=request,
                errors=("Cache cleanup worker stopped without a result.",),
            )
        if result is None:
            self._active_target = None
            self.terminal.emit(
                False,
                "Model cleanup stopped unexpectedly. Try removing the model again.",
            )
            return

        self.cache_cleanup_finished.emit(result)
        self._active_target = None
        self.terminal.emit(result.ok, result.public_message)

    def _start_model_inspection(
        self,
        request: ModelStatusInspectionRequest,
    ) -> bool:
        self._pending_inspection_request = request
        self._pending_inspection_result = None
        thread = QThread(self)
        thread.setObjectName(MODEL_STATUS_PROBE_THREAD_NAME)
        worker = _ModelStatusInspectionWorker(request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._record_inspection_result)
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._on_inspection_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._inspection_thread = thread
        self._inspection_worker = worker
        try:
            thread.start()
        except Exception as exc:
            diagnostic = (
                f"Model inspection QThread could not start: {type(exc).__name__}: {exc}"
            )
            logger.error(
                "Model status inspection thread start failed for %s: %s",
                request.model_name,
                diagnostic,
            )
            self._inspection_thread = None
            self._inspection_worker = None
            self._pending_inspection_request = None
            self._pending_inspection_result = None
            _delete_unstarted_qobject(worker)
            _delete_unstarted_qobject(thread)
            self.inspection_finished.emit(
                ModelStatusInspectionResult.unavailable(
                    request,
                    "Model status could not be checked. Try again.",
                    diagnostic_message=diagnostic,
                )
            )
            return False
        return True

    def _record_inspection_result(self, result: object) -> None:
        if isinstance(result, ModelStatusInspectionResult):
            self._pending_inspection_result = result

    def _on_inspection_thread_finished(self) -> None:
        request = self._pending_inspection_request
        result = self._pending_inspection_result
        self._inspection_thread = None
        self._inspection_worker = None
        self._pending_inspection_request = None
        self._pending_inspection_result = None
        if result is None and request is not None:
            result = ModelStatusInspectionResult.unavailable(
                request,
                "Model status could not be checked. Try again.",
                diagnostic_message="Model status worker stopped without a result.",
            )
        if result is not None:
            self.inspection_finished.emit(result)

        queued = self._queued_inspection_request
        self._queued_inspection_request = None
        if queued is not None and not self._shutdown_requested:
            self._start_model_inspection(queued)

    def _publish_download_outcome(self, outcome: ModelDownloadOutcome) -> None:
        self._active_target = None
        if outcome.ok:
            self.finished.emit(outcome)
        else:
            self.failed.emit(outcome)
        self.terminal.emit(outcome.ok, outcome.message)
