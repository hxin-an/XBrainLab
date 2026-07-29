"""Strict local BIDS channels.tsv review and apply tests."""

from __future__ import annotations

from pathlib import Path

import mne
import numpy as np
import pytest
from mne.io.constants import FIFF

from XBrainLab.backend.application.data_interpretation_bids_channels import (
    apply_bids_channel_review,
    review_bids_channel_sidecars,
)
from XBrainLab.backend.load_data.raw import Raw


def test_review_marks_missing_required_columns_as_ready_with_warnings(
    tmp_path: Path,
) -> None:
    eeg = tmp_path / "sub-01_task-mi_run-1_eeg.fif"
    channels = tmp_path / "sub-01_task-mi_run-1_channels.tsv"
    channels.write_text(
        "name\tstatus\tstatus_description\nC3\tgood\tn/a\nC4\tbad\tflat\n",
        encoding="utf-8",
    )

    review = review_bids_channel_sidecars(
        bids={
            "is_bids": True,
            "layout": [
                {
                    "file": str(eeg),
                    "channels_file": str(channels),
                }
            ],
        },
        selected_eeg_files=[str(eeg)],
    )

    assert review.status == "ready_with_warnings"
    assert review.blocked_reasons == []
    assert len(review.warnings) == 1
    run = review.runs[0]
    assert run["eeg_file"] == str(eeg.resolve())
    assert run["channels_file"] == str(channels.resolve())
    assert run["status"] == "ready_with_warnings"
    assert run["channel_count"] == 2
    assert run["channel_statuses"] == {"C3": "good", "C4": "bad"}
    assert run["channel_types"] == {"C3": "unspecified", "C4": "unspecified"}
    assert run["channel_units"] == {"C3": "unspecified", "C4": "unspecified"}
    assert run["missing_type_channels"] == ["C3", "C4"]
    assert run["missing_unit_channels"] == ["C3", "C4"]
    assert run["missing_required_columns"] == ["type", "units"]
    assert run["bad_channels"] == ["C4"]
    assert len(run["status_identity"]) == 64
    assert len(run["semantics_identity"]) == 64


def test_apply_sets_exact_run_bads_and_rejects_channel_name_mismatch(
    tmp_path: Path,
) -> None:
    eeg = tmp_path / "sub-01_task-mi_eeg.fif"
    raw = Raw(
        str(eeg),
        mne.io.RawArray(
            np.zeros((2, 100)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose=False,
        ),
    )
    review = {
        "status": "ready",
        "runs": [
            {
                "eeg_file": str(eeg),
                "channels_file": str(tmp_path / "channels.tsv"),
                "status": "ready",
                "channel_count": 2,
                "channel_statuses": {"C3": "good", "C4": "bad"},
                "bad_channels": ["C4"],
                "status_identity": "a" * 64,
            }
        ],
    }

    applied = apply_bids_channel_review(
        review=review,
        loaded_data=[raw],
        data_filepath=lambda item: item.get_filepath(),
    )

    assert raw.get_mne().info["bads"] == ["C4"]
    assert applied[0]["bad_channels"] == ["C4"]
    assert raw.get_runtime_detail("bids_channels") == applied[0]

    review["runs"][0]["channel_statuses"] = {"C3": "good", "PO10": "bad"}
    review["runs"][0]["bad_channels"] = ["PO10"]
    with pytest.raises(ValueError, match="do not match"):
        apply_bids_channel_review(
            review=review,
            loaded_data=[raw],
            data_filepath=lambda item: item.get_filepath(),
        )


@pytest.mark.parametrize("reviewed_status", ["unspecified", "n/a"])
def test_unknown_or_unavailable_status_preserves_loader_bad_channels(
    tmp_path: Path,
    reviewed_status: str,
) -> None:
    eeg = tmp_path / "sub-01_task-mi_eeg.fif"
    raw = Raw(
        str(eeg),
        mne.io.RawArray(
            np.zeros((2, 100)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose=False,
        ),
    )
    raw.get_mne().info["bads"] = ["C3"]
    review = {
        "status": "ready_with_warnings",
        "runs": [
            {
                "eeg_file": str(eeg),
                "channels_file": str(tmp_path / "channels.tsv"),
                "channel_statuses": {
                    "C3": reviewed_status,
                    "C4": reviewed_status,
                },
            }
        ],
    }

    applied = apply_bids_channel_review(
        review=review,
        loaded_data=[raw],
        data_filepath=lambda item: item.get_filepath(),
    )

    assert raw.get_mne().info["bads"] == ["C3"]
    assert applied[0]["bad_channels"] == ["C3"]


def test_review_accepts_na_status_without_clearing_existing_quality(
    tmp_path: Path,
) -> None:
    eeg = tmp_path / "sub-01_task-mi_eeg.fif"
    channels = tmp_path / "sub-01_task-mi_channels.tsv"
    channels.write_text(
        "name\ttype\tunits\tstatus\nC3\tEEG\tuV\tn/a\nC4\tEEG\tuV\tbad\n",
        encoding="utf-8",
    )

    review = review_bids_channel_sidecars(
        bids={
            "is_bids": True,
            "layout": [{"file": str(eeg), "channels_file": str(channels)}],
        },
        selected_eeg_files=[str(eeg)],
    )

    assert review.status == "ready"
    assert review.runs[0]["channel_statuses"] == {
        "C3": "unspecified",
        "C4": "bad",
    }


def test_multi_run_apply_rolls_back_earlier_channel_mutations_on_failure(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "sub-01_task-mi_run-1_eeg.fif"
    second_path = tmp_path / "sub-01_task-mi_run-2_eeg.fif"
    first = Raw(
        str(first_path),
        mne.io.RawArray(
            np.zeros((1, 100)),
            mne.create_info(["C3"], sfreq=100.0, ch_types="eeg"),
            verbose=False,
        ),
    )
    second = Raw(
        str(second_path),
        mne.io.RawArray(
            np.zeros((1, 100)),
            mne.create_info(["C4"], sfreq=100.0, ch_types="eeg"),
            verbose=False,
        ),
    )
    review = {
        "status": "ready",
        "runs": [
            {
                "eeg_file": str(first_path),
                "channel_statuses": {"C3": "bad"},
                "mne_channel_types": {"C3": "eog"},
            },
            {
                "eeg_file": str(second_path),
                "channel_statuses": {"C4": "good"},
                "mne_channel_types": {"C4": "not-a-channel-type"},
            },
        ],
    }

    with pytest.raises(ValueError, match="not-a-channel-type"):
        apply_bids_channel_review(
            review=review,
            loaded_data=[first, second],
            data_filepath=lambda item: item.get_filepath(),
        )

    assert first.get_mne().get_channel_types() == ["eeg"]
    assert first.get_mne().info["bads"] == []
    assert first.get_runtime_detail("bids_channels") is None


def test_apply_sets_reviewed_bids_types_units_and_status_on_mne_raw(
    tmp_path: Path,
) -> None:
    eeg = tmp_path / "sub-01_task-monitoring_eeg.fif"
    channels = tmp_path / "sub-01_task-monitoring_channels.tsv"
    channels.write_text(
        "name\ttype\tunits\tstatus\n"
        "Cz\tEEG\tmicroV\tgood\n"
        "EOG horizontal\tEOG\tmicroV\tgood\n"
        "Temp\tTEMP\toC\tbad\n",
        encoding="utf-8",
    )
    review = review_bids_channel_sidecars(
        bids={
            "is_bids": True,
            "layout": [{"file": str(eeg), "channels_file": str(channels)}],
        },
        selected_eeg_files=[str(eeg)],
    )
    raw = Raw(
        str(eeg),
        mne.io.RawArray(
            np.zeros((3, 100)),
            mne.create_info(
                ["Cz", "EOG horizontal", "Temp"],
                sfreq=100.0,
                ch_types="eeg",
            ),
            verbose=False,
        ),
    )

    applied = apply_bids_channel_review(
        review=review,
        loaded_data=[raw],
        data_filepath=lambda item: item.get_filepath(),
    )

    run_review = review.runs[0]
    assert run_review["channel_types"] == {
        "Cz": "EEG",
        "EOG horizontal": "EOG",
        "Temp": "TEMP",
    }
    assert run_review["channel_units"] == {
        "Cz": "microV",
        "EOG horizontal": "microV",
        "Temp": "oC",
    }
    mne_raw = raw.get_mne()
    assert mne_raw.get_channel_types() == ["eeg", "eog", "temperature"]
    assert [channel["unit"] for channel in mne_raw.info["chs"]] == [
        FIFF.FIFF_UNIT_V,
        FIFF.FIFF_UNIT_V,
        FIFF.FIFF_UNIT_CEL,
    ]
    assert mne_raw.info["bads"] == ["Temp"]
    assert applied[0]["applied_channel_types"] == {
        "Cz": "eeg",
        "EOG horizontal": "eog",
        "Temp": "temperature",
    }
    assert applied[0]["applied_channel_units"] == {
        "Cz": int(FIFF.FIFF_UNIT_V),
        "EOG horizontal": int(FIFF.FIFF_UNIT_V),
        "Temp": int(FIFF.FIFF_UNIT_CEL),
    }
    assert raw.get_runtime_detail("bids_channels") == applied[0]


def test_unmapped_bids_type_and_unit_remain_explicit_without_guessing(
    tmp_path: Path,
) -> None:
    eeg = tmp_path / "sub-01_task-monitoring_eeg.fif"
    channels = tmp_path / "sub-01_task-monitoring_channels.tsv"
    channels.write_text(
        "name\ttype\tunits\tstatus\nAux\tVENDOR_AUX\tvendor-unit\tgood\n",
        encoding="utf-8",
    )
    review = review_bids_channel_sidecars(
        bids={
            "is_bids": True,
            "layout": [{"file": str(eeg), "channels_file": str(channels)}],
        },
        selected_eeg_files=[str(eeg)],
    )
    raw = Raw(
        str(eeg),
        mne.io.RawArray(
            np.zeros((1, 100)),
            mne.create_info(["Aux"], sfreq=100.0, ch_types="eeg"),
            verbose=False,
        ),
    )

    applied = apply_bids_channel_review(
        review=review,
        loaded_data=[raw],
        data_filepath=lambda item: item.get_filepath(),
    )

    assert review.runs[0]["unmapped_type_channels"] == ["Aux"]
    assert review.runs[0]["unmapped_unit_channels"] == ["Aux"]
    assert len(review.warnings) == 2
    assert raw.get_mne().get_channel_types() == ["eeg"]
    assert raw.get_mne().info["chs"][0]["unit"] == FIFF.FIFF_UNIT_V
    assert applied[0]["unmapped_type_channels"] == ["Aux"]
    assert applied[0]["unmapped_unit_channels"] == ["Aux"]


def test_review_blocks_unknown_channel_status(tmp_path: Path) -> None:
    eeg = tmp_path / "sub-01_task-mi_eeg.fif"
    channels = tmp_path / "sub-01_task-mi_channels.tsv"
    channels.write_text(
        "name\tstatus\nC3\tgood\nC4\tquestionable\n",
        encoding="utf-8",
    )

    review = review_bids_channel_sidecars(
        bids={
            "is_bids": True,
            "layout": [{"file": str(eeg), "channels_file": str(channels)}],
        },
        selected_eeg_files=[str(eeg)],
    )

    assert review.status == "blocked"
    assert review.runs[0]["status"] == "blocked"
    assert "unsupported status questionable" in review.blocked_reasons[0]
