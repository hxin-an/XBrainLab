from __future__ import annotations

from pathlib import Path

from scripts.dev.fetch_public_eeg_fixtures import (
    create_tiny_bids_eeg_fixture,
    fixture_file_is_valid,
    sha256_file,
)


def _write_brainvision_sources(root: Path) -> None:
    source_dir = root / "tests" / "fixtures" / "data" / "multiformat"
    source_dir.mkdir(parents=True)
    (source_dir / "A01T-mini-real.eeg").write_bytes(b"binary-eeg")
    (source_dir / "A01T-mini-real.vhdr").write_text(
        "Brain Vision Data Exchange Header File Version 1.0\n"
        "[Common Infos]\n"
        "DataFile=A01T-mini-real.eeg\n"
        "MarkerFile=A01T-mini-real.vmrk\n",
        encoding="utf-8",
    )
    (source_dir / "A01T-mini-real.vmrk").write_text(
        "Brain Vision Data Exchange Marker File, Version 1.0\n"
        "[Common Infos]\n"
        "DataFile=A01T-mini-real.eeg\n",
        encoding="utf-8",
    )


def test_create_tiny_bids_eeg_fixture_writes_bids_sidecars(tmp_path: Path):
    repo_root = tmp_path / "repo"
    public_dir = tmp_path / "public"
    _write_brainvision_sources(repo_root)

    create_tiny_bids_eeg_fixture(public_dir=public_dir, repo_root=repo_root)

    eeg_dir = public_dir / "tiny-bids-eeg" / "sub-01" / "ses-01" / "eeg"
    vhdr = eeg_dir / "sub-01_ses-01_task-mi_run-1_eeg.vhdr"
    vmrk = eeg_dir / "sub-01_ses-01_task-mi_run-1_eeg.vmrk"
    eeg = eeg_dir / "sub-01_ses-01_task-mi_run-1_eeg.eeg"
    events = eeg_dir / "sub-01_ses-01_task-mi_run-1_events.tsv"
    channels = eeg_dir / "sub-01_ses-01_task-mi_run-1_channels.tsv"

    assert eeg.read_bytes() == b"binary-eeg"
    assert "DataFile=sub-01_ses-01_task-mi_run-1_eeg.eeg" in vhdr.read_text(
        encoding="utf-8"
    )
    assert "MarkerFile=sub-01_ses-01_task-mi_run-1_eeg.vmrk" in vhdr.read_text(
        encoding="utf-8"
    )
    assert "DataFile=sub-01_ses-01_task-mi_run-1_eeg.eeg" in vmrk.read_text(
        encoding="utf-8"
    )
    assert "trial_type" in events.read_text(encoding="utf-8")
    assert "status" in channels.read_text(encoding="utf-8")
    assert (public_dir / "tiny-bids-eeg" / "dataset_description.json").exists()
    assert (public_dir / "tiny-bids-eeg" / "participants.tsv").exists()


def test_fixture_file_is_valid_rejects_empty_or_hash_mismatch(tmp_path: Path):
    fixture = tmp_path / "fixture.edf"
    fixture.write_bytes(b"fixture")
    expected = sha256_file(fixture)

    assert fixture_file_is_valid(fixture, expected) is True
    assert fixture_file_is_valid(fixture, "0" * 64) is False

    fixture.write_bytes(b"")
    assert fixture_file_is_valid(fixture, expected) is False
