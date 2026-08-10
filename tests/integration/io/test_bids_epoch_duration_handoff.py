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
    CommandName,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
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
    run_id: str = "01",
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "exact-end", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True, exist_ok=True)
    stem = f"sub-01_task-mi_run-{run_id}"
    eeg_path = eeg_dir / f"{stem}_eeg.fif"
    events_path = eeg_dir / f"{stem}_events.tsv"

    info = mne.create_info(["Cz"], sfreq=sfreq, ch_types="eeg")
    n_times = round(sfreq * recording_duration_seconds)
    raw = mne.io.RawArray(np.zeros((1, n_times)), info, verbose="ERROR")
    raw.save(eeg_path, overwrite=True, verbose="ERROR")
    events_path.write_text(
        ("onset\tduration\ttrial_type\n1.0\t0.5\tearly_event\n9.5\t0.5\tlate_event\n"),
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


def test_reviewed_bids_mixed_sampling_rates_block_then_resample_enables_epoch(
    tmp_path: Path,
) -> None:
    bids_root = tmp_path / "bids"
    first_eeg, first_events = _write_exact_end_bids_run(
        bids_root,
        sfreq=100.0,
        run_id="01",
    )
    second_eeg, second_events = _write_exact_end_bids_run(
        bids_root,
        sfreq=256.0,
        run_id="02",
    )
    service = ApplicationService()

    scan_result = service.execute(
        ScanSourceCommand(source_path=str(bids_root), source_hint="bids")
    )
    preview_result = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(first_eeg), str(second_eeg)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _class_value_decisions(
                            "early_event",
                            "late_event",
                        ),
                    }
                    for events_path in (first_events, second_events)
                },
            }
        )
    )
    validation_result = service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan_result.ok is True
    assert preview_result.ok is True
    assert validation_result.ok is True
    assert apply_result.ok is True
    assert apply_result.state.epoch.exists is False
    preprocessed_before = tuple(service.study.preprocessed_data_list)
    assert [data.get_sfreq() for data in preprocessed_before] == [100.0, 256.0]
    blocked_capability = service.get_capabilities().get(CommandName.CREATE_EPOCH)
    blocked_context = service.get_epoch_dialog_context()

    assert blocked_capability.available is False
    assert blocked_context.usable is False
    assert blocked_context.capability == blocked_capability
    assert "different sampling frequencies (100 Hz, 256 Hz)" in str(
        blocked_context.unavailable_reason
    )

    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.4,
            event_ids=["early_event", "late_event"],
        )
    )

    assert epoch_result.ok is False
    assert epoch_result.error_type is ErrorType.PRECONDITION
    assert epoch_result.recoverable is True
    assert "different sampling frequencies (100 Hz, 256 Hz)" in epoch_result.message
    assert (
        "Resample them to one shared rate before creating epochs."
        in epoch_result.message
    )
    assert epoch_result.state.epoch == apply_result.state.epoch
    assert epoch_result.changed_state.epoch_changed is False
    assert service.study.epoch_data is None
    assert all(
        retained is original
        for retained, original in zip(
            service.study.preprocessed_data_list,
            preprocessed_before,
            strict=True,
        )
    )
    assert all(data.is_raw() for data in service.study.preprocessed_data_list)

    resample_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.RESAMPLE,
            rate=100,
        )
    )

    assert resample_result.ok is True
    assert resample_result.changed_state.preprocessed_changed is True
    assert [data.get_sfreq() for data in service.study.preprocessed_data_list] == [
        100.0,
        100.0,
    ]
    ready_capability = service.get_capabilities().get(CommandName.CREATE_EPOCH)
    ready_context = service.get_epoch_dialog_context()
    assert ready_capability.available is True
    assert ready_context.usable is True
    assert ready_context.capability == ready_capability
    assert ready_context.epoch_setup is not None
    assert ready_context.epoch_setup["requires_common_sampling_frequency"] is False

    ready_epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.4,
            event_ids=["early_event", "late_event"],
        )
    )

    assert ready_epoch_result.ok is True
    assert ready_epoch_result.changed_state.epoch_changed is True
    assert ready_epoch_result.state.epoch.available is True
    assert ready_epoch_result.state.epoch.epoch_count == 4


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
                        "value_decisions": _class_value_decisions(
                            "early_event",
                            "late_event",
                        ),
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
            event_ids=["early_event", "late_event"],
        )
    )

    assert epoch_result.ok is True
    assert epoch_result.state.epoch.available is True
    assert epoch_result.state.epoch.epoch_count == 2


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
                        "value_decisions": _class_value_decisions(
                            "early_event",
                            "late_event",
                        ),
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
            event_ids=["early_event", "late_event"],
        )
    )

    assert epoch_result.ok is False
    assert "would exclude 1 of 2" in epoch_result.message
