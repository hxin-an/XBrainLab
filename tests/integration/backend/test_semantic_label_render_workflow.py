"""Reviewed class semantics must survive the complete downstream workflow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CreateEpochCommand,
    EvaluationPlanIdentity,
    EvaluationRenderRequest,
    EvaluationRunIdentity,
    GenerateDatasetCommand,
    PreviewInterpretationCommand,
    SaliencyPlanIdentity,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.evaluation_render import EvaluationRenderPublisher
from XBrainLab.backend.application.saliency_render import SaliencyRenderPublisher
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.record.train import TrainRecord
from XBrainLab.backend.training.saliency_provenance import SaliencyProducerIdentity
from XBrainLab.backend.training_state_contract import TrainingReadBoundary

OFNER_CLASS_MAP = {
    "1536": "right elbow flexion",
    "1537": "right elbow extension",
    "1538": "right supination",
    "1539": "right pronation",
    "1540": "right hand close",
    "1541": "right hand open",
    "1542": "rest",
}


class _TrainingHolder:
    def __init__(
        self,
        dataset: Any,
        record: TrainRecord,
        producer: SaliencyProducerIdentity,
    ) -> None:
        self.dataset = dataset
        self._record = record
        self._producer = producer

    def get_plans(self) -> list[TrainRecord]:
        return [self._record]

    def get_dataset(self) -> Any:
        return self.dataset

    def build_saliency_producer_identity(
        self,
        record: TrainRecord,
        *,
        evaluation_split: str,
    ) -> SaliencyProducerIdentity:
        assert record is self._record
        assert evaluation_split == "test"
        return self._producer


def _write_internal_event_run(
    path,
    event_names: list[str],
    *,
    repeats: int,
    seed: int,
) -> None:
    sfreq = 64
    ordered_events = event_names * repeats
    duration_seconds = len(ordered_events) + 2
    info = mne.create_info(["C3", "C4"], sfreq, ch_types="eeg")
    raw = mne.io.RawArray(
        np.random.default_rng(seed).normal(
            size=(2, sfreq * duration_seconds),
        ),
        info,
        verbose=False,
    )
    event_desc = dict(enumerate(event_names, start=1))
    event_codes = {event_name: code for code, event_name in event_desc.items()}
    events = np.asarray(
        [
            [second * sfreq, 0, event_codes[event_name]]
            for second, event_name in enumerate(ordered_events, start=1)
        ],
        dtype=int,
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc=event_desc,
        )
    )
    raw.save(path, overwrite=True, verbose=False)


def _publish_final_labels(service: ApplicationService) -> tuple[set[str], set[str]]:
    dataset = service.study.datasets[0]
    epoch_data = dataset.get_epoch_data()
    class_count = len(epoch_data.label_map)
    labels = np.arange(class_count, dtype=int)
    outputs = np.eye(class_count, dtype=np.float32)
    saliency = {
        class_index: np.ones(
            (1, len(epoch_data.get_channel_names()), epoch_data.get_data().shape[-1]),
            dtype=np.float32,
        )
        for class_index in range(class_count)
    }
    eval_record = EvalRecord(
        label=labels,
        output=outputs,
        gradient=saliency,
        gradient_input={},
        smoothgrad={},
        smoothgrad_sq={},
        vargrad={},
        evaluation_split="test",
    )
    producer = SaliencyProducerIdentity.from_components(
        dataset={"name": dataset.get_name()},
        split={"name": "test"},
        run={"index": 0},
        model={"name": "semantic-label-probe"},
    )
    eval_record.bind_saliency_context(epoch_data, producer_identity=producer)

    record = object.__new__(TrainRecord)
    record.dataset = dataset
    record.eval_record = eval_record
    record.evaluation_records = {"test": eval_record}
    record.epoch = 1
    record.option = cast(Any, SimpleNamespace(epoch=1))
    record.repeat = 0
    record.plan_id = "semantic-label-probe"
    assert record.dataset.get_epoch_data().label_map == epoch_data.label_map

    holder = _TrainingHolder(dataset, record, producer)
    boundary = TrainingReadBoundary.no_trainer()
    publication: Any = SimpleNamespace(
        generation=1,
        usable=True,
        training_boundary=boundary,
    )
    runtime: Any = SimpleNamespace(
        has_trainer=lambda: True,
        training_plan_holders=lambda: [holder],
    )
    evaluation = EvaluationRenderPublisher(
        training_runtime=runtime,
        get_publication=lambda: publication,
        capture_training_boundary=lambda: boundary,
    ).publish(
        EvaluationRenderRequest(
            publication_generation=1,
            selection=EvaluationRunIdentity(
                plan=EvaluationPlanIdentity(plan_index=0),
                run_index=0,
            ),
        )
    )
    visualization = SaliencyRenderPublisher(
        training_runtime=runtime,
        get_publication=lambda: publication,
        capture_training_boundary=lambda: boundary,
    ).publish(
        SaliencyRenderRequest(
            publication_generation=1,
            run=SaliencyRunIdentity(
                plan=SaliencyPlanIdentity(plan_index=0),
                run_index=0,
            ),
            method="Gradient",
        )
    )
    return (
        set(evaluation.data.class_labels.values()),
        {display_name for _class_index, display_name in visualization.data.class_map},
    )


def _run_reviewed_workflow(
    tmp_path,
    *,
    files: list,
    choices: dict[str, Any],
    expected_labels: set[str],
) -> tuple[ApplicationService, dict[str, Any]]:
    service = ApplicationService()
    try:
        scan = service.execute(
            ScanSourceCommand(source_path=str(tmp_path), source_hint="folder")
        )
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        validation = service.execute(ValidateInterpretationCommand())
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert scan.ok, scan.message
        assert preview.ok, preview.message
        assert validation.ok, validation.message
        assert applied.ok, applied.message
        assert applied.state.interpretation.epoch_handoff["supervised_ready"] is True

        epoch = service.execute(CreateEpochCommand(t_min=0.0, t_max=0.25))
        generated = service.execute(
            GenerateDatasetCommand(
                test_ratio=0.2,
                val_ratio=0.2,
                split_strategy="trial",
                training_mode="group",
            )
        )
        assert epoch.ok, epoch.message
        assert generated.ok, generated.message
        assert set(epoch.state.epoch.event_ids) == expected_labels
        assert set(service.study.datasets[0].get_epoch_data().label_map.values()) == (
            expected_labels
        )
        assert len(service.preprocess.get_preprocessed_data_list()) == len(files)
        handoff = applied.state.interpretation.epoch_handoff
    except BaseException:
        service.close()
        raise
    return service, handoff


def test_ofner_reviewed_aliases_reach_evaluation_and_saliency_labels(tmp_path) -> None:
    eeg_path = tmp_path / "ofner_run_01_raw.fif"
    _write_internal_event_run(
        eeg_path,
        list(OFNER_CLASS_MAP),
        repeats=4,
        seed=17,
    )
    choices = {
        "selected_eeg_files": [str(eeg_path)],
        "label_carrier": "embedded_events",
        "class_map": OFNER_CLASS_MAP,
        "internal_event_selection": {
            "label_event_codes": list(OFNER_CLASS_MAP),
            "class_map": OFNER_CLASS_MAP,
        },
    }

    service, handoff = _run_reviewed_workflow(
        tmp_path,
        files=[eeg_path],
        choices=choices,
        expected_labels=set(OFNER_CLASS_MAP.values()),
    )
    try:
        assert handoff["event_label_aliases"] == OFNER_CLASS_MAP
        evaluation_labels, saliency_labels = _publish_final_labels(service)
        assert evaluation_labels == set(OFNER_CLASS_MAP.values())
        assert saliency_labels == set(OFNER_CLASS_MAP.values())
    finally:
        service.close()


def test_run_specific_t1_t2_meanings_stay_distinct_in_final_labels(tmp_path) -> None:
    run_04 = tmp_path / "S001R04_raw.fif"
    run_08 = tmp_path / "S001R08_raw.fif"
    _write_internal_event_run(run_04, ["T1", "T2"], repeats=5, seed=4)
    _write_internal_event_run(run_08, ["T1", "T2"], repeats=5, seed=8)
    run_maps = {
        run_04.name: {"T1": "left fist", "T2": "right fist"},
        run_08.name: {"T1": "both fists", "T2": "both feet"},
    }
    expected_labels = {
        "left fist",
        "right fist",
        "both fists",
        "both feet",
    }
    choices = {
        "selected_eeg_files": [str(run_04), str(run_08)],
        "label_carrier": "embedded_events",
        "internal_event_selection": {"label_event_codes": ["T1", "T2"]},
        "run_event_mappings": run_maps,
    }

    service, handoff = _run_reviewed_workflow(
        tmp_path,
        files=[run_04, run_08],
        choices=choices,
        expected_labels=expected_labels,
    )
    try:
        assert handoff["run_dependent_mapping"] is True
        assert "event_label_aliases" not in handoff
        hints = {
            data.get_filename(): data.get_runtime_detail(
                "data_interpretation_epoch_hint"
            )["event_label_aliases"]
            for data in service.preprocess.get_preprocessed_data_list()
        }
        assert hints == run_maps
        evaluation_labels, saliency_labels = _publish_final_labels(service)
        assert evaluation_labels == expected_labels
        assert saliency_labels == expected_labels
        assert not ({"T1", "T2"} & evaluation_labels)
        assert not ({"T1", "T2"} & saliency_labels)
    finally:
        service.close()
