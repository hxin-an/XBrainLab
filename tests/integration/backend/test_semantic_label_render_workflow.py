"""Reviewed class semantics must survive the complete downstream workflow."""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluationPlanIdentity,
    EvaluationRenderRequest,
    EvaluationRunIdentity,
    PreviewInterpretationCommand,
    SaliencyPlanIdentity,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
    training_service,
)
from XBrainLab.backend.application.evaluation_render import EvaluationRenderPublisher
from XBrainLab.backend.application.resource_guard import ResourcePreflightResult
from XBrainLab.backend.application.saliency_render import SaliencyRenderPublisher
from XBrainLab.backend.training import Trainer
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.record.train import TrainRecord
from XBrainLab.backend.training.saliency_provenance import (
    SaliencyArtifactContext,
    SaliencyProducerIdentity,
)

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
        sealed_epoch_data_fingerprint: str | None = None,
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


def _publish_final_label_maps(
    service: ApplicationService,
) -> tuple[dict[int, str], tuple[tuple[int, str], ...]]:
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
    publication = service.get_view_publication()
    boundary = publication.training_boundary
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
            publication_generation=publication.generation,
            selection=EvaluationRunIdentity(
                plan=EvaluationPlanIdentity(plan_index=0),
                run_index=0,
            ),
            trainer_identity=boundary.trainer_identity,
            split_specification_fingerprint=(
                publication.state.dataset.split_specification_fingerprint
            ),
            split_epoch_revision=publication.state.dataset.split_epoch_revision,
        )
    )
    visualization = SaliencyRenderPublisher(
        training_runtime=runtime,
        get_publication=lambda: publication,
        capture_training_boundary=lambda: boundary,
    ).publish(
        SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=SaliencyRunIdentity(
                plan=SaliencyPlanIdentity(plan_index=0),
                run_index=0,
            ),
            method="Gradient",
        )
    )
    return dict(evaluation.data.class_labels), tuple(visualization.data.class_map)


def _publish_final_labels(service: ApplicationService) -> tuple[set[str], set[str]]:
    evaluation_labels, saliency_labels = _publish_final_label_maps(service)
    return set(evaluation_labels.values()), {
        display_name for _class_index, display_name in saliency_labels
    }


def _run_reviewed_workflow(
    tmp_path,
    monkeypatch,
    *,
    files: list,
    choices: dict[str, Any],
    expected_labels: set[str],
    source_path=None,
    source_hint: str = "folder",
) -> tuple[ApplicationService, dict[str, Any]]:
    service = ApplicationService()
    try:
        scan = service.execute(
            ScanSourceCommand(
                source_path=str(source_path or tmp_path),
                source_hint=source_hint,
            )
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
            SaveDatasetSplitCommand(
                test_ratio=0.2,
                val_ratio=0.2,
                split_strategy="trial",
                training_mode="group",
            )
        )
        assert epoch.ok, epoch.message
        assert generated.ok, generated.message
        assert set(epoch.state.epoch.event_ids) == expected_labels
        assert generated.state.dataset.split_spec_saved is True
        assert generated.state.dataset.available is False
        assert service.study.datasets == []

        configured = service.execute(
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=1,
                batch_size=2,
                learning_rate=0.001,
                device="cpu",
                output_dir=str(tmp_path / "training-output"),
            )
        )

        def publish_training_identity(**_kwargs: Any) -> int:
            trainer = Trainer([])
            trainer.run(interact=False)
            service.study.training_manager.trainer = trainer
            return 1

        service.training.start_training = MagicMock(
            side_effect=publish_training_identity
        )
        monkeypatch.setattr(
            training_service,
            "check_training_resource_preflight",
            lambda *_args, **_kwargs: ResourcePreflightResult(
                issues=(), diagnostics={"risk_level": "safe"}
            ),
        )
        trained = service.execute(TrainCommand(confirmed=True))

        assert configured.ok, configured.message
        assert trained.ok, trained.message
        assert trained.state.dataset.available is True
        assert trained.diagnostics["split_preparation"]["split_audit"]["ok"] is True
        assert set(service.study.datasets[0].get_epoch_data().label_map.values()) == (
            expected_labels
        )
        assert len(service.preprocess.get_preprocessed_data_list()) == len(files)
        handoff = applied.state.interpretation.epoch_handoff
    except BaseException:
        service.close()
        raise
    return service, handoff


def test_ofner_reviewed_aliases_reach_evaluation_and_saliency_labels(
    tmp_path,
    monkeypatch,
) -> None:
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
        monkeypatch,
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


def test_run_specific_t1_t2_meanings_stay_distinct_in_final_labels(
    tmp_path,
    monkeypatch,
) -> None:
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
        monkeypatch,
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


def test_bids_source_event_codes_stay_separate_from_runtime_class_indices(
    tmp_path,
    monkeypatch,
) -> None:
    """Reviewed BIDS codes are provenance, not the model's class indices.

    The TSV deliberately puts ``zeta`` before ``alpha`` and gives both values
    non-contiguous source codes.  The runtime contract may canonicalize the
    supervised classes, but must never leak those source codes into the
    contiguous Epochs/Evaluation/Saliency class-index space.
    """
    bids_root, eeg_path, events_path = _write_bids_event_value_run(tmp_path)
    choices = {
        "selected_eeg_files": [str(eeg_path)],
        "label_carrier_choices": {
            str(events_path): {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "granularity": "event",
                "value_decisions": {
                    "zeta": {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "zeta",
                    },
                    "alpha": {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "alpha",
                    },
                    "nuisance": {
                        "role": "response",
                        "keep_event": True,
                        "use_as_class": False,
                    },
                },
            }
        },
    }

    service, handoff = _run_reviewed_workflow(
        tmp_path,
        monkeypatch,
        files=[eeg_path],
        choices=choices,
        expected_labels={"alpha", "zeta"},
        source_path=bids_root,
        source_hint="bids",
    )
    try:
        # The formal BIDS source owns its non-contiguous source codes and source
        # row order.  Runtime class indices are deliberately a separate contract.
        with events_path.open(newline="", encoding="utf-8") as source_file:
            source_rows = list(csv.DictReader(source_file, delimiter="\t"))
        assert [row["trial_type"] for row in source_rows[:3]] == [
            "zeta",
            "alpha",
            "nuisance",
        ]
        assert {row["trial_type"]: row["value"] for row in source_rows} == {
            "zeta": "7",
            "alpha": "9",
            "nuisance": "42",
        }

        # Applied interpretation retains all reviewed values, including the
        # excluded nuisance event, without treating source codes as class IDs.
        catalog = handoff["event_catalog"]
        assert {row["raw_value"] for row in catalog} == {
            "zeta",
            "alpha",
            "nuisance",
        }
        assert {
            row["raw_value"]
            for row in catalog
            if row["keep_event"] is True and row["use_as_class"] is False
        } == {"nuisance"}

        epoch_data = service.study.datasets[0].get_epoch_data()
        assert epoch_data.label_map == {0: "alpha", 1: "zeta"}
        assert epoch_data.event_id == {"alpha": 0, "zeta": 1}

        producer = SaliencyProducerIdentity.from_components(
            dataset={"name": "bids-event-value-probe"},
            split={"name": "test"},
            run={"index": 0},
            model={"name": "semantic-label-probe"},
        )
        context = SaliencyArtifactContext.from_epoch_data(
            epoch_data,
            class_count=2,
            producer_identity=producer,
        )
        assert context.class_map == ((0, "alpha"), (1, "zeta"))

        evaluation_labels, saliency_labels = _publish_final_label_maps(service)
        assert evaluation_labels == {0: "alpha", 1: "zeta"}
        assert saliency_labels == ((0, "alpha"), (1, "zeta"))
    finally:
        service.close()


def _write_bids_event_value_run(tmp_path):
    root = tmp_path / "bids-event-values"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "event value contract", "BIDSVersion": "1.9.0"}),
        encoding="utf-8",
    )
    eeg_path = eeg_dir / "sub-01_task-mi_eeg.fif"
    raw = mne.io.RawArray(
        np.zeros((2, 1000)),
        mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
        verbose=False,
    )
    raw.save(eeg_path, overwrite=True, verbose=False)
    events_path = eeg_dir / "sub-01_task-mi_events.tsv"
    event_rows = [
        "0.5\t0\tzeta\t7",
        "1.0\t0\talpha\t9",
        "1.5\t0\tnuisance\t42",
        *(
            f"{2.0 + 0.5 * index:.1f}\t0\t{label}\t{code}"
            for index, (label, code) in enumerate([("zeta", "7"), ("alpha", "9")] * 5)
        ),
    ]
    events_path.write_text(
        "onset\tduration\ttrial_type\tvalue\n" + "\n".join(event_rows) + "\n",
        encoding="utf-8",
    )
    (eeg_dir / "sub-01_task-mi_events.json").write_text(
        json.dumps(
            {
                "trial_type": {
                    "Levels": {
                        "zeta": "Zeta trial",
                        "alpha": "Alpha trial",
                        "nuisance": "Nuisance response",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return root, eeg_path.resolve(), events_path.resolve()
