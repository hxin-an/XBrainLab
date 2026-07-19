"""Strict local BIDS channels.tsv review and apply tests."""

from __future__ import annotations

from pathlib import Path

import mne
import numpy as np
import pytest

from XBrainLab.backend.application.data_interpretation_bids_channels import (
    apply_bids_channel_review,
    review_bids_channel_sidecars,
)
from XBrainLab.backend.load_data.raw import Raw


def test_review_preserves_per_run_bad_channels_and_status_identity(
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

    assert review.blocked_reasons == []
    assert review.runs == [
        {
            "eeg_file": str(eeg.resolve()),
            "channels_file": str(channels.resolve()),
            "status": "ready",
            "channel_count": 2,
            "channel_statuses": {"C3": "good", "C4": "bad"},
            "bad_channels": ["C4"],
            "status_identity": review.runs[0]["status_identity"],
        }
    ]
    assert len(review.runs[0]["status_identity"]) == 64


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
