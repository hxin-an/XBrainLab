"""Tests for product-safe assistant presentation copy."""

from dataclasses import replace
from typing import Any, cast

import pytest

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    EpochStateSnapshot,
    InterpretationStateSnapshot,
    PreprocessedStateSnapshot,
    TrainingStateSnapshot,
)
from XBrainLab.backend.application.view_publication import (
    PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
    ApplicationViewPublication,
)
from XBrainLab.backend.application.workflow_projection import (
    build_workflow_projection,
)
from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.ui.components.agent_presentation_service import (
    AgentPresentationService,
)
from XBrainLab.ui.components.assistant_status_projection import (
    AssistantStatusProjection,
    AssistantWorkflowSurface,
    build_assistant_status_projection,
)
from XBrainLab.ui.components.workflow_surface_router import (
    WorkflowSurfaceOutcome,
    WorkflowSurfaceStatus,
)


@pytest.mark.parametrize(
    ("activity", "expected"),
    [
        (
            AssistantTurnActivity(AssistantTurnActivityPhase.PREPARING),
            "Checking data",
        ),
        (
            AssistantTurnActivity(AssistantTurnActivityPhase.THINKING),
            "Thinking",
        ),
        (
            AssistantTurnActivity(
                AssistantTurnActivityPhase.RUNNING_COMMAND,
                command_name="create_epoch",
            ),
            "Running: Create epochs",
        ),
        (
            AssistantTurnActivity(AssistantTurnActivityPhase.RUNNING_COMMAND),
            "Running workflow step",
        ),
        (
            AssistantTurnActivity(
                AssistantTurnActivityPhase.WAITING_FOR_DECISION,
            ),
            "Waiting for decision",
        ),
        (
            AssistantTurnActivity(AssistantTurnActivityPhase.STOPPING),
            "Stopping",
        ),
        (
            AssistantTurnActivity(AssistantTurnActivityPhase.NEEDS_ATTENTION),
            "Needs attention",
        ),
        (AssistantTurnActivity(AssistantTurnActivityPhase.IDLE), ""),
    ],
)
def test_workflow_status_uses_typed_turn_activity(activity, expected):
    assert AgentPresentationService.workflow_status(activity) == expected


def test_activity_message_cannot_override_the_typed_phase() -> None:
    activity = AssistantTurnActivity(
        phase=AssistantTurnActivityPhase.THINKING,
        command_name="clear_dataset",
        message="Executing: clear_dataset failed while waiting for confirmation",
    )

    assert AgentPresentationService.workflow_status(activity) == "Thinking"


def test_workflow_status_rejects_raw_status_text() -> None:
    with pytest.raises(TypeError, match="typed assistant turn activity"):
        AgentPresentationService.workflow_status(
            cast(Any, "Executing: create_epoch...")
        )


def test_raw_status_diagnostic_normalizes_without_classifying_activity() -> None:
    diagnostic = AgentPresentationService.raw_status_diagnostic(
        "  Executing: create_epoch...\nfailed while waiting  "
    )

    assert diagnostic == "Executing: create_epoch... failed while waiting"
    assert diagnostic not in {
        "Running: Create epochs",
        "Waiting for decision",
        "Needs attention",
    }


def test_runtime_unavailable_copy_points_to_settings():
    visible = AgentPresentationService.runtime_unavailable_message(
        "Local model cache is missing"
    )

    assert "Assistant unavailable" in visible
    assert "settings" in visible


@pytest.mark.parametrize(
    ("raw", "safe_reason"),
    [
        (
            "Model cache not found for microsoft/Phi-4-mini-instruct",
            "model cache",
        ),
        (
            "RuntimeError: CUDA driver initialization failed at /usr/lib/cuda.so",
            "CUDA",
        ),
    ],
)
def test_runtime_failure_copy_preserves_safe_reason_without_runtime_internals(
    raw,
    safe_reason,
):
    visible = AgentPresentationService.runtime_unavailable_message(raw)
    status = AgentPresentationService.runtime_status_message(raw)

    for rendered in (visible, status):
        assert safe_reason in rendered
        assert "RuntimeError" not in rendered
        assert "/usr/lib" not in rendered
        assert "microsoft/Phi-4-mini-instruct" not in rendered


def test_arbitrary_exception_text_is_never_reflected_to_user():
    raw = (
        "ValueError: secret-token-123 while opening /private/runtime/cache/config.json"
    )

    unavailable = AgentPresentationService.runtime_unavailable_message(raw)
    status = AgentPresentationService.runtime_status_message(raw)

    for rendered in (unavailable, status):
        assert "ValueError" not in rendered
        assert "secret-token-123" not in rendered
        assert "/private/runtime" not in rendered


def test_runtime_settings_notice_does_not_reopen_current_dialog() -> None:
    notice = AgentPresentationService.runtime_settings_notice(
        "ValueError: secret-token-123 at /private/model.bin"
    )

    assert notice == (
        "The local model could not start. Check the installed model and runtime, "
        "then try again."
    )
    assert "Open assistant settings" not in notice
    assert "ValueError" not in notice
    assert "secret-token-123" not in notice
    assert "/private/model.bin" not in notice


def test_legacy_cancelled_turn_copy_is_concise_and_actionable() -> None:
    visible = AgentPresentationService.assistant_transcript_message(
        "The assistant stopped this request. No further response or action will run."
    )

    assert visible == "Request cancelled. You can revise it or ask something else."


def test_regular_assistant_copy_is_not_reclassified() -> None:
    visible = AgentPresentationService.assistant_transcript_message(
        "I need a folder path before I can list files."
    )

    assert visible == "I need a folder path before I can list files."


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (
            WorkflowSurfaceStatus.CANCELLED,
            "Evaluation review was cancelled. Your current workflow is unchanged.",
        ),
        (
            WorkflowSurfaceStatus.COMPLETED,
            "Evaluation review is ready in XBrainLab.",
        ),
        (
            WorkflowSurfaceStatus.FAILED,
            "XBrainLab could not open Evaluation. Try again from the main window.",
        ),
    ],
)
def test_evaluation_handoff_outcomes_use_natural_product_copy(status, expected):
    outcome = WorkflowSurfaceOutcome(
        status=status,
        command_name="evaluate",
        message="ignored backend detail",
    )

    assert (
        AgentPresentationService.workflow_surface_outcome_message(outcome) == expected
    )


def _publication(
    state: ApplicationStateSnapshot,
    *,
    generation: int = 7,
) -> ApplicationViewPublication:
    return ApplicationViewPublication(
        generation=generation,
        state=state,
        capabilities=build_capability_policy(state),
    )


@pytest.mark.parametrize(
    ("state", "command_name", "surface", "decision_fields"),
    [
        (
            replace(
                ApplicationStateSnapshot.empty(),
                interpretation=InterpretationStateSnapshot(
                    source_path="/datasets/demo",
                    has_scan_result=True,
                    has_candidate=True,
                    has_validation_decision=True,
                    validation_decision="needs_confirmation",
                    pending_confirmation=True,
                    action_items=[
                        {
                            "target_step": "Review Metadata",
                            "severity": "needs_confirmation",
                        },
                        {
                            "target_step": "Match Labels",
                            "severity": "needs_confirmation",
                        },
                    ],
                ),
            ),
            "apply_interpretation",
            AssistantWorkflowSurface.DATA_IMPORT,
            ("metadata_review", "label_matching"),
        ),
        (
            replace(
                ApplicationStateSnapshot.empty(),
                pipeline_stage="data_loaded",
                active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
            ),
            "preprocess",
            AssistantWorkflowSurface.PREPROCESSING,
            ("preprocess_settings",),
        ),
        (
            replace(
                ApplicationStateSnapshot.empty(),
                pipeline_stage="preprocessed",
                preprocessed=PreprocessedStateSnapshot(available=True, count=1),
                active_dataset=ActiveDatasetSnapshot(
                    has_raw_data=True,
                    has_preprocessed_data=True,
                ),
            ),
            "create_epoch",
            AssistantWorkflowSurface.EPOCH_SETTINGS,
            ("target_event", "epoch_window"),
        ),
        (
            replace(
                ApplicationStateSnapshot.empty(),
                pipeline_stage="epoch_ready",
                epoch=EpochStateSnapshot(
                    available=True,
                    exists=True,
                    epoch_count=12,
                    event_names=["left", "right"],
                    event_ids={"left": 0, "right": 1},
                ),
                active_dataset=ActiveDatasetSnapshot(
                    has_raw_data=True,
                    has_preprocessed_data=True,
                    has_epoch_data=True,
                ),
                interpretation=InterpretationStateSnapshot(
                    has_applied_interpretation=True,
                ),
            ),
            "generate_dataset",
            AssistantWorkflowSurface.DATASET_SPLIT,
            ("split_strategy", "training_mode"),
        ),
        (
            replace(
                ApplicationStateSnapshot.empty(),
                pipeline_stage="dataset_ready",
                active_dataset=ActiveDatasetSnapshot(
                    has_raw_data=True,
                    has_datasets=True,
                ),
                training=TrainingStateSnapshot(),
            ),
            "configure_training",
            AssistantWorkflowSurface.TRAINING_SETTINGS,
            ("model", "training_options"),
        ),
    ],
)
def test_status_projection_preserves_atomic_backend_workflow_truth(
    state,
    command_name,
    surface,
    decision_fields,
) -> None:
    publication = _publication(state)
    backend_projection = build_workflow_projection(
        publication.state,
        publication.effective_capabilities,
    )

    projection = build_assistant_status_projection(publication)

    assert isinstance(projection, AssistantStatusProjection)
    assert projection.publication_generation == publication.generation
    assert projection.publication_revision == publication.revision
    assert projection.recommended_command == command_name
    assert projection.recommended_command == backend_projection.recommended_command
    assert projection.blocked_command == backend_projection.blocked_command
    assert projection.blocked_reasons == backend_projection.blocked_reasons
    assert projection.decision_fields == backend_projection.decision_fields
    assert projection.existing_ui_surface is surface
    assert projection.available_commands == (command_name,)


def test_status_projection_uses_recommended_command_blocker_not_train_blocker() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="epoch_ready",
        epoch=EpochStateSnapshot(available=True, exists=True, epoch_count=12),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
        ),
        interpretation=InterpretationStateSnapshot(
            has_applied_interpretation=True,
            epoch_handoff={
                "supervised_ready": False,
                "supervised_blockers": [
                    "Resolve label mapping before training.",
                ],
            },
        ),
    )

    projection = build_assistant_status_projection(_publication(state))

    assert projection.recommended_command is None
    assert projection.blocked_command == "generate_dataset"
    assert projection.blocked_reasons == ("Resolve label mapping before training.",)
    assert projection.blocked_reason == "Resolve label mapping before training."
    assert "Select a model before training." not in projection.tooltip


def test_status_projection_exposes_stop_as_control_not_implicit_next_step() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="training",
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
            has_datasets=True,
        ),
        active_training=ActiveTrainingSnapshot(
            has_model=True,
            has_training_option=True,
            has_trainer=True,
            is_running=True,
        ),
    )

    projection = build_assistant_status_projection(_publication(state))

    assert projection.recommended_command is None
    assert projection.available_commands == ("stop_training",)
    assert projection.blocked_reasons == ()
    assert projection.blocked_reason is None
    assert "Action required" not in projection.footer_hint


@pytest.mark.parametrize(
    ("verified", "stale"),
    [(False, False), (True, True), (False, True)],
)
def test_status_projection_fails_closed_for_unusable_publication(
    verified,
    stale,
) -> None:
    state = ApplicationStateSnapshot.empty()
    publication = ApplicationViewPublication(
        generation=11,
        state=state,
        capabilities=build_capability_policy(state),
        verified=verified,
        stale=stale,
        refresh_error="private backend diagnostic",
    )

    projection = build_assistant_status_projection(publication)

    assert projection.usable is False
    assert projection.publication_generation == 11
    assert projection.stage == "Workflow status unavailable"
    assert projection.recommended_command is None
    assert projection.available_commands == ()
    assert projection.existing_ui_surface is None
    assert projection.blocked_reasons == (PUBLIC_VIEW_UNAVAILABLE_MESSAGE,)
    assert "private backend diagnostic" not in projection.tooltip


def test_status_projection_fails_closed_for_unreliable_state_payload() -> None:
    state = ApplicationStateSnapshot.empty(
        read_errors=["private state reconstruction failure"],
    )
    publication = ApplicationViewPublication(
        generation=12,
        state=state,
        capabilities=build_capability_policy(state),
        verified=True,
        stale=False,
    )

    projection = build_assistant_status_projection(publication)

    assert projection.usable is False
    assert projection.available_commands == ()
    assert projection.blocked_reasons == (PUBLIC_VIEW_UNAVAILABLE_MESSAGE,)
    assert "private state reconstruction failure" not in projection.tooltip
