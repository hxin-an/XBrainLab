"""Host-side admission tests for explicit assistant workflow requests."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    InterpretationStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.llm.agent.request_admission import (
    UserRequestAdmissionAction,
    UserRequestAdmissionPolicy,
)
from XBrainLab.llm.agent.turn import AssistantTurnScope


def _publication(state: ApplicationStateSnapshot) -> ApplicationViewPublication:
    return ApplicationViewPublication(
        generation=7,
        state=state,
        capabilities=build_capability_policy(state),
    )


def _loaded_state() -> ApplicationStateSnapshot:
    state = ApplicationStateSnapshot.empty()
    return replace(
        state,
        pipeline_stage="data_loaded",
        raw=RawStateSnapshot(loaded=True, count=1, files=["/data/A01T.gdf"]),
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
    )


def _preprocessed_state() -> ApplicationStateSnapshot:
    state = _loaded_state()
    return replace(
        state,
        pipeline_stage="preprocessed",
        preprocessed=PreprocessedStateSnapshot(
            available=True,
            count=1,
            files=["/data/A01T.gdf"],
        ),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
        ),
    )


def _epoched_state() -> ApplicationStateSnapshot:
    state = _preprocessed_state()
    return replace(
        state,
        pipeline_stage="epoch_ready",
        epoch=EpochStateSnapshot(
            available=True,
            exists=True,
            epoch_count=288,
            event_names=["Left hand", "Right hand"],
            event_ids={"Left hand": 769, "Right hand": 770},
        ),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
        ),
    )


def _dataset_ready_state() -> ApplicationStateSnapshot:
    state = _epoched_state()
    return replace(
        state,
        pipeline_stage="dataset_ready",
        dataset=DatasetStateSnapshot(available=True, count=1),
        active_dataset=replace(state.active_dataset, has_datasets=True),
    )


def _training_state() -> ApplicationStateSnapshot:
    state = _dataset_ready_state()
    return replace(
        state,
        pipeline_stage="training",
        active_training=ActiveTrainingSnapshot(
            has_model=True,
            has_training_option=True,
            has_trainer=True,
            is_running=True,
        ),
    )


def _with_pending_interpretation(
    state: ApplicationStateSnapshot,
) -> ApplicationStateSnapshot:
    return replace(
        state,
        interpretation=InterpretationStateSnapshot(
            source_path="/data/pending",
            has_scan_result=True,
            has_candidate=True,
        ),
    )


def _validated_interpretation_state() -> ApplicationStateSnapshot:
    state = ApplicationStateSnapshot.empty()
    return replace(
        state,
        interpretation=InterpretationStateSnapshot(
            source_path="/data/reviewed.fif",
            has_scan_result=True,
            has_candidate=True,
            has_preview=True,
            has_validation_decision=True,
            validation_decision="needs_confirmation",
            latest_scan_id="scan-1",
            latest_candidate_id="candidate-1",
            latest_preview_id="preview-1",
        ),
    )


@pytest.mark.parametrize(
    ("state_factory", "text", "command", "expected_fields"),
    (
        (
            lambda: _with_pending_interpretation(_preprocessed_state()),
            "Create epochs now.",
            CommandName.CREATE_EPOCH,
            ("target_event", "epoch_window"),
        ),
        (
            lambda: _with_pending_interpretation(_epoched_state()),
            "Generate a training dataset.",
            CommandName.GENERATE_DATASET,
            ("split_strategy", "training_mode"),
        ),
        (
            ApplicationStateSnapshot.empty,
            "Configure training.",
            CommandName.CONFIGURE_TRAINING,
            ("model", "training_options"),
        ),
    ),
)
def test_non_recommended_commands_use_backend_decision_schema(
    state_factory: Callable[[], ApplicationStateSnapshot],
    text: str,
    command: CommandName,
    expected_fields: tuple[str, ...],
) -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        text,
        _publication(state_factory()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is command
    assert decision.decision_fields == expected_fields
    assert decision.suggestions == {}


def test_blocked_explicit_command_is_resolved_before_model_generation() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Train an EEGNet model now.",
        _publication(ApplicationStateSnapshot.empty()),
    )

    assert decision.action is UserRequestAdmissionAction.BLOCKED
    assert decision.command is CommandName.TRAIN
    assert "Load raw data before training" in decision.message
    assert "Configure training options before training" in decision.message


def test_guided_goal_starts_from_backend_recommended_prerequisite() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Prepare this EEG dataset for training.",
        _publication(ApplicationStateSnapshot.empty()),
        scope=AssistantTurnScope.GUIDED_WORKFLOW,
        terminal_command=CommandName.GENERATE_DATASET.value,
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.SCAN_SOURCE
    assert decision.decision_fields == ("source_path",)


def test_direct_train_request_does_not_inherit_guided_scope() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Start training.",
        _publication(ApplicationStateSnapshot.empty()),
        scope=AssistantTurnScope.SINGLE_ACTION,
    )

    assert decision.action is UserRequestAdmissionAction.BLOCKED
    assert decision.command is CommandName.TRAIN


@pytest.mark.parametrize(
    "text",
    (
        "Compare standard preprocessing and training settings.",
        "I am trying to understand loading and preprocessing.",
        "請比較標準前處理和訓練設定",
        "我想了解載入和標準前處理",
        "想了解載入和標準前處理",
        "了解載入和前處理的差異",
    ),
)
def test_explanatory_request_does_not_authorize_a_mutation(text: str) -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        text,
        _publication(_loaded_state()),
        scope=AssistantTurnScope.SINGLE_ACTION,
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE
    assert decision.command is None


@pytest.mark.parametrize("text", ("Reset preprocessing.", "重設前處理"))
def test_reset_preprocess_admission_never_widens_to_session_reset(text: str) -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        text,
        _publication(_preprocessed_state()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE
    assert decision.command is CommandName.RESET_PREPROCESS


@pytest.mark.parametrize("text", ("Stop training.", "停止訓練"))
def test_active_training_stop_is_admitted_as_execution_control(text: str) -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        text,
        _publication(_training_state()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE
    assert decision.command is CommandName.STOP_TRAINING


def test_missing_scan_path_opens_existing_import_surface() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Load my EEG file.",
        _publication(ApplicationStateSnapshot.empty()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.SCAN_SOURCE
    assert decision.decision_fields == ("source_path",)


def test_explicit_scan_path_can_reach_model_tool_selection() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Load /data/A01T.gdf",
        _publication(ApplicationStateSnapshot.empty()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE


def test_natural_continue_request_authorizes_current_backend_step() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Continue with the reviewed recording.",
        _publication(_validated_interpretation_state()),
        scope=AssistantTurnScope.GUIDED_WORKFLOW,
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE
    assert decision.command is CommandName.APPLY_INTERPRETATION


def test_natural_continue_stops_for_preprocess_settings() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Continue the workflow.",
        _publication(_loaded_state()),
        scope=AssistantTurnScope.GUIDED_WORKFLOW,
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.PREPROCESS
    assert decision.decision_fields == ("preprocess_settings",)


def test_explicit_standard_preprocess_defaults_are_model_ready() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Apply the standard preprocessing defaults.",
        _publication(_loaded_state()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE
    assert decision.command is CommandName.PREPROCESS


def test_state_query_is_admitted_as_deterministic_read_only_execution() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "What is ready now?",
        _publication(ApplicationStateSnapshot.empty()),
    )

    assert decision.action is UserRequestAdmissionAction.EXECUTE_READ_ONLY
    assert decision.command is CommandName.QUERY_STATE


def test_complete_epoch_request_can_reach_model_tool_selection() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Create epochs from -0.2 to 0.8 seconds for event 769.",
        _publication(_preprocessed_state()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE


def test_incomplete_epoch_request_opens_existing_epoch_surface() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Create epochs now.",
        _publication(_preprocessed_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.CREATE_EPOCH
    assert decision.decision_fields == ("target_event", "epoch_window")
    assert decision.suggestions == {}


def test_incomplete_epoch_request_preserves_explicit_event_for_ui() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Create epochs for event 769.",
        _publication(_preprocessed_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.CREATE_EPOCH
    assert decision.decision_fields == ("epoch_window",)
    assert decision.suggestions == {"target_event": "769"}


def test_incomplete_epoch_request_preserves_explicit_window_for_ui() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Create epochs from -0.2 to 0.8 seconds.",
        _publication(_preprocessed_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.CREATE_EPOCH
    assert decision.decision_fields == ("target_event",)
    assert decision.suggestions == {"t_min": "-0.2", "t_max": "0.8"}


def test_missing_split_strategy_opens_existing_splitting_surface() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Generate an individual training dataset with 20% test split.",
        _publication(_epoched_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.GENERATE_DATASET
    assert decision.decision_fields == ("split_strategy",)
    assert decision.suggestions == {
        "training_mode": "individual",
        "test_ratio": "0.2",
    }


def test_explicit_split_strategy_can_reach_model_tool_selection() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Generate an individual trial-wise dataset with 20% test split.",
        _publication(_epoched_state()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE


def test_missing_training_mode_opens_existing_splitting_surface() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Generate a trial-wise training dataset with 20% test split.",
        _publication(_epoched_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.GENERATE_DATASET
    assert decision.decision_fields == ("training_mode",)
    assert decision.suggestions == {
        "split_strategy": "trial",
        "test_ratio": "0.2",
    }


def test_explicit_model_does_not_get_reopened_when_training_options_are_partial() -> (
    None
):
    decision = UserRequestAdmissionPolicy().evaluate(
        "Configure EEGNet with batch size 32 and learning rate 0.001.",
        _publication(_dataset_ready_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.CONFIGURE_TRAINING
    assert decision.decision_fields == ("training_options",)
    assert decision.suggestions == {
        "model": "eegnet",
        "batch_size": "32",
        "learning_rate": "0.001",
    }


def test_complete_model_and_training_options_can_use_one_backend_command() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Configure EEGNet for 10 epochs with batch size 32 and learning rate 0.001.",
        _publication(_dataset_ready_state()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE
    assert decision.command is CommandName.CONFIGURE_TRAINING


def test_partial_training_request_preserves_options_for_existing_ui() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Configure training with batch size 32 and learning rate 0.001.",
        _publication(_dataset_ready_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.CONFIGURE_TRAINING
    assert decision.decision_fields == ("model", "training_options")
    assert decision.suggestions == {
        "batch_size": "32",
        "learning_rate": "0.001",
    }


@pytest.mark.parametrize(
    ("text", "expected_suggestions"),
    (
        (
            "Configure EEGNet with batch 32.",
            {"model": "eegnet", "batch_size": "32"},
        ),
        (
            "Configure EEGNet with bs 16.",
            {"model": "eegnet", "batch_size": "16"},
        ),
        (
            "Configure EEGNet with lr 1e-3.",
            {"model": "eegnet", "learning_rate": "1e-3"},
        ),
        (
            "Configure EEGNet with learning_rate 2.5E-4.",
            {"model": "eegnet", "learning_rate": "2.5e-4"},
        ),
        (
            "Configure EEGNet with epoch 10.",
            {"model": "eegnet", "epoch": "10"},
        ),
        (
            "Configure EEGNet with 12 epochs.",
            {"model": "eegnet", "epoch": "12"},
        ),
    ),
)
def test_partial_training_aliases_trigger_handoff_and_preserve_suggestions(
    text: str,
    expected_suggestions: dict[str, str],
) -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        text,
        _publication(_dataset_ready_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.CONFIGURE_TRAINING
    assert decision.decision_fields == ("training_options",)
    assert decision.suggestions == expected_suggestions


@pytest.mark.parametrize(
    "text",
    (
        "Configure EEGNet with epoch 10, batch 32, lr 1e-3.",
        "Configure EEGNet with 10 epochs, bs 32, learning rate .001.",
    ),
)
def test_complete_training_aliases_can_reach_model_tool_selection(text: str) -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        text,
        _publication(_dataset_ready_state()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE
    assert decision.command is CommandName.CONFIGURE_TRAINING


def test_training_admission_uses_backend_positive_learning_rate_contract() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Configure EEGNet with epoch 10, batch 32, lr 1.",
        _publication(_dataset_ready_state()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE
    assert decision.command is CommandName.CONFIGURE_TRAINING


@pytest.mark.parametrize(
    "text",
    (
        "Configure EEGNet with epoch 1.5, batch 32, lr 0.001.",
        "Configure EEGNet with 1.5 epochs, batch 32, lr 0.001.",
    ),
)
def test_fractional_epoch_is_not_truncated_into_complete_training_request(
    text: str,
) -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        text,
        _publication(_dataset_ready_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.CONFIGURE_TRAINING
    assert decision.decision_fields == ("training_options",)
    assert decision.suggestions == {
        "model": "eegnet",
        "batch_size": "32",
        "learning_rate": "0.001",
    }


@pytest.mark.parametrize(
    "text",
    (
        "Configure EEGNet with epoch ten.",
        "Configure EEGNet with bs many.",
        "Configure EEGNet with lr fast.",
        "Configure EEGNet with epoch ten, bs many, and lr fast.",
    ),
)
def test_malformed_training_values_do_not_complete_model_only_request(
    text: str,
) -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        text,
        _publication(_dataset_ready_state()),
    )

    assert decision.action is UserRequestAdmissionAction.UI_HANDOFF
    assert decision.command is CommandName.CONFIGURE_TRAINING
    assert decision.decision_fields == ("training_options",)
    assert decision.suggestions == {"model": "eegnet"}


def test_model_only_request_remains_narrow() -> None:
    decision = UserRequestAdmissionPolicy().evaluate(
        "Configure EEGNet.",
        _publication(_dataset_ready_state()),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE
    assert decision.command is CommandName.CONFIGURE_TRAINING


def test_selected_source_satisfies_scan_source_decision() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        interpretation=InterpretationStateSnapshot(
            source_path="/data/selected",
            source_kind="folder",
        ),
    )
    decision = UserRequestAdmissionPolicy().evaluate(
        "Scan the selected source.",
        _publication(state),
    )

    assert decision.action is UserRequestAdmissionAction.GENERATE


def test_unusable_publication_fails_closed_for_explicit_action() -> None:
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=8,
        state=state,
        capabilities=build_capability_policy(state),
        verified=False,
        stale=True,
        refresh_error="private backend detail",
    )

    decision = UserRequestAdmissionPolicy().evaluate(
        "Apply standard preprocessing.",
        publication,
    )

    assert decision.action is UserRequestAdmissionAction.BLOCKED
    assert decision.command is CommandName.PREPROCESS
    assert decision.message == "Workflow state is temporarily unavailable."
    assert "private backend detail" not in decision.message
