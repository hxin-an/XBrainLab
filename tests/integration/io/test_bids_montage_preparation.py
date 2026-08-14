"""Real-fixture coverage for generic BIDS montage preparation."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.dev.fetch_public_eeg_fixtures import resolve_public_fixture_dir
from XBrainLab.backend.application.bids_montage_preparation import (
    BidsMontageRecordingRequest,
    prepare_bids_montage,
    resolve_bids_montage_resource_paths,
)

pytestmark = pytest.mark.optional_public_fixture


def _public_fixtures() -> Path:
    return resolve_public_fixture_dir()


def test_public_fixture_root_follows_configured_dataset_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XBRAINLAB_DATA_DIR", str(tmp_path))

    assert _public_fixtures() == tmp_path / "datasets" / "public-fixtures"


def _channel_info(path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(csv.DictReader(handle, delimiter="\t"))
    return (
        tuple(str(row["name"]) for row in rows),
        tuple(str(row["type"]) for row in rows),
    )


def _require_fixture(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"public BIDS fixture is not installed: {path}")
    return path.resolve()


def test_mne_bids_tiny_resolves_captrak_geometry_and_explicit_na_rows() -> None:
    eeg_dir = _public_fixtures() / "mne-bids-tiny-eeg/sub-01/ses-eeg/eeg"
    recording = _require_fixture(eeg_dir / "sub-01_ses-eeg_task-rest_eeg.vhdr")
    channels = _require_fixture(eeg_dir / "sub-01_ses-eeg_task-rest_channels.tsv")
    channel_names, channel_types = _channel_info(channels)

    resources = resolve_bids_montage_resource_paths(recording)
    snapshot = prepare_bids_montage(
        (
            BidsMontageRecordingRequest(
                str(recording),
                channel_names,
                channel_types,
            ),
        ),
        generation=11,
    )

    assert len(resources) == 2
    assert resources[0].endswith("sub-01_ses-eeg_electrodes.tsv")
    assert resources[1].endswith("sub-01_ses-eeg_coordsystem.json")
    assert snapshot.state == "ready"
    prepared = snapshot.recordings[0]
    assert prepared.coordinate_system == "CapTrak"
    assert prepared.coordinate_frame == "head"
    assert prepared.coordinate_units == "m"
    assert prepared.source_coordinate_units == "m"
    assert prepared.channel_names[:3] == ("Fp1", "Fp2", "F7")
    assert prepared.unpositioned_channel_names == ()
    assert prepared.unexpected_channel_names == ()
    assert prepared.positions_m[0][0] == pytest.approx(-0.03741270038437644)
    assert snapshot.aggregate.compatible is True


def test_openneuro_ctf_geometry_requires_verified_head_transform() -> None:
    root = _public_fixtures() / "openneuro-ds003061-p300"
    requests: list[BidsMontageRecordingRequest] = []
    for subject in ("001", "002"):
        eeg_dir = root / f"sub-{subject}" / "eeg"
        stem = f"sub-{subject}_task-P300_run-1"
        recording = _require_fixture(eeg_dir / f"{stem}_eeg.set")
        channels = _require_fixture(eeg_dir / f"{stem}_channels.tsv")
        channel_names, channel_types = _channel_info(channels)
        requests.append(
            BidsMontageRecordingRequest(
                str(recording),
                channel_names,
                channel_types,
            )
        )

    snapshot = prepare_bids_montage(tuple(requests), generation=12)

    assert snapshot.state == "unavailable"
    assert len(snapshot.recordings) == 2
    assert snapshot.aggregate.compatible is False
    assert snapshot.aggregate.positions_m == ()
    assert all(item.positions_m == () for item in snapshot.recordings)
    assert "verified transform" in (snapshot.reason or "")
    assert {
        tuple(item.path for item in recording.provenance)
        for recording in snapshot.recordings
    } == {
        (
            str(
                (
                    root
                    / f"sub-{subject}"
                    / "eeg"
                    / f"sub-{subject}_task-P300_run-1_electrodes.tsv"
                ).resolve()
            ),
            str(
                (
                    root
                    / f"sub-{subject}"
                    / "eeg"
                    / f"sub-{subject}_task-P300_run-1_coordsystem.json"
                ).resolve()
            ),
        )
        for subject in ("001", "002")
    }
