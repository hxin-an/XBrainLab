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
    ImportRecipe,
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
from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
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


def test_application_service_accepts_dialog_generator_split_and_updates_readiness(
    tmp_path,
):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    assert service.execute(LoadDataCommand(paths=[str(fif_path)])).ok is True
    assert (
        service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z-score",
            ),
        ).ok
        is True
    )
    assert (
        service.execute(
            CreateEpochCommand(
                t_min=0.0,
                t_max=0.25,
                event_ids=["left", "right"],
            ),
        ).ok
        is True
    )

    dialog_like_config = DataSplittingConfig(
        train_type=TrainingType.FULL,
        is_cross_validation=False,
        val_splitter_list=[
            DataSplitter(
                split_type=ValSplitByType.TRIAL,
                value_var="0.2",
                split_unit=SplitUnit.RATIO,
            ),
        ],
        test_splitter_list=[
            DataSplitter(
                split_type=SplitByType.TRIAL,
                value_var="0.2",
                split_unit=SplitUnit.RATIO,
            ),
        ],
    )
    generator = service.study.get_datasets_generator(dialog_like_config)

    dataset_result = service.execute(GenerateDatasetCommand(generator=generator))

    assert dataset_result.ok is True
    assert dataset_result.diagnostics["split_audit"]["ok"] is True
    assert dataset_result.state.dataset.available is True
    assert dataset_result.state.dataset.split_summary["train_count"] > 0
    assert dataset_result.state.dataset.split_summary["val_count"] > 0
    assert dataset_result.state.dataset.split_summary["test_count"] > 0

    assert service.execute(ConfigureTrainingCommand(model_name="EEGNet")).ok is True
    assert (
        service.execute(
            ConfigureTrainingCommand(
                epoch=1,
                batch_size=2,
                learning_rate=0.001,
                output_dir=str(tmp_path / "training-output"),
            ),
        ).ok
        is True
    )
    assert service.get_capabilities().get(CommandName.TRAIN).available is True


def test_data_interpretation_to_dataset_workflow_is_non_mocked(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    recipe_path = tmp_path / "synthetic_import_recipe.json"

    scan_result = service.execute(ScanSourceCommand(source_path=str(fif_path)))
    recipe_choices = {
        "metadata_overrides": {
            fif_path.name: {
                "subject": "S01",
                "task": "motor-imagery",
            }
        },
        "event_roles": {"internal_events": "class cue"},
        "class_map": {"1": "left", "2": "right"},
    }
    preview_result = service.execute(
        PreviewInterpretationCommand(choices=recipe_choices),
    )
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
    reloaded_candidate = reload_result.diagnostics["candidate"]
    reload_preview = reload_result.diagnostics["preview"]
    assert (
        reloaded_candidate["choices"]["metadata_overrides"]
        == (recipe_choices["metadata_overrides"])
    )
    assert reload_preview["recipe_reload_summary"]["reapplied_choice_types"] == [
        "selected EEG files",
        "metadata overrides",
        "event roles",
        "class map",
    ]
    assert {
        "item": "EEG files",
        "status": "Matched",
        "detail": "Saved recipe still matches 1 saved file(s).",
    } in reload_preview["recipe_reload_summary"]["diff_rows"]
    assert reloaded_candidate["event_roles"]["internal_events"] == "class cue"
    assert reloaded_candidate["class_map"] == {"1": "left", "2": "right"}
    assert "choices:metadata_overrides" in reloaded_candidate["recipe_trace"]
    assert "choices:event_roles" in reloaded_candidate["recipe_trace"]
    assert "choices:class_map" in reloaded_candidate["recipe_trace"]

    reload_apply_without_confirmation = reload_service.execute(
        ApplyInterpretationCommand(),
    )
    reload_apply_result = reload_service.execute(
        ApplyInterpretationCommand(confirmed=True),
    )

    assert reload_apply_without_confirmation.failed is True
    assert (
        reload_apply_without_confirmation.state.last_error.error_type
        == "confirmation_required"
    )
    assert reload_apply_result.ok is True
    assert reload_apply_result.state.raw.loaded is True
    assert reload_apply_result.state.raw.files == [fif_path.name]
    assert reload_apply_result.diagnostics["applied_interpretation"][
        "loaded_files"
    ] == [str(fif_path)]

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


def test_reload_recipe_blocks_missing_saved_eeg_file(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    recipe_path = tmp_path / "missing-file-recipe.json"
    missing_path = tmp_path / "missing_raw.fif"
    ImportRecipe(
        recipe_id="recipe-missing",
        interpretation_id="interpretation-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(fif_path), str(missing_path)],
    ).write_json(str(recipe_path))

    reload_result = service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert reload_result.ok is True
    decision = reload_result.diagnostics["validation_decision"]
    assert decision["decision"] == "blocked"
    assert "missing_raw.fif" in decision["blocked_reasons"][0]
    assert reload_result.state.interpretation.validation_decision == "blocked"


def test_reload_recipe_blocks_missing_saved_label_carrier(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    recipe_path = tmp_path / "missing-label-carrier-recipe.json"
    missing_events = tmp_path / "missing_events.tsv"
    ImportRecipe(
        recipe_id="recipe-missing-label",
        interpretation_id="interpretation-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(fif_path)],
        label_carriers=[str(missing_events)],
    ).write_json(str(recipe_path))

    reload_result = service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert reload_result.ok is True
    decision = reload_result.diagnostics["validation_decision"]
    assert decision["decision"] == "blocked"
    assert "missing_events.tsv" in decision["blocked_reasons"][0]
    assert "label/event carrier" in decision["blocked_reasons"][0]
    assert reload_result.state.interpretation.validation_decision == "blocked"


def test_reload_recipe_accepts_explicit_label_carrier_remap(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    old_events = tmp_path / "old_events.tsv"
    new_events = tmp_path / "renamed_events.tsv"
    new_events.write_text("onset\tduration\ttrial_type\n1\t0\tleft\n", encoding="utf-8")
    recipe_path = tmp_path / "remap-label-carrier-recipe.json"
    ImportRecipe(
        recipe_id="recipe-remap-label",
        interpretation_id="interpretation-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(fif_path)],
        label_carriers=[str(old_events)],
        label_carrier_plan=[
            {
                "path": str(old_events),
                "selected_label_field": "trial_type",
                "selected_anchor": "onset",
                "time_model": "seconds",
                "granularity": "trial",
                "role": "class cue labels",
            }
        ],
    ).write_json(str(recipe_path))

    reload_result = service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    scan = reload_result.diagnostics["scan_result"]
    candidate = reload_result.diagnostics["candidate"]
    choices = dict(candidate["choices"])
    choices["label_carrier_remap"] = {
        str(old_events): str(new_events),
    }

    preview_result = service.execute(
        PreviewInterpretationCommand(
            scan_id=scan["scan_id"],
            choices=choices,
        ),
    )
    validation_result = service.execute(ValidateInterpretationCommand())

    assert reload_result.diagnostics["validation_decision"]["decision"] == "blocked"
    assert preview_result.ok is True
    assert validation_result.ok is True
    assert validation_result.diagnostics["validation_decision"]["decision"] == (
        "needs_confirmation"
    )
    remapped = preview_result.diagnostics["candidate"]["label_carrier_plan"][0]
    assert remapped["path"] == str(new_events)
    assert remapped["selected_label_field"] == "trial_type"
    assert (
        "choices:label_carrier_remap"
        in preview_result.diagnostics["candidate"]["recipe_trace"]
    )


def test_reload_recipe_accepts_explicit_eeg_file_remap(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    old_fif = tmp_path / "old_raw.fif"
    recipe_path = tmp_path / "remap-eeg-file-recipe.json"
    ImportRecipe(
        recipe_id="recipe-remap-eeg",
        interpretation_id="interpretation-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(old_fif)],
    ).write_json(str(recipe_path))

    reload_result = service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    scan = reload_result.diagnostics["scan_result"]
    candidate = reload_result.diagnostics["candidate"]
    choices = dict(candidate["choices"])
    choices["eeg_file_remap"] = {
        str(old_fif): str(fif_path),
    }

    preview_result = service.execute(
        PreviewInterpretationCommand(
            scan_id=scan["scan_id"],
            choices=choices,
        ),
    )
    validation_result = service.execute(ValidateInterpretationCommand())

    assert reload_result.diagnostics["validation_decision"]["decision"] == "blocked"
    assert preview_result.ok is True
    assert validation_result.ok is True
    assert validation_result.diagnostics["validation_decision"]["decision"] in {
        "safe",
        "needs_confirmation",
    }
    remapped = preview_result.diagnostics["candidate"]
    assert remapped["selected_eeg_files"] == [str(fif_path)]
    assert "choices:eeg_file_remap" in remapped["recipe_trace"]


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
