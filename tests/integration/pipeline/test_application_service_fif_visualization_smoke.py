"""Real command-spine smoke from FIF import through visualization readiness.

This test deliberately proves the ApplicationService workflow and persisted
training artifacts. It does not claim scientific model quality or arbitrary
FIF compatibility.
"""

from __future__ import annotations

from pathlib import Path
from threading import Event

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    EvaluationPlanIdentity,
    EvaluationRenderRequest,
    EvaluationRunIdentity,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
)
from XBrainLab.backend.application.owned_work import OwnedWorkPhase
from XBrainLab.backend.training import TrainingPlanHolder
from XBrainLab.backend.training.record import EvalRecord
from XBrainLab.backend.training.record.artifact_store import load_model_state_dict
from XBrainLab.backend.training_state_contract import TrainingOutcomeState


def _write_command_spine_fif(target: Path) -> None:
    sfreq = 128.0
    channel_names = ["C3", "C4", "Cz", "Pz"]
    info = mne.create_info(channel_names, sfreq=sfreq, ch_types="eeg")
    samples = int(sfreq * 26)
    rng = np.random.default_rng(20260730)
    data = rng.standard_normal((len(channel_names), samples))
    raw = mne.io.RawArray(data, info, verbose=False)
    events = np.asarray(
        [
            [second * int(sfreq), 0, 1 if index % 2 == 0 else 2]
            for index, second in enumerate(range(1, 25, 2))
        ],
        dtype=int,
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc={1: "left", 2: "right"},
        )
    )
    raw.save(target, overwrite=True, verbose=False)


def test_application_service_fif_reaches_persisted_visualization_readiness(
    tmp_path: Path,
) -> None:
    """Commands, real EEGNet execution and artifact writes reach visualization."""
    fif_path = tmp_path / "command-spine_raw.fif"
    output_root = tmp_path / "training-output"
    _write_command_spine_fif(fif_path)
    service = ApplicationService()

    try:
        scanned = service.execute(
            ScanSourceCommand(source_path=str(fif_path), source_hint="file")
        )
        previewed = service.execute(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(fif_path)],
                    "label_carrier": "embedded_events",
                    "class_map": {"left": "left", "right": "right"},
                    "internal_event_selection": {
                        "label_event_codes": ["left", "right"],
                        "class_map": {"left": "left", "right": "right"},
                    },
                }
            )
        )
        validated = service.execute(ValidateInterpretationCommand())
        imported = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert scanned.ok, scanned.message
        assert previewed.ok, previewed.message
        assert validated.ok, validated.message
        assert imported.ok, imported.message
        assert imported.state.raw.files == [fif_path.name]
        assert imported.state.interpretation.epoch_handoff["supervised_ready"] is True

        normalized = service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z-score",
            )
        )
        epoched = service.execute(
            CreateEpochCommand(
                t_min=0.0,
                t_max=1.3,
                event_ids=["left", "right"],
            )
        )
        split = service.execute(
            SaveDatasetSplitCommand(
                test_ratio=0.25,
                val_ratio=0.25,
                split_strategy="trial",
                training_mode="individual",
            )
        )
        configured = service.execute(
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=1,
                batch_size=2,
                learning_rate=0.001,
                device="cpu",
                save_checkpoints_every=0,
                output_dir=str(output_root),
                evaluation_option="val_acc",
            )
        )
        trained = service.execute(
            TrainCommand(confirmed=True, interactive=False),
        )
        evaluated = service.execute(EvaluateCommand())
        visualized = service.execute(VisualizeCommand(view="summary"))

        assert normalized.ok, normalized.message
        assert epoched.ok, epoched.message
        assert epoched.state.epoch.epoch_count == 12
        assert split.ok, split.message
        assert split.state.dataset.split_spec_saved is True
        assert split.state.dataset.available is False
        assert configured.ok, configured.message
        assert trained.ok, trained.message
        assert trained.diagnostics["split_preparation"]["split_audit"]["ok"] is True
        assert trained.state.dataset.available is True
        assert trained.state.training.finished_run_count == 1
        assert evaluated.ok, evaluated.message
        assert evaluated.diagnostics["available"] is True
        assert evaluated.diagnostics["finished_run_count"] == 1
        assert visualized.ok, visualized.message
        assert visualized.diagnostics["available"] is True
        assert visualized.diagnostics["trainer_count"] == 1
        assert {"confusion matrix", "metrics", "saliency setup"} <= set(
            visualized.diagnostics["available_views"]
        )

        persisted_files = [path for path in output_root.rglob("*") if path.is_file()]
        assert persisted_files
        assert any(path.name == "record" for path in persisted_files)
        assert any(path.name.startswith("Epoch-1-model") for path in persisted_files)
    finally:
        assert service.wait_for_background_tasks(timeout=30.0)
        service.close()


def test_command_subject_folds_stop_restart_and_reopen_exact_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real admitted multi-plan work survives Stop and republishes saved results.

    The sole training interception runs the real first plan, then pauses its
    return so Stop is deterministic. No admission, compute or IO is stubbed.
    """
    sources = tmp_path / "sources"
    sources.mkdir()
    paths = [sources / f"subject-{index}_raw.fif" for index in range(3)]
    for path in paths:
        _write_command_spine_fif(path)
    output_root = tmp_path / "training-output"
    service = ApplicationService()
    first_plan_saved = Event()
    release_first_plan = Event()
    real_train = TrainingPlanHolder.train

    def pause_after_first_real_plan(holder: TrainingPlanHolder) -> None:
        real_train(holder)
        if not first_plan_saved.is_set():
            first_plan_saved.set()
            assert release_first_plan.wait(timeout=20.0)

    monkeypatch.setattr(TrainingPlanHolder, "train", pause_after_first_real_plan)
    try:
        commands = (
            ScanSourceCommand(source_path=str(sources)),
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(path) for path in paths],
                    "metadata_overrides": {
                        path.name: {"subject": f"S{index}", "session": "01"}
                        for index, path in enumerate(paths)
                    },
                    "label_carrier": "embedded_events",
                    "class_map": {"left": "left", "right": "right"},
                    "internal_event_selection": {
                        "label_event_codes": ["left", "right"],
                        "class_map": {"left": "left", "right": "right"},
                    },
                },
            ),
            ValidateInterpretationCommand(),
            ApplyInterpretationCommand(confirmed=True),
            CreateEpochCommand(t_min=0.0, t_max=1.3, event_ids=["left", "right"]),
            SaveDatasetSplitCommand(
                split_config={
                    "train_type": "Individual",
                    "is_cross_validation": True,
                    "val_splitters": [],
                    "test_splitters": [
                        {
                            "split_type": "By Trial",
                            "split_unit": "K Fold",
                            "value": "5",
                            "is_option": True,
                        }
                    ],
                },
            ),
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=1,
                batch_size=2,
                learning_rate=0.001,
                device="cpu",
                output_dir=str(output_root),
                evaluation_option="Last Epoch",
                seed=1729,
            ),
        )
        for command in commands:
            result = service.execute(command)
            assert result.ok, result.message

        train_command = TrainCommand(confirmed=True, interactive=True)
        first_operation = service.begin_owned_operation(train_command)
        started = service.execute(
            train_command, operation_id=first_operation.operation_id
        )
        assert started.ok, started.message
        assert started.state.training.plan_count == 15
        assert first_plan_saved.wait(timeout=20.0)
        stopped = service.execute(StopTrainingCommand(wait_timeout=0.0))
        assert stopped.ok, stopped.message
        assert stopped.diagnostics["control_path"] == "lock_independent"
        release_first_plan.set()
        assert service.wait_for_background_tasks(timeout=30.0)
        cancelled = service.get_state()
        assert (
            cancelled.training.terminal_outcome.state is TrainingOutcomeState.CANCELLED
        )
        assert cancelled.training.finished_run_count == 1
        assert (
            service.get_owned_operation(first_operation.operation_id).phase
            is OwnedWorkPhase.CANCELLED
        )
        saved_before_restart = set(output_root.rglob("record"))
        assert len(saved_before_restart) == 1
        previous_bytes = {path: path.read_bytes() for path in saved_before_restart}

        second_operation = service.begin_owned_operation(train_command)
        restarted = service.execute(
            train_command, operation_id=second_operation.operation_id
        )
        assert restarted.ok, restarted.message
        assert service.wait_for_background_tasks(timeout=45.0)
        completed = service.get_state()
        assert (
            completed.training.terminal_outcome.state is TrainingOutcomeState.COMPLETED
        )
        assert (
            completed.training.terminal_outcome.run
            != cancelled.training.terminal_outcome.run
        )
        assert completed.training.plan_count == 30
        assert completed.training.finished_run_count == 16
        assert (
            service.get_owned_operation(second_operation.operation_id).phase
            is OwnedWorkPhase.COMPLETED
        )
        assert (
            service.get_owned_operation(first_operation.operation_id).phase
            is OwnedWorkPhase.CANCELLED
        )
        assert all(
            path.read_bytes() == content for path, content in previous_bytes.items()
        )

        records = set(output_root.rglob("record"))
        assert len(records - saved_before_restart) == 15
        for path in records:
            reloaded = EvalRecord.load(str(path.parent))
            assert reloaded is not None
            assert reloaded.evaluation_split == "test"
            assert load_model_state_dict(path.parent / "Epoch-1-model")
        history = service.execute(QueryStateCommand(query="training_history"))
        assert history.ok, history.message
        assert (
            sum(row["status"] == "Completed" for row in history.diagnostics["rows"])
            == 16
        )
        evaluated = service.execute(EvaluateCommand())
        assert evaluated.ok, evaluated.message
        assert evaluated.diagnostics["finished_run_count"] == 16
        assert evaluated.diagnostics["evaluation_splits"] == ["test", "training"]

        publication = service.get_view_publication()
        request = EvaluationRenderRequest(
            publication_generation=publication.generation,
            selection=EvaluationRunIdentity(EvaluationPlanIdentity(15), 0),
            trainer_identity=publication.training_boundary.trainer_identity,
            split_specification_fingerprint=publication.state.dataset.split_specification_fingerprint,
            split_epoch_revision=publication.state.dataset.split_epoch_revision,
            split="test",
        )
        rendered = service.get_evaluation_render(request)
        assert rendered.data.evaluation_split == "test"
        assert rendered.data.labels.size in {2, 3}
        assert rendered.data.outputs.shape == (rendered.data.labels.size, 2)
        assert not rendered.data.outputs.flags.writeable
        selected_record = service.training_runtime.training_plan_holders()[
            15
        ].train_record_list[0]
        selected_saved = EvalRecord.load(selected_record.target_path)
        assert selected_saved is not None
        np.testing.assert_array_equal(rendered.data.labels, selected_saved.label)
        np.testing.assert_array_equal(rendered.data.outputs, selected_saved.output)
    finally:
        release_first_plan.set()
        service.execute(StopTrainingCommand(wait_timeout=0.0))
        try:
            assert service.wait_for_background_tasks(timeout=30.0)
        finally:
            service.close()
