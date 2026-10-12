"""Application boundary: service behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from tests.unit.backend.application.application_test_support import (
    _raw_mock,
    _use_test_raw_factory,
)
from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationService,
    ApplyInterpretationCommand,
    ApplyMontageCommand,
    ApplySmartParseCommand,
    ChangedState,
    ClearDatasetsCommand,
    ClearTrainingHistoryCommand,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    DiscardTrainingPreparationCommand,
    ErrorType,
    EvaluateCommand,
    NewSessionCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    RemoveFilesCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
    ReviewInterpretationCommand,
    SaliencyCommand,
    SaveDatasetSplitCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
)
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.state import (
    ErrorSnapshot,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    Trainer,
)
from XBrainLab.backend.utils.filesystem_identity import LegacyOutputNamespaceError


def test_product_pipeline_rollback_restores_complete_data_manager_state() -> None:
    study = Study()
    service = ApplicationService(study)
    manager = study.data_manager
    old_raw = object()
    old_backup = object()
    old_preprocessed = object()
    old_epoch = object()
    old_dataset = object()
    old_generator = object()
    manager.loaded_data_list = [old_raw]  # type: ignore[list-item]
    manager.backup_loaded_data_list = [old_backup]  # type: ignore[list-item]
    manager.preprocessed_data_list = [old_preprocessed]  # type: ignore[list-item]
    manager.epoch_data = old_epoch  # type: ignore[assignment]
    manager.datasets = [old_dataset]  # type: ignore[list-item]
    manager.dataset_generator = old_generator  # type: ignore[assignment]
    manager.dataset_locked = True

    snapshot = service.pipeline_transaction.capture()
    manager.loaded_data_list = []
    manager.backup_loaded_data_list = None
    manager.preprocessed_data_list = []
    manager.epoch_data = None
    manager.datasets = []
    manager.dataset_generator = None
    manager.dataset_locked = False
    service.pipeline_transaction.restore(snapshot)

    assert manager.loaded_data_list == [old_raw]
    assert manager.backup_loaded_data_list == [old_backup]
    assert manager.preprocessed_data_list == [old_preprocessed]
    assert manager.epoch_data is old_epoch
    assert manager.datasets == [old_dataset]
    assert manager.dataset_generator is old_generator
    assert manager.dataset_locked is True


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
    assert state.interpretation.has_scan_result is False
    assert state.interpretation.has_applied_interpretation is False
    assert policy.get(CommandName.SCAN_SOURCE).available is True
    assert policy.get(CommandName.PREVIEW_INTERPRETATION).available is False
    assert policy.get(CommandName.PREPROCESS).available is False
    assert policy.get(CommandName.TRAIN).available is False
    assert policy.get(CommandName.TRAIN).requires_confirmation is True
    assert policy.get(CommandName.TRAIN).can_auto_execute is False
    assert policy.get(CommandName.RESET_SESSION).confirmation_required is False


def test_serialized_query_uses_committed_state_when_fresh_builder_is_unavailable() -> (
    None
):
    service = ApplicationService(Study())
    service.state_snapshot.build = MagicMock(
        side_effect=RuntimeError("state backend unavailable"),
    )

    result = service.execute(QueryStateCommand(query="data_lists"))

    assert result.ok is True
    assert result.diagnostics["raw_count"] == 0
    assert result.state.state_reliable is True
    assert result.state.pipeline_stage == "empty"
    service.state_snapshot.build.assert_not_called()


def test_stop_control_uses_detached_publication_and_preserves_concurrent_error() -> (
    None
):
    service = ApplicationService(Study())
    committed = service.get_view_publication()
    retained_error = ErrorSnapshot(
        error_type=ErrorType.INTERNAL.value,
        message="concurrent command failure",
        recoverable=True,
    )
    service._last_error = retained_error
    service.state_snapshot.build = MagicMock(
        side_effect=AssertionError("control acknowledgement rebuilt mutable state"),
    )

    result = service.execute(StopTrainingCommand(wait_timeout=0.0))

    assert result.ok is True
    assert result.state == committed.state
    assert result.changed_state == ChangedState()
    assert service._last_error is retained_error
    service.state_snapshot.build.assert_not_called()


def test_handler_error_and_refresh_failure_fails_closed_without_retry() -> None:
    service = ApplicationService(Study())
    before = service.get_state()
    service.state_snapshot.build = MagicMock(
        side_effect=[before, RuntimeError("refresh unavailable")],
    )

    result = service.execute(
        ConfigureTrainingCommand(model_name="not-a-real-model"),
    )

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert result.recoverable is False
    assert result.diagnostics["state_refresh_error"] == "refresh unavailable"
    assert result.diagnostics["handler_error_type"] == ErrorType.VALIDATION.value
    assert "Unknown model architecture" in result.diagnostics["handler_error_message"]
    assert result.diagnostics["command_effect_may_have_applied"] is True
    assert result.state is not before
    assert result.state.state_reliable is False
    assert result.state.pipeline_stage == "unavailable"


def test_handler_failure_does_not_execute_hostile_exception_metaclass() -> None:
    class HostileMeta(type):
        def __getattribute__(cls, name: str) -> object:
            if name == "__name__":
                raise AssertionError("hostile exception metaclass name access executed")
            return super().__getattribute__(name)

    class HostileHandlerError(Exception, metaclass=HostileMeta):
        def __str__(self) -> str:
            raise AssertionError("hostile exception string protocol executed")

    service = ApplicationService(Study())

    def fail(_command: ConfigureTrainingCommand) -> Any:
        raise HostileHandlerError("/srv/Clinical Records/Mary Example")

    service._command_handlers[CommandName.CONFIGURE_TRAINING] = fail

    result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert result.message == "An unexpected application error occurred."
    assert result.diagnostics["exception_type"] == "Exception"
    assert "Mary Example" not in repr(result.to_public_dict())


def test_unexpected_handler_failure_is_logged_at_the_command_boundary() -> None:
    service = ApplicationService(Study())

    class InjectedTrainingFailure(Exception):
        pass

    def fail(_command: ConfigureTrainingCommand) -> Any:
        raise InjectedTrainingFailure("injected training configuration failure")

    service._command_handlers[CommandName.CONFIGURE_TRAINING] = fail

    with patch(
        "XBrainLab.backend.application.service.logger.exception",
    ) as log_exception:
        result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))

    assert result.failed is True
    assert result.message == "An unexpected application error occurred."
    log_exception.assert_called_once_with(
        "%s command failed unexpectedly",
        CommandName.CONFIGURE_TRAINING.value,
    )


def test_legacy_training_output_namespace_is_an_actionable_precondition() -> None:
    service = ApplicationService(Study())

    def fail(_command: TrainCommand) -> Any:
        raise LegacyOutputNamespaceError("private legacy namespace detail")

    service._command_handlers[CommandName.TRAIN] = fail
    service._ensure_command_allowed = MagicMock()

    result = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.message == (
        "The selected training output folder contains results from an older "
        "XBrainLab version. Choose a different output folder or archive the "
        "existing results before starting training."
    )
    assert "private legacy namespace detail" not in repr(result.to_public_dict())


def test_explicit_state_unknown_handler_failure_fails_closed_when_state_is_readable() -> (
    None
):
    service = ApplicationService(Study())

    def fail_with_partial_rollback(_command: Any) -> Any:
        raise ApplicationError(
            message="Label rollback was incomplete.",
            error_type=ErrorType.INTERNAL,
            recoverable=False,
            diagnostics={
                "state_unknown": True,
                "retryable": False,
                "command_effect_may_have_applied": True,
            },
        )

    service._command_handlers[CommandName.CONFIGURE_TRAINING] = (
        fail_with_partial_rollback
    )

    result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))

    assert result.failed is True
    assert result.recoverable is False
    assert result.diagnostics["state_unknown"] is True
    assert result.diagnostics["command_effect_may_have_applied"] is True
    assert result.changed_state.state_unknown is True
    assert result.state.state_reliable is False


def test_state_read_failure_marks_the_entire_ui_state_unknown() -> None:
    service = ApplicationService(Study())
    service.state_snapshot.build = MagicMock(
        side_effect=RuntimeError("snapshot unavailable")
    )

    result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))

    assert result.failed is True
    assert result.changed_state.error_changed is True
    assert result.changed_state.state_unknown is True


def test_successful_mutation_fails_closed_when_updated_state_cannot_be_verified() -> (
    None
):
    service = ApplicationService(Study())
    before_publication = service.get_view_publication()
    publications = []
    service.subscribe(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        publications.append,
    )
    before = service.get_state()
    service.state_snapshot.build = MagicMock(
        side_effect=[before, RuntimeError("refresh unavailable")],
    )

    result = service.execute(NewSessionCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert result.recoverable is False
    assert result.state.state_reliable is False
    assert result.diagnostics["state_refresh_failed"] is True
    assert result.diagnostics["command_effect_may_have_applied"] is True
    assert result.changed_state.state_unknown is True
    assert len(publications) == 1
    assert publications[0].generation == before_publication.generation
    assert publications[0].revision > before_publication.revision
    assert publications[0].usable is False


def test_capability_policy_covers_all_declared_commands():
    service = ApplicationService(Study())
    policy = service.get_capabilities()

    assert set(policy.capabilities) == {name.value for name in CommandName}
    assert policy.get(CommandName.EVALUATE).available is False
    assert policy.get(CommandName.VISUALIZE).available is False
    assert policy.get(CommandName.SALIENCY).available is False
    assert policy.get(CommandName.RESET_PREPROCESS).available is False
    assert policy.get(CommandName.CLEAR_DATASETS).available is False
    assert policy.get(CommandName.CLEAR_TRAINING_HISTORY).available is False
    assert policy.get(CommandName.SCAN_SOURCE).available is True
    assert policy.get(CommandName.REVIEW_INTERPRETATION).available is True
    assert policy.get(CommandName.PREVIEW_INTERPRETATION).available is False
    assert policy.get(CommandName.VALIDATE_INTERPRETATION).available is False
    assert policy.get(CommandName.APPLY_INTERPRETATION).available is False
    assert policy.get(CommandName.SAVE_INTERPRETATION_RECIPE).available is False
    assert policy.get(CommandName.RELOAD_INTERPRETATION_RECIPE).available is True
    assert policy.get(CommandName.QUERY_STATE).available is True
    assert policy.get(CommandName.NEW_SESSION).available is True


def test_epoch_capability_accepts_raw_data_without_preprocess_operation():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = []
    service.get_state()

    policy = service.get_capabilities()

    assert policy.get(CommandName.PREPROCESS).available is True
    assert policy.get(CommandName.CREATE_EPOCH).available is True
    assert policy.get(CommandName.CREATE_EPOCH).reasons == []


def test_command_result_rejects_source_without_supported_eeg_files(tmp_path):
    service = ApplicationService(Study())
    unsupported_path = tmp_path / "sample.unsupported"
    unsupported_path.write_text("not eeg", encoding="utf-8")

    review = service.execute(
        ReviewInterpretationCommand(source_path=str(unsupported_path))
    )
    assert review.ok
    assert review.diagnostics["scan_result"]["eeg_files"] == []
    result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert result.failed is True
    assert result.ok is False
    assert result.command_name == "apply_interpretation"
    assert result.error_type == ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.state.last_error is not None
    assert result.state.last_error.error_type == "precondition"
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


def test_every_declared_command_returns_result_envelope():
    service = ApplicationService(Study())
    commands = [
        UpdateMetadataCommand(index=0, subject="S01"),
        ApplySmartParseCommand(results={"/tmp/sample.fif": ("S01", "001")}),
        RemoveFilesCommand(indices=[0]),
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=1,
            high_freq=40,
        ),
        CreateEpochCommand(t_min=0, t_max=1),
        SaveDatasetSplitCommand(),
        ClearDatasetsCommand(),
        ConfigureTrainingCommand(model_name="EEGNet"),
        TrainCommand(),
        DiscardTrainingPreparationCommand(),
        EvaluateCommand(),
        VisualizeCommand(),
        SaliencyCommand(),
        StopTrainingCommand(),
        ClearTrainingHistoryCommand(),
        ScanSourceCommand(source_path=""),
        ReviewInterpretationCommand(source_path=""),
        PreviewInterpretationCommand(),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(),
        SaveInterpretationRecipeCommand(recipe_path=""),
        ReloadInterpretationRecipeCommand(recipe_path=""),
        ApplyMontageCommand(channels=["Cz"], positions=[(0.0, 0.0, 0.0)]),
        QueryStateCommand(),
        ResetPreprocessCommand(),
        ResetSessionCommand(),
        NewSessionCommand(),
    ]

    seen = set()
    for command in commands:
        result = service.execute(command)
        seen.add(result.command_name)
        assert result.command_name
        assert result.status.value in {"ok", "failed"}
        assert result.error_type is not ErrorType.UNSUPPORTED_COMMAND
        assert result.state is not None
        assert result.changed_state is not None

    assert seen == {name.value for name in CommandName}


def test_raw_mutation_commands_block_after_epoch_without_side_effects():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.dataset_state.remove_files = MagicMock()

    result = service.execute(RemoveFilesCommand(indices=[0]))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Reset the session" in result.message
    service.dataset_state.remove_files.assert_not_called()


def test_apply_interpretation_blocks_after_epoch_without_import_side_effect(
    tmp_path,
):
    source_dir = tmp_path / "new_source"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-02_task-mi_raw.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(PreviewInterpretationCommand())
    validation = service.execute(ValidateInterpretationCommand())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.get_state()
    policy = service.get_capabilities()

    result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert validation.ok is True
    assert policy.get(CommandName.APPLY_INTERPRETATION).available is False
    assert "Reset the session" in " ".join(
        policy.get(CommandName.APPLY_INTERPRETATION).reasons,
    )
    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Reset the session" in result.message
    load.assert_not_called()


def test_blocked_query_and_lifecycle_commands_still_return_result_envelopes():
    service = ApplicationService(Study())

    for command in (
        EvaluateCommand(),
        VisualizeCommand(),
        SaliencyCommand(),
        ClearDatasetsCommand(),
        ClearTrainingHistoryCommand(),
        ResetPreprocessCommand(),
    ):
        result = service.execute(command)

        assert result.failed is True
        assert result.command_name == command.name.value
        assert result.error_type == ErrorType.PRECONDITION
        assert result.state is not None
        assert result.changed_state is not None


def test_metadata_update_command_routes_through_service():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.dataset_state.update_metadata_batch = MagicMock(return_value=1)

    result = service.execute(UpdateMetadataCommand(index=0, subject="S01"))

    assert result.ok is True
    assert result.command_name == CommandName.UPDATE_METADATA.value
    assert result.diagnostics["success_count"] == 1
    service.dataset_state.update_metadata_batch.assert_called_once_with(
        [(0, "S01", None)],
    )


def test_query_state_returns_typed_dataset_summary():
    raw = _raw_mock()
    study = Study()
    study.data_manager.loaded_data_list = [raw]
    study.data_manager.preprocessed_data_list = [raw]
    service = ApplicationService(study)

    result = service.execute(QueryStateCommand(query="data_summary"))

    assert result.ok is True
    assert result.diagnostics["count"] == 1
    assert result.diagnostics["metadata"][0]["subject"] == "S01"


def test_query_state_smart_filter_uses_study_port_target_file_argument():
    service = ApplicationService(Study())
    raw = object()
    service.study.data_manager.loaded_data_list = [raw]
    service.dataset_state.get_smart_filter_suggestions = MagicMock(return_value=[7, 8])

    result = service.execute(
        QueryStateCommand(
            query="smart_filter_suggestions",
            params={"target_index": 0, "target_count": 2},
        ),
    )

    assert result.ok is True
    assert result.diagnostics == {"suggestions": [7, 8]}
    service.dataset_state.get_smart_filter_suggestions.assert_called_once_with(raw, 2)


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


def test_mutation_publishes_only_committed_application_view(monkeypatch):
    service = ApplicationService(Study())
    initial = service.get_view_publication()
    publications = []
    original_execute_allowed = service._execute_allowed

    def execute_without_early_publication(command, name):
        assert publications == []
        return original_execute_allowed(command, name)

    monkeypatch.setattr(service, "_execute_allowed", execute_without_early_publication)
    service.subscribe(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        publications.append,
    )

    result = service.execute(NewSessionCommand(confirmed=True))

    assert result.ok is True
    assert len(publications) == 1
    publication = publications[0]
    assert publication.usable is True
    assert publication.generation > initial.generation
    assert publication.state == result.state
    assert publication == service.get_view_publication()


def test_destructive_capabilities_expose_confirmation_boundary_metadata():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.datasets = [object()]
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    service.get_state()

    policy = service.get_capabilities()

    for command_name in (
        CommandName.RESET_SESSION,
        CommandName.NEW_SESSION,
        CommandName.CLEAR_DATASETS,
    ):
        capability = policy.get(command_name)
        assert capability.confirmation_required is True
        assert capability.requires_confirmation is True
        assert capability.can_auto_execute is False
        assert capability.decision_boundary


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
    assert "app confirmation path" in result.message
