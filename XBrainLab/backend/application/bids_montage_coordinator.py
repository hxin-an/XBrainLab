"""Application-owned background coordination for BIDS electrode geometry."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from threading import Condition, RLock, Thread, current_thread
from time import monotonic
from typing import Any, cast

from XBrainLab.backend.utils.logger import logger

from .bids_montage_preparation import (
    BidsMontageRecordingRequest,
    BidsMontageResourceReceipt,
    MontagePreparationSnapshot,
    RecordingMontagePreparation,
    admit_bids_montage_resources,
    prepare_bids_montage,
)
from .montage_preparation_lifecycle import (
    EffectiveMontage,
    ManualMontageOverride,
    MontagePreparationLifecycle,
    MontagePreparationWork,
    effective_montage_from_snapshot,
)


class BidsMontagePreparationCoordinator:
    """Prepare optional BIDS geometry without delaying the import command."""

    def __init__(
        self,
        *,
        on_publication: Callable[[MontagePreparationSnapshot], None] | None = None,
        commit_publication: (
            Callable[[MontagePreparationWork, MontagePreparationSnapshot], None] | None
        ) = None,
        prepare: Callable[..., MontagePreparationSnapshot] = prepare_bids_montage,
        admit: Callable[
            [Iterable[BidsMontageRecordingRequest]],
            BidsMontageResourceReceipt,
        ] = admit_bids_montage_resources,
    ) -> None:
        self._lifecycle = MontagePreparationLifecycle()
        self._on_publication = on_publication
        self._commit_publication = commit_publication
        self._prepare = prepare
        self._admit = admit
        self._lock = RLock()
        self._idle = Condition(self._lock)
        self._pending_work: MontagePreparationWork | None = None
        self._active_work: MontagePreparationWork | None = None
        self._closed = False
        self._worker: Thread | None = None
        self._validation_candidate: MontagePreparationSnapshot | None = None
        self._retry_candidate: (
            tuple[MontagePreparationWork, MontagePreparationSnapshot] | None
        ) = None

    def start(
        self,
        recordings: Iterable[BidsMontageRecordingRequest],
    ) -> MontagePreparationSnapshot:
        """Publish pending state immediately and prepare the latest request."""
        requested = tuple(recordings)
        with self._idle:
            if self._closed:
                return self._lifecycle.snapshot()
            work = self._lifecycle.begin(requested)
            pending = self._lifecycle.snapshot()
            # Coalesce queued requests. A currently running bounded read may
            # finish, but its generation will be rejected as stale.
            self._pending_work = work
            self._validation_candidate = None
            self._retry_candidate = None
            self._ensure_worker_locked()
            self._idle.notify_all()
        return pending

    def reset(self) -> MontagePreparationSnapshot:
        """Invalidate outstanding work and clear automatic/manual geometry."""
        with self._idle:
            snapshot = self._lifecycle.reset()
            self._pending_work = None
            self._validation_candidate = None
            self._retry_candidate = None
            self._idle.notify_all()
            return snapshot

    def select_manual(
        self,
        override: ManualMontageOverride,
    ) -> MontagePreparationSnapshot:
        """Make an explicit user montage authoritative over background work."""
        with self._idle:
            snapshot = self._lifecycle.select_manual(override)
            self._pending_work = None
            self._validation_candidate = None
            self._retry_candidate = None
            self._idle.notify_all()
            return snapshot

    def snapshot(self) -> MontagePreparationSnapshot:
        with self._idle:
            return self._validation_candidate or self._lifecycle.snapshot()

    def effective_montage(self) -> EffectiveMontage | None:
        with self._idle:
            if self._validation_candidate is not None:
                return effective_montage_from_snapshot(self._validation_candidate)
            return self._lifecycle.effective_montage()

    @property
    def worker_thread(self) -> Thread | None:
        """Expose worker identity for lifecycle validation."""
        with self._idle:
            return self._worker

    def synchronize_loaded_recordings(
        self,
        recordings: Iterable[Any],
    ) -> MontagePreparationSnapshot:
        """Build typed preparation requests from application-owned loaded records."""
        loaded_recordings = tuple(recordings)
        # Invalidate geometry from the previous inventory before calling any
        # foreign recording accessor. Conversion is all-or-nothing: a partial
        # replacement must never become authoritative.
        reset_snapshot = self.reset()
        if not loaded_recordings:
            return reset_snapshot
        requests: list[BidsMontageRecordingRequest] = []
        for index, item in enumerate(loaded_recordings):
            filepath_getter = getattr(item, "get_filepath", None)
            mne_getter = getattr(item, "get_mne", None)
            if not callable(filepath_getter) or not callable(mne_getter):
                raise ValueError(
                    f"loaded recording {index + 1} is missing required accessors"
                )
            filepath = str(filepath_getter() or "").strip()
            mne_data = mne_getter()
            channel_names = tuple(
                str(name) for name in getattr(mne_data, "ch_names", ())
            )
            channel_types_getter = getattr(mne_data, "get_channel_types", None)
            if not callable(channel_types_getter):
                raise ValueError(
                    f"loaded recording {index + 1} has no channel type metadata"
                )
            channel_types = tuple(
                str(value) for value in cast(Iterable[object], channel_types_getter())
            )
            if not filepath or not channel_names:
                raise ValueError(
                    f"loaded recording {index + 1} has incomplete identity metadata"
                )
            if len(channel_types) != len(channel_names):
                raise ValueError(
                    f"loaded recording {index + 1} has inconsistent channel metadata"
                )
            requests.append(
                BidsMontageRecordingRequest(
                    recording_path=filepath,
                    channel_names=channel_names,
                    channel_types=channel_types,
                )
            )
        return self.start(requests)

    def select_manual_values(
        self,
        *,
        name: str,
        channel_names: Iterable[str],
        positions: Iterable[Iterable[float]],
    ) -> MontagePreparationSnapshot:
        """Normalize one confirmed manual selection under montage ownership."""
        rows: list[tuple[float, float, float]] = []
        for raw_row in positions:
            row = tuple(raw_row)
            if len(row) != 3:
                raise ValueError("Manual montage positions must contain x, y, and z.")
            rows.append((float(row[0]), float(row[1]), float(row[2])))
        return self.select_manual(
            ManualMontageOverride(
                name=name or "Manual montage",
                channel_names=tuple(channel_names),
                positions_m=tuple(rows),
                coordinate_frame="head",
            )
        )

    def promote_result(
        self,
        work: MontagePreparationWork,
        result: MontagePreparationSnapshot,
        *,
        refresh_candidate: Callable[[], Any],
    ) -> bool:
        """Refresh against a validated candidate before making it authoritative."""
        with self._idle:
            return self._promote_locked(
                work,
                result,
                refresh_candidate=refresh_candidate,
            )

    def retry_promotion(
        self,
        *,
        refresh_candidate: Callable[[], Any],
    ) -> bool:
        """Retry a candidate retained after a transient application refresh failure."""
        with self._idle:
            if self._closed or self._retry_candidate is None:
                return False
            work, result = self._retry_candidate
            return self._promote_locked(
                work,
                result,
                refresh_candidate=refresh_candidate,
            )

    @property
    def has_pending_promotion(self) -> bool:
        """Return whether a validated result is waiting for view recovery."""
        with self._idle:
            return self._retry_candidate is not None

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        """Wait only at an explicit test, headless, or shutdown boundary."""
        deadline = None if timeout is None else monotonic() + max(0.0, timeout)
        with self._idle:
            while (
                self._active_work is not None
                or self._pending_work is not None
                or self._worker is not None
            ):
                remaining = (
                    None if deadline is None else max(0.0, deadline - monotonic())
                )
                if remaining == 0.0:
                    return False
                self._idle.wait(timeout=remaining)
            return True

    def close(self, timeout: float | None = 2.0) -> bool:
        """Fence and join the owned non-daemon parser worker within a bound."""
        deadline = None if timeout is None else monotonic() + max(0.0, timeout)
        with self._idle:
            if not self._closed:
                self._closed = True
                self._pending_work = None
                self._validation_candidate = None
                self._retry_candidate = None
                self._lifecycle.reset()
                self._idle.notify_all()
            worker = self._worker
        if worker is not None and worker is not current_thread():
            remaining = None if deadline is None else max(0.0, deadline - monotonic())
            worker.join(timeout=remaining)
        with self._idle:
            worker = self._worker
            if worker is not None and not worker.is_alive():
                self._worker = None
                worker = None
            return worker is None and self._active_work is None

    def _ensure_worker_locked(self) -> None:
        """Start one worker only when preparation work actually exists."""
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = Thread(
            target=self._worker_loop,
            name="xbrainlab-bids-montage",
            daemon=False,
        )
        self._worker.start()

    def _run(
        self,
        work: MontagePreparationWork,
    ) -> MontagePreparationSnapshot | None:
        try:
            receipt = self._admit(work.recordings)
            if not self._lifecycle.is_current(work):
                return None
            return self._prepare(
                work.recordings,
                generation=work.generation,
                resource_reader=receipt.resource_reader,
                resource_receipt=receipt,
            )
        except Exception as exc:
            logger.exception("BIDS montage preparation failed unexpectedly")
            reason = (
                f"BIDS electrode positions could not be prepared: {type(exc).__name__}."
            )
            return MontagePreparationSnapshot(
                state="failed",
                generation=work.generation,
                requested_recording_paths=tuple(
                    item.recording_path for item in work.recordings
                ),
                recordings=tuple(
                    RecordingMontagePreparation(
                        recording_path=item.recording_path,
                        state="failed",
                        recording_channel_names=item.channel_names,
                        reason=reason,
                    )
                    for item in work.recordings
                ),
                reason=reason,
            )

    def _worker_loop(self) -> None:
        while True:
            with self._idle:
                if self._pending_work is None:
                    self._worker = None
                    self._idle.notify_all()
                    return
                work = self._pending_work
                self._pending_work = None
                self._active_work = work
            if work is None:
                continue
            if not self._lifecycle.is_current(work):
                with self._idle:
                    if self._active_work == work:
                        self._active_work = None
                    self._idle.notify_all()
                continue
            result = self._run(work)
            with self._lock:
                closed = self._closed
            if not closed and result is not None:
                self._deliver(work, result)
            with self._idle:
                if self._active_work == work:
                    self._active_work = None
                self._idle.notify_all()

    def _promote_locked(
        self,
        work: MontagePreparationWork,
        result: MontagePreparationSnapshot,
        *,
        refresh_candidate: Callable[[], Any],
    ) -> bool:
        validation = self._lifecycle.validate_candidate(work, result)
        if not validation.accepted:
            if self._retry_candidate == (work, result):
                self._retry_candidate = None
            return False
        self._validation_candidate = result
        try:
            refresh_candidate()
        except Exception:
            self._retry_candidate = (work, result)
            return False
        finally:
            self._validation_candidate = None

        publication = self._lifecycle.publish(work, result)
        if publication.accepted:
            self._retry_candidate = None
            return True

        # This should be unreachable while the coordinator lock excludes begin,
        # reset, and manual selection. Rebuild without the staged candidate if a
        # future lifecycle change violates that invariant.
        self._retry_candidate = None
        try:
            refresh_candidate()
        except Exception:
            logger.exception("Could not roll back rejected montage candidate view")
        return False

    def _deliver(
        self,
        work: MontagePreparationWork,
        result: MontagePreparationSnapshot,
    ) -> None:
        if self._commit_publication is not None:
            try:
                self._commit_publication(work, result)
            except Exception:
                logger.exception("BIDS montage application commit failed")
            return
        publication = self._lifecycle.publish(work, result)
        if publication.accepted and self._on_publication is not None:
            try:
                self._on_publication(publication.snapshot)
            except Exception:
                logger.exception("BIDS montage publication callback failed")
