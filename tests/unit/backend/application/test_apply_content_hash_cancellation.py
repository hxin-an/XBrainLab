"""Cancellation contracts for Apply's reviewed-content fingerprinting."""

from __future__ import annotations

import threading
from contextvars import ContextVar
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic
from types import SimpleNamespace
from typing import Any

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ChangedState,
    ErrorType,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    data_interpretation_content_identity,
)
from XBrainLab.backend.application.data_interpretation_content_identity import (
    build_review_content_identity,
)
from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
    current_owned_operation_id,
)
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.study import Study

_THREAD_WATCHDOG_SECONDS = 5.0
_HASH_STAGE = "Hashing reviewed import content"


class _RecordingRegistry(OwnedWorkRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.hash_progress: list[tuple[int | None, int | None]] = []

    def update(
        self,
        operation_id: str,
        *,
        stage: str,
        completed: int | None = None,
        total: int | None = None,
        message: str = "",
    ):
        snapshot = super().update(
            operation_id,
            stage=stage,
            completed=completed,
            total=total,
            message=message,
        )
        if stage == _HASH_STAGE:
            self.hash_progress.append((snapshot.completed, snapshot.total))
        return snapshot


class _BlockingDigest:
    """Pause each content worker in its first digest update."""

    def __init__(
        self,
        delegate: Any,
        *,
        started: Event,
        release: Event,
        updates: list[int],
        update_lock: Lock,
    ) -> None:
        self._delegate = delegate
        self._started = started
        self._release = release
        self._updates = updates
        self._update_lock = update_lock

    def update(self, payload: bytes) -> None:
        with self._update_lock:
            self._updates.append(len(payload))
            if len(self._updates) >= 2:
                self._started.set()
        assert self._release.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        self._delegate.update(payload)

    def hexdigest(self) -> str:
        return self._delegate.hexdigest()


def _block_content_worker_digests(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Event, Event, list[int]]:
    real_sha256 = data_interpretation_content_identity.hashlib.sha256
    started = Event()
    release = Event()
    updates: list[int] = []
    update_lock = Lock()

    def sha256(payload: bytes = b"") -> Any:
        delegate = real_sha256(payload)
        if payload or not threading.current_thread().name.startswith(
            "interpretation-content-identity"
        ):
            return delegate
        return _BlockingDigest(
            delegate,
            started=started,
            release=release,
            updates=updates,
            update_lock=update_lock,
        )

    monkeypatch.setattr(
        data_interpretation_content_identity.hashlib,
        "sha256",
        sha256,
    )
    return started, release, updates


def _minimal_raw(filepath: Path) -> Raw:
    return Raw(
        str(filepath),
        mne.io.RawArray(
            np.zeros((1, 100)),
            mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )


def _prepare_apply(
    tmp_path: Path,
) -> tuple[ApplicationService, ApplyInterpretationCommand, int]:
    source_dir = tmp_path / "reviewed"
    source_dir.mkdir()
    chunk_bytes = 8
    recording_paths = [
        source_dir / "subject01_run1.fif",
        source_dir / "subject01_run2.fif",
    ]
    for index, path in enumerate(recording_paths):
        path.write_bytes(bytes([index + 1]) * (chunk_bytes * 8))

    service = ApplicationService(Study())
    service.dataset._raw_factory_provider = lambda: SimpleNamespace(
        load=lambda path: _minimal_raw(Path(path))
    )
    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(path) for path in recording_paths],
                "skip_labels": True,
            },
        )
    )
    assert preview.ok
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    return (
        service,
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True),
        sum(path.stat().st_size for path in recording_paths),
    )


def test_parallel_content_hash_workers_inherit_only_the_owned_operation_and_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A worker checkpoint must observe cancellation from the parent operation."""
    chunk_bytes = 8
    monkeypatch.setattr(
        data_interpretation_content_identity,
        "CONTENT_HASH_CHUNK_BYTES",
        chunk_bytes,
    )
    paths = [tmp_path / "run-1.set", tmp_path / "run-2.set"]
    for index, path in enumerate(paths):
        path.write_bytes(bytes([index + 1]) * (chunk_bytes * 8))
    started, release, updates = _block_content_worker_digests(monkeypatch)
    registry = OwnedWorkRegistry()
    operation = registry.begin(
        OwnedWorkKind.IMPORT_APPLY,
        cancellable=True,
        command_identity="apply_interpretation",
    )
    failures: list[BaseException] = []

    def fingerprint() -> None:
        registry.start(operation.operation_id)
        try:
            with registry.bind(operation.operation_id):
                build_review_content_identity(
                    label_carrier_plan=[],
                    selected_eeg_files=[str(path) for path in paths],
                )
        except BaseException as exc:  # pragma: no branch - asserted below
            failures.append(exc)

    worker = Thread(target=fingerprint, name="apply-content-hash-owner")
    worker.start()
    assert started.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    hashing = registry.snapshot(operation.operation_id)

    started_at = monotonic()
    assert registry.cancel(operation.operation_id) is True
    cancel_elapsed = monotonic() - started_at
    release.set()
    worker.join(timeout=_THREAD_WATCHDOG_SECONDS)

    assert cancel_elapsed < 0.1
    assert not worker.is_alive()
    assert hashing.stage == _HASH_STAGE
    assert hashing.completed == 0
    assert hashing.total == sum(path.stat().st_size for path in paths)
    assert len(failures) == 1
    assert isinstance(failures[0], OwnedOperationCancelledError)
    assert len(updates) <= len(paths)
    cancelled = registry.snapshot(operation.operation_id)
    assert cancelled.phase is OwnedWorkPhase.CANCELLED
    assert cancelled.stage == _HASH_STAGE
    assert cancelled.completed is not None
    assert 0 < cancelled.completed < cancelled.total


def test_parallel_hash_progress_is_monotonic_and_preserves_exact_content_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_bytes = 8
    monkeypatch.setattr(
        data_interpretation_content_identity,
        "CONTENT_HASH_CHUNK_BYTES",
        chunk_bytes,
    )
    payloads = [b"a" * (chunk_bytes * 5), b"b" * (chunk_bytes * 3)]
    paths = [tmp_path / "run-1.set", tmp_path / "run-2.set"]
    for path, payload in zip(paths, payloads, strict=True):
        path.write_bytes(payload)

    unrelated_context = ContextVar(
        "test_apply_hash_unrelated_context",
        default="worker-default",
    )
    token = unrelated_context.set("caller-private-context")
    observed_context: list[tuple[str, str | None]] = []
    observation_lock = Lock()
    original = data_interpretation_content_identity._stable_stream_sha256

    def observed_stream(path: Path) -> tuple[int, str]:
        with observation_lock:
            observed_context.append(
                (unrelated_context.get(), current_owned_operation_id())
            )
        return original(path)

    monkeypatch.setattr(
        data_interpretation_content_identity,
        "_stable_stream_sha256",
        observed_stream,
    )
    registry = _RecordingRegistry()
    operation = registry.begin(OwnedWorkKind.IMPORT_APPLY, cancellable=True)
    registry.start(operation.operation_id)
    try:
        with registry.bind(operation.operation_id):
            identity = build_review_content_identity(
                label_carrier_plan=[],
                selected_eeg_files=[str(path) for path in paths],
            )
        completed = registry.complete(operation.operation_id)
    finally:
        unrelated_context.reset(token)

    assert observed_context == [
        ("worker-default", operation.operation_id),
        ("worker-default", operation.operation_id),
    ]
    assert [row["sha256"] for row in identity["files"]] == [
        sha256(payload).hexdigest() for payload in payloads
    ]
    completed_bytes = [
        progress
        for progress, total in registry.hash_progress
        if progress is not None and total is not None
    ]
    assert completed_bytes == sorted(completed_bytes)
    assert completed_bytes[0] == 0
    assert completed_bytes[-1] == sum(map(len, payloads))
    assert completed.completed == completed.total == sum(map(len, payloads))
    assert completed.phase is OwnedWorkPhase.COMPLETED


def test_apply_hash_close_fence_is_immediate_preserves_state_and_allows_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, command, total_bytes = _prepare_apply(tmp_path)
    before = service.get_view_publication()
    monkeypatch.setattr(
        data_interpretation_content_identity,
        "CONTENT_HASH_CHUNK_BYTES",
        8,
    )
    started, release, updates = _block_content_worker_digests(monkeypatch)
    operation = service.begin_owned_operation(command)
    results = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="apply-content-hash-command",
    )

    worker.start()
    assert started.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    hashing = service.get_owned_operation(operation.operation_id)

    started_at = monotonic()
    service.request_shutdown_fence()
    fence_elapsed = monotonic() - started_at
    release.set()
    worker.join(timeout=_THREAD_WATCHDOG_SECONDS)

    assert fence_elapsed < 0.1
    assert not worker.is_alive()
    assert hashing.stage == _HASH_STAGE
    assert hashing.completed == 0
    assert hashing.total == total_bytes
    assert len(results) == 1
    cancelled_result = results[0]
    assert cancelled_result.failed
    assert cancelled_result.error_type is ErrorType.CANCELLED
    assert cancelled_result.changed_state == ChangedState()
    assert cancelled_result.state == before.state
    assert service.study.data_manager.loaded_data_list == []
    assert len(updates) <= 2
    cancelled = service.get_owned_operation(operation.operation_id)
    assert cancelled.phase is OwnedWorkPhase.CANCELLED
    assert cancelled.stage == _HASH_STAGE
    assert 0 < cancelled.completed < cancelled.total

    assert service.release_shutdown_fence() is True
    retry_operation = service.begin_owned_operation(command)
    retried = service.execute(
        command,
        operation_id=retry_operation.operation_id,
    )

    assert retried.ok
    assert len(service.study.data_manager.loaded_data_list) == 2
    assert service.get_owned_operation(retry_operation.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    service.close()
