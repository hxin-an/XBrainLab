from XBrainLab.backend.application.data_interpretation_pairing import (
    resolve_label_file_pairing,
)


def test_pairing_accepts_single_generic_carrier_for_single_eeg() -> None:
    result = resolve_label_file_pairing(
        [{"path": "/labels/events.tsv"}],
        ["/data/sub-01_task-mi_raw.fif"],
    )

    assert result.complete is True
    assert result.file_mapping == {"/data/sub-01_task-mi_raw.fif": "/labels/events.tsv"}


def test_pairing_matches_run_specific_bids_events_by_stem() -> None:
    result = resolve_label_file_pairing(
        [
            {"path": "/bids/sub-01_task-mi_run-1_events.tsv"},
            {"path": "/bids/sub-01_task-mi_run-2_events.tsv"},
        ],
        [
            "/bids/sub-01_task-mi_run-1_eeg.vhdr",
            "/bids/sub-01_task-mi_run-2_eeg.vhdr",
        ],
    )

    assert result.complete is True
    assert result.matched_count == 2


def test_pairing_reports_unmatched_eeg_after_partial_manual_mapping() -> None:
    result = resolve_label_file_pairing(
        [
            {
                "path": "/labels/events.tsv",
                "selected_target_file": "run-2_raw.fif",
            }
        ],
        ["/data/run-1_raw.fif", "/data/run-2_raw.fif"],
    )

    assert result.complete is False
    assert result.unmatched_eeg_files == ("/data/run-1_raw.fif",)
    assert "1/2 selected EEG files are paired" in result.blocking_reason()


def test_pairing_rejects_two_carriers_targeting_the_same_eeg() -> None:
    result = resolve_label_file_pairing(
        [
            {"path": "/labels/a.tsv", "selected_target_file": "run-1_raw.fif"},
            {"path": "/labels/b.tsv", "selected_target_file": "run-1_raw.fif"},
        ],
        ["/data/run-1_raw.fif"],
    )

    assert result.complete is False
    assert result.errors == (
        "Multiple reviewed label carriers target the same EEG file.",
    )
