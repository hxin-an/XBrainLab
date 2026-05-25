from __future__ import annotations

from pathlib import Path

from scripts.dev.fetch_public_eeg_fixtures import (
    MNE_BIDS_TINY_ENTRYPOINT,
    MNE_BIDS_TINY_NAME,
    MNE_BIDS_TINY_REVISION,
    _mne_bids_tiny_downloads,
    fixture_file_is_valid,
    sha256_file,
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
