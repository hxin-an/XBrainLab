"""Candidate-level tests for external event value decisions."""

from __future__ import annotations

import json
from pathlib import Path

import mne
import numpy as np

from XBrainLab.backend.application.data_interpretation_candidate import (
    build_interpretation_candidate,
)
from XBrainLab.backend.application.data_interpretation_choice_schema import (
    data_interpretation_choices_schema,
)
from XBrainLab.backend.application.data_interpretation_label_carriers import (
    build_label_carrier_plan,
)
from XBrainLab.backend.application.data_interpretation_review import (
    validate_interpretation_candidate,
)
from XBrainLab.backend.application.data_interpretation_scan import scan_source_path


def test_choice_schema_exposes_per_carrier_value_decisions() -> None:
    schema = data_interpretation_choices_schema()
    carrier = schema["properties"]["label_carrier_choices"]["additionalProperties"]
    decisions = carrier["properties"]["value_decisions"]
    decision = decisions["additionalProperties"]

    assert decisions["type"] == "object"
    assert decision["additionalProperties"] is False
    assert decision["properties"]["role"]["enum"] == [
        "stimulus",
        "response",
        "artifact",
        "boundary",
        "system",
        "annotation",
        "unknown",
    ]
    assert {"keep_event", "use_as_class", "class_name"} <= set(decision["properties"])


def test_label_carrier_plan_auto_resolves_generic_classlabel_series(
    tmp_path: Path,
) -> None:
    labels = tmp_path / "subject_labels.csv"
    labels.write_text(
        "trial,classlabel\n1,left\n2,right\n3,left\n",
        encoding="utf-8",
    )

    plan = build_label_carrier_plan(
        [str(labels)],
        {
            str(labels): {
                "label_field": "classlabel",
                "role": "class labels",
                "time_model": "trial_order",
                "granularity": "trial",
            }
        },
    )[0]

    assert plan["value_decisions"]["left"]["count"] == 2
    assert plan["value_decisions"]["left"]["decision_source"] == ("format_domain_rule")
    assert plan["run_class_map"] == {"left": "left", "right": "right"}
    assert plan["unresolved_values"] == []


def test_mixed_bids_values_require_complete_decisions_and_levels_only_suggest(
    tmp_path: Path,
) -> None:
    bids_root, eeg, events = _mixed_bids_fixture(tmp_path)
    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(bids_root),
        source_hint="bids",
    )

    incomplete = build_interpretation_candidate(
        candidate_id="candidate-incomplete",
        scan=scan,
        choices={
            "selected_eeg_files": [str(eeg)],
            "label_carrier_choices": {
                str(events): {
                    **_carrier_placement_choices(),
                    "value_decisions": {
                        "left": _value_choice("stimulus", True, "Left class"),
                        "right": _value_choice("stimulus", True, "Right class"),
                    },
                }
            },
        },
    )

    incomplete_plan = incomplete.label_carrier_plan[0]
    assert incomplete.class_map == {
        "left": "Left class",
        "right": "Right class",
    }
    assert incomplete_plan["value_decisions"]["left"]["suggested_name"] == ("Left hand")
    assert incomplete_plan["value_decisions"]["button_press"]["suggested_name"] == (
        "Button press"
    )
    assert incomplete_plan["value_decisions"]["button_press"]["use_as_class"] is None
    assert validate_interpretation_candidate(incomplete).decision == "blocked"
    assert any(
        "button_press" in reason and "boundary" in reason
        for reason in incomplete.blocked_reasons
    )

    complete = build_interpretation_candidate(
        candidate_id="candidate-complete",
        scan=scan,
        choices={
            "selected_eeg_files": [str(eeg)],
            "label_carrier_choices": {
                str(events): {
                    **_carrier_placement_choices(),
                    "value_decisions": {
                        "left": _value_choice("stimulus", True, "Left class"),
                        "right": _value_choice("stimulus", True, "Right class"),
                        "button_press": _value_choice("response", False),
                        "bad_segment": _value_choice(
                            "artifact", False, keep_event=False
                        ),
                        "boundary": _value_choice("boundary", False),
                    },
                }
            },
        },
    )

    complete_plan = complete.label_carrier_plan[0]
    assert complete.blocked_reasons == []
    assert complete.class_map == {
        "left": "Left class",
        "right": "Right class",
    }
    assert complete_plan["run_class_map"] == complete.class_map
    assert complete_plan["bids_event_review"]["placement"]["usable_event_count"] == 4
    assert complete_plan["bids_event_review"]["placement"]["excluded_event_count"] == 1
    channel_review = complete.bids["channel_review"]
    assert channel_review["status"] == "ready"
    assert channel_review["scope"] == "exact_local_sidecar_only"
    assert channel_review["runs"][0]["bad_channels"] == ["C4"]
    assert {
        (row["role"], Path(row["path"]).name)
        for row in complete.content_identity["files"]
    } >= {
        ("label_carrier", events.name),
        ("bids_channels", "sub-01_task-mi_channels.tsv"),
    }


def test_channels_sidecar_change_after_preview_blocks_validation(
    tmp_path: Path,
) -> None:
    bids_root, eeg, events = _mixed_bids_fixture(tmp_path)
    channels = events.with_name("sub-01_task-mi_channels.tsv")
    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(bids_root),
        source_hint="bids",
    )
    decisions = {
        "left": _value_choice("stimulus", True, "Left class"),
        "right": _value_choice("stimulus", True, "Right class"),
        "button_press": _value_choice("response", False),
        "bad_segment": _value_choice("artifact", False, keep_event=False),
        "boundary": _value_choice("boundary", False),
    }
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=scan,
        choices={
            "selected_eeg_files": [str(eeg)],
            "label_carrier_choices": {
                str(events): {
                    **_carrier_placement_choices(),
                    "value_decisions": decisions,
                }
            },
        },
    )
    channels.write_text(
        "name\tstatus\nC3\tbad\nC4\tbad\n",
        encoding="utf-8",
    )

    decision = validate_interpretation_candidate(candidate)

    assert decision.decision == "blocked"
    assert any("changed after preview" in reason for reason in decision.blocked_reasons)


def test_multi_run_same_raw_value_keeps_distinct_confirmed_semantics(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "runs", "BIDSVersion": "1.9.0"}),
        encoding="utf-8",
    )
    eeg_files: list[Path] = []
    event_files: list[Path] = []
    for run in ("1", "2"):
        eeg = eeg_dir / f"sub-01_task-mi_run-{run}_eeg.fif"
        raw = mne.io.RawArray(
            np.zeros((1, 500)),
            mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
            verbose=False,
        )
        raw.save(eeg, overwrite=True, verbose=False)
        events = eeg_dir / f"sub-01_task-mi_run-{run}_events.tsv"
        events.write_text(
            "onset\tduration\ttrial_type\n0.5\t0\tT1\n",
            encoding="utf-8",
        )
        eeg_files.append(eeg.resolve())
        event_files.append(events.resolve())
    scan = scan_source_path(
        scan_id="scan-runs",
        source_path=str(root),
        source_hint="bids",
    )
    candidate = build_interpretation_candidate(
        candidate_id="candidate-runs",
        scan=scan,
        choices={
            "selected_eeg_files": [str(path) for path in eeg_files],
            "label_carrier_choices": {
                str(event_files[0]): {
                    **_carrier_placement_choices(),
                    "target_file": str(eeg_files[0]),
                    "value_decisions": {"T1": _value_choice("stimulus", True, "left")},
                },
                str(event_files[1]): {
                    **_carrier_placement_choices(),
                    "target_file": str(eeg_files[1]),
                    "value_decisions": {"T1": _value_choice("stimulus", True, "right")},
                },
            },
        },
    )

    assert candidate.class_map == {}
    assert {
        plan["selected_target_file"]: plan["run_class_map"]
        for plan in candidate.label_carrier_plan
    } == {
        str(eeg_files[0]): {"T1": "left"},
        str(eeg_files[1]): {"T1": "right"},
    }
    assert candidate.bids["event_validation"]["mapping_conflicts"] == []
    assert not any(
        "Confirm per-run mapping" in item for item in candidate.confirmation_items
    )


def _mixed_bids_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "bids"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "mixed", "BIDSVersion": "1.9.0"}),
        encoding="utf-8",
    )
    eeg = eeg_dir / "sub-01_task-mi_eeg.fif"
    raw = mne.io.RawArray(
        np.zeros((2, 1000)),
        mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
        verbose=False,
    )
    raw.save(eeg, overwrite=True, verbose=False)
    events = eeg_dir / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0.5\t0\tleft\t1\n"
        "1.5\t0\tright\t2\n"
        "2.5\t0\tbutton_press\t3\n"
        "3.5\t0.2\tbad_segment\t4\n"
        "4.5\t0\tboundary\t5\n",
        encoding="utf-8",
    )
    (eeg_dir / "sub-01_task-mi_events.json").write_text(
        json.dumps(
            {
                "trial_type": {
                    "Levels": {
                        "left": "Left hand",
                        "right": "Right hand",
                        "button_press": "Button press",
                        "bad_segment": "Bad segment",
                        "boundary": "Boundary",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (eeg_dir / "sub-01_task-mi_channels.tsv").write_text(
        "name\ttype\tunits\tstatus\tstatus_description\n"
        "C3\tEEG\tuV\tgood\tn/a\n"
        "C4\tEEG\tuV\tbad\tflat\n",
        encoding="utf-8",
    )
    return root, eeg.resolve(), events.resolve()


def _carrier_placement_choices() -> dict[str, object]:
    return {
        "label_field": "trial_type",
        "anchor": "onset",
        "duration_field": "duration",
        "time_model": "seconds",
        "placement_method": "interval",
        "granularity": "event",
    }


def _value_choice(
    role: str,
    use_as_class: bool,
    class_name: str = "",
    *,
    keep_event: bool = True,
) -> dict[str, object]:
    choice: dict[str, object] = {
        "role": role,
        "keep_event": keep_event,
        "use_as_class": use_as_class,
    }
    if class_name:
        choice["class_name"] = class_name
    return choice
