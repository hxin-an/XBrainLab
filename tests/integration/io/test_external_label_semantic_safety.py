"""Low-mock external label semantic and timestamp safety workflows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import mne
import numpy as np
import pytest
from scipy.io import savemat

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CreateEpochCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)


def _decision(
    role: str,
    *,
    use_as_class: bool,
    class_name: str = "",
) -> dict[str, object]:
    result: dict[str, object] = {
        "role": role,
        "keep_event": True,
        "use_as_class": use_as_class,
    }
    if use_as_class:
        result["class_name"] = class_name
    return result


def _write_raw(
    path: Path,
    *,
    first_samp: int = 0,
    duration_seconds: int = 5,
) -> tuple[object, list[tuple[float, float, str, tuple[str, ...]]]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = mne.create_info(["Cz", "Pz"], sfreq=100.0, ch_types="eeg")
    info.set_meas_date(datetime(2024, 1, 2, tzinfo=UTC))
    raw = mne.io.RawArray(
        np.zeros((2, duration_seconds * 100)),
        info,
        first_samp=first_samp,
        verbose=False,
    )
    raw.set_annotations(
        mne.Annotations(
            onset=[0.2, 0.4, 3.5],
            duration=[0.1, 0.0, 0.0],
            description=["BAD_acquisition", "system/start", "boundary"],
            ch_names=[("Cz",), (), ("Pz",)],
        )
    )
    raw.save(path, overwrite=True, verbose=False)
    persisted = mne.io.read_raw_fif(path, preload=False, verbose=False)
    return persisted.annotations.orig_time, _annotation_rows(persisted.annotations)


def _annotation_rows(
    annotations: mne.Annotations,
) -> list[tuple[float, float, str, tuple[str, ...]]]:
    return [
        (
            float(onset),
            float(duration),
            str(description),
            tuple(str(name) for name in annotations.ch_names[index]),
        )
        for index, (onset, duration, description) in enumerate(
            zip(
                annotations.onset,
                annotations.duration,
                annotations.description,
                strict=True,
            )
        )
    ]


def test_bids_artifact_and_boundary_rows_reject_overlapping_class_epoch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    root.mkdir()
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "semantic-safety", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    eeg_dir = root / "sub-01" / "eeg"
    eeg_path = eeg_dir / "sub-01_task-mi_run-01_eeg.fif"
    events_path = eeg_dir / "sub-01_task-mi_run-01_events.tsv"
    acquisition_orig_time, acquisition_rows = _write_raw(eeg_path)
    events_path.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "1.0\t0.0\tleft\t1\n"
        "1.1\t0.2\tocular\t2\n"
        "1.1\t0.2\tocular\t2\n"
        "2.5\t0.1\trun_break\t3\n"
        "4.0\t0.0\tright\t4\n"
        "4.1\t0.2\tocular\t2\n",
        encoding="utf-8",
    )
    choices = {
        "selected_eeg_files": [str(eeg_path.resolve())],
        "label_carrier_choices": {
            str(events_path.resolve()): {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "granularity": "event",
                "value_decisions": {
                    "left": _decision(
                        "stimulus",
                        use_as_class=True,
                        class_name="Left hand",
                    ),
                    "right": _decision(
                        "stimulus",
                        use_as_class=True,
                        class_name="Right hand",
                    ),
                    "ocular": _decision("artifact", use_as_class=False),
                    "run_break": _decision("boundary", use_as_class=False),
                },
            }
        },
    }
    service = ApplicationService()

    scan = service.execute(ScanSourceCommand(str(root), source_hint="bids"))
    preview = service.execute(PreviewInterpretationCommand(choices=choices))
    validation = service.execute(ValidateInterpretationCommand())
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan.ok is True
    assert preview.ok is True
    assert validation.ok is True
    assert validation.diagnostics["validation_decision"]["decision"] == "safe"
    assert applied.ok is True
    loaded = service.study.preprocessed_data_list[0]
    events, event_id = loaded.get_event_list()
    assert events[:, 0].tolist() == [100, 400]
    assert event_id == {"Left hand": 1, "Right hand": 2}
    annotations = loaded.get_mne().annotations
    assert annotations.orig_time == acquisition_orig_time
    merged_rows = _annotation_rows(annotations)
    assert all(row in merged_rows for row in acquisition_rows), (
        acquisition_rows,
        merged_rows,
    )
    assert annotations.description.tolist().count("BAD_artifact/ocular") == 2
    assert "BAD_boundary/run_break" in annotations.description

    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.4,
            event_ids=["Left hand", "Right hand"],
        )
    )

    assert epoch_result.ok is False
    assert epoch_result.error_type.value == "validation", epoch_result
    assert epoch_result.recoverable is True
    assert "No usable epochs remain" in epoch_result.message
    assert epoch_result.state.pipeline_stage == "preprocessed"
    assert epoch_result.state.epoch.exists is False
    assert epoch_result.changed_state.preprocessed_changed is False
    assert epoch_result.changed_state.epoch_changed is False
    retained = service.study.preprocessed_data_list[0]
    retained_events, retained_event_id = retained.get_event_list()
    assert retained_events[:, 0].tolist() == [100, 400]
    assert retained_event_id == {"Left hand": 1, "Right hand": 2}
    assert isinstance(retained.get_mne(), mne.io.BaseRaw)


@pytest.mark.parametrize(
    ("carrier_format", "index_base", "index_origin", "first_index"),
    [
        ("csv", "zero_based", "recording_relative", 100),
        ("tsv", "one_based", "recording_relative", 101),
        ("mat", "zero_based", "absolute", 600),
        ("csv", "one_based", "absolute", 601),
    ],
)
def test_sample_index_contract_produces_consistent_events_through_epoch(
    tmp_path: Path,
    carrier_format: str,
    index_base: str,
    index_origin: str,
    first_index: int,
) -> None:
    root = tmp_path / f"sample-{carrier_format}-{index_base}-{index_origin}"
    eeg_path = root / "sample_raw.fif"
    acquisition_orig_time, acquisition_rows = _write_raw(
        eeg_path,
        first_samp=500,
    )
    if carrier_format == "mat":
        label_path = root / "sample.mat"
        savemat(
            label_path,
            {
                "classlabel": np.array([1, 1, 2]),
                "sample": np.array([first_index, first_index, first_index + 100]),
            },
        )
        label_field = "classlabel"
        value_decisions = {
            "1": _decision("stimulus", use_as_class=True, class_name="Left"),
            "2": _decision("stimulus", use_as_class=True, class_name="Right"),
        }
        granularity = "trial"
    else:
        label_path = root / f"sample_labels.{carrier_format}"
        delimiter = "\t" if carrier_format == "tsv" else ","
        label_path.write_text(
            delimiter.join(["sample", "label"])
            + "\n"
            + delimiter.join([str(first_index), "left"])
            + "\n"
            + delimiter.join([str(first_index), "left"])
            + "\n"
            + delimiter.join([str(first_index + 100), "right"])
            + "\n",
            encoding="utf-8",
        )
        label_field = "label"
        value_decisions = {
            "left": _decision("stimulus", use_as_class=True, class_name="Left"),
            "right": _decision("stimulus", use_as_class=True, class_name="Right"),
        }
        granularity = "event"
    choices = {
        "selected_eeg_files": [str(eeg_path.resolve())],
        "label_carrier_choices": {
            str(label_path.resolve()): {
                "target_file": str(eeg_path.resolve()),
                "label_field": label_field,
                "anchor": "sample",
                "time_model": "sample_index",
                "sample_index_base": index_base,
                "sample_index_origin": index_origin,
                "placement_method": "time_field",
                "granularity": granularity,
                "value_decisions": value_decisions,
            }
        },
    }
    service = ApplicationService()

    scan = service.execute(ScanSourceCommand(str(root)))
    preview = service.execute(PreviewInterpretationCommand(choices=choices))
    validation = service.execute(ValidateInterpretationCommand())
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan.ok is True
    assert preview.ok is True
    plan = preview.diagnostics["candidate"]["label_carrier_plan"][0]
    assert plan["placement_review"]["status"] == "ready"
    assert plan["sample_index_base"] == index_base
    assert plan["sample_index_origin"] == index_origin
    assert validation.ok is True
    assert applied.ok is True
    loaded = service.study.preprocessed_data_list[0]
    events, event_id = loaded.get_event_list()
    assert events[:, 0].tolist() == [600, 700]
    assert event_id == {"Left": 1, "Right": 2}
    annotations = loaded.get_mne().annotations
    assert annotations.orig_time == acquisition_orig_time
    merged_rows = _annotation_rows(annotations)
    assert all(row in merged_rows for row in acquisition_rows), (
        acquisition_rows,
        merged_rows,
    )
    assert annotations.description.tolist().count("Left") == 1
    assert annotations.description.tolist().count("Right") == 1

    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.1,
            event_ids=["Left", "Right"],
        )
    )

    assert epoch_result.ok is True
    assert epoch_result.state.epoch.epoch_count == 2


def test_generic_timestamp_apply_rolls_back_when_any_row_is_out_of_range(
    tmp_path: Path,
) -> None:
    root = tmp_path / "rollback"
    eeg_path = root / "rollback_raw.fif"
    _write_raw(eeg_path)
    labels_path = root / "rollback_labels.csv"
    labels_path.write_text(
        "onset,label\n1.0,left\n5.0,right\n",
        encoding="utf-8",
    )
    service = ApplicationService()
    service.execute(ScanSourceCommand(str(root)))
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path.resolve())],
                "label_carrier_choices": {
                    str(labels_path.resolve()): {
                        "target_file": str(eeg_path.resolve()),
                        "label_field": "label",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "placement_method": "time_field",
                        "granularity": "event",
                        "value_decisions": {
                            "left": _decision(
                                "stimulus",
                                use_as_class=True,
                                class_name="Left",
                            ),
                            "right": _decision(
                                "stimulus",
                                use_as_class=True,
                                class_name="Right",
                            ),
                        },
                    }
                },
            }
        )
    )
    validation = service.execute(ValidateInterpretationCommand())
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert preview.ok is True
    assert validation.diagnostics["validation_decision"]["decision"] in {
        "safe",
        "needs_confirmation",
    }
    assert applied.ok is False
    assert "outside the stored EEG range" in applied.message
    assert "Applied labels to 0/1" not in applied.message
    assert applied.diagnostics["label_apply"]["reason"] == (
        "Timestamp label row 2 is outside the stored EEG range."
    )
    assert applied.diagnostics["label_apply"]["failure"] == {
        "code": "label_validation_failed",
        "phase": "preparation",
        "recoverable": True,
        "state_unknown": False,
    }
    assert applied.state.raw.count == 0
    assert applied.state.interpretation.label_import_count == 0
