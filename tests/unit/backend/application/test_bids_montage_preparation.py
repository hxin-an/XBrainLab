from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from XBrainLab.backend.application import bids_montage_preparation
from XBrainLab.backend.application.bids_dataset_index import build_bids_dataset_index
from XBrainLab.backend.application.bids_montage_preparation import (
    BidsMontageRecordingRequest,
    admit_bids_montage_resources,
    prepare_bids_montage,
    resolve_bids_montage_resource_paths,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.montage_preparation_lifecycle import (
    ManualMontageOverride,
    MontagePreparationLifecycle,
)


def _write_bids_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "montage-test", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )


def _write_recording(root: Path, subject: str, *, run: int = 1) -> Path:
    eeg_dir = root / f"sub-{subject}" / "eeg"
    eeg_dir.mkdir(parents=True, exist_ok=True)
    recording = eeg_dir / f"sub-{subject}_task-rest_run-{run}_eeg.fif"
    recording.write_bytes(b"recording identity only")
    return recording


def _write_geometry(
    directory: Path,
    stem: str,
    *,
    rows: tuple[tuple[str, str, str, str], ...],
    units: str = "m",
    coordinate_system: str = "CapTrak",
) -> tuple[Path, Path]:
    electrodes = directory / f"{stem}electrodes.tsv"
    coordsystem = directory / f"{stem}coordsystem.json"
    electrodes.write_text(
        "name\tx\ty\tz\n" + "".join("\t".join(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    coordsystem.write_text(
        json.dumps(
            {
                "EEGCoordinateSystem": coordinate_system,
                "EEGCoordinateUnits": units,
                "EEGCoordinateSystemDescription": "test coordinates",
            }
        ),
        encoding="utf-8",
    )
    return electrodes, coordsystem


def _prepare(
    recording: Path,
    channel_names: tuple[str, ...] = ("Cz",),
    *,
    channel_types: tuple[str, ...] = (),
    generation: int = 1,
):
    return prepare_bids_montage(
        (
            BidsMontageRecordingRequest(
                recording_path=str(recording),
                channel_names=channel_names,
                channel_types=channel_types,
            ),
        ),
        generation=generation,
    )


@pytest.mark.parametrize(
    ("units", "coordinate", "expected_meters"),
    [("m", "0.1", 0.1), ("cm", "10", 0.1), ("mm", "100", 0.1)],
)
def test_inherited_geometry_is_normalized_with_immutable_provenance(
    tmp_path: Path,
    units: str,
    coordinate: str,
    expected_meters: float,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    electrodes, coordsystem = _write_geometry(
        root,
        "task-rest_",
        rows=(("Cz", coordinate, "0", "0"),),
        units=units,
    )

    snapshot = _prepare(recording)

    assert snapshot.state == "ready"
    assert snapshot.generation == 1
    assert snapshot.reason is None
    assert snapshot.aggregate.compatible is True
    assert snapshot.aggregate.channel_names == ("Cz",)
    assert snapshot.aggregate.positions_m == ((expected_meters, 0.0, 0.0),)
    prepared = snapshot.recordings[0]
    assert prepared.recording_path == str(recording.resolve())
    assert prepared.channel_names == ("Cz",)
    assert prepared.positions_m == ((expected_meters, 0.0, 0.0),)
    assert prepared.coordinate_system == "CapTrak"
    assert prepared.coordinate_frame == "head"
    assert prepared.coordinate_units == "m"
    assert prepared.source_coordinate_units == units
    assert tuple(item.path for item in prepared.provenance) == (
        str(electrodes.resolve()),
        str(coordsystem.resolve()),
    )
    assert all(item.inheritance_level == "dataset" for item in prepared.provenance)
    with pytest.raises(FrozenInstanceError):
        snapshot.state = "failed"  # type: ignore[misc]


def test_more_specific_run_resources_override_inherited_resources(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        root,
        "task-rest_",
        rows=(("Cz", "0.1", "0", "0"),),
    )
    local_electrodes, local_coordsystem = _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0.2", "0", "0"),),
    )

    snapshot = _prepare(recording)

    assert snapshot.recordings[0].positions_m == ((0.2, 0.0, 0.0),)
    assert tuple(item.path for item in snapshot.recordings[0].provenance) == (
        str(local_electrodes.resolve()),
        str(local_coordsystem.resolve()),
    )


def test_montage_inheritance_consumes_current_index_without_rewalking_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    inherited = _write_geometry(
        root,
        "task-rest_",
        rows=(("Cz", "0.1", "0", "0"),),
    )
    index = build_bids_dataset_index(root)

    def _forbid_rewalk(_path: Path):
        pytest.fail("montage inheritance re-walked an already indexed BIDS root")

    monkeypatch.setattr(Path, "iterdir", _forbid_rewalk)

    resources = resolve_bids_montage_resource_paths(
        recording,
        bids_index=index,
    )

    assert resources == tuple(str(path.resolve()) for path in inherited)
    assert resolve_bids_montage_resource_paths(recording) == resources


def test_montage_rejects_changed_explicit_index_instead_of_using_stale_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        root,
        "task-rest_",
        rows=(("Cz", "0.1", "0", "0"),),
    )
    index = build_bids_dataset_index(root)
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0.2", "0", "0"),),
    )

    with pytest.raises(PreconditionError, match="index changed"):
        resolve_bids_montage_resource_paths(recording, bids_index=index)


def test_montage_registry_chooses_nested_exact_bids_root(tmp_path: Path) -> None:
    parent = tmp_path / "parent-bids"
    _write_bids_dataset(parent)
    _write_recording(parent, "parent")
    nested = parent / "sourcedata" / "nested-bids"
    _write_bids_dataset(nested)
    recording = _write_recording(nested, "01")
    inherited = _write_geometry(
        nested,
        "task-rest_",
        rows=(("Cz", "0.1", "0", "0"),),
    )
    parent_index = build_bids_dataset_index(parent)

    resources = resolve_bids_montage_resource_paths(recording)

    assert not any(
        item.file == str(recording.resolve()) for item in parent_index.recordings
    )
    assert resources == tuple(str(path.resolve()) for path in inherited)


def test_admitted_receipt_rejects_same_size_sidecar_change_before_parser_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    electrodes, _coordsystem = _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0.1", "0", "0"),),
    )
    request = BidsMontageRecordingRequest(str(recording), ("Cz",))
    receipt = admit_bids_montage_resources((request,))
    original_bytes = electrodes.read_bytes()
    electrodes.write_bytes(original_bytes.replace(b"0.1", b"0.2"))
    parser_calls = 0

    def reject_parser_entry(*_args, **_kwargs):
        nonlocal parser_calls
        parser_calls += 1
        raise AssertionError("changed resources must fail before parsing")

    monkeypatch.setattr(
        bids_montage_preparation,
        "_parse_electrodes",
        reject_parser_entry,
    )

    snapshot = prepare_bids_montage(
        (request,),
        generation=3,
        resource_receipt=receipt,
    )

    assert snapshot.state == "failed"
    assert "changed after resource admission" in (snapshot.reason or "").lower()
    assert parser_calls == 0


def test_receipt_does_not_fall_back_to_another_recordings_admitted_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    first = _write_recording(root, "01")
    second = _write_recording(root, "02")
    _write_geometry(
        root,
        "task-rest_",
        rows=(("Cz", "0.1", "0", "0"),),
    )
    local_electrodes, local_coordsystem = _write_geometry(
        first.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0.2", "0", "0"),),
    )
    requests = (
        BidsMontageRecordingRequest(str(first), ("Cz",)),
        BidsMontageRecordingRequest(str(second), ("Cz",)),
    )
    receipt = admit_bids_montage_resources(requests)
    local_electrodes.unlink()
    local_coordsystem.unlink()
    original_parser = bids_montage_preparation._parse_electrodes
    parser_calls = 0

    def track_parser_entry(*args, **kwargs):
        nonlocal parser_calls
        parser_calls += 1
        return original_parser(*args, **kwargs)

    monkeypatch.setattr(
        bids_montage_preparation,
        "_parse_electrodes",
        track_parser_entry,
    )

    snapshot = prepare_bids_montage(
        requests,
        generation=4,
        resource_receipt=receipt,
    )

    assert snapshot.state == "failed"
    assert snapshot.recordings[0].state == "failed"
    assert "changed after admission" in (snapshot.recordings[0].reason or "").lower()
    assert snapshot.recordings[1].state == "ready"
    assert parser_calls == 1


def test_recording_without_space_prefers_unspaced_inherited_geometry(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    unspaced, _ = _write_geometry(
        recording.parent,
        "sub-01_task-rest_",
        rows=(("Cz", "0.1", "0", "0"),),
    )
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_space-CapTrak_",
        rows=(("Cz", "0.2", "0", "0"),),
    )

    snapshot = _prepare(recording)

    assert snapshot.state == "ready"
    assert snapshot.recordings[0].positions_m == ((0.1, 0.0, 0.0),)
    assert snapshot.recordings[0].provenance[0].path == str(unspaced.resolve())


def test_na_positions_are_explicit_without_discarding_valid_geometry(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0", "1", "0"), ("EOG", "n/a", "n/a", "n/a")),
    )

    snapshot = _prepare(recording, ("Cz", "EOG"))

    assert snapshot.state == "ready"
    assert snapshot.recordings[0].channel_names == ("Cz",)
    assert snapshot.recordings[0].unpositioned_channel_names == ("EOG",)


def test_recording_channels_without_electrode_rows_remain_explicit_and_nonblocking(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0", "1", "0"),),
    )

    snapshot = _prepare(recording, ("Cz", "EOG"))

    assert snapshot.state == "ready"
    assert snapshot.aggregate.compatible is True
    assert snapshot.aggregate.channel_names == ("Cz",)
    assert snapshot.recordings[0].channel_names == ("Cz",)
    assert snapshot.recordings[0].unpositioned_channel_names == ("EOG",)
    assert snapshot.recordings[0].missing_channel_names == ("EOG",)


@pytest.mark.parametrize(
    ("rows", "reason_fragment"),
    [
        ((("Cz", "0", "0", "0"), ("Cz", "1", "0", "0")), "unique"),
        ((("Cz", "nan", "0", "0"),), "finite"),
        ((("Cz", "0", "n/a", "0"),), "all coordinates"),
    ],
)
def test_malformed_electrode_rows_fail_without_partial_publication(
    tmp_path: Path,
    rows: tuple[tuple[str, str, str, str], ...],
    reason_fragment: str,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=rows,
    )

    snapshot = _prepare(recording)

    assert snapshot.state == "failed"
    assert snapshot.recordings[0].state == "failed"
    assert reason_fragment in (snapshot.reason or "").lower()
    assert len(snapshot.recordings[0].provenance) == 2
    assert snapshot.aggregate.compatible is False
    assert snapshot.aggregate.positions_m == ()


def test_unknown_coordinate_frame_is_unavailable_and_non_blocking(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0", "0", "1"),),
        coordinate_system="Other",
    )

    snapshot = _prepare(recording)

    assert snapshot.state == "unavailable"
    assert snapshot.recordings[0].state == "unavailable"
    assert "not safe" in (snapshot.reason or "").lower()
    assert snapshot.import_blocking is False


def test_ctf_coordinates_are_not_misrepresented_as_head_coordinates(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0", "0", "1"),),
        coordinate_system="CTF",
    )

    snapshot = _prepare(recording)

    assert snapshot.state == "unavailable"
    assert snapshot.recordings[0].coordinate_frame is None
    assert "transform" in (snapshot.reason or "").lower()


def test_only_eeg_channels_are_targets_and_extra_electrodes_are_diagnostic(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(
            ("Cz", "0", "1", "0"),
            ("REF", "0", "0", "1"),
            ("GND", "0", "0", "-1"),
        ),
    )

    snapshot = _prepare(
        recording,
        ("Cz", "EOG1", "Trigger"),
        channel_types=("eeg", "eog", "stim"),
    )

    assert snapshot.state == "ready"
    prepared = snapshot.recordings[0]
    assert prepared.channel_names == ("Cz",)
    assert prepared.missing_channel_names == ()
    assert prepared.unpositioned_channel_names == ()
    assert prepared.unexpected_channel_names == ("REF", "GND")


def test_two_dimensional_eeg_coordinates_support_topomap_but_not_3d(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(
            ("F3", "-1", "1", "n/a"),
            ("F4", "1", "1", "n/a"),
            ("Pz", "0", "-1", "n/a"),
        ),
    )

    snapshot = _prepare(recording, ("F3", "F4", "Pz"))

    assert snapshot.state == "ready"
    assert snapshot.aggregate.coordinate_dimension == 2
    assert snapshot.aggregate.supports_topographic is True
    assert snapshot.aggregate.supports_three_dimensional is False
    assert snapshot.aggregate.positions_m == (
        (-1.0, 1.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, -1.0, 0.0),
    )


def test_channel_mapping_mismatch_is_unavailable_not_silently_normalized(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(("CZ", "0", "0", "1"),),
    )

    snapshot = _prepare(recording, ("Cz",))

    assert snapshot.state == "unavailable"
    assert snapshot.recordings[0].missing_channel_names == ("Cz",)
    assert snapshot.recordings[0].unexpected_channel_names == ("CZ",)
    assert "channel mapping" in (snapshot.reason or "").lower()


@pytest.mark.parametrize("second_x", ["0.1", "0.2"])
def test_aggregate_geometry_is_exposed_only_when_all_recordings_match(
    tmp_path: Path,
    second_x: str,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    first = _write_recording(root, "01")
    second = _write_recording(root, "02")
    _write_geometry(
        first.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0.1", "0", "0"),),
    )
    _write_geometry(
        second.parent,
        "sub-02_task-rest_run-1_",
        rows=(("Cz", second_x, "0", "0"),),
    )

    snapshot = prepare_bids_montage(
        (
            BidsMontageRecordingRequest(str(first), ("Cz",)),
            BidsMontageRecordingRequest(str(second), ("Cz",)),
        ),
        generation=7,
    )

    expected_compatible = second_x == "0.1"
    assert snapshot.aggregate.compatible is expected_compatible
    if expected_compatible:
        assert snapshot.state == "ready"
        assert snapshot.aggregate.positions_m == ((0.1, 0.0, 0.0),)
    else:
        assert snapshot.state == "unavailable"
        assert snapshot.aggregate.positions_m == ()
        assert "differ" in (snapshot.aggregate.reason or "").lower()
        assert snapshot.recordings[0].positions_m == ((0.1, 0.0, 0.0),)
        assert snapshot.recordings[1].positions_m == ((0.2, 0.0, 0.0),)


def test_missing_bids_resources_are_non_blocking_unavailable(tmp_path: Path) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")

    snapshot = _prepare(recording)

    assert snapshot.state == "unavailable"
    assert snapshot.import_blocking is False
    assert "not found" in (snapshot.reason or "").lower()


def test_lifecycle_rejects_stale_results_after_import_reset_and_manual_override(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    first_recording = _write_recording(root, "01")
    second_recording = _write_recording(root, "02")
    for recording, subject in ((first_recording, "01"), (second_recording, "02")):
        _write_geometry(
            recording.parent,
            f"sub-{subject}_task-rest_run-1_",
            rows=(("Cz", "0.1", "0", "0"),),
        )

    lifecycle = MontagePreparationLifecycle()
    first = lifecycle.begin(
        (BidsMontageRecordingRequest(str(first_recording), ("Cz",)),)
    )
    assert lifecycle.snapshot().state == "pending"
    first_result = prepare_bids_montage(
        first.recordings,
        generation=first.generation,
    )

    second = lifecycle.begin(
        (BidsMontageRecordingRequest(str(second_recording), ("Cz",)),)
    )
    stale_import = lifecycle.publish(first, first_result)
    assert stale_import.accepted is False
    assert stale_import.reason == "stale_generation"
    assert lifecycle.snapshot().generation == second.generation
    assert lifecycle.snapshot().state == "pending"

    second_result = prepare_bids_montage(
        second.recordings,
        generation=second.generation,
    )
    lifecycle.reset()
    stale_reset = lifecycle.publish(second, second_result)
    assert stale_reset.accepted is False
    assert lifecycle.snapshot().state == "not_applicable"

    third = lifecycle.begin(
        (BidsMontageRecordingRequest(str(first_recording), ("Cz",)),)
    )
    third_result = prepare_bids_montage(
        third.recordings,
        generation=third.generation,
    )
    lifecycle.select_manual(
        ManualMontageOverride(
            name="standard_1020",
            channel_names=("Cz",),
            positions_m=((0.0, 0.0, 0.1),),
            coordinate_frame="head",
        )
    )
    stale_manual = lifecycle.publish(third, third_result)
    assert stale_manual.accepted is False
    effective = lifecycle.effective_montage()
    assert effective is not None
    assert effective.source == "manual"
    assert effective.name == "standard_1020"
    assert effective.positions_m == ((0.0, 0.0, 0.1),)


def test_manual_override_has_explicit_precedence_over_ready_bids_geometry(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _write_bids_dataset(root)
    recording = _write_recording(root, "01")
    _write_geometry(
        recording.parent,
        "sub-01_task-rest_run-1_",
        rows=(("Cz", "0.1", "0", "0"),),
    )
    lifecycle = MontagePreparationLifecycle()
    work = lifecycle.begin((BidsMontageRecordingRequest(str(recording), ("Cz",)),))
    result = prepare_bids_montage(work.recordings, generation=work.generation)
    assert lifecycle.publish(work, result).accepted is True
    assert lifecycle.effective_montage().source == "bids"  # type: ignore[union-attr]

    lifecycle.select_manual(
        ManualMontageOverride(
            name="manual",
            channel_names=("Cz",),
            positions_m=((0.0, 0.1, 0.0),),
            coordinate_frame="head",
        )
    )

    effective = lifecycle.effective_montage()
    assert effective is not None
    assert effective.source == "manual"
    assert effective.positions_m == ((0.0, 0.1, 0.0),)
