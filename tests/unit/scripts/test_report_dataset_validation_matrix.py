from __future__ import annotations

from pathlib import Path

from scripts.dev.report_dataset_validation_matrix import (
    build_dataset_validation_rows,
    build_snapshot,
    render_markdown,
    validate_required_dataset_matrix,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture", encoding="utf-8")


def test_build_dataset_validation_rows_reports_checked_in_and_public_layers(
    tmp_path: Path,
):
    _touch(tmp_path / "tests" / "fixtures" / "data" / "A01T.gdf")
    _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / "A01T.mat")
    _touch(
        tmp_path / "tests" / "fixtures" / "data" / "multiformat" / "A01T-mini-real.edf"
    )
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "physionet-eegmmidb-S008R01.edf"
    )
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "physionet-eegmmidb-S008R04.edf"
    )
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "bbci-competition-iii-O3VR.gdf"
    )
    _touch(tmp_path / "tests" / "fixtures" / "data" / "public" / "sccn-eeglab_data.set")
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "mne-bids-tiny-eeg"
        / "sub-01"
        / "ses-eeg"
        / "eeg"
        / "sub-01_ses-eeg_task-rest_eeg.vhdr"
    )

    rows = build_dataset_validation_rows(tmp_path)

    assert rows[0].layer == "checked-in core GDF + MAT"
    assert rows[0].representative_data == "A01T"
    assert rows[0].training_smoke == "yes (1 stems)"
    assert rows[1].layer == "checked-in compact multiformat"
    assert rows[1].representative_data == "1 derived files from A01T"
    assert rows[2].layer == "public local-only event-rich fixtures"
    assert rows[2].training_smoke == "yes (3 fixtures)"
    assert "BBCI" in rows[2].source_families
    assert "PhysioNet" in rows[2].source_families
    assert rows[3].layer == "public local-only import-only fixtures"
    assert "PhysioNet" in rows[3].source_families
    assert rows[4].layer == "public local-only BIDS EEG fixture"
    assert rows[4].representative_data == "BIDS EEG"
    assert rows[4].label_attach == "BIDS events.tsv"
    assert rows[2].reproducibility_class == "local-only"
    assert rows[3].reproducibility_class == "local-only"
    assert rows[4].reproducibility_class == "local-only downloaded"


def test_render_markdown_includes_current_truth(tmp_path: Path):
    _touch(tmp_path / "tests" / "fixtures" / "data" / "A01T.gdf")
    _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / "A01T.mat")

    snapshot = build_snapshot(tmp_path)
    rendered = render_markdown(snapshot)

    assert snapshot["tests_data_dir"] == str(tmp_path / "tests" / "fixtures" / "data")
    assert "# Dataset Validation Matrix" in rendered
    assert "checked-in core GDF + MAT" in rendered
    assert "public local-only event-rich fixtures" in rendered
    assert "public local-only BIDS EEG fixture" in rendered
    assert "Required Hand-Test Dataset Gate" in rendered
    assert "event-rich public local-only fixtures" in rendered
    assert "cross-source evidence is stronger" in rendered.lower()


def test_dataset_validation_rows_ignore_empty_public_fixture(tmp_path: Path):
    public_dir = tmp_path / "tests" / "fixtures" / "data" / "public"
    public_dir.mkdir(parents=True)
    (public_dir / "physionet-eegmmidb-S008R04.edf").write_bytes(b"")

    rows = build_dataset_validation_rows(tmp_path)

    assert rows[2].layer == "public local-only event-rich fixtures"
    assert rows[2].representative_data == "not downloaded"
    assert rows[2].training_smoke == "pending"


def test_required_dataset_matrix_passes_only_with_source_diverse_fixtures(
    tmp_path: Path,
):
    for stem in ("A01T", "A02T", "A03T"):
        _touch(tmp_path / "tests" / "fixtures" / "data" / f"{stem}.gdf")
        _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / f"{stem}.mat")
    for filename in (
        "A01T-mini-real_raw.fif",
        "A01T-mini-real_raw.fif.gz",
        "A01T-mini-real-epo.fif",
        "A01T-mini-real.edf",
        "A01T-mini-real.bdf",
        "A01T-mini-real.vhdr",
        "A01T-mini-real.eeg",
        "A01T-mini-real.vmrk",
        "A01T-mini-real.set",
    ):
        _touch(tmp_path / "tests" / "fixtures" / "data" / "multiformat" / filename)
    for filename in (
        "physionet-eegmmidb-S008R04.edf",
        "bbci-competition-iii-O3VR.gdf",
        "sccn-eeglab_data.set",
    ):
        _touch(tmp_path / "tests" / "fixtures" / "data" / "public" / filename)
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "mne-bids-tiny-eeg"
        / "sub-01"
        / "ses-eeg"
        / "eeg"
        / "sub-01_ses-eeg_task-rest_eeg.vhdr"
    )

    requirements = validate_required_dataset_matrix(tmp_path)

    assert [requirement.key for requirement in requirements] == [
        "checked_in_gdf_mat",
        "compact_multiformat",
        "public_event_rich_sources",
        "public_bids_eeg",
    ]
    assert all(requirement.ok for requirement in requirements)


def test_required_dataset_matrix_rejects_single_source_only(tmp_path: Path):
    _touch(tmp_path / "tests" / "fixtures" / "data" / "A01T.gdf")
    _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / "A01T.mat")
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "physionet-eegmmidb-S008R04.edf"
    )

    requirements = validate_required_dataset_matrix(tmp_path)
    by_key = {requirement.key: requirement for requirement in requirements}

    assert by_key["checked_in_gdf_mat"].ok is False
    assert by_key["compact_multiformat"].ok is False
    assert by_key["public_event_rich_sources"].ok is False
    assert by_key["public_bids_eeg"].ok is False
