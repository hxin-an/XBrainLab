"""Real backend workflow tests for the ApplicationService command layer."""

from __future__ import annotations

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
    SaliencyCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
)


def _write_synthetic_raw_fif(tmp_path):
    sfreq = 128
    n_channels = 4
    duration = 6
    ch_names = [f"EEG{i}" for i in range(n_channels)]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    data = np.random.default_rng(42).normal(
        size=(n_channels, sfreq * duration),
    )
    raw = mne.io.RawArray(data, info)
    events = np.array(
        [
            [128, 0, 1],
            [256, 0, 2],
            [384, 0, 1],
            [512, 0, 2],
            [640, 0, 1],
            [704, 0, 2],
        ],
    )
    annotations = mne.annotations_from_events(
        events,
        sfreq=sfreq,
        event_desc={1: "left", 2: "right"},
    )
    raw.set_annotations(annotations)

    path = tmp_path / "synthetic_raw.fif"
    raw.save(path, overwrite=True)
    return path


def test_application_service_load_epoch_dataset_workflow(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    load_result = service.execute(LoadDataCommand(paths=[str(fif_path)]))

    assert load_result.ok is True
    assert load_result.diagnostics["success_count"] == 1
    assert load_result.changed_state.raw_changed is True
    assert load_result.changed_state.preprocessed_changed is True
    assert load_result.state.raw.loaded is True
    assert load_result.state.preprocessed.available is True
    assert service.get_capabilities().get(CommandName.CREATE_EPOCH).available is True

    preprocess_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
    )
    assert preprocess_result.ok is True
    assert preprocess_result.changed_state.preprocessed_changed is True

    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.25,
            event_ids=["left", "right"],
        ),
    )

    assert epoch_result.ok is True
    assert epoch_result.changed_state.epoch_changed is True
    assert epoch_result.state.epoch.available is True
    assert epoch_result.state.epoch.epoch_count == 6
    assert epoch_result.state.dataset.available is False
    policy_after_epoch = service.get_capabilities()
    assert policy_after_epoch.get(CommandName.LOAD_DATA).available is False
    assert policy_after_epoch.get(CommandName.CREATE_EPOCH).available is False
    assert (
        "Reset the session"
        in policy_after_epoch.get(
            CommandName.CREATE_EPOCH,
        ).reasons[0]
    )
    assert (
        policy_after_epoch.get(CommandName.RESET_SESSION).confirmation_required is True
    )

    dataset_result = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
    )

    assert dataset_result.ok is True
    assert dataset_result.changed_state.datasets_changed is True
    assert dataset_result.state.dataset.available is True
    assert dataset_result.state.dataset.count > 0
    assert service.get_capabilities().get(CommandName.TRAIN).available is False

    model_result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
    assert model_result.ok is True
    assert model_result.changed_state.training_changed is True
    assert model_result.state.training.has_model is True
    assert service.get_capabilities().get(CommandName.TRAIN).available is False

    training_result = service.execute(
        ConfigureTrainingCommand(
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            output_dir=str(tmp_path / "training-output"),
        ),
    )
    assert training_result.ok is True
    assert training_result.state.training.has_training_option is True
    assert service.get_capabilities().get(CommandName.TRAIN).available is True

    evaluate_result = service.execute(EvaluateCommand())
    visualize_result = service.execute(VisualizeCommand())
    saliency_result = service.execute(SaliencyCommand())
    query_result = service.execute(QueryStateCommand(query="data_summary"))

    assert evaluate_result.failed is True
    assert visualize_result.ok is True
    assert visualize_result.diagnostics["payload_type"] == "visualization_summary"
    assert saliency_result.ok is True
    assert saliency_result.diagnostics["payload_type"] == "saliency_summary"
    assert query_result.ok is True
    assert query_result.diagnostics["count"] == 1

    reset_preprocess_without_confirmation = service.execute(ResetPreprocessCommand())
    assert reset_preprocess_without_confirmation.failed is True
    assert (
        reset_preprocess_without_confirmation.state.last_error.error_type
        == "confirmation_required"
    )

    reset_without_confirmation = service.execute(ResetSessionCommand())
    assert reset_without_confirmation.failed is True
    assert reset_without_confirmation.state.last_error is not None
    assert (
        reset_without_confirmation.state.last_error.error_type
        == "confirmation_required"
    )

    reset_result = service.execute(ResetSessionCommand(confirmed=True))
    assert reset_result.ok is True
    assert reset_result.state.raw.loaded is False
    assert reset_result.state.preprocessed.available is False
    assert reset_result.state.epoch.available is False
    assert reset_result.state.dataset.available is False
    assert reset_result.state.training.has_model is False
    assert reset_result.state.training.has_training_option is False
    assert reset_result.state.training.has_trainer is False
    assert reset_result.state.last_error is None
    assert reset_result.changed_state.error_changed is True
    assert service.get_capabilities().get(CommandName.LOAD_DATA).available is True


def test_data_interpretation_to_dataset_workflow_is_non_mocked(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    recipe_path = tmp_path / "synthetic_import_recipe.json"

    scan_result = service.execute(ScanSourceCommand(source_path=str(fif_path)))
    preview_result = service.execute(PreviewInterpretationCommand())
    validation_result = service.execute(ValidateInterpretationCommand())

    assert scan_result.ok is True
    assert scan_result.diagnostics["payload_type"] == "scan_result"
    assert preview_result.ok is True
    assert preview_result.diagnostics["payload_type"] == "interpretation_preview"
    assert validation_result.ok is True
    assert validation_result.state.interpretation.validation_decision == (
        "needs_confirmation"
    )

    apply_without_confirmation = service.execute(ApplyInterpretationCommand())
    assert apply_without_confirmation.failed is True
    assert (
        apply_without_confirmation.state.last_error.error_type
        == "confirmation_required"
    )

    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    save_recipe_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert apply_result.ok is True
    assert apply_result.changed_state.raw_changed is True
    assert apply_result.changed_state.interpretation_changed is True
    assert apply_result.state.raw.loaded is True
    assert apply_result.state.interpretation.has_applied_interpretation is True
    assert save_recipe_result.ok is True
    assert save_recipe_result.state.interpretation.has_recipe is True
    assert recipe_path.exists()

    reload_service = ApplicationService()
    reload_result = reload_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert reload_result.ok is True
    assert reload_result.diagnostics["payload_type"] == "recipe_reload_preview"
    assert reload_result.state.raw.loaded is False
    assert reload_result.state.interpretation.has_preview is True
    assert reload_result.state.interpretation.has_validation_decision is True

    preprocess_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
    )
    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.25,
            event_ids=["left", "right"],
        ),
    )
    dataset_result = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
    )

    assert preprocess_result.ok is True
    assert epoch_result.ok is True
    assert epoch_result.state.epoch.epoch_count == 6
    assert dataset_result.ok is True
    assert dataset_result.diagnostics["split_audit"]["ok"] is True
    assert dataset_result.state.dataset.available is True
    assert dataset_result.state.dataset.split_summary["train_count"] == 4
    assert dataset_result.state.dataset.split_summary["val_count"] == 1
    assert dataset_result.state.dataset.split_summary["test_count"] == 1


def test_application_service_failed_command_sets_and_clears_last_error(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    load_result = service.execute(LoadDataCommand(paths=[str(fif_path)]))
    assert load_result.ok is True
    assert load_result.state.last_error is None

    premature_dataset = service.execute(GenerateDatasetCommand())
    assert premature_dataset.failed is True
    assert premature_dataset.state.last_error is not None
    assert premature_dataset.state.raw.loaded is True
    assert premature_dataset.state.epoch.available is False
    assert premature_dataset.state.dataset.available is False
    assert premature_dataset.changed_state.error_changed is True
    assert premature_dataset.changed_state.datasets_changed is False

    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.25,
            event_ids=["left", "right"],
        ),
    )

    assert epoch_result.ok is True
    assert epoch_result.state.epoch.available is True
    assert epoch_result.state.last_error is None
    assert epoch_result.changed_state.error_changed is True
