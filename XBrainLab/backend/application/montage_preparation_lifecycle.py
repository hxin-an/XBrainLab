"""Generation and manual-precedence primitives for montage preparation."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Literal

from .bids_montage_preparation import (
    BidsMontageRecordingRequest,
    MontageCoordinateFrame,
    MontagePreparationSnapshot,
)
from .montage_capability import (
    MontageCoordinateDimension,
    montage_geometry_capabilities,
)


@dataclass(frozen=True, slots=True)
class MontagePreparationWork:
    """Identity captured before dispatching one background preparation."""

    generation: int
    recordings: tuple[BidsMontageRecordingRequest, ...]


@dataclass(frozen=True, slots=True)
class ManualMontageOverride:
    """One user-confirmed montage that always outranks automatic BIDS geometry."""

    name: str
    channel_names: tuple[str, ...]
    positions_m: tuple[tuple[float, float, float], ...]
    coordinate_frame: MontageCoordinateFrame
    electrode_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        channel_names = tuple(str(item).strip() for item in self.channel_names)
        electrode_names = tuple(str(item).strip() for item in self.electrode_names)
        if not electrode_names:
            electrode_names = channel_names
        positions = tuple(
            tuple(float(value) for value in row) for row in self.positions_m
        )
        _validate_geometry(channel_names, positions)
        if len(electrode_names) != len(channel_names) or any(
            not name for name in electrode_names
        ):
            raise ValueError("manual montage electrode names must align")
        if len(set(electrode_names)) != len(electrode_names):
            raise ValueError("manual montage electrode names must be unique")
        if not name:
            raise ValueError("manual montage name is required")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "channel_names", channel_names)
        object.__setattr__(self, "electrode_names", electrode_names)
        object.__setattr__(self, "positions_m", positions)


@dataclass(frozen=True, slots=True)
class EffectiveMontage:
    """Geometry selected after applying explicit manual-over-automatic precedence."""

    source: Literal["manual", "bids"]
    name: str | None
    channel_names: tuple[str, ...]
    positions_m: tuple[tuple[float, float, float], ...]
    coordinate_frame: MontageCoordinateFrame
    electrode_names: tuple[str, ...] = ()
    coordinate_units: Literal["m"] = "m"
    coordinate_dimension: MontageCoordinateDimension = 3
    supports_topographic: bool = False
    supports_three_dimensional: bool = False


@dataclass(frozen=True, slots=True)
class MontagePublicationResult:
    """Observable result of attempting to publish background preparation."""

    accepted: bool
    reason: Literal[
        "accepted",
        "stale_generation",
        "manual_override",
        "request_mismatch",
        "result_generation_mismatch",
    ]
    snapshot: MontagePreparationSnapshot


class MontagePreparationLifecycle:
    """Serialize import/reset/manual transitions against background publication."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._generation = 0
        self._snapshot = MontagePreparationSnapshot.not_applicable(
            generation=0,
            reason="No BIDS montage preparation has been requested.",
        )
        self._manual_override: ManualMontageOverride | None = None
        self._bids_restore_snapshot: MontagePreparationSnapshot | None = None
        self._active_work: MontagePreparationWork | None = None

    def begin(
        self,
        recordings: Iterable[BidsMontageRecordingRequest],
    ) -> MontagePreparationWork:
        """Invalidate older work and reserve a new non-blocking generation."""
        requested = tuple(
            BidsMontageRecordingRequest(
                recording_path=str(
                    Path(item.recording_path).expanduser().resolve(strict=False)
                ),
                channel_names=item.channel_names,
                channel_types=item.channel_types,
            )
            for item in recordings
        )
        if not requested:
            raise ValueError("at least one recording is required")
        with self._lock:
            self._generation += 1
            self._manual_override = None
            self._bids_restore_snapshot = None
            self._snapshot = MontagePreparationSnapshot.pending(
                generation=self._generation,
                recording_paths=(item.recording_path for item in requested),
            )
            self._active_work = MontagePreparationWork(
                generation=self._generation,
                recordings=requested,
            )
            return self._active_work

    def reset(self) -> MontagePreparationSnapshot:
        """Invalidate every outstanding result and clear manual selection."""
        with self._lock:
            self._generation += 1
            self._manual_override = None
            self._bids_restore_snapshot = None
            self._active_work = None
            self._snapshot = MontagePreparationSnapshot.not_applicable(
                generation=self._generation,
                reason="Montage preparation was reset.",
            )
            return self._snapshot

    def can_restore_bids(self) -> bool:
        """Return whether this import retains a ready BIDS layout to restore."""
        with self._lock:
            return (
                self._manual_override is not None
                and self._bids_restore_snapshot is not None
            )

    def restore_bids(self) -> MontagePreparationSnapshot:
        """Restore the already-reviewed BIDS geometry without reading sidecars again."""
        with self._lock:
            if self._manual_override is None or self._bids_restore_snapshot is None:
                raise ValueError(
                    "No retained BIDS electrode layout is available to restore."
                )
            self._generation += 1
            self._manual_override = None
            self._active_work = None
            self._snapshot = replace(
                self._bids_restore_snapshot,
                generation=self._generation,
            )
            return self._snapshot

    def select_manual(
        self,
        override: ManualMontageOverride,
    ) -> MontagePreparationSnapshot:
        """Invalidate automatic work before making manual geometry authoritative."""
        with self._lock:
            self._generation += 1
            self._manual_override = override
            self._active_work = None
            self._snapshot = MontagePreparationSnapshot.not_applicable(
                generation=self._generation,
                reason=f"Manual montage '{override.name}' is authoritative.",
            )
            return self._snapshot

    def publish(
        self,
        work: MontagePreparationWork,
        result: MontagePreparationSnapshot,
    ) -> MontagePublicationResult:
        """Publish only the current generation while no manual override is active."""
        with self._lock:
            rejection = self._candidate_rejection_locked(work, result)
            if rejection is not None:
                return MontagePublicationResult(
                    accepted=False,
                    reason=rejection,
                    snapshot=self._snapshot,
                )
            self._snapshot = result
            self._active_work = None
            if result.state == "ready" and result.aggregate.compatible:
                self._bids_restore_snapshot = result
            return MontagePublicationResult(
                accepted=True,
                reason="accepted",
                snapshot=self._snapshot,
            )

    def validate_candidate(
        self,
        work: MontagePreparationWork,
        result: MontagePreparationSnapshot,
    ) -> MontagePublicationResult:
        """Validate a candidate without making ready geometry externally visible."""
        with self._lock:
            rejection = self._candidate_rejection_locked(work, result)
            return MontagePublicationResult(
                accepted=rejection is None,
                reason="accepted" if rejection is None else rejection,
                snapshot=self._snapshot,
            )

    def snapshot(self) -> MontagePreparationSnapshot:
        with self._lock:
            return self._snapshot

    def is_current(self, work: MontagePreparationWork) -> bool:
        """Return whether work may still enter the background parser."""
        with self._lock:
            return (
                self._manual_override is None
                and work.generation == self._generation
                and work == self._active_work
            )

    def effective_montage(self) -> EffectiveMontage | None:
        """Return manual geometry first, otherwise only compatible BIDS geometry."""
        with self._lock:
            if self._manual_override is not None:
                manual = self._manual_override
                supports_topographic, supports_three_dimensional = (
                    montage_geometry_capabilities(
                        manual.positions_m,
                        coordinate_dimension=3,
                    )
                )
                return EffectiveMontage(
                    source="manual",
                    name=manual.name,
                    channel_names=manual.channel_names,
                    electrode_names=manual.electrode_names,
                    positions_m=manual.positions_m,
                    coordinate_frame=manual.coordinate_frame,
                    coordinate_dimension=3,
                    supports_topographic=supports_topographic,
                    supports_three_dimensional=supports_three_dimensional,
                )
            return effective_montage_from_snapshot(self._snapshot)

    def _candidate_rejection_locked(
        self,
        work: MontagePreparationWork,
        result: MontagePreparationSnapshot,
    ) -> (
        Literal[
            "stale_generation",
            "manual_override",
            "request_mismatch",
            "result_generation_mismatch",
        ]
        | None
    ):
        if self._manual_override is not None:
            return "manual_override"
        if work.generation != self._generation:
            return "stale_generation"
        if work != self._active_work:
            return "request_mismatch"
        if result.generation != work.generation:
            return "result_generation_mismatch"
        expected_paths = tuple(item.recording_path for item in work.recordings)
        if self._snapshot.requested_recording_paths != expected_paths:
            return "request_mismatch"
        if result.requested_recording_paths != expected_paths:
            return "request_mismatch"
        expected_canonical = tuple(
            recording.recording_path for recording in result.recordings
        )
        if expected_canonical != result.requested_recording_paths:
            return "request_mismatch"
        return None


def effective_montage_from_snapshot(
    snapshot: MontagePreparationSnapshot,
) -> EffectiveMontage | None:
    """Project compatible automatic geometry from an uncommitted candidate."""
    aggregate = snapshot.aggregate
    if (
        snapshot.state != "ready"
        or not aggregate.compatible
        or aggregate.coordinate_frame is None
    ):
        return None
    return EffectiveMontage(
        source="bids",
        name=None,
        channel_names=aggregate.channel_names,
        electrode_names=aggregate.channel_names,
        positions_m=aggregate.positions_m,
        coordinate_frame=aggregate.coordinate_frame,
        coordinate_dimension=aggregate.coordinate_dimension or 3,
        supports_topographic=aggregate.supports_topographic,
        supports_three_dimensional=aggregate.supports_three_dimensional,
    )


def _validate_geometry(
    channel_names: tuple[str, ...],
    positions: tuple[tuple[float, ...], ...],
) -> None:
    if not channel_names or any(not name for name in channel_names):
        raise ValueError("montage channel names must be non-empty")
    if len(set(channel_names)) != len(channel_names):
        raise ValueError("montage channel names must be unique")
    if len(channel_names) != len(positions):
        raise ValueError("montage channel names and positions must align")
    if any(len(row) != 3 for row in positions):
        raise ValueError("each montage position must contain x, y, and z")
    if any(not math.isfinite(value) for row in positions for value in row):
        raise ValueError("montage positions must be finite")
