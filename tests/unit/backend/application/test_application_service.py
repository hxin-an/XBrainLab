"""Application service contract tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyMontageCommand,
    ApplySmartParseCommand,
    AttachLabelsCommand,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    ErrorType,
    EvaluateCommand,
    GenerateDatasetCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    NewSessionCommand,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    RemoveFilesCommand,
    ResetSessionCommand,
    SaliencyCommand,
    StopTrainingCommand,
    TrainCommand,
    UpdateMetadataCommand,
    VisualizeCommand,
)
from XBrainLab.backend.study import Study


def test_empty_state_snapshot_and_policy():
    service = ApplicationService(Study())

    state = service.get_state()
    policy = service.get_capabilities()

    assert state.pipeline_stage == "empty"
    assert state.raw.loaded is False
    assert state.preprocessed.available is False
    assert state.epoch.available is False
    assert state.dataset.available is False
    assert state.training.has_trainer is False
    assert policy.get(CommandName.LOAD_DATA).available is True
    assert policy.get(CommandName.PREPROCESS).available is False
    assert policy.get(CommandName.TRAIN).available is False
    assert policy.get(CommandName.RESET_SESSION).confirmation_required is False


def test_capability_policy_covers_all_declared_commands():
    service = ApplicationService(Study())
    policy = service.get_capabilities()

    assert set(policy.capabilities) == {name.value for name in CommandName}
    assert policy.get(CommandName.EVALUATE).available is True
    assert policy.get(CommandName.VISUALIZE).available is True
    assert policy.get(CommandName.SALIENCY).available is True
    assert policy.get(CommandName.QUERY_STATE).available is True
    assert policy.get(CommandName.NEW_SESSION).available is True


def test_preprocess_capability_requires_raw_data_not_existing_preprocessed_copy():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = []

    policy = service.get_capabilities()

    assert policy.get(CommandName.PREPROCESS).available is True
    assert policy.get(CommandName.CREATE_EPOCH).available is False
    assert (
        "Preprocess data before creating epochs"
        in (policy.get(CommandName.CREATE_EPOCH).reasons[0])
    )


def test_evaluate_command_returns_service_backed_empty_summary():
    service = ApplicationService(Study())

    result = service.execute(EvaluateCommand())

    assert result.ok is True
    assert result.command_name == "evaluate"
    assert result.diagnostics["available"] is False
    assert result.diagnostics["plan_count"] == 0
    assert result.state.last_error is None


def test_visualize_and_saliency_commands_return_typed_query_payloads():
    service = ApplicationService(Study())

    visualize = service.execute(VisualizeCommand(view="summary"))
    saliency = service.execute(SaliencyCommand())

    assert visualize.ok is True
    assert visualize.command_name == "visualize"
    assert visualize.diagnostics["available"] is False
    assert "available_views" in visualize.diagnostics
    assert saliency.ok is True
    assert saliency.command_name == "saliency"
    assert saliency.diagnostics["saliency_configured"] is False


def test_saliency_command_can_configure_params():
    service = ApplicationService(Study())

    result = service.execute(SaliencyCommand(params={"method": "Gradient"}))

    assert result.ok is True
    assert result.changed_state.visualization_changed is True
    assert result.diagnostics["saliency_configured"] is True


def test_command_result_classifies_unsupported_load(tmp_path):
    service = ApplicationService(Study())
    unsupported_path = tmp_path / "sample.unsupported"
    unsupported_path.write_text("not eeg", encoding="utf-8")

    result = service.execute(LoadDataCommand(paths=[str(unsupported_path)]))

    assert result.failed is True
    assert result.ok is False
    assert result.command_name == "load_data"
    assert result.error_type == ErrorType.UNSUPPORTED_FORMAT
    assert result.recoverable is True
    assert result.state.last_error is not None
    assert result.state.last_error.error_type == "unsupported_format"
    assert result.changed_state.error_changed is True


def test_successful_command_clears_previous_last_error():
    service = ApplicationService(Study())

    failed_result = service.execute(TrainCommand())
    assert failed_result.failed is True
    assert failed_result.state.last_error is not None

    reset_result = service.execute(ResetSessionCommand())

    assert reset_result.ok is True
    assert reset_result.state.last_error is None
    assert reset_result.changed_state.error_changed is True


def test_train_command_blocked_until_backend_ready():
    service = ApplicationService(Study())

    result = service.execute(TrainCommand())

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Generate datasets before training" in result.message
    assert result.state.training.has_trainer is False


def test_every_declared_command_returns_result_envelope():
    service = ApplicationService(Study())
    commands = [
        LoadDataCommand(paths=[]),
        AttachLabelsCommand(mapping={}),
        ImportLabelsCommand(plan=LabelImportPlan(label_map={"labels": [1]})),
        UpdateMetadataCommand(index=0, subject="S01"),
        ApplySmartParseCommand(results={"/tmp/sample.fif": ("S01", "001")}),
        RemoveFilesCommand(indices=[0]),
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=1,
            high_freq=40,
        ),
        CreateEpochCommand(t_min=0, t_max=1),
        GenerateDatasetCommand(),
        ConfigureTrainingCommand(model_name="EEGNet"),
        TrainCommand(),
        EvaluateCommand(),
        VisualizeCommand(),
        SaliencyCommand(),
        StopTrainingCommand(),
        ApplyMontageCommand(channels=["Cz"], positions=[(0.0, 0.0, 0.0)]),
        QueryStateCommand(),
        ResetSessionCommand(),
        NewSessionCommand(),
    ]

    seen = set()
    for command in commands:
        result = service.execute(command)
        seen.add(result.command_name)
        assert result.command_name
        assert result.status.value in {"ok", "failed"}
        assert result.state is not None
        assert result.changed_state is not None

    assert seen == {name.value for name in CommandName}


def test_raw_mutation_commands_block_after_epoch_without_side_effects():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.dataset.remove_files = MagicMock()

    result = service.execute(RemoveFilesCommand(indices=[0]))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Reset the session" in result.message
    service.dataset.remove_files.assert_not_called()


def test_generate_dataset_blocks_when_dataset_already_exists():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.study.data_manager.datasets = [MagicMock()]

    result = service.execute(GenerateDatasetCommand())

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "new session" in result.message


def test_metadata_update_command_routes_through_service():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.dataset.update_metadata = MagicMock()

    result = service.execute(UpdateMetadataCommand(index=0, subject="S01"))

    assert result.ok is True
    assert result.command_name == CommandName.UPDATE_METADATA.value
    assert result.diagnostics["success_count"] == 1
    service.dataset.update_metadata.assert_called_once_with(
        0,
        subject="S01",
        session=None,
    )


def test_import_labels_plan_routes_batch_import():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    result = service.execute(
        ImportLabelsCommand(
            plan=LabelImportPlan(
                target_indices=[0],
                label_map={"labels.txt": [1, 2]},
                file_mapping={"/tmp/sample.fif": "labels.txt"},
                mapping={1: "left", 2: "right"},
                mode="batch",
            ),
        ),
    )

    assert result.ok is True
    assert result.diagnostics["success_count"] == 1
    service.dataset.apply_labels_batch.assert_called_once()


def test_apply_montage_command_routes_confirmed_positions():
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    service.preprocess.apply_montage = MagicMock()

    result = service.execute(
        ApplyMontageCommand(
            channels=["Cz"],
            positions=[(0.0, 0.0, 0.0)],
            montage_name="standard_1020",
        ),
    )

    assert result.ok is True
    assert result.command_name == CommandName.APPLY_MONTAGE.value
    service.preprocess.apply_montage.assert_called_once_with(
        ["Cz"],
        [(0.0, 0.0, 0.0)],
    )


def test_query_state_returns_typed_dataset_summary():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]

    result = service.execute(QueryStateCommand(query="data_summary"))

    assert result.ok is True
    assert result.diagnostics["count"] == 1
    assert result.diagnostics["metadata"][0]["subject"] == "S01"


def test_new_session_requires_confirmation_and_clears_single_backend_session():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]

    unconfirmed = service.execute(NewSessionCommand())

    assert unconfirmed.failed is True
    assert unconfirmed.error_type == ErrorType.CONFIRMATION_REQUIRED

    confirmed = service.execute(NewSessionCommand(confirmed=True))

    assert confirmed.ok is True
    assert confirmed.command_name == "new_session"
    assert confirmed.state.raw.loaded is False


def test_set_montage_preprocess_operation_requires_ui_confirmation():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.SET_MONTAGE,
            montage_name="standard_1020",
        ),
    )

    assert result.failed is True
    assert result.error_type == ErrorType.CONFIRMATION_REQUIRED
    assert "BackendFacade legacy path" in result.message


def _raw_mock():
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    raw.get_subject_name.return_value = "S01"
    raw.get_session_name.return_value = "001"
    raw.is_raw.return_value = True
    mne_raw = MagicMock()
    mne_raw.ch_names = ["C3", "C4"]
    mne_raw.annotations = []
    raw.get_mne.return_value = mne_raw
    return raw
