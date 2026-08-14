from pathlib import Path

import mne
import numpy as np

from XBrainLab.backend.application.data_interpretation_apply import (
    DataInterpretationApplyService,
)
from XBrainLab.backend.application.data_interpretation_candidate import (
    InterpretationCandidate,
)
from XBrainLab.backend.application.data_interpretation_label_carriers import (
    build_label_carrier_plan,
)
from XBrainLab.backend.application.label_resource_admission import (
    LabelResourceAdmissionService,
    LabelResourceSpec,
)
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.services.label_import_service import (
    LabelImportService,
    LabelPayload,
)


class _RealLabelDataset:
    def __init__(self, loaded: list[Raw]) -> None:
        self.loaded = loaded
        self.label_import = LabelImportService()

    def get_loaded_data_list(self) -> list[Raw]:
        return self.loaded

    def apply_labels_batch(
        self,
        target_files: list[Raw],
        label_map: dict[str, LabelPayload],
        file_mapping: dict[str, str],
        mapping: dict[object, str],
        selected_event_names: set[str] | None = None,
    ) -> int:
        return self.label_import.apply_labels_batch(
            target_files,
            label_map,
            file_mapping,
            mapping,
            selected_event_names,
        )


def test_generic_timestamp_apply_keeps_semantic_annotations_and_class_only_events(
    tmp_path: Path,
) -> None:
    eeg = tmp_path / "subject_raw.fif"
    labels = tmp_path / "subject_labels.csv"
    labels.write_text(
        "onset,label\n0.5,left\n1.0,button\n1.5,bad_segment\n2.0,ignored\n",
        encoding="utf-8",
    )
    plan = {
        "path": str(labels),
        "name": labels.name,
        "format": "CSV",
        "selected_target_file": str(eeg),
        "selected_label_field": "label",
        "selected_anchor": "onset",
        "selected_duration_field": "",
        "time_model": "seconds",
        "placement_method": "time_field",
        "granularity": "event",
        "placement_review": {"status": "ready"},
        "value_decisions": {
            "left": _decision("stimulus", True, "Left hand"),
            "button": _decision("response", False),
            "bad_segment": _decision("artifact", False),
            "ignored": _decision("annotation", False, keep_event=False),
        },
        "run_class_map": {"left": "Left hand"},
    }
    candidate = InterpretationCandidate(
        candidate_id="candidate-1",
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(eeg)],
        label_carriers=[str(labels)],
        label_carrier_plan=[plan],
        class_map={"left": "legacy global", "bad_segment": "legacy artifact"},
    )
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    raw = Raw(
        str(eeg),
        mne.io.RawArray(np.zeros((1, 300)), info, verbose=False),
    )
    dataset = _RealLabelDataset([raw])
    service = DataInterpretationApplyService(
        dataset,
        data_filename=lambda item: item.get_filename(),
        data_filepath=lambda item: item.get_filepath(),
        record_label_import=lambda **_kwargs: None,
    )

    label_resources = LabelResourceAdmissionService(
        command_name="test_apply_interpretation"
    ).admit(
        [
            LabelResourceSpec(
                path=str(labels),
                label_field="label",
                anchor="onset",
            )
        ],
        confirmed=False,
        token=None,
    )

    result = service.apply_label_carriers(candidate, label_resources)

    assert result["status"] == "applied"
    events, event_id = raw.get_event_list()
    assert events[:, 0].tolist() == [50]
    assert event_id == {"Left hand": 1}
    raw_mne = raw.get_mne()
    assert raw_mne is not None
    annotations = raw_mne.annotations
    assert annotations is not None
    assert list(annotations.description) == [
        "Left hand",
        "response/button",
        "BAD_artifact/bad_segment",
    ]
    assert raw.is_labels_imported() is True


def test_numeric_bids_preview_decisions_apply_through_admitted_pandas_reader(
    tmp_path: Path,
) -> None:
    eeg = tmp_path / "sub-1_task-cvep_eeg.fif"
    events = tmp_path / "sub-1_task-cvep_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\tvalue\n0.5\t0.3\t0.0\t1\n1.0\t0.3\t1.0\t2\n",
        encoding="utf-8",
    )
    carrier_choices = {
        "label_field": "trial_type",
        "anchor": "onset",
        "duration_field": "duration",
        "time_model": "seconds",
        "placement_method": "interval",
        "granularity": "event",
        "target_file": str(eeg),
    }
    preview_plan = build_label_carrier_plan(
        [str(events)],
        {str(events): carrier_choices},
    )[0]
    observed_values = list(preview_plan["value_decisions"])
    assert observed_values == ["0.0", "1.0"]
    reviewed_plan = build_label_carrier_plan(
        [str(events)],
        {
            str(events): {
                **carrier_choices,
                "value_decisions": {
                    value: _decision("stimulus", True, f"Class {value}")
                    for value in observed_values
                },
            }
        },
    )[0]
    assert reviewed_plan["run_class_map"] == {
        "0.0": "Class 0.0",
        "1.0": "Class 1.0",
    }
    reviewed_plan["placement_review"] = {"status": "ready"}
    candidate = InterpretationCandidate(
        candidate_id="candidate-numeric-bids",
        scan_id="scan-numeric-bids",
        source_path=str(tmp_path),
        source_kind="bids",
        selected_eeg_files=[str(eeg)],
        label_carriers=[str(events)],
        label_carrier_plan=[reviewed_plan],
        class_map=dict(reviewed_plan["run_class_map"]),
    )
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    raw = Raw(
        str(eeg),
        mne.io.RawArray(np.zeros((1, 300)), info, verbose=False),
    )
    service = DataInterpretationApplyService(
        _RealLabelDataset([raw]),
        data_filename=lambda item: item.get_filename(),
        data_filepath=lambda item: item.get_filepath(),
        record_label_import=lambda **_kwargs: None,
    )
    label_resources = LabelResourceAdmissionService(
        command_name="test_apply_interpretation"
    ).admit(
        [
            LabelResourceSpec(
                path=str(events),
                label_field="trial_type",
                anchor="onset",
                duration_field="duration",
            )
        ],
        confirmed=False,
        token=None,
    )

    result = service.apply_label_carriers(candidate, label_resources)

    assert result["status"] == "applied"
    assert result["success_count"] == 1
    applied_events, event_id = raw.get_event_list()
    assert applied_events[:, 0].tolist() == [50, 100]
    assert set(event_id) == {f"Class {value}" for value in observed_values}


def test_bids_apply_preserves_na_like_categories_and_excludes_canonical_na(
    tmp_path: Path,
) -> None:
    eeg = tmp_path / "sub-1_task-categories_eeg.fif"
    events = tmp_path / "sub-1_task-categories_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\n0.5\t0.1\tNone\n1.0\t0.1\t#N/A\n1.5\t0.1\tn/a\n",
        encoding="utf-8",
    )
    carrier_choices = {
        "label_field": "trial_type",
        "anchor": "onset",
        "duration_field": "duration",
        "time_model": "seconds",
        "placement_method": "interval",
        "granularity": "event",
        "target_file": str(eeg),
    }
    preview_plan = build_label_carrier_plan(
        [str(events)],
        {str(events): carrier_choices},
    )[0]
    assert set(preview_plan["value_decisions"]) == {"None", "#N/A"}
    reviewed_plan = build_label_carrier_plan(
        [str(events)],
        {
            str(events): {
                **carrier_choices,
                "value_decisions": {
                    "None": _decision("stimulus", True, "None category"),
                    "#N/A": _decision("stimulus", True, "Hash N/A category"),
                },
            }
        },
    )[0]
    reviewed_plan["placement_review"] = {"status": "ready"}
    candidate = InterpretationCandidate(
        candidate_id="candidate-na-like",
        scan_id="scan-na-like",
        source_path=str(tmp_path),
        source_kind="bids",
        selected_eeg_files=[str(eeg)],
        label_carriers=[str(events)],
        label_carrier_plan=[reviewed_plan],
        class_map=dict(reviewed_plan["run_class_map"]),
    )
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    raw = Raw(
        str(eeg),
        mne.io.RawArray(np.zeros((1, 300)), info, verbose=False),
    )
    service = DataInterpretationApplyService(
        _RealLabelDataset([raw]),
        data_filename=lambda item: item.get_filename(),
        data_filepath=lambda item: item.get_filepath(),
        record_label_import=lambda **_kwargs: None,
    )
    label_resources = LabelResourceAdmissionService(
        command_name="test_apply_interpretation"
    ).admit(
        [
            LabelResourceSpec(
                path=str(events),
                label_field="trial_type",
                anchor="onset",
                duration_field="duration",
            )
        ],
        confirmed=False,
        token=None,
    )

    loaded_rows = label_resources.load(str(events))
    assert [row["label"] for row in loaded_rows] == ["None", "#N/A", "n/a"]

    result = service.apply_label_carriers(candidate, label_resources)

    assert result["status"] == "applied"
    assert result["success_count"] == 1
    applied_events, event_id = raw.get_event_list()
    assert applied_events[:, 0].tolist() == [50, 100]
    assert set(event_id) == {"None category", "Hash N/A category"}
    assert raw.is_labels_imported() is True


def test_bids_epoch_duration_stats_include_only_class_rows() -> None:
    plan = {
        "bids_event_review": {
            "row_evidence": [
                {
                    "row": 0,
                    "placement_status": "usable",
                    "duration_provenance": "known",
                    "raw_duration": 1.5,
                    "value_decision": {"use_as_class": True},
                },
                {
                    "row": 1,
                    "placement_status": "usable",
                    "duration_provenance": "known",
                    "raw_duration": 20.0,
                    "value_decision": {"use_as_class": False, "role": "artifact"},
                },
            ],
        },
    }

    stats = DataInterpretationApplyService._duration_stats_from_bids_review(plan)

    assert stats == {
        "row_count": 1,
        "value_counts": {"1.5": 1},
        "numeric_count": 1,
        "min": 1.5,
        "max": 1.5,
    }

    evidence = DataInterpretationApplyService._bids_duration_epoch_evidence(plan)

    assert evidence == {
        "duration_stats": stats,
        "placement_event_count": 1,
        "unknown_duration_count": 0,
        "unknown_duration_rows": [],
    }


def test_bids_epoch_duration_evidence_counts_only_selected_class_rows() -> None:
    plan = {
        "bids_event_review": {
            "row_evidence": [
                {
                    "row": 0,
                    "placement_status": "usable",
                    "duration_provenance": "known",
                    "raw_duration": 0.0,
                    "value_decision": {"use_as_class": True},
                },
                {
                    "row": 1,
                    "placement_status": "usable",
                    "duration_provenance": "unknown",
                    "raw_duration": None,
                    "value_decision": {"use_as_class": True},
                },
                {
                    "row": 2,
                    "placement_status": "usable",
                    "duration_provenance": "known",
                    "raw_duration": 2.0,
                    "value_decision": {"use_as_class": False},
                },
            ],
        },
    }

    evidence = DataInterpretationApplyService._bids_duration_epoch_evidence(plan)

    assert evidence == {
        "duration_stats": {
            "row_count": 1,
            "value_counts": {"0": 1},
            "numeric_count": 1,
            "min": 0.0,
            "max": 0.0,
        },
        "placement_event_count": 2,
        "unknown_duration_count": 1,
        "unknown_duration_rows": [1],
    }


def test_sequence_label_plan_requires_eeg_event_placement_and_target() -> None:
    plan = {
        "format": "MAT labels",
        "placement_method": "eeg_event",
        "selected_label_field": "classlabel",
        "selected_target_event_codes": ["768"],
        "time_model": "trial_order",
        "granularity": "trial",
    }
    class_map = {"1": "Left hand", "2": "Right hand"}

    assert (
        DataInterpretationApplyService._is_auto_applicable_sequence_label_plan(
            plan,
            class_map,
        )
        is True
    )

    assert (
        DataInterpretationApplyService._is_auto_applicable_sequence_label_plan(
            {**plan, "placement_method": "event_code"},
            class_map,
        )
        is False
    )
    assert (
        DataInterpretationApplyService._is_auto_applicable_sequence_label_plan(
            {**plan, "selected_target_event_codes": []},
            class_map,
        )
        is False
    )


def _decision(
    role: str,
    use_as_class: bool,
    class_name: str = "",
    *,
    keep_event: bool = True,
) -> dict[str, object]:
    result: dict[str, object] = {
        "role": role,
        "keep_event": keep_event,
        "use_as_class": use_as_class,
        "decision": "resolved",
        "decision_source": "user_choice",
        "provenance": "test",
        "suggested_name": class_name or role,
        "count": 1,
    }
    if use_as_class:
        result["class_name"] = class_name
    return result
