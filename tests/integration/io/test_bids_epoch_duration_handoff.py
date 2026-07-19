"""BIDS interval-to-epoch handoff regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CreateEpochCommand,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.epoch_context import build_epoching_context
from XBrainLab.backend.application.results import ErrorType


def _class_value_decisions(*values: str) -> dict[str, dict[str, object]]:
    return {
        value: {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": value,
        }
        for value in values
    }


def _write_exact_end_bids_run(
    root: Path,
    *,
    sfreq: float = 100.0,
    recording_duration_seconds: float = 10.0,
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "exact-end", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True, exist_ok=True)
    stem = "sub-01_task-mi_run-01"
    eeg_path = eeg_dir / f"{stem}_eeg.fif"
    events_path = eeg_dir / f"{stem}_events.tsv"

    info = mne.create_info(["Cz"], sfreq=sfreq, ch_types="eeg")
    n_times = round(sfreq * recording_duration_seconds)
    raw = mne.io.RawArray(np.zeros((1, n_times)), info, verbose="ERROR")
    raw.save(eeg_path, overwrite=True, verbose="ERROR")
    events_path.write_text(
        "onset\tduration\ttrial_type\n9.5\t0.5\tlate_event\n",
        encoding="utf-8",
    )
    return eeg_path.resolve(), events_path.resolve()


def _write_duration_review_bids_run(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "duration-review", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True, exist_ok=True)
    stem = "sub-01_task-mi_run-01"
    eeg_path = eeg_dir / f"{stem}_eeg.fif"
    events_path = eeg_dir / f"{stem}_events.tsv"
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, 3_000)), info, verbose="ERROR")
    raw.save(eeg_path, overwrite=True, verbose="ERROR")
    events_path.write_text(
        "onset\tduration\ttrial_type\n1.0\t0.25\tshort_event\n15.0\t12.0\tlong_event\n",
        encoding="utf-8",
    )
    return eeg_path.resolve(), events_path.resolve()


def test_bids_long_uneven_duration_requires_receipt_before_create_epoch(
    tmp_path: Path,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_path, events_path = _write_duration_review_bids_run(bids_root)
    service = ApplicationService()
    service.execute(ScanSourceCommand(source_path=str(bids_root), source_hint="bids"))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _class_value_decisions(
                            "short_event",
                            "long_event",
                        ),
                    }
                },
            }
        )
    )
    service.execute(ValidateInterpretationCommand())
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))
    assert applied.ok is True

    context = build_epoching_context(service.study.preprocessed_data_list)
    command = CreateEpochCommand(
        t_min=context["suggested_t_min"],
        t_max=context["suggested_t_max"],
        event_ids=["short_event", "long_event"],
    )
    challenged = service.execute(command)

    assert challenged.ok is False
    assert challenged.error_type is ErrorType.CONFIRMATION_REQUIRED
    requirement = challenged.diagnostics["confirmation_requirement"]
    assert requirement["code"] == "bids_duration_review"
    assert challenged.state.epoch.available is False

    accepted = service.execute(
        CreateEpochCommand(
            t_min=command.t_min,
            t_max=command.t_max,
            event_ids=command.event_ids,
            confirmation_receipt=requirement["receipt"],
        )
    )

    assert accepted.ok is True
    assert accepted.state.epoch.available is True
    assert accepted.state.epoch.epoch_count == 2


@pytest.mark.parametrize(
    ("sfreq", "expected_tmax"),
    [
        (100.0, 0.49),
        (128.0, 63 / 128),
        (250.0, 124 / 250),
    ],
)
def test_bids_exact_end_duration_handoff_uses_last_included_sample(
    tmp_path: Path,
    sfreq: float,
    expected_tmax: float,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_path, events_path = _write_exact_end_bids_run(bids_root, sfreq=sfreq)
    recipe_path = tmp_path / "exact-end-recipe.json"
    service = ApplicationService()

    scan_result = service.execute(
        ScanSourceCommand(source_path=str(bids_root), source_hint="bids")
    )
    preview_result = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _class_value_decisions("late_event"),
                    }
                },
            }
        )
    )
    validation_result = service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    recipe_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )

    assert scan_result.ok is True
    assert preview_result.ok is True
    assert validation_result.ok is True
    assert apply_result.ok is True
    assert recipe_result.ok is True
    assert (
        preview_result.diagnostics["preview"]["bids"]["event_validation"]["runs"][0][
            "placement"
        ]["status"]
        == "ready"
    )
    assert (
        recipe_result.diagnostics["recipe"]["label_carrier_plan"][0][
            "selected_duration_field"
        ]
        == "duration"
    )

    replay_service = ApplicationService()
    reload_result = replay_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    replay_validation = replay_service.execute(ValidateInterpretationCommand())
    replay_apply = replay_service.execute(ApplyInterpretationCommand(confirmed=True))

    assert reload_result.ok is True
    assert replay_validation.ok is True
    assert replay_apply.ok is True

    preprocessed = replay_service.study.preprocessed_data_list
    runtime_hint = preprocessed[0].get_runtime_detail("data_interpretation_epoch_hint")
    context = build_epoching_context(preprocessed)

    assert runtime_hint["duration_stats"]["max"] == 0.5
    assert context["duration_field"] == "duration"
    assert context["duration_stats"]["max"] == 0.5
    assert context["suggested_t_min"] == 0.0
    assert context["suggested_t_max"] == pytest.approx(expected_tmax)

    epoch_result = replay_service.execute(
        CreateEpochCommand(
            t_min=context["suggested_t_min"],
            t_max=context["suggested_t_max"],
            event_ids=["late_event"],
        )
    )

    assert epoch_result.ok is True
    assert epoch_result.state.epoch.available is True
    assert epoch_result.state.epoch.epoch_count == 1


def test_bids_exact_end_manual_inclusive_tmax_is_not_silently_rewritten(
    tmp_path: Path,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_path, events_path = _write_exact_end_bids_run(bids_root)
    service = ApplicationService()
    service.execute(ScanSourceCommand(source_path=str(bids_root), source_hint="bids"))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _class_value_decisions("late_event"),
                    }
                },
            }
        )
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True

    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.5,
            event_ids=["late_event"],
        )
    )

    assert epoch_result.ok is False
    assert "exceeds recording bounds" in epoch_result.message
