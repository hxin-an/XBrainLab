from __future__ import annotations

from pathlib import Path

from scripts.dev.report_dataset_validation_matrix import (
    build_dataset_validation_rows,
    build_snapshot,
    render_markdown,
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
        / "tiny-bids-eeg"
        / "sub-01"
        / "ses-01"
        / "eeg"
        / "sub-01_ses-01_task-mi_run-1_eeg.vhdr"
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
    assert rows[4].layer == "public local-only BIDS-like EEG fixture"
    assert rows[4].representative_data == "BIDS-like EEG"
    assert rows[4].label_attach == "BIDS events.tsv"
    assert rows[2].reproducibility_class == "local-only"
    assert rows[3].reproducibility_class == "local-only"
    assert rows[4].reproducibility_class == "local-only generated"


def test_render_markdown_includes_current_truth(tmp_path: Path):
    _touch(tmp_path / "tests" / "fixtures" / "data" / "A01T.gdf")
    _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / "A01T.mat")

    snapshot = build_snapshot(tmp_path)
    rendered = render_markdown(snapshot)

    assert snapshot["tests_data_dir"] == str(tmp_path / "tests" / "fixtures" / "data")
    assert "# Dataset Validation Matrix" in rendered
    assert "checked-in core GDF + MAT" in rendered
    assert "public local-only event-rich fixtures" in rendered
    assert "public local-only BIDS-like EEG fixture" in rendered
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
