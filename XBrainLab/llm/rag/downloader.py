"""Consent- and quota-gated downloader for the pinned RAG embedder."""

from __future__ import annotations

import contextlib
import math
import multiprocessing
import os
import queue
import shutil
import stat
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import portalocker

from XBrainLab.llm.core.model_catalog import (
    BYTES_PER_GB,
    MAX_SINGLE_MODEL_DOWNLOAD_GB,
    MAX_TOTAL_MODEL_CACHE_GB,
    MIN_DISK_FREE_AFTER_DOWNLOAD_GB,
    CacheInspectionError,
    CacheScanCancellation,
    available_disk_bytes,
    cache_usage_bytes,
    format_bytes,
)

from .config import RAGConfig

try:
    from huggingface_hub import snapshot_download
except ImportError:
    snapshot_download = None  # type: ignore[assignment]


_ATTEMPT_PREFIX = ".xbrainlab-rag-download-"
_DOWNLOAD_PROCESS_START_METHOD = "spawn"
_DOWNLOAD_POLL_INTERVAL_SEC = 0.25
_DEFAULT_DOWNLOAD_TIMEOUT_SEC = 900.0
_PROCESS_JOIN_TIMEOUT_SEC = 2.0
_PROCESS_TERMINATE_TIMEOUT_SEC = 2.0
_PROCESS_KILL_TIMEOUT_SEC = 1.0
_PUBLISH_LOCK_NAME = ".xbrainlab-rag-publish.lock"
_PUBLISH_LOCK_POLL_INTERVAL_SEC = 0.05


@dataclass(frozen=True)
class RAGEmbeddingDownloadPlan:
    """Pre-network resource admission for the pinned embedding snapshot."""

    ok: bool
    message: str
    cache_dir: str
    estimated_download_bytes: int
    current_cache_bytes: int
    projected_cache_bytes: int
    max_single_model_bytes: int
    max_total_cache_bytes: int
    minimum_free_after_download_bytes: int
    available_disk_bytes: int


@dataclass(frozen=True)
class RAGEmbeddingDownloadResult:
    """Terminal result for one explicit embedding download request."""

    ok: bool
    message: str
    snapshot_path: str | None = None
    downloaded: bool = False


@dataclass(frozen=True)
class _RAGDownloadConsumption:
    """Actual resource use observed while one isolated attempt is active."""

    ok: bool
    public_message: str
    attempt_bytes: int
    total_cache_bytes: int
    available_disk_bytes: int


@dataclass(frozen=True)
class _RAGAttemptDownloadResult:
    """Internal terminal state from the bounded download child."""

    ok: bool
    public_message: str
    returned_snapshot_path: str | None = None
    attempt_cleanup_safe: bool = True


@dataclass(frozen=True)
class _RAGPublishResult:
    """Published target plus an optional target-specific rollback directory."""

    ok: bool
    public_message: str
    snapshot_path: Path | None = None
    target_root: Path | None = None
    backup_root: Path | None = None
    target_identity: tuple[int, int, int] | None = None


class _RAGOperationStoppedError(RuntimeError):
    """Internal control flow for bounded publication admission."""

    def __init__(self, public_message: str) -> None:
        super().__init__(public_message)
        self.public_message = public_message


def plan_rag_embedding_download(
    cache_dir: str | Path | None = None,
    *,
    deadline: float | None = None,
    cancel_event: CacheScanCancellation | None = None,
) -> RAGEmbeddingDownloadPlan:
    """Apply the local-model cache limits before any embedding download."""
    root = Path(cache_dir or RAGConfig.get_embedding_cache_path()).expanduser()
    normalized_cache = str(root.resolve(strict=False))
    estimated = int(RAGConfig.EMBEDDING_ESTIMATED_DOWNLOAD_GB * BYTES_PER_GB)
    max_single = int(MAX_SINGLE_MODEL_DOWNLOAD_GB * BYTES_PER_GB)
    max_total = int(MAX_TOTAL_MODEL_CACHE_GB * BYTES_PER_GB)
    minimum_free = int(MIN_DISK_FREE_AFTER_DOWNLOAD_GB * BYTES_PER_GB)
    free = available_disk_bytes(normalized_cache)
    try:
        current = cache_usage_bytes(
            normalized_cache,
            deadline=deadline,
            cancel_event=cancel_event,
        )
        target = cache_usage_bytes(
            str(RAGConfig.embedding_snapshot_path(normalized_cache).parent.parent),
            deadline=deadline,
            cancel_event=cancel_event,
        )
    except CacheInspectionError:
        return _plan(
            ok=False,
            message=(
                "RAG embedding cache usage could not be verified. Check cache "
                "permissions and try again."
            ),
            cache_dir=normalized_cache,
            estimated=estimated,
            current=0,
            projected=0,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )

    ready = RAGConfig.embedding_cache_ready(normalized_cache)
    required_download = 0 if ready else estimated
    projected = current + required_download

    if target > max_single:
        return _plan(
            ok=False,
            message=(
                "The pinned RAG embedding cache is already above the "
                f"{MAX_SINGLE_MODEL_DOWNLOAD_GB:.2f} GB per-artifact limit."
            ),
            cache_dir=normalized_cache,
            estimated=required_download,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if current > max_total:
        return _plan(
            ok=False,
            message=(
                "The RAG embedding cache is already above the "
                f"{MAX_TOTAL_MODEL_CACHE_GB:.2f} GB total cache limit."
            ),
            cache_dir=normalized_cache,
            estimated=required_download,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if ready:
        return _plan(
            ok=True,
            message="The pinned RAG embedding is already cached.",
            cache_dir=normalized_cache,
            estimated=0,
            current=current,
            projected=current,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if free <= 0:
        return _plan(
            ok=False,
            message=(
                "Available disk space could not be verified. Check that the RAG "
                "cache drive is available and try again."
            ),
            cache_dir=normalized_cache,
            estimated=estimated,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if estimated > max_single:
        return _plan(
            ok=False,
            message="The RAG embedding exceeds the per-artifact cache limit.",
            cache_dir=normalized_cache,
            estimated=estimated,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if projected > max_total:
        return _plan(
            ok=False,
            message=(
                f"The RAG embedding would raise cache usage to "
                f"{format_bytes(projected)}, above the total cache limit."
            ),
            cache_dir=normalized_cache,
            estimated=estimated,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    if estimated + minimum_free > free:
        return _plan(
            ok=False,
            message=(
                "The RAG embedding download would not preserve the required "
                f"{MIN_DISK_FREE_AFTER_DOWNLOAD_GB:.2f} GB free-disk reserve."
            ),
            cache_dir=normalized_cache,
            estimated=estimated,
            current=current,
            projected=projected,
            max_single=max_single,
            max_total=max_total,
            minimum_free=minimum_free,
            free=free,
        )
    return _plan(
        ok=True,
        message=(
            "RAG embedding download allowed after explicit consent: estimated "
            f"{format_bytes(estimated)}."
        ),
        cache_dir=normalized_cache,
        estimated=estimated,
        current=current,
        projected=projected,
        max_single=max_single,
        max_total=max_total,
        minimum_free=minimum_free,
        free=free,
    )


def download_rag_embedding(
    *,
    user_consent: bool,
    cache_dir: str | Path | None = None,
    timeout_seconds: float = _DEFAULT_DOWNLOAD_TIMEOUT_SEC,
    cancel_event: CacheScanCancellation | None = None,
) -> RAGEmbeddingDownloadResult:
    """Download the exact embedding only after explicit user admission."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        return RAGEmbeddingDownloadResult(
            False,
            "The RAG embedding download deadline must be positive and finite.",
        )
    deadline = time.monotonic() + timeout_seconds
    stopped_message = _operation_stopped_message(deadline, cancel_event)
    if stopped_message:
        return RAGEmbeddingDownloadResult(False, stopped_message)

    plan = plan_rag_embedding_download(
        cache_dir,
        deadline=deadline,
        cancel_event=cancel_event,
    )
    stopped_message = _operation_stopped_message(deadline, cancel_event)
    if stopped_message:
        return RAGEmbeddingDownloadResult(False, stopped_message)
    if not plan.ok:
        return RAGEmbeddingDownloadResult(False, plan.message)
    if plan.estimated_download_bytes == 0:
        return RAGEmbeddingDownloadResult(
            True,
            "The pinned RAG embedding is already cached.",
            snapshot_path=str(RAGConfig.embedding_snapshot_path(plan.cache_dir)),
        )
    if not user_consent:
        return RAGEmbeddingDownloadResult(
            False,
            "Explicit user consent is required before downloading the RAG embedding.",
        )
    if snapshot_download is None:
        return RAGEmbeddingDownloadResult(
            False,
            "The Hugging Face download dependency is unavailable.",
        )

    try:
        cache_root = Path(plan.cache_dir)
        cache_root.mkdir(parents=True, exist_ok=True)
        attempt_root = Path(
            tempfile.mkdtemp(
                prefix=_ATTEMPT_PREFIX,
                dir=cache_root,
            )
        )
    except OSError:
        return RAGEmbeddingDownloadResult(
            False,
            "The RAG embedding download workspace could not be created.",
        )

    attempt_cleanup_safe = True
    try:
        attempt = _run_bounded_snapshot_download(
            plan,
            attempt_root,
            deadline=deadline,
            cancel_event=cancel_event,
        )
        attempt_cleanup_safe = attempt.attempt_cleanup_safe
        if not attempt.ok:
            return RAGEmbeddingDownloadResult(False, attempt.public_message)

        try:
            with _publication_lock(
                Path(plan.cache_dir),
                deadline=deadline,
                cancel_event=cancel_event,
            ):
                stopped_message = _operation_stopped_message(deadline, cancel_event)
                if stopped_message:
                    return RAGEmbeddingDownloadResult(False, stopped_message)

                published = _publish_downloaded_embedding(
                    plan,
                    attempt_root,
                    attempt.returned_snapshot_path,
                )
                if not published.ok:
                    return RAGEmbeddingDownloadResult(False, published.public_message)
                if published.target_root is None or published.snapshot_path is None:
                    _rollback_published_embedding(published)
                    return RAGEmbeddingDownloadResult(
                        False,
                        "The downloaded RAG embedding could not be safely published.",
                    )

                consumption = _inspect_rag_download_consumption(
                    plan,
                    published.target_root,
                    deadline=deadline,
                    cancel_event=cancel_event,
                )
                if not consumption.ok:
                    stopped_message = _operation_stopped_message(
                        deadline,
                        cancel_event,
                    )
                    _rollback_published_embedding(published)
                    return RAGEmbeddingDownloadResult(
                        False,
                        stopped_message or consumption.public_message,
                    )

                stopped_message = _operation_stopped_message(deadline, cancel_event)
                if stopped_message:
                    _rollback_published_embedding(published)
                    return RAGEmbeddingDownloadResult(False, stopped_message)

                expected = published.snapshot_path
        except _RAGOperationStoppedError as exc:
            return RAGEmbeddingDownloadResult(False, exc.public_message)

        return RAGEmbeddingDownloadResult(
            True,
            "RAG embedding downloaded and verified.",
            snapshot_path=str(expected),
            downloaded=True,
        )
    finally:
        if attempt_cleanup_safe:
            _cleanup_attempt_root(cache_root, attempt_root)


def _run_snapshot_download_task(attempt_cache_dir: str, result_queue) -> None:
    """Download the pinned snapshot in a child-owned isolated cache."""
    if snapshot_download is None:
        result_queue.put(("error", "dependency_unavailable"))
        return

    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    try:
        downloaded_path = snapshot_download(
            repo_id=RAGConfig.EMBEDDING_MODEL,
            revision=RAGConfig.EMBEDDING_REVISION,
            cache_dir=attempt_cache_dir,
            resume_download=True,
        )
    except Exception as exc:
        result_queue.put(("error", type(exc).__name__))
        return
    result_queue.put(("finished", str(downloaded_path)))


def _run_bounded_snapshot_download(
    plan: RAGEmbeddingDownloadPlan,
    attempt_root: Path,
    *,
    deadline: float,
    cancel_event: CacheScanCancellation | None,
) -> _RAGAttemptDownloadResult:
    """Run and monitor one child until it is reaped or rejected."""
    context = multiprocessing.get_context(_DOWNLOAD_PROCESS_START_METHOD)
    result_queue = context.Queue()
    process = context.Process(
        target=_run_snapshot_download_task,
        args=(str(attempt_root), result_queue),
        daemon=True,
    )
    try:
        process.start()
    except Exception:
        if _started_child_may_exist(process):
            cleanup_safe = _stop_download_process(process)
        else:
            cleanup_safe = _close_unstarted_process(process)
        _close_result_queue(result_queue)
        return _RAGAttemptDownloadResult(
            False,
            "The RAG embedding download process could not be started.",
            attempt_cleanup_safe=cleanup_safe,
        )

    try:
        while True:
            stopped_message = _operation_stopped_message(deadline, cancel_event)
            if stopped_message:
                stopped = _stop_download_process(process)
                return _RAGAttemptDownloadResult(
                    False,
                    stopped_message,
                    attempt_cleanup_safe=stopped,
                )
            try:
                terminal = result_queue.get(
                    timeout=_bounded_poll_timeout(deadline),
                )
            except queue.Empty:
                terminal = None
            except (OSError, ValueError):
                stopped = _stop_download_process(process)
                return _RAGAttemptDownloadResult(
                    False,
                    "The RAG embedding download result could not be verified.",
                    attempt_cleanup_safe=stopped,
                )

            stopped_message = _operation_stopped_message(deadline, cancel_event)
            if stopped_message:
                stopped = _stop_download_process(process)
                return _RAGAttemptDownloadResult(
                    False,
                    stopped_message,
                    attempt_cleanup_safe=stopped,
                )

            consumption = _inspect_rag_download_consumption(
                plan,
                attempt_root,
                deadline=deadline,
                cancel_event=cancel_event,
            )
            if not consumption.ok:
                stopped_message = _operation_stopped_message(deadline, cancel_event)
                stopped = _stop_download_process(process)
                return _RAGAttemptDownloadResult(
                    False,
                    stopped_message or consumption.public_message,
                    attempt_cleanup_safe=stopped,
                )

            if terminal is not None:
                return _consume_download_terminal(
                    process,
                    terminal,
                    deadline=deadline,
                    cancel_event=cancel_event,
                )

            alive = _process_is_alive(process)
            if alive is None:
                stopped = _stop_download_process(process)
                return _RAGAttemptDownloadResult(
                    False,
                    "The RAG embedding download process could not be verified.",
                    attempt_cleanup_safe=stopped,
                )
            if not alive:
                try:
                    delayed_terminal = result_queue.get(
                        timeout=_bounded_poll_timeout(deadline)
                    )
                except (queue.Empty, OSError, ValueError):
                    delayed_terminal = None
                if delayed_terminal is not None:
                    return _consume_download_terminal(
                        process,
                        delayed_terminal,
                        deadline=deadline,
                        cancel_event=cancel_event,
                    )
                finished = _finish_download_process(process, deadline=deadline)
                return _RAGAttemptDownloadResult(
                    False,
                    "The RAG embedding download ended without a verified result.",
                    attempt_cleanup_safe=finished,
                )
    finally:
        _close_result_queue(result_queue)


def _consume_download_terminal(
    process,
    terminal: object,
    *,
    deadline: float,
    cancel_event: CacheScanCancellation | None,
) -> _RAGAttemptDownloadResult:
    stopped_message = _operation_stopped_message(deadline, cancel_event)
    if stopped_message:
        stopped = _stop_download_process(process)
        return _RAGAttemptDownloadResult(
            False,
            stopped_message,
            attempt_cleanup_safe=stopped,
        )
    if (
        not isinstance(terminal, tuple)
        or len(terminal) != 2
        or terminal[0] not in {"finished", "error"}
    ):
        stopped = _stop_download_process(process)
        return _RAGAttemptDownloadResult(
            False,
            "The RAG embedding download returned an invalid result.",
            attempt_cleanup_safe=stopped,
        )

    kind, payload = terminal
    if not _finish_download_process(process, deadline=deadline):
        cleanup_safe = _stop_download_process(process)
        return _RAGAttemptDownloadResult(
            False,
            "The RAG embedding download process could not be cleaned up.",
            attempt_cleanup_safe=cleanup_safe,
        )
    if kind == "error":
        error_kind = str(payload) if str(payload).isidentifier() else "download_error"
        return _RAGAttemptDownloadResult(
            False,
            f"RAG embedding download failed: {error_kind}.",
        )
    return _RAGAttemptDownloadResult(
        True,
        "",
        returned_snapshot_path=str(payload),
    )


def _inspect_rag_download_consumption(
    plan: RAGEmbeddingDownloadPlan,
    artifact_root: Path,
    *,
    deadline: float | None = None,
    cancel_event: CacheScanCancellation | None = None,
) -> _RAGDownloadConsumption:
    """Measure actual attempt/cache usage and fail closed without path output."""
    attempt_bytes = 0
    total_bytes = 0
    free_bytes = available_disk_bytes(plan.cache_dir)
    try:
        attempt_bytes = cache_usage_bytes(
            str(artifact_root),
            deadline=deadline,
            cancel_event=cancel_event,
        )
        total_bytes = cache_usage_bytes(
            plan.cache_dir,
            deadline=deadline,
            cancel_event=cancel_event,
        )
    except CacheInspectionError:
        return _RAGDownloadConsumption(
            False,
            (
                "RAG embedding download stopped because cache usage could not "
                "be verified."
            ),
            attempt_bytes,
            total_bytes,
            free_bytes,
        )

    if attempt_bytes > plan.max_single_model_bytes:
        message = (
            "RAG embedding download stopped because the per-artifact cache "
            "limit was exceeded."
        )
    elif total_bytes > plan.max_total_cache_bytes:
        message = (
            "RAG embedding download stopped because the total cache limit was exceeded."
        )
    elif free_bytes <= 0:
        message = (
            "RAG embedding download stopped because free disk space could not "
            "be verified."
        )
    elif free_bytes < plan.minimum_free_after_download_bytes:
        message = "The downloaded RAG embedding did not preserve the free-disk reserve."
    else:
        return _RAGDownloadConsumption(
            True,
            "",
            attempt_bytes,
            total_bytes,
            free_bytes,
        )
    return _RAGDownloadConsumption(
        False,
        message,
        attempt_bytes,
        total_bytes,
        free_bytes,
    )


def _operation_stopped_message(
    deadline: float,
    cancel_event: CacheScanCancellation | None,
) -> str | None:
    try:
        if cancel_event is not None and cancel_event.is_set():
            return "RAG embedding download cancelled by the caller."
    except Exception:
        return "RAG embedding download cancellation state could not be verified."
    if time.monotonic() >= deadline:
        return "RAG embedding download exceeded its wall-clock deadline."
    return None


def _bounded_poll_timeout(deadline: float) -> float:
    return max(0.001, min(_DOWNLOAD_POLL_INTERVAL_SEC, deadline - time.monotonic()))


@contextlib.contextmanager
def _publication_lock(
    cache_root: Path,
    *,
    deadline: float,
    cancel_event: CacheScanCancellation | None,
) -> Iterator[None]:
    """Hold a persistent OS lock for one publication and possible rollback."""
    lock_path = cache_root / _PUBLISH_LOCK_NAME
    if not _prepare_publication_lock_file(cache_root, lock_path):
        raise _RAGOperationStoppedError(
            "The RAG embedding publication lock could not be safely prepared."
        )

    lock = portalocker.Lock(
        lock_path,
        mode="a",
        timeout=0,
        flags=portalocker.LockFlags.EXCLUSIVE | portalocker.LockFlags.NON_BLOCKING,
    )
    acquired = False
    while not acquired:
        stopped_message = _operation_stopped_message(deadline, cancel_event)
        if stopped_message:
            raise _RAGOperationStoppedError(stopped_message)
        try:
            lock.acquire()
            acquired = True
        except portalocker.exceptions.LockException:
            time.sleep(
                max(
                    0.001,
                    min(
                        _PUBLISH_LOCK_POLL_INTERVAL_SEC,
                        deadline - time.monotonic(),
                    ),
                )
            )
        except OSError as exc:
            raise _RAGOperationStoppedError(
                "The RAG embedding publication lock could not be acquired."
            ) from exc

    try:
        if not _publication_lock_file_is_safe(cache_root, lock_path):
            raise _RAGOperationStoppedError(
                "The RAG embedding publication lock could not be safely verified."
            )
        yield
    finally:
        try:
            lock.release()
        except Exception as exc:
            raise _RAGOperationStoppedError(
                "The RAG embedding publication lock could not be safely released."
            ) from exc


def _prepare_publication_lock_file(cache_root: Path, lock_path: Path) -> bool:
    try:
        root_stat = cache_root.lstat()
        if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
            return False
        if lock_path.exists() or lock_path.is_symlink():
            return _secure_existing_publication_lock_file(cache_root, lock_path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NOINHERIT", 0)
        descriptor = os.open(lock_path, flags, 0o600)
        os.close(descriptor)
        os.chmod(lock_path, 0o600)
        return _publication_lock_file_is_safe(cache_root, lock_path)
    except FileExistsError:
        return _secure_existing_publication_lock_file(cache_root, lock_path)
    except OSError:
        return False


def _secure_existing_publication_lock_file(
    cache_root: Path,
    lock_path: Path,
) -> bool:
    if not _publication_lock_file_has_safe_identity(cache_root, lock_path):
        return False
    try:
        os.chmod(lock_path, 0o600)
    except OSError:
        return False
    return _publication_lock_file_is_safe(cache_root, lock_path)


def _publication_lock_file_has_safe_identity(
    cache_root: Path,
    lock_path: Path,
) -> bool:
    try:
        lock_stat = lock_path.lstat()
        owner_is_current_user = not hasattr(os, "getuid") or (
            lock_stat.st_uid == os.getuid()
        )
        return (
            lock_path.parent.resolve(strict=True) == cache_root.resolve(strict=True)
            and stat.S_ISREG(lock_stat.st_mode)
            and not stat.S_ISLNK(lock_stat.st_mode)
            and lock_stat.st_nlink == 1
            and owner_is_current_user
        )
    except OSError:
        return False


def _publication_lock_file_is_safe(cache_root: Path, lock_path: Path) -> bool:
    try:
        permissions_are_private = os.name == "nt" or (
            stat.S_IMODE(lock_path.lstat().st_mode) & 0o077 == 0
        )
    except OSError:
        return False
    return permissions_are_private and _publication_lock_file_has_safe_identity(
        cache_root,
        lock_path,
    )


def _publish_downloaded_embedding(
    plan: RAGEmbeddingDownloadPlan,
    attempt_root: Path,
    returned_snapshot_path: str | None,
) -> _RAGPublishResult:
    staged_snapshot = RAGConfig.embedding_snapshot_path(attempt_root)
    try:
        returned = Path(returned_snapshot_path or "").resolve(strict=True)
        staged_resolved = staged_snapshot.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return _RAGPublishResult(
            False,
            "The downloaded RAG embedding snapshot could not be verified.",
        )
    if returned != staged_resolved or not RAGConfig.embedding_cache_ready(attempt_root):
        return _RAGPublishResult(
            False,
            "The downloaded RAG embedding did not match the pinned snapshot.",
        )

    cache_root = Path(plan.cache_dir)
    target_snapshot = RAGConfig.embedding_snapshot_path(cache_root)
    staged_root = staged_snapshot.parent.parent
    target_root = target_snapshot.parent.parent
    backup_root = attempt_root / ".previous-target"
    try:
        resolved_cache = cache_root.resolve(strict=True)
        resolved_attempt = attempt_root.resolve(strict=True)
        staged_parent = staged_root.parent.resolve(strict=True)
        target_parent = target_root.parent.resolve(strict=True)
        staged_stat = staged_root.lstat()
        try:
            target_stat = target_root.lstat()
        except FileNotFoundError:
            target_stat = None
    except OSError:
        return _RAGPublishResult(
            False,
            "The RAG embedding target could not be safely prepared.",
        )
    if (
        staged_parent != resolved_attempt
        or target_parent != resolved_cache
        or not stat.S_ISDIR(staged_stat.st_mode)
        or (target_stat is not None and not stat.S_ISDIR(target_stat.st_mode))
    ):
        return _RAGPublishResult(
            False,
            "The RAG embedding target could not be safely prepared.",
        )

    moved_previous = False
    try:
        if target_root.exists():
            os.replace(target_root, backup_root)
            moved_previous = True
        os.replace(staged_root, target_root)
    except OSError:
        if moved_previous and not target_root.exists():
            with contextlib.suppress(OSError):
                os.replace(backup_root, target_root)
        return _RAGPublishResult(
            False,
            "The RAG embedding target could not be safely published.",
        )

    published = _RAGPublishResult(
        True,
        "",
        snapshot_path=target_snapshot,
        target_root=target_root,
        backup_root=backup_root if moved_previous else None,
        target_identity=_directory_identity(target_root),
    )
    if published.target_identity is None:
        _rollback_published_embedding(published)
        return _RAGPublishResult(
            False,
            "The published RAG embedding ownership could not be verified.",
        )
    if not RAGConfig.embedding_cache_ready(cache_root):
        _rollback_published_embedding(published)
        return _RAGPublishResult(
            False,
            "The published RAG embedding snapshot could not be verified.",
        )
    return published


def _rollback_published_embedding(published: _RAGPublishResult) -> None:
    target_root = published.target_root
    target_identity = published.target_identity
    if target_root is None or target_identity is None:
        return
    if _directory_identity(target_root) != target_identity:
        return
    if target_root.exists() and not _remove_owned_directory(target_root):
        return
    backup_root = published.backup_root
    if backup_root is not None and backup_root.exists():
        with contextlib.suppress(OSError):
            os.replace(backup_root, target_root)


def _directory_identity(path: Path) -> tuple[int, int, int] | None:
    """Return replacement-sensitive identity for an owned directory."""
    try:
        path_stat = path.lstat()
    except OSError:
        return None
    if not stat.S_ISDIR(path_stat.st_mode) or stat.S_ISLNK(path_stat.st_mode):
        return None
    return (path_stat.st_dev, path_stat.st_ino, path_stat.st_ctime_ns)


def _cleanup_attempt_root(cache_root: Path, attempt_root: Path) -> None:
    try:
        if attempt_root.parent.resolve(strict=True) != cache_root.resolve(strict=True):
            return
        if not attempt_root.name.startswith(_ATTEMPT_PREFIX):
            return
    except (FileNotFoundError, OSError):
        return
    _remove_owned_directory(attempt_root)


def _remove_owned_directory(path: Path) -> bool:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        if stat.S_ISLNK(path_stat.st_mode):
            path.unlink()
        elif stat.S_ISDIR(path_stat.st_mode):
            shutil.rmtree(path)
        else:
            return False
    except OSError:
        return False
    return True


def _process_is_alive(process) -> bool | None:
    try:
        return bool(process.is_alive())
    except Exception:
        return None


def _started_child_may_exist(process) -> bool:
    """Conservatively detect ownership after a partially failed start."""
    try:
        return process.pid is not None or process._popen is not None
    except Exception:
        return True


def _close_unstarted_process(process) -> bool:
    """Release a Process handle without joining when no child was started."""
    try:
        process.close()
    except Exception:
        return False
    return True


def _finish_download_process(process, *, deadline: float | None = None) -> bool:
    join_timeout = _PROCESS_JOIN_TIMEOUT_SEC
    if deadline is not None:
        join_timeout = max(0.0, min(join_timeout, deadline - time.monotonic()))
    try:
        process.join(join_timeout)
    except Exception:
        return False
    alive = _process_is_alive(process)
    if alive is None:
        return False
    if alive:
        return False
    with contextlib.suppress(Exception):
        process.close()
    return True


def _stop_download_process(process) -> bool:
    alive = _process_is_alive(process)
    if alive is None:
        return False
    try:
        if alive:
            process.terminate()
        process.join(_PROCESS_TERMINATE_TIMEOUT_SEC)
    except Exception:
        return False
    alive = _process_is_alive(process)
    if alive is None:
        return False
    if alive:
        try:
            process.kill()
            process.join(_PROCESS_KILL_TIMEOUT_SEC)
        except Exception:
            return False
        alive = _process_is_alive(process)
    if alive:
        return False
    with contextlib.suppress(Exception):
        process.close()
    return True


def _close_result_queue(result_queue) -> None:
    with contextlib.suppress(AttributeError, OSError, ValueError):
        result_queue.close()
    with contextlib.suppress(AttributeError, OSError, ValueError):
        result_queue.join_thread()


def _plan(
    *,
    ok: bool,
    message: str,
    cache_dir: str,
    estimated: int,
    current: int,
    projected: int,
    max_single: int,
    max_total: int,
    minimum_free: int,
    free: int,
) -> RAGEmbeddingDownloadPlan:
    return RAGEmbeddingDownloadPlan(
        ok=ok,
        message=message,
        cache_dir=cache_dir,
        estimated_download_bytes=estimated,
        current_cache_bytes=current,
        projected_cache_bytes=projected,
        max_single_model_bytes=max_single,
        max_total_cache_bytes=max_total,
        minimum_free_after_download_bytes=minimum_free,
        available_disk_bytes=free,
    )
