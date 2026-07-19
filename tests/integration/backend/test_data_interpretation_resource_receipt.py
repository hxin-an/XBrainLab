"""Low-mock one-shot resource receipt workflow through ApplicationService."""

from __future__ import annotations

from pathlib import Path

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import ApplicationService, ErrorType
from XBrainLab.backend.application import data_interpretation_service as service_module
from XBrainLab.backend.application.resource_guard import ResourcePreflightResult


def test_review_resource_warning_requires_and_consumes_exact_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = _write_raw_fif(tmp_path / "sub-01_task-mi_raw.fif")

    def _warning(paths: list[str]) -> ResourcePreflightResult:
        return ResourcePreflightResult(
            issues=(),
            warnings=("Dataset preview requires confirmation.",),
            unknowns=(),
            diagnostics={
                "risk_level": "warning",
                "message": "Dataset preview requires confirmation.",
                "files": [
                    {
                        "path": str(Path(path).resolve()),
                        "file_bytes": Path(path).stat().st_size,
                    }
                    for path in paths
                ],
            },
        )

    monkeypatch.setattr(service_module, "check_import_resource_preflight", _warning)
    application = ApplicationService()
    challenged = application.review_interpretation(
        source_path=str(eeg_path),
        choices={"skip_labels": True},
    )

    assert challenged.failed
    assert challenged.error_type is ErrorType.CONFIRMATION_REQUIRED
    challenge = challenged.diagnostics["resource_preflight"]["confirmation_challenge"]
    assert challenge["command_name"] == "review_interpretation"
    assert challenge["configuration_fingerprint"]
    assert challenge["preflight_fingerprint"]

    reviewed = application.review_interpretation(
        source_path=str(eeg_path),
        choices={"skip_labels": True},
        resource_preflight_confirmed=True,
        resource_preflight_token=challenge["challenge_id"],
    )

    assert reviewed.ok
    assert (
        reviewed.diagnostics["resource_preflight"]["confirmation_receipt_reused"]
        is True
    )
    assert reviewed.diagnostics["candidate"]["selected_eeg_files"] == [
        str(eeg_path.resolve())
    ]

    replayed = application.review_interpretation(
        source_path=str(eeg_path),
        choices={"skip_labels": True},
        resource_preflight_confirmed=True,
        resource_preflight_token=challenge["challenge_id"],
    )

    assert replayed.failed
    assert replayed.error_type is ErrorType.CONFIRMATION_REQUIRED
    replay_challenge = replayed.diagnostics["resource_preflight"][
        "confirmation_challenge"
    ]
    assert replay_challenge["challenge_id"] != challenge["challenge_id"]


def _write_raw_fif(path: Path) -> Path:
    info = mne.create_info(["C3", "C4"], sfreq=128.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((2, 256), dtype=np.float64), info)
    raw.save(path, overwrite=True, verbose="ERROR")
    return path
