from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

import scripts.dev.fetch_public_eeg_fixtures as fixture_fetcher
from scripts.dev.fetch_public_eeg_fixtures import (
    CI_REQUIRED_GROUP_NAMES,
    CI_REQUIRED_MAX_BYTES,
    DEFAULT_FIXTURE_PROFILE,
    MNE_BIDS_TINY_ENTRYPOINT,
    MNE_BIDS_TINY_NAME,
    MNE_BIDS_TINY_REVISION,
    MNE_TESTING_DATA_REVISION,
    OPENNEURO_P300_MULTISUBJECT_NAME,
    OPENNEURO_P300_NAME,
    OPENNEURO_P300_VERSION,
    P300_MULTISUBJECT_GROUP_NAMES,
    P300_MULTISUBJECT_MAX_BYTES,
    TEACHER_PREFLIGHT_GROUP_NAMES,
    TEACHER_PREFLIGHT_MAX_BYTES,
    FixtureFile,
    FixtureGroup,
    _mne_bids_tiny_downloads,
    _openneuro_p300_downloads,
    _openneuro_p300_multisubject_downloads,
    download_fixture_file,
    fixture_file_is_valid,
    fixture_groups_for_profile,
    fixture_profile_size_bytes,
    sha256_file,
    validate_fixture_set,
)


def test_mne_bids_tiny_downloads_are_pinned_external_bids_files():
    downloads = _mne_bids_tiny_downloads()
    filenames = {download["filename"] for download in downloads}

    assert MNE_BIDS_TINY_ENTRYPOINT in filenames
    assert f"{MNE_BIDS_TINY_NAME}/dataset_description.json" in filenames
    assert f"{MNE_BIDS_TINY_NAME}/participants.tsv" in filenames
    assert (
        f"{MNE_BIDS_TINY_NAME}/sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_events.tsv"
    ) in filenames
    assert (
        f"{MNE_BIDS_TINY_NAME}/sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_channels.tsv"
    ) in filenames
    assert all(
        download["filename"].startswith(f"{MNE_BIDS_TINY_NAME}/")
        for download in downloads
    )
    assert all(
        f"/mne-tools/mne-bids/{MNE_BIDS_TINY_REVISION}/" in download["url"]
        for download in downloads
    )
    assert all(
        download["sha256"] and len(download["sha256"]) == 64 for download in downloads
    )


def test_fixture_file_is_valid_rejects_empty_or_hash_mismatch(tmp_path: Path):
    fixture = tmp_path / "fixture.edf"
    fixture.write_bytes(b"fixture")
    expected = sha256_file(fixture)

    assert fixture_file_is_valid(fixture, expected) is True
    assert fixture_file_is_valid(fixture, "0" * 64) is False

    fixture.write_bytes(b"")
    assert fixture_file_is_valid(fixture, expected) is False


def test_required_ci_profile_is_small_pinned_and_source_diverse():
    groups = fixture_groups_for_profile("required-ci")

    assert {str(group["name"]) for group in groups} == set(CI_REQUIRED_GROUP_NAMES)
    assert {
        "physionet-edf-motor",
        "bbci-gdf",
        "sccn-eeglab",
        "mne-testing-cnt",
        "mne-testing-brainvision",
        MNE_BIDS_TINY_NAME,
        OPENNEURO_P300_NAME,
    }.issubset(CI_REQUIRED_GROUP_NAMES)
    assert 0 < fixture_profile_size_bytes(groups) <= CI_REQUIRED_MAX_BYTES
    assert all(
        int(fixture_file["size_bytes"]) > 0
        for group in groups
        for fixture_file in group["files"]
    )


def test_required_ci_profile_rejects_incomplete_manifest(
    monkeypatch: pytest.MonkeyPatch,
):
    groups = copy.deepcopy(fixture_fetcher.FIXTURE_GROUPS)
    brainvision = next(
        group for group in groups if group["name"] == "mne-testing-brainvision"
    )
    brainvision["files"] = [
        fixture_file
        for fixture_file in brainvision["files"]
        if fixture_file["filename"] != "test_NO.vmrk"
    ]
    monkeypatch.setattr(fixture_fetcher, "FIXTURE_GROUPS", groups)

    with pytest.raises(RuntimeError, match="stale or incomplete"):
        fixture_groups_for_profile("required-ci")


def test_required_ci_profile_rejects_stale_manifest_pin(
    monkeypatch: pytest.MonkeyPatch,
):
    groups = copy.deepcopy(fixture_fetcher.FIXTURE_GROUPS)
    motor = next(group for group in groups if group["name"] == "physionet-edf-motor")
    motor["files"][0]["sha256"] = "0" * 64
    monkeypatch.setattr(fixture_fetcher, "FIXTURE_GROUPS", groups)

    with pytest.raises(RuntimeError, match="stale or incomplete"):
        fixture_groups_for_profile("required-ci")


def test_teacher_preflight_profile_adds_independent_real_dataset_models():
    required_groups = fixture_groups_for_profile("required-ci")
    teacher_groups = fixture_groups_for_profile("teacher-preflight")
    teacher_names = {str(group["name"]) for group in teacher_groups}

    assert teacher_names == set(TEACHER_PREFLIGHT_GROUP_NAMES)
    assert {
        OPENNEURO_P300_NAME,
        "chbmit-chb01",
        "sleep-edfx-st7011",
    }.issubset(teacher_names)
    assert fixture_profile_size_bytes(teacher_groups) > fixture_profile_size_bytes(
        required_groups
    )
    assert fixture_profile_size_bytes(teacher_groups) <= TEACHER_PREFLIGHT_MAX_BYTES
    assert len(teacher_groups) == 10
    assert fixture_profile_size_bytes(teacher_groups) == 277_106_963


def test_default_download_profile_stays_within_compact_ci_boundary() -> None:
    assert DEFAULT_FIXTURE_PROFILE == "required-ci"
    assert (
        fixture_profile_size_bytes(fixture_groups_for_profile(DEFAULT_FIXTURE_PROFILE))
        <= CI_REQUIRED_MAX_BYTES
    )


def test_openneuro_p300_manifest_contains_three_paired_bids_runs():
    downloads = _openneuro_p300_downloads()
    filenames = {download["filename"] for download in downloads}

    assert f"{OPENNEURO_P300_NAME}/dataset_description.json" in filenames
    for run in (1, 2, 3):
        prefix = f"{OPENNEURO_P300_NAME}/sub-001/eeg/sub-001_task-P300_run-{run}"
        assert f"{prefix}_eeg.set" in filenames
        assert f"{prefix}_events.tsv" in filenames
        assert f"{prefix}_channels.tsv" in filenames
    assert all(
        download["url"].startswith("https://s3.amazonaws.com/openneuro.org/ds003061/")
        for download in downloads
    )
    assert all(len(download["sha256"]) == 64 for download in downloads)
    openneuro_group = next(
        group
        for group in fixture_groups_for_profile("teacher-preflight")
        if group["name"] == OPENNEURO_P300_NAME
    )
    assert OPENNEURO_P300_VERSION == "1.1.2"
    assert OPENNEURO_P300_VERSION in openneuro_group["source"]


def test_p300_multisubject_profile_adds_two_complete_subjects_without_expanding_ci():
    required_groups = fixture_groups_for_profile("required-ci")
    multisubject_groups = fixture_groups_for_profile("p300-multisubject")
    multisubject_names = {str(group["name"]) for group in multisubject_groups}
    downloads = _openneuro_p300_multisubject_downloads()
    filenames = {download["filename"] for download in downloads}

    assert multisubject_names == set(P300_MULTISUBJECT_GROUP_NAMES)
    assert OPENNEURO_P300_MULTISUBJECT_NAME not in {
        str(group["name"]) for group in required_groups
    }
    for subject in ("002", "003"):
        for run in (1, 2, 3):
            prefix = (
                f"{OPENNEURO_P300_NAME}/sub-{subject}/eeg/"
                f"sub-{subject}_task-P300_run-{run}"
            )
            assert f"{prefix}_eeg.set" in filenames
            assert f"{prefix}_events.tsv" in filenames
            assert f"{prefix}_channels.tsv" in filenames
            assert f"{prefix}_eeg.json" in filenames
    assert all(len(download["sha256"]) == 64 for download in downloads)
    assert fixture_profile_size_bytes(multisubject_groups) > fixture_profile_size_bytes(
        required_groups
    )
    assert (
        fixture_profile_size_bytes(multisubject_groups) <= P300_MULTISUBJECT_MAX_BYTES
    )


def test_mne_testing_data_downloads_are_pinned_to_revision():
    mne_groups = [
        group
        for group in fixture_groups_for_profile("required-ci")
        if str(group["name"]).startswith("mne-testing-")
    ]

    assert mne_groups
    assert all(
        f"/mne-tools/mne-testing-data/{MNE_TESTING_DATA_REVISION}/"
        in str(fixture_file["url"])
        for group in mne_groups
        for fixture_file in group["files"]
    )


def test_validate_fixture_set_rejects_missing_and_corrupt_files(tmp_path: Path):
    payload = b"small-public-eeg-fixture"
    fixture_file: FixtureFile = {
        "filename": "fixture.edf",
        "url": "https://physionet.org/fixture.edf",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }
    groups: list[FixtureGroup] = [
        {
            "name": "test",
            "description": "test fixture",
            "source": "unit test",
            "entrypoint": fixture_file["filename"],
            "files": [fixture_file],
        }
    ]

    with pytest.raises(FileNotFoundError, match=r"fixture\.edf"):
        validate_fixture_set(tmp_path, groups)

    (tmp_path / "fixture.edf").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match=r"(?:size|hash) mismatch"):
        validate_fixture_set(tmp_path, groups)

    (tmp_path / "fixture.edf").write_bytes(payload)
    validate_fixture_set(tmp_path, groups)


def test_download_fixture_file_keeps_previous_file_when_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    destination = tmp_path / "fixture.edf"
    destination.write_bytes(b"known-good-cache")
    expected = b"expected"
    fixture_file: FixtureFile = {
        "filename": destination.name,
        "url": "https://physionet.org/fixture.edf",
        "sha256": hashlib.sha256(expected).hexdigest(),
        "size_bytes": len(expected),
    }

    def _write_corrupt_download(
        _url: str,
        temporary_path: Path,
        *,
        max_bytes: int,
    ) -> None:
        assert max_bytes == len(expected)
        temporary_path.write_bytes(b"bad")

    monkeypatch.setattr(fixture_fetcher, "download_file", _write_corrupt_download)

    with pytest.raises(ValueError, match=r"(?:size|hash) mismatch"):
        download_fixture_file(fixture_file, destination)

    assert destination.read_bytes() == b"known-good-cache"
    assert not destination.with_name(f"{destination.name}.part").exists()


def test_required_ci_verify_only_fails_when_fixture_cache_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(fixture_fetcher, "PUBLIC_DIR", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fetch_public_eeg_fixtures.py",
            "--profile",
            "required-ci",
            "--verify-only",
        ],
    )

    with pytest.raises(FileNotFoundError, match=r"Downloaded fixture is missing"):
        fixture_fetcher.main()
