from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

import scripts.dev.fetch_public_eeg_fixtures as fixture_fetcher
from scripts.dev.fetch_public_eeg_fixtures import (
    CI_REQUIRED_GROUP_NAMES,
    CI_REQUIRED_MAX_BYTES,
    MNE_BIDS_TINY_ENTRYPOINT,
    MNE_BIDS_TINY_NAME,
    MNE_BIDS_TINY_REVISION,
    MNE_TESTING_DATA_REVISION,
    FixtureFile,
    FixtureGroup,
    _mne_bids_tiny_downloads,
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
    }.issubset(CI_REQUIRED_GROUP_NAMES)
    assert 0 < fixture_profile_size_bytes(groups) <= CI_REQUIRED_MAX_BYTES
    assert all(
        int(fixture_file["size_bytes"]) > 0
        for group in groups
        for fixture_file in group["files"]
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
