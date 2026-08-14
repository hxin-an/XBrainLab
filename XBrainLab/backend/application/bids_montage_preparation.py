"""Pure BIDS electrode geometry resolution for deferred montage preparation."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import stat
from collections.abc import Iterable
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from .bids_dataset_index import (
    BidsDatasetIndex,
    build_bids_dataset_index,
    current_bids_dataset_index_for_path,
)
from .data_interpretation_resource_reader import AdmittedResourceReader
from .errors import PreconditionError
from .montage_capability import (
    MontageCoordinateDimension,
    montage_geometry_capabilities,
)
from .resource_guard import check_import_resource_preflight

MontagePreparationState = Literal[
    "not_applicable",
    "pending",
    "ready",
    "unavailable",
    "failed",
]
RecordingMontageState = Literal["ready", "unavailable", "failed"]
MontageCoordinateFrame = Literal["head"]
MontageResourceKind = Literal["electrodes", "coordsystem"]
MontageInheritanceLevel = Literal[
    "dataset",
    "subject",
    "session",
    "recording",
    "ancestor",
]

_RESOURCE_LIMIT_BYTES = 8 * 1024 * 1024
_MAX_INHERITANCE_DIRECTORY_ENTRIES = 16_384
_SAFE_COORDINATE_FRAMES: dict[str, MontageCoordinateFrame] = {
    "captrak": "head",
}
_UNIT_SCALE_TO_METERS = {"m": 1.0, "cm": 0.01, "mm": 0.001}


@dataclass(frozen=True, slots=True)
class BidsMontageRecordingRequest:
    """One exact selected recording and its authoritative loaded channel order."""

    recording_path: str
    channel_names: tuple[str, ...]
    channel_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        path = str(self.recording_path).strip()
        names = tuple(str(name).strip() for name in self.channel_names)
        types = tuple(str(item).strip().casefold() for item in self.channel_types)
        if not path:
            raise ValueError("recording_path is required")
        if not names or any(not name for name in names):
            raise ValueError("recording channel names must be non-empty")
        if len(set(names)) != len(names):
            raise ValueError("recording channel names must be unique")
        if not types:
            types = ("eeg",) * len(names)
        if len(types) != len(names) or any(not item for item in types):
            raise ValueError("recording channel types must align with channel names")
        object.__setattr__(self, "recording_path", path)
        object.__setattr__(self, "channel_names", names)
        object.__setattr__(self, "channel_types", types)


@dataclass(frozen=True, slots=True)
class BidsMontageResourceReceipt:
    """Exact inherited resources admitted for one preparation generation."""

    recording_resources: tuple[tuple[str, tuple[str, ...]], ...]
    resource_sha256: tuple[tuple[str, str], ...] = ()
    resource_reader: AdmittedResourceReader | None = None

    def __post_init__(self) -> None:
        normalized = tuple(
            (
                _canonical_or_lexical(recording_path),
                tuple(_canonical_or_lexical(path) for path in resource_paths),
            )
            for recording_path, resource_paths in self.recording_resources
        )
        recording_paths = tuple(path for path, _resources in normalized)
        if not recording_paths or len(set(recording_paths)) != len(recording_paths):
            raise ValueError("receipt recording paths must be non-empty and unique")
        if any(len(resources) not in {0, 2} for _path, resources in normalized):
            raise ValueError("each receipt row must contain zero or two BIDS resources")
        admitted_paths = tuple(
            dict.fromkeys(
                path for _recording, resources in normalized for path in resources
            )
        )
        if admitted_paths and self.resource_reader is None:
            raise ValueError(
                "BIDS montage resources require an admitted resource reader"
            )
        normalized_digests = tuple(
            (_canonical_or_lexical(path), str(digest).strip().lower())
            for path, digest in self.resource_sha256
        )
        if tuple(path for path, _digest in normalized_digests) != admitted_paths:
            raise ValueError(
                "BIDS montage content identities must match the exact receipt paths"
            )
        if any(
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for _path, digest in normalized_digests
        ):
            raise ValueError("BIDS montage content identities must be SHA-256 digests")
        if self.resource_reader is not None:
            expected_keys = {
                self.resource_reader.canonical_key(path) for path in admitted_paths
            }
            if set(self.resource_reader.admitted_files) != expected_keys:
                raise ValueError(
                    "the BIDS montage resource reader must admit exactly the "
                    "receipt paths"
                )
        object.__setattr__(self, "recording_resources", normalized)
        object.__setattr__(self, "resource_sha256", normalized_digests)

    @property
    def recording_paths(self) -> tuple[str, ...]:
        return tuple(path for path, _resources in self.recording_resources)

    def resources_for(self, recording_path: str | Path) -> tuple[str, ...]:
        canonical = _canonical_or_lexical(recording_path)
        for admitted_recording, resources in self.recording_resources:
            if admitted_recording == canonical:
                return resources
        raise PreconditionError(
            "BIDS montage preparation was denied because the recording is outside "
            "the admitted resource receipt."
        )

    def sha256_for(self, resource_path: str | Path) -> str:
        canonical = _canonical_or_lexical(resource_path)
        for admitted_path, digest in self.resource_sha256:
            if admitted_path == canonical:
                return digest
        raise PreconditionError(
            "BIDS montage preparation was denied because a resource content "
            "identity is missing from the admitted receipt."
        )


@dataclass(frozen=True, slots=True)
class MontageResourceProvenance:
    """Exact inherited BIDS resource identity used for one recording."""

    kind: MontageResourceKind
    path: str
    inheritance_level: MontageInheritanceLevel
    matched_entities: tuple[tuple[str, str], ...]
    content_sha256: str


@dataclass(frozen=True, slots=True)
class RecordingMontagePreparation:
    """Immutable geometry result for one selected recording."""

    recording_path: str
    state: RecordingMontageState
    recording_channel_names: tuple[str, ...]
    channel_names: tuple[str, ...] = ()
    positions_m: tuple[tuple[float, float, float], ...] = ()
    unpositioned_channel_names: tuple[str, ...] = ()
    missing_channel_names: tuple[str, ...] = ()
    unexpected_channel_names: tuple[str, ...] = ()
    coordinate_system: str | None = None
    coordinate_frame: MontageCoordinateFrame | None = None
    coordinate_units: Literal["m"] | None = None
    source_coordinate_units: Literal["m", "cm", "mm"] | None = None
    coordinate_dimension: MontageCoordinateDimension | None = None
    provenance: tuple[MontageResourceProvenance, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class AggregateMontageCompatibility:
    """Geometry safe to apply to an aggregate only when compatible is true."""

    compatible: bool
    channel_names: tuple[str, ...] = ()
    positions_m: tuple[tuple[float, float, float], ...] = ()
    coordinate_frame: MontageCoordinateFrame | None = None
    coordinate_units: Literal["m"] | None = None
    coordinate_dimension: MontageCoordinateDimension | None = None
    supports_topographic: bool = False
    supports_three_dimensional: bool = False
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MontagePreparationSnapshot:
    """Generation-bound, deeply immutable BIDS montage preparation state."""

    state: MontagePreparationState
    generation: int
    requested_recording_paths: tuple[str, ...] = ()
    recordings: tuple[RecordingMontagePreparation, ...] = ()
    aggregate: AggregateMontageCompatibility = AggregateMontageCompatibility(
        compatible=False,
        reason="No compatible BIDS geometry has been prepared.",
    )
    reason: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise ValueError("generation must be a non-negative integer")

    @property
    def import_blocking(self) -> bool:
        """Montage preparation is advisory and never blocks data import."""
        return False

    @classmethod
    def not_applicable(
        cls,
        *,
        generation: int,
        reason: str,
    ) -> MontagePreparationSnapshot:
        return cls(
            state="not_applicable",
            generation=generation,
            aggregate=AggregateMontageCompatibility(
                compatible=False,
                reason=reason,
            ),
            reason=reason,
        )

    @classmethod
    def pending(
        cls,
        *,
        generation: int,
        recording_paths: Iterable[str],
    ) -> MontagePreparationSnapshot:
        paths = tuple(str(path) for path in recording_paths)
        return cls(
            state="pending",
            generation=generation,
            requested_recording_paths=paths,
            aggregate=AggregateMontageCompatibility(
                compatible=False,
                reason="BIDS montage preparation is pending.",
            ),
            reason="BIDS montage preparation is pending.",
        )


@dataclass(frozen=True, slots=True)
class _ResourceCandidate:
    path: Path
    kind: MontageResourceKind
    entities: tuple[tuple[str, str], ...]
    directory_depth: int
    inheritance_level: MontageInheritanceLevel

    @property
    def entity_map(self) -> dict[str, str]:
        return dict(self.entities)


@dataclass(frozen=True, slots=True)
class _ResolvedResources:
    dataset_root: Path | None
    electrodes: _ResourceCandidate | None = None
    coordsystem: _ResourceCandidate | None = None
    reason: str | None = None
    not_applicable: bool = False


class _MontageUnavailableError(Exception):
    pass


class _MontageResourceError(Exception):
    pass


class _StaleBidsIndexError(_MontageResourceError):
    pass


def prepare_bids_montage(
    recordings: Iterable[BidsMontageRecordingRequest],
    *,
    generation: int,
    resource_reader: AdmittedResourceReader | None = None,
    resource_receipt: BidsMontageResourceReceipt | None = None,
    bids_index: BidsDatasetIndex | None = None,
) -> MontagePreparationSnapshot:
    """Resolve and parse per-recording BIDS geometry without mutating import state."""
    requests = tuple(recordings)
    if not requests:
        return MontagePreparationSnapshot.not_applicable(
            generation=generation,
            reason="No selected recordings require BIDS montage preparation.",
        )
    paths = tuple(_canonical_or_lexical(item.recording_path) for item in requests)
    if len(set(paths)) != len(paths):
        raise ValueError("selected montage recording paths must be unique")
    if resource_receipt is not None:
        if resource_receipt.recording_paths != paths:
            raise PreconditionError(
                "BIDS montage preparation was denied because the selected recordings "
                "do not match the admitted resource receipt."
            )
        if (
            resource_reader is not None
            and resource_reader is not resource_receipt.resource_reader
        ):
            raise ValueError("resource reader and BIDS montage receipt do not match")
        resource_reader = resource_receipt.resource_reader

    prepared: list[RecordingMontagePreparation] = []
    non_bids_count = 0
    for request in requests:
        result, not_applicable = _prepare_one_recording(
            request,
            bids_index=bids_index,
            resource_reader=resource_reader,
            expected_resource_paths=(
                resource_receipt.resources_for(request.recording_path)
                if resource_receipt is not None
                else None
            ),
            expected_resource_sha256=(
                tuple(
                    resource_receipt.sha256_for(path)
                    for path in resource_receipt.resources_for(request.recording_path)
                )
                if resource_receipt is not None
                else None
            ),
        )
        prepared.append(result)
        non_bids_count += int(not_applicable)

    prepared_tuple = tuple(prepared)
    aggregate = _aggregate_compatibility(prepared_tuple)
    if any(item.state == "failed" for item in prepared_tuple):
        state: MontagePreparationState = "failed"
        reason = next(item.reason for item in prepared_tuple if item.state == "failed")
    elif non_bids_count == len(prepared_tuple):
        state = "not_applicable"
        reason = "Selected recordings are not inside a BIDS dataset."
    elif any(item.state == "unavailable" for item in prepared_tuple):
        state = "unavailable"
        reason = next(
            item.reason for item in prepared_tuple if item.state == "unavailable"
        )
    elif not aggregate.compatible:
        state = "unavailable"
        reason = aggregate.reason
    else:
        state = "ready"
        reason = None
    return MontagePreparationSnapshot(
        state=state,
        generation=generation,
        requested_recording_paths=paths,
        recordings=prepared_tuple,
        aggregate=aggregate,
        reason=reason,
    )


def admit_bids_montage_resources(
    recordings: Iterable[BidsMontageRecordingRequest],
    *,
    bids_index: BidsDatasetIndex | None = None,
) -> BidsMontageResourceReceipt:
    """Capture an exact sidecar receipt before any montage payload is parsed."""
    requests = tuple(recordings)
    if not requests:
        raise ValueError("at least one recording is required for montage admission")
    recording_resources: list[tuple[str, tuple[str, ...]]] = []
    admitted_paths: list[str] = []
    for request in requests:
        recording_path = _canonical_or_lexical(request.recording_path)
        resolved = _resolve_resources(
            Path(request.recording_path),
            bids_index=bids_index,
        )
        resources = _resolved_resource_paths(resolved)
        recording_resources.append((recording_path, resources))
        admitted_paths.extend(resources)
    unique_paths = tuple(dict.fromkeys(admitted_paths))
    resource_reader = None
    resource_sha256: tuple[tuple[str, str], ...] = ()
    if unique_paths:
        preflight = check_import_resource_preflight(unique_paths)
        if preflight.blocking:
            raise PreconditionError(
                "BIDS montage resources could not be admitted safely.",
                diagnostics={"resource_preflight": preflight.to_diagnostics()},
            )
        resource_reader = AdmittedResourceReader.from_resource_preflight(
            unique_paths,
            preflight,
        )
        with resource_reader.guard(
            unique_paths,
            purpose="BIDS montage resource receipt",
        ):
            resource_sha256 = tuple(
                (path, _read_bounded_resource(Path(path))[1]) for path in unique_paths
            )
    return BidsMontageResourceReceipt(
        recording_resources=tuple(recording_resources),
        resource_sha256=resource_sha256,
        resource_reader=resource_reader,
    )


def resolve_bids_montage_resource_paths(
    recording_path: str | Path,
    *,
    bids_index: BidsDatasetIndex | None = None,
) -> tuple[str, ...]:
    """Discover the exact inherited pair for preflight before content reads."""
    try:
        resolved = _resolve_resources(
            Path(recording_path),
            bids_index=bids_index,
        )
    except _StaleBidsIndexError as exc:
        raise PreconditionError(str(exc)) from exc
    return _resolved_resource_paths(resolved)


def _resolved_resource_paths(resolved: _ResolvedResources) -> tuple[str, ...]:
    if resolved.electrodes is None or resolved.coordsystem is None:
        return ()
    return (str(resolved.electrodes.path), str(resolved.coordsystem.path))


def _prepare_one_recording(
    request: BidsMontageRecordingRequest,
    *,
    bids_index: BidsDatasetIndex | None,
    resource_reader: AdmittedResourceReader | None,
    expected_resource_paths: tuple[str, ...] | None,
    expected_resource_sha256: tuple[str, ...] | None,
) -> tuple[RecordingMontagePreparation, bool]:
    recording_path = _canonical_or_lexical(request.recording_path)
    base = {
        "recording_path": recording_path,
        "recording_channel_names": request.channel_names,
    }
    try:
        resolved = _resolve_resources(
            Path(request.recording_path),
            bids_index=bids_index,
        )
    except _MontageResourceError as exc:
        reason = str(exc)
        if expected_resource_paths is not None:
            reason = (
                "BIDS montage resources could not be revalidated after admission; "
                "review the import again."
            )
        return (
            RecordingMontagePreparation(
                **base,
                state="failed",
                reason=reason,
            ),
            False,
        )
    resolved_resource_paths = _resolved_resource_paths(resolved)
    if (
        expected_resource_paths is not None
        and resolved_resource_paths != expected_resource_paths
    ):
        return (
            RecordingMontagePreparation(
                **base,
                state="failed",
                reason=(
                    "BIDS montage resources changed after admission; review the "
                    "import again before preparing electrode positions."
                ),
            ),
            False,
        )
    if resolved.not_applicable:
        return (
            RecordingMontagePreparation(
                **base,
                state="unavailable",
                reason=resolved.reason,
            ),
            True,
        )
    if resolved.electrodes is None or resolved.coordsystem is None:
        return (
            RecordingMontagePreparation(
                **base,
                state="unavailable",
                reason=resolved.reason,
            ),
            False,
        )

    paths = (resolved.electrodes.path, resolved.coordsystem.path)
    electrodes_digest: str | None = None
    coordsystem_digest: str | None = None
    metadata: _CoordinateMetadata | None = None
    guard = (
        resource_reader.guard(paths, purpose="BIDS montage preparation")
        if resource_reader is not None
        else nullcontext()
    )
    try:
        with guard:
            electrodes_payload, electrodes_digest = _read_bounded_resource(paths[0])
            coordsystem_payload, coordsystem_digest = _read_bounded_resource(paths[1])
            _assert_resource_content_unchanged(
                observed=(electrodes_digest, coordsystem_digest),
                expected=expected_resource_sha256,
            )
            metadata = _parse_coordinate_metadata(coordsystem_payload)
            parsed = _parse_electrodes(
                electrodes_payload,
                scale_to_meters=metadata.scale_to_meters,
            )
    except _MontageUnavailableError as exc:
        provenance = _provenance(
            resolved,
            electrodes_digest=electrodes_digest,
            coordsystem_digest=coordsystem_digest,
        )
        return (
            RecordingMontagePreparation(
                **base,
                state="unavailable",
                coordinate_system=(
                    metadata.coordinate_system if metadata is not None else None
                ),
                coordinate_frame=(
                    metadata.coordinate_frame if metadata is not None else None
                ),
                source_coordinate_units=(
                    metadata.source_units if metadata is not None else None
                ),
                provenance=provenance,
                reason=str(exc),
            ),
            False,
        )
    except (OSError, UnicodeDecodeError, csv.Error, json.JSONDecodeError) as exc:
        return (
            RecordingMontagePreparation(
                **base,
                state="failed",
                coordinate_system=(
                    metadata.coordinate_system if metadata is not None else None
                ),
                coordinate_frame=(
                    metadata.coordinate_frame if metadata is not None else None
                ),
                source_coordinate_units=(
                    metadata.source_units if metadata is not None else None
                ),
                provenance=_provenance(
                    resolved,
                    electrodes_digest=electrodes_digest,
                    coordsystem_digest=coordsystem_digest,
                ),
                reason=f"BIDS montage resources could not be parsed: {exc}",
            ),
            False,
        )
    except (_MontageResourceError, PreconditionError) as exc:
        return (
            RecordingMontagePreparation(
                **base,
                state="failed",
                coordinate_system=(
                    metadata.coordinate_system if metadata is not None else None
                ),
                coordinate_frame=(
                    metadata.coordinate_frame if metadata is not None else None
                ),
                source_coordinate_units=(
                    metadata.source_units if metadata is not None else None
                ),
                provenance=_provenance(
                    resolved,
                    electrodes_digest=electrodes_digest,
                    coordsystem_digest=coordsystem_digest,
                ),
                reason=str(exc),
            ),
            False,
        )

    provenance = _provenance(
        resolved,
        electrodes_digest=electrodes_digest,
        coordsystem_digest=coordsystem_digest,
    )
    electrode_names = tuple(row.name for row in parsed)
    requested_names = tuple(
        name
        for name, channel_type in zip(
            request.channel_names,
            request.channel_types,
            strict=True,
        )
        if channel_type == "eeg"
    )
    if not requested_names:
        return (
            RecordingMontagePreparation(
                **base,
                state="unavailable",
                coordinate_system=metadata.coordinate_system,
                coordinate_frame=metadata.coordinate_frame,
                source_coordinate_units=metadata.source_units,
                provenance=provenance,
                reason="The recording contains no EEG channels for montage use.",
            ),
            False,
        )
    available = set(electrode_names)
    requested = set(requested_names)
    missing = tuple(name for name in requested_names if name not in available)
    unexpected = tuple(name for name in electrode_names if name not in requested)
    positioned = tuple(
        row for row in parsed if row.name in requested and row.position_m is not None
    )
    if not positioned:
        reason = (
            "BIDS electrode channel mapping does not match any recording EEG channel."
            if missing
            else "BIDS electrodes.tsv contains no finite channel positions."
        )
        return (
            RecordingMontagePreparation(
                **base,
                state="unavailable",
                unpositioned_channel_names=requested_names,
                missing_channel_names=missing,
                unexpected_channel_names=unexpected,
                coordinate_system=metadata.coordinate_system,
                coordinate_frame=metadata.coordinate_frame,
                source_coordinate_units=metadata.source_units,
                provenance=provenance,
                reason=reason,
            ),
            False,
        )
    positioned_names = {row.name for row in positioned}
    unpositioned = tuple(
        name for name in requested_names if name not in positioned_names
    )
    dimensions = {
        row.coordinate_dimension
        for row in positioned
        if row.coordinate_dimension is not None
    }
    if len(dimensions) != 1:
        return (
            RecordingMontagePreparation(
                **base,
                state="unavailable",
                unpositioned_channel_names=unpositioned,
                missing_channel_names=missing,
                unexpected_channel_names=unexpected,
                coordinate_system=metadata.coordinate_system,
                coordinate_frame=metadata.coordinate_frame,
                source_coordinate_units=metadata.source_units,
                provenance=provenance,
                reason="BIDS electrode coordinate dimensions are inconsistent.",
            ),
            False,
        )
    coordinate_dimension = cast(MontageCoordinateDimension, dimensions.pop())
    return (
        RecordingMontagePreparation(
            **base,
            state="ready",
            channel_names=tuple(row.name for row in positioned),
            positions_m=tuple(row.position_m for row in positioned),  # type: ignore[arg-type]
            unpositioned_channel_names=unpositioned,
            missing_channel_names=missing,
            unexpected_channel_names=unexpected,
            coordinate_system=metadata.coordinate_system,
            coordinate_frame=metadata.coordinate_frame,
            coordinate_units="m",
            source_coordinate_units=metadata.source_units,
            coordinate_dimension=coordinate_dimension,
            provenance=provenance,
        ),
        False,
    )


@dataclass(frozen=True, slots=True)
class _CoordinateMetadata:
    coordinate_system: str
    coordinate_frame: MontageCoordinateFrame
    source_units: Literal["m", "cm", "mm"]
    scale_to_meters: float


def _assert_resource_content_unchanged(
    *,
    observed: tuple[str, str],
    expected: tuple[str, ...] | None,
) -> None:
    if expected is not None and observed != expected:
        raise _MontageResourceError(
            "BIDS montage resource content changed after admission; review the "
            "import again before preparing electrode positions."
        )


@dataclass(frozen=True, slots=True)
class _ElectrodeRow:
    name: str
    position_m: tuple[float, float, float] | None
    coordinate_dimension: MontageCoordinateDimension | None


def _parse_coordinate_metadata(payload: bytes) -> _CoordinateMetadata:
    parsed = json.loads(payload.decode("utf-8-sig"))
    if not isinstance(parsed, dict):
        raise _MontageResourceError(
            "BIDS coordsystem.json must contain one JSON object."
        )
    raw_system = parsed.get("EEGCoordinateSystem")
    raw_units = parsed.get("EEGCoordinateUnits")
    if not isinstance(raw_system, str) or not _safe_metadata_value(raw_system):
        raise _MontageUnavailableError(
            "BIDS EEG coordinate system metadata is missing or unsafe."
        )
    coordinate_system = raw_system.strip()
    coordinate_frame = _SAFE_COORDINATE_FRAMES.get(coordinate_system.casefold())
    if coordinate_frame is None:
        detail = (
            " requires a verified transform into head coordinates"
            if coordinate_system.casefold() == "ctf"
            else " is not safe"
        )
        raise _MontageUnavailableError(
            f"BIDS EEG coordinate system '{coordinate_system}'{detail} for "
            "automatic montage preparation."
        )
    if not isinstance(raw_units, str):
        raise _MontageUnavailableError("BIDS EEG coordinate units are missing.")
    units = raw_units.strip().lower()
    if units not in _UNIT_SCALE_TO_METERS:
        raise _MontageUnavailableError(
            f"BIDS EEG coordinate units '{raw_units}' are unsupported."
        )
    source_units: Literal["m", "cm", "mm"] = units  # type: ignore[assignment]
    return _CoordinateMetadata(
        coordinate_system=coordinate_system,
        coordinate_frame=coordinate_frame,
        source_units=source_units,
        scale_to_meters=_UNIT_SCALE_TO_METERS[units],
    )


def _parse_electrodes(
    payload: bytes,
    *,
    scale_to_meters: float,
) -> tuple[_ElectrodeRow, ...]:
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    fieldnames = tuple(reader.fieldnames or ())
    if len(set(fieldnames)) != len(fieldnames) or not {"name", "x", "y", "z"} <= set(
        fieldnames
    ):
        raise _MontageResourceError(
            "BIDS electrodes.tsv requires unique name, x, y, and z columns."
        )
    rows: list[_ElectrodeRow] = []
    seen: set[str] = set()
    for row_number, row in enumerate(reader, start=2):
        name = str(row.get("name") or "").strip()
        if not name:
            raise _MontageResourceError(
                f"BIDS electrodes.tsv row {row_number} has no channel name."
            )
        if name in seen:
            raise _MontageResourceError(
                "BIDS electrodes.tsv channel names must be unique."
            )
        seen.add(name)
        raw_coordinates = tuple(str(row.get(axis) or "").strip() for axis in "xyz")
        na_coordinates = tuple(value.casefold() == "n/a" for value in raw_coordinates)
        coordinate_dimension: MontageCoordinateDimension | None
        if all(na_coordinates):
            position = None
            coordinate_dimension = None
        elif na_coordinates[0] or na_coordinates[1]:
            raise _MontageResourceError(
                f"BIDS electrodes.tsv row {row_number} must provide both x and y "
                "coordinates or mark all coordinates n/a."
            )
        else:
            try:
                numeric_xy = tuple(float(value) for value in raw_coordinates[:2])
                numeric_z = 0.0 if na_coordinates[2] else float(raw_coordinates[2])
            except ValueError as exc:
                raise _MontageResourceError(
                    f"BIDS electrodes.tsv row {row_number} has non-numeric coordinates."
                ) from exc
            numeric = (*numeric_xy, numeric_z)
            if not all(math.isfinite(value) for value in numeric):
                raise _MontageResourceError(
                    f"BIDS electrodes.tsv row {row_number} positions must be finite."
                )
            position = (
                numeric[0] * scale_to_meters,
                numeric[1] * scale_to_meters,
                numeric[2] * scale_to_meters,
            )
            coordinate_dimension = 2 if na_coordinates[2] else 3
        rows.append(
            _ElectrodeRow(
                name=name,
                position_m=position,
                coordinate_dimension=coordinate_dimension,
            )
        )
    if not rows:
        raise _MontageResourceError("BIDS electrodes.tsv contains no channel rows.")
    return tuple(rows)


def _aggregate_compatibility(
    recordings: tuple[RecordingMontagePreparation, ...],
) -> AggregateMontageCompatibility:
    if not recordings:
        return AggregateMontageCompatibility(
            compatible=False,
            reason="No recording geometry is available for aggregate use.",
        )
    if any(item.state != "ready" for item in recordings):
        return AggregateMontageCompatibility(
            compatible=False,
            reason="Not every selected recording has usable BIDS geometry.",
        )
    first = recordings[0]
    for item in recordings[1:]:
        if item.coordinate_frame != first.coordinate_frame:
            return AggregateMontageCompatibility(
                compatible=False,
                reason="Selected recording coordinate frames differ.",
            )
        if item.channel_names != first.channel_names:
            return AggregateMontageCompatibility(
                compatible=False,
                reason="Selected recording montage channel orders differ.",
            )
        if item.positions_m != first.positions_m:
            return AggregateMontageCompatibility(
                compatible=False,
                reason="Selected recording electrode geometries differ.",
            )
        if item.coordinate_dimension != first.coordinate_dimension:
            return AggregateMontageCompatibility(
                compatible=False,
                reason="Selected recording coordinate dimensions differ.",
            )
    supports_topographic, supports_three_dimensional = montage_geometry_capabilities(
        first.positions_m,
        coordinate_dimension=first.coordinate_dimension,
    )
    return AggregateMontageCompatibility(
        compatible=True,
        channel_names=first.channel_names,
        positions_m=first.positions_m,
        coordinate_frame=first.coordinate_frame,
        coordinate_units="m",
        coordinate_dimension=first.coordinate_dimension,
        supports_topographic=supports_topographic,
        supports_three_dimensional=supports_three_dimensional,
    )


def _resolve_resources(
    recording_path: Path,
    *,
    bids_index: BidsDatasetIndex | None = None,
) -> _ResolvedResources:
    try:
        recording = recording_path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise _MontageResourceError(
            f"Selected recording identity is unavailable: {recording_path}."
        ) from exc
    active_index = bids_index
    if active_index is not None:
        dataset_root = Path(active_index.root)
        if not active_index.looks_like_bids:
            raise _MontageResourceError(
                "The supplied dataset index is not a valid BIDS root."
            )
        try:
            recording.relative_to(dataset_root)
        except ValueError as exc:
            raise _MontageResourceError(
                "Selected recording is outside the supplied BIDS dataset index."
            ) from exc
        if not active_index.is_current():
            raise _StaleBidsIndexError(
                "BIDS dataset index changed before montage inheritance resolution."
            )
        if not _index_contains_recording(active_index, recording):
            raise _MontageResourceError(
                "Selected recording is outside the supplied BIDS recording index."
            )
    else:
        active_index = current_bids_dataset_index_for_path(recording)
        if active_index is not None and not _index_contains_recording(
            active_index,
            recording,
        ):
            active_index = None
        if active_index is None:
            dataset_root = _find_dataset_root(recording)
            if dataset_root is None:
                return _ResolvedResources(
                    dataset_root=None,
                    reason="Selected recording is not inside a BIDS dataset.",
                    not_applicable=True,
                )
            active_index = build_bids_dataset_index(dataset_root)
        dataset_root = Path(active_index.root)
    try:
        recording.relative_to(dataset_root)
    except ValueError as exc:
        raise _MontageResourceError(
            "Selected recording resolves outside its BIDS dataset root."
        ) from exc

    recording_entities = _filename_entities(recording.name, suffix="eeg")
    candidates = _discover_candidates(
        dataset_root=dataset_root,
        recording=recording,
        recording_entities=recording_entities,
        indexed_files=active_index.indexed_files,
    )
    electrodes = [item for item in candidates if item.kind == "electrodes"]
    coordsystems = [item for item in candidates if item.kind == "coordsystem"]
    if not electrodes or not coordsystems:
        missing = []
        if not electrodes:
            missing.append("electrodes.tsv")
        if not coordsystems:
            missing.append("coordsystem.json")
        return _ResolvedResources(
            dataset_root=dataset_root,
            reason=f"Inherited BIDS {' and '.join(missing)} not found.",
        )

    pairs = [
        (electrode, coordsystem)
        for electrode in electrodes
        for coordsystem in coordsystems
        if electrode.entity_map.get("space") == coordsystem.entity_map.get("space")
    ]
    if not pairs:
        return _ResolvedResources(
            dataset_root=dataset_root,
            reason=(
                "Inherited BIDS electrodes.tsv and coordsystem.json do not describe "
                "the same coordinate space."
            ),
        )
    ranked = sorted(pairs, key=_pair_rank, reverse=True)
    best_rank = _pair_rank(ranked[0])
    best = [pair for pair in ranked if _pair_rank(pair) == best_rank]
    if len(best) != 1:
        return _ResolvedResources(
            dataset_root=dataset_root,
            reason="Inherited BIDS montage resources are ambiguous for this recording.",
        )
    return _ResolvedResources(
        dataset_root=dataset_root,
        electrodes=best[0][0],
        coordsystem=best[0][1],
    )


def _index_contains_recording(index: BidsDatasetIndex, recording: Path) -> bool:
    return index.contains_recording(recording)


def _discover_candidates(
    *,
    dataset_root: Path,
    recording: Path,
    recording_entities: dict[str, str],
    indexed_files: Iterable[str],
) -> tuple[_ResourceCandidate, ...]:
    directories = _inheritance_directories(dataset_root, recording.parent)
    directory_depths = {directory: depth for depth, directory in enumerate(directories)}
    directory_entry_counts: dict[Path, int] = {}
    for path_text in indexed_files:
        path = Path(path_text)
        if path.parent in directory_depths:
            directory_entry_counts[path.parent] = (
                directory_entry_counts.get(path.parent, 0) + 1
            )
    oversized = next(
        (
            directory
            for directory, count in directory_entry_counts.items()
            if count > _MAX_INHERITANCE_DIRECTORY_ENTRIES
        ),
        None,
    )
    if oversized is not None:
        raise _MontageResourceError(
            f"BIDS inheritance directory has too many entries: {oversized}."
        )
    candidates: list[_ResourceCandidate] = []
    for entry in sorted(
        (Path(path) for path in indexed_files), key=lambda path: str(path)
    ):
        directory = entry.parent
        depth = directory_depths.get(directory)
        if depth is None:
            continue
        kind = _resource_kind(entry.name)
        if kind is None:
            continue
        entities = _filename_entities(entry.name, suffix=kind)
        if not _entities_apply(entities, recording_entities):
            continue
        try:
            resolved = entry.resolve(strict=True)
            resolved.relative_to(dataset_root)
            file_stat = resolved.stat()
        except (OSError, ValueError) as exc:
            raise _MontageResourceError(
                f"BIDS montage resource identity is unsafe: {entry}."
            ) from exc
        if not stat.S_ISREG(file_stat.st_mode):
            continue
        candidates.append(
            _ResourceCandidate(
                path=resolved,
                kind=kind,
                entities=tuple(sorted(entities.items())),
                directory_depth=depth,
                inheritance_level=_inheritance_level(
                    directory,
                    dataset_root=dataset_root,
                    recording_directory=recording.parent,
                ),
            )
        )
    return tuple(candidates)


def _inheritance_directories(dataset_root: Path, local: Path) -> tuple[Path, ...]:
    directories: list[Path] = []
    current = local
    while True:
        directories.append(current)
        if current == dataset_root:
            break
        parent = current.parent
        if parent == current:
            raise _MontageResourceError(
                "BIDS inheritance scope does not reach the dataset root."
            )
        current = parent
    directories.reverse()
    return tuple(directories)


def _find_dataset_root(recording: Path) -> Path | None:
    for directory in (recording.parent, *recording.parent.parents):
        marker = directory / "dataset_description.json"
        try:
            marker_stat = marker.stat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise _MontageResourceError(
                f"BIDS dataset marker could not be inspected: {marker}."
            ) from exc
        if stat.S_ISREG(marker_stat.st_mode):
            return directory.resolve(strict=True)
    return None


def _resource_kind(name: str) -> MontageResourceKind | None:
    lowered = name.lower()
    if lowered == "electrodes.tsv" or lowered.endswith("_electrodes.tsv"):
        return "electrodes"
    if lowered == "coordsystem.json" or lowered.endswith("_coordsystem.json"):
        return "coordsystem"
    return None


def _filename_entities(filename: str, *, suffix: str) -> dict[str, str]:
    lowered = filename.lower()
    suffixes = {
        "eeg": "_eeg",
        "electrodes": "_electrodes",
        "coordsystem": "_coordsystem",
    }
    semantic_suffix = suffixes[suffix]
    without_extensions = filename
    extensions = (
        ".gz",
        ".json",
        ".tsv",
        ".fif",
        ".set",
        ".edf",
        ".bdf",
        ".cnt",
        ".vhdr",
        ".eeg",
    )
    for extension in extensions:
        if lowered.endswith(extension):
            without_extensions = without_extensions[: -len(extension)]
            lowered = lowered[: -len(extension)]
    if lowered.endswith(semantic_suffix):
        without_extensions = without_extensions[: -len(semantic_suffix)]
    entities: dict[str, str] = {}
    for part in without_extensions.split("_"):
        if "-" not in part:
            continue
        key, value = part.split("-", 1)
        if key and value:
            entities[key.lower()] = value
    return entities


def _entities_apply(
    resource_entities: dict[str, str],
    recording_entities: dict[str, str],
) -> bool:
    for key, value in resource_entities.items():
        if key == "space" and key not in recording_entities:
            continue
        if recording_entities.get(key) != value:
            return False
    return True


def _pair_rank(
    pair: tuple[_ResourceCandidate, _ResourceCandidate],
) -> tuple[int, int, int, int]:
    electrodes, coordsystem = pair
    electrode_entities = electrodes.entity_map
    coordsystem_entities = coordsystem.entity_map
    return (
        min(electrodes.directory_depth, coordsystem.directory_depth),
        electrodes.directory_depth + coordsystem.directory_depth,
        int("space" not in electrode_entities),
        len(electrode_entities) + len(coordsystem_entities),
    )


def _inheritance_level(
    directory: Path,
    *,
    dataset_root: Path,
    recording_directory: Path,
) -> MontageInheritanceLevel:
    if directory == dataset_root:
        return "dataset"
    if directory == recording_directory:
        return "recording"
    if directory.name.startswith("ses-"):
        return "session"
    if directory.name.startswith("sub-"):
        return "subject"
    return "ancestor"


def _read_bounded_resource(path: Path) -> tuple[bytes, str]:
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise _MontageResourceError(
                    f"BIDS montage resource is not a regular file: {path}."
                )
            file_bytes = max(int(opened.st_size), 0)
            if file_bytes > _RESOURCE_LIMIT_BYTES:
                raise _MontageResourceError(
                    f"BIDS montage resource exceeds the bounded read limit: {path}."
                )
            payload = handle.read(file_bytes + 1)
            final = os.fstat(handle.fileno())
    except OSError as exc:
        raise _MontageResourceError(
            f"BIDS montage resource could not be read: {path}."
        ) from exc
    opened_identity = (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
        opened.st_ctime_ns,
    )
    final_identity = (
        final.st_dev,
        final.st_ino,
        final.st_size,
        final.st_mtime_ns,
        final.st_ctime_ns,
    )
    if opened_identity != final_identity or len(payload) != file_bytes:
        raise _MontageResourceError(
            f"BIDS montage resource changed while it was read: {path}."
        )
    return payload, hashlib.sha256(payload).hexdigest()


def _provenance(
    resolved: _ResolvedResources,
    *,
    electrodes_digest: str | None,
    coordsystem_digest: str | None,
) -> tuple[MontageResourceProvenance, ...]:
    resources = (
        (resolved.electrodes, electrodes_digest),
        (resolved.coordsystem, coordsystem_digest),
    )
    return tuple(
        MontageResourceProvenance(
            kind=candidate.kind,
            path=str(candidate.path),
            inheritance_level=candidate.inheritance_level,
            matched_entities=candidate.entities,
            content_sha256=digest,
        )
        for candidate, digest in resources
        if candidate is not None and digest is not None
    )


def _safe_metadata_value(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and len(stripped) <= 128 and stripped.isprintable()


def _canonical_or_lexical(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))
