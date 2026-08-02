"""Contract tests for bounded, correlated assistant response actions."""

from __future__ import annotations

import pytest

from XBrainLab.backend.application import CommandName
from XBrainLab.chat_contract import (
    MAX_CHAT_ACTION_ID_LENGTH,
    MAX_CHAT_ACTION_LABEL_LENGTH,
    MAX_CHAT_ACTION_PROMPT_LENGTH,
    MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    MAX_CHAT_PRESENTATION_ID_LENGTH,
)
from XBrainLab.llm.agent.interaction import (
    AgentInteractionOutcome,
    AgentInteractionStatus,
)
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
    AssistantResponseAction,
    AssistantResponseActionKind,
    AssistantResponseActionSelection,
    AssistantResponseKind,
    AssistantResponsePresentation,
    interaction_outcome_kind,
    interaction_outcome_message,
    panel_target_for_blocked_command,
    panel_target_for_command,
    user_facing_generation_error,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation

_CORRELATION = AssistantTurnCorrelation(generation=1, turn_id=1)
_EXPECTED_MAX_CONTENT_LENGTH = MAX_CHAT_MESSAGE_CONTENT_LENGTH
_EXPECTED_MAX_ACTION_LABEL_LENGTH = MAX_CHAT_ACTION_LABEL_LENGTH
_EXPECTED_MAX_ACTION_PROMPT_LENGTH = MAX_CHAT_ACTION_PROMPT_LENGTH
_EXPECTED_MAX_ACTION_ID_LENGTH = MAX_CHAT_ACTION_ID_LENGTH
_EXPECTED_MAX_PRESENTATION_ID_LENGTH = MAX_CHAT_PRESENTATION_ID_LENGTH


def test_panel_navigation_request_is_typed_and_bounded() -> None:
    request = AssistantPanelNavigationRequest(
        target=AssistantPanelTarget.VISUALIZATION,
        view_mode="3d_plot",
    )

    assert request.target is AssistantPanelTarget.VISUALIZATION
    assert request.view_mode == "3d_plot"

    with pytest.raises(TypeError, match="panel target"):
        AssistantPanelNavigationRequest(target="training")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not available"):
        AssistantPanelNavigationRequest(
            target=AssistantPanelTarget.TRAINING,
            view_mode="metrics",
        )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (AgentInteractionStatus.CANCELLED, "workspace is unchanged"),
        (AgentInteractionStatus.CONFIRMED, "Approved"),
        (AgentInteractionStatus.DEFERRED_TO_UI, "open in the main window"),
        (AgentInteractionStatus.BLOCKED, "blocked"),
        (AgentInteractionStatus.UNAVAILABLE, "not available"),
        (AgentInteractionStatus.FAILED, "could not be opened"),
    ],
)
def test_interaction_copy_is_derived_from_structured_outcome(status, expected):
    outcome = AgentInteractionOutcome(status=status, command_name="clear_dataset")

    assert expected in interaction_outcome_message(outcome)


def test_cancelled_data_import_uses_product_language() -> None:
    outcome = AgentInteractionOutcome(
        status=AgentInteractionStatus.CANCELLED,
        command_name="apply_interpretation",
    )

    assert interaction_outcome_message(outcome) == (
        "Data import was cancelled. No data was added."
    )


def test_handoff_blocker_uses_specific_product_surface_message() -> None:
    outcome = AgentInteractionOutcome(
        status=AgentInteractionStatus.BLOCKED,
        command_name="create_epoch",
        message="Load preprocessed data before creating epochs.",
    )

    assert interaction_outcome_message(outcome) == (
        "Load preprocessed data before creating epochs."
    )
    assert interaction_outcome_kind(outcome) is AssistantResponseKind.BLOCKED


def test_failed_interaction_has_explicit_error_presentation_kind() -> None:
    outcome = AgentInteractionOutcome(
        status=AgentInteractionStatus.FAILED,
        command_name="create_epoch",
        message="Any user-facing copy may be used here.",
    )

    assert interaction_outcome_kind(outcome) is AssistantResponseKind.ERROR


@pytest.mark.parametrize(
    ("status", "expected_kind"),
    [
        (AgentInteractionStatus.CANCELLED, AssistantResponseKind.CANCELLED),
        (AgentInteractionStatus.COMPLETED_IN_UI, AssistantResponseKind.TOOL_RESULT),
    ],
)
def test_terminal_interaction_has_authoritative_response_kind(
    status: AgentInteractionStatus,
    expected_kind: AssistantResponseKind,
) -> None:
    outcome = AgentInteractionOutcome(
        status=status,
        command_name="create_epoch",
        message="Display copy does not determine the persisted bubble kind.",
    )

    assert interaction_outcome_kind(outcome) is expected_kind


def test_evaluation_handoff_names_the_destination_page() -> None:
    visible = interaction_outcome_message(
        AgentInteractionOutcome(
            status=AgentInteractionStatus.DEFERRED_TO_UI,
            command_name="evaluate",
        )
    )

    assert visible == "Evaluation is open in the main window. Review results there."


def test_cancelled_interaction_copy_never_claims_completion_or_success() -> None:
    visible = interaction_outcome_message(
        AgentInteractionOutcome(
            status=AgentInteractionStatus.CANCELLED,
            command_name="clear_dataset",
        )
    )

    lowered = visible.lower()
    assert "workspace is unchanged" in lowered
    assert "background action completed" not in lowered
    assert "success" not in lowered


def test_response_presentation_accepts_one_typed_correlated_action() -> None:
    action = AssistantResponseAction.open_panel(
        "Open Dataset",
        AssistantPanelTarget.DATASET,
    )

    presentation = AssistantResponsePresentation(
        text="Open Dataset to review the selected files.",
        correlation=_CORRELATION,
        kind=AssistantResponseKind.BLOCKED,
        actions=(action,),
        presentation_id="presentation-1",
    )
    selection = AssistantResponseActionSelection(
        presentation_id=presentation.presentation_id,
        action=action,
    )

    assert selection.presentation_id == "presentation-1"
    assert selection.action.panel is AssistantPanelTarget.DATASET


def test_data_import_response_action_is_a_typed_product_surface_action() -> None:
    action = AssistantResponseAction.open_data_import("Open Data Import")

    assert action.kind is AssistantResponseActionKind.OPEN_DATA_IMPORT
    assert action.prompt == ""
    assert action.panel is None


@pytest.mark.parametrize(
    ("raw_error", "expected"),
    (
        (
            "CUDA out of memory while allocating tensor 0x7f00",
            "ran out of GPU memory",
        ),
        (
            "Model load failed: /private/cache/model.gguf",
            "could not start or continue",
        ),
        (
            "RuntimeError: internal engine detail",
            "could not complete the request",
        ),
    ),
)
def test_generation_error_copy_is_actionable_without_raw_details(
    raw_error,
    expected,
) -> None:
    visible = user_facing_generation_error(raw_error)

    assert expected in visible
    assert raw_error not in visible
    assert "/private/cache" not in visible


@pytest.mark.parametrize("command_name", ["set_montage", "apply_montage"])
def test_montage_commands_share_visualization_surface_truth(command_name: str) -> None:
    assert panel_target_for_command(command_name) is AssistantPanelTarget.VISUALIZATION


def test_panel_routing_accepts_typed_canonical_command_identity() -> None:
    assert (
        panel_target_for_command(CommandName.CREATE_EPOCH)
        is AssistantPanelTarget.PREPROCESS
    )
    assert (
        panel_target_for_command(CommandName.APPLY_MONTAGE)
        is AssistantPanelTarget.VISUALIZATION
    )


def test_interaction_label_accepts_typed_canonical_command_identity() -> None:
    outcome = AgentInteractionOutcome(
        status=AgentInteractionStatus.CONFIRMED,
        command_name=CommandName.CREATE_EPOCH,
    )

    assert interaction_outcome_message(outcome) == (
        "Approved: Create EEG epochs. XBrainLab is starting the action."
    )


@pytest.mark.parametrize(
    ("command_name", "display_reason", "expected_target"),
    [
        (
            CommandName.SCAN_SOURCE,
            "Create epochs before continuing.",
            AssistantPanelTarget.DATASET,
        ),
        (
            CommandName.CREATE_EPOCH,
            "Select a model before training.",
            AssistantPanelTarget.PREPROCESS,
        ),
        (
            CommandName.EVALUATE,
            "Create epochs before evaluating results.",
            AssistantPanelTarget.TRAINING,
        ),
    ],
)
def test_blocked_panel_routing_does_not_infer_identity_from_display_copy(
    command_name: CommandName,
    display_reason: str,
    expected_target: AssistantPanelTarget,
) -> None:
    assert (
        panel_target_for_blocked_command(command_name, display_reason)
        is expected_target
    )


@pytest.mark.parametrize(
    "action",
    [
        AssistantResponseAction.send_message("Check workflow", "What is ready now?"),
        AssistantResponseAction.open_panel(
            "Open Training",
            AssistantPanelTarget.TRAINING,
        ),
    ],
)
def test_action_contract_rejects_untyped_kind_or_panel(
    action: AssistantResponseAction,
) -> None:
    with pytest.raises(TypeError, match="action kind"):
        AssistantResponseAction(
            label=action.label,
            kind="open_panel",  # type: ignore[arg-type]
            panel=AssistantPanelTarget.TRAINING,
        )
    with pytest.raises(TypeError, match="panel target"):
        AssistantResponseAction(
            label=action.label,
            kind=AssistantResponseActionKind.OPEN_PANEL,
            panel="training",  # type: ignore[arg-type]
        )


def test_presentation_contract_rejects_untyped_kind_and_actions() -> None:
    action = AssistantResponseAction.send_message("Check workflow", "What is ready?")

    with pytest.raises(TypeError, match="response kind"):
        AssistantResponsePresentation(
            text="Choose the next step.",
            correlation=_CORRELATION,
            kind="clarification",  # type: ignore[arg-type]
            actions=(action,),
        )
    with pytest.raises(TypeError, match="actions must be a tuple"):
        AssistantResponsePresentation(
            text="Choose the next step.",
            correlation=_CORRELATION,
            actions=[action],  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="typed response actions"):
        AssistantResponsePresentation(
            text="Choose the next step.",
            correlation=_CORRELATION,
            actions=(object(),),  # type: ignore[arg-type]
        )


def test_action_selection_rejects_empty_or_untyped_correlation() -> None:
    action = AssistantResponseAction.send_message("Check workflow", "What is ready?")

    with pytest.raises(ValueError, match="presentation id"):
        AssistantResponseActionSelection(presentation_id=" ", action=action)
    with pytest.raises(TypeError, match="typed response action"):
        AssistantResponseActionSelection(
            presentation_id="presentation-1",
            action=object(),  # type: ignore[arg-type]
        )


def test_response_presentation_requires_exact_turn_generation_correlation() -> None:
    correlation = AssistantTurnCorrelation(generation=7, turn_id=11)

    presentation = AssistantResponsePresentation(
        text="Correlated response.",
        correlation=correlation,
    )

    assert presentation.correlation == correlation
    with pytest.raises(TypeError, match="correlation"):
        AssistantResponsePresentation(
            text="Uncorrelated response.",
            correlation=object(),  # type: ignore[arg-type]
        )


def test_agent_action_and_presentation_accept_exact_string_capacities() -> None:
    action = AssistantResponseAction(
        label="l" * _EXPECTED_MAX_ACTION_LABEL_LENGTH,
        kind=AssistantResponseActionKind.SEND_MESSAGE,
        prompt="q" * _EXPECTED_MAX_ACTION_PROMPT_LENGTH,
        action_id="a" * _EXPECTED_MAX_ACTION_ID_LENGTH,
    )
    presentation = AssistantResponsePresentation(
        text="c" * _EXPECTED_MAX_CONTENT_LENGTH,
        correlation=_CORRELATION,
        actions=(action,),
        presentation_id="p" * _EXPECTED_MAX_PRESENTATION_ID_LENGTH,
    )
    selection = AssistantResponseActionSelection(
        presentation_id="p" * _EXPECTED_MAX_PRESENTATION_ID_LENGTH,
        action=action,
    )

    assert presentation.actions == (action,)
    assert selection.presentation_id == presentation.presentation_id


@pytest.mark.parametrize(
    "build",
    [
        lambda: AssistantResponseAction(
            label="l" * (_EXPECTED_MAX_ACTION_LABEL_LENGTH + 1),
            kind=AssistantResponseActionKind.OPEN_PANEL,
            panel=AssistantPanelTarget.DATASET,
        ),
        lambda: AssistantResponseAction(
            label="Send",
            kind=AssistantResponseActionKind.SEND_MESSAGE,
            prompt="q" * (_EXPECTED_MAX_ACTION_PROMPT_LENGTH + 1),
        ),
        lambda: AssistantResponseAction(
            label="Open Dataset",
            kind=AssistantResponseActionKind.OPEN_PANEL,
            panel=AssistantPanelTarget.DATASET,
            action_id="a" * (_EXPECTED_MAX_ACTION_ID_LENGTH + 1),
        ),
        lambda: AssistantResponsePresentation(
            text="c" * (_EXPECTED_MAX_CONTENT_LENGTH + 1),
            correlation=_CORRELATION,
        ),
        lambda: AssistantResponsePresentation(
            text="Visible response",
            correlation=_CORRELATION,
            presentation_id="p" * (_EXPECTED_MAX_PRESENTATION_ID_LENGTH + 1),
        ),
        lambda: AssistantResponseActionSelection(
            presentation_id="p" * (_EXPECTED_MAX_PRESENTATION_ID_LENGTH + 1),
            action=AssistantResponseAction.open_panel(
                "Open Dataset",
                AssistantPanelTarget.DATASET,
            ),
        ),
    ],
)
def test_agent_action_and_presentation_reject_each_string_overflow(build) -> None:
    with pytest.raises(ValueError, match=r"maximum|at most"):
        build()


def test_assistant_response_and_actions_redact_private_diagnostic_context() -> None:
    private_path = "/srv/clinical/subject-17/events.tsv"
    private_subject = "Alice-Smith"
    action = AssistantResponseAction.send_message(
        f"Retry subject_id={private_subject}",
        f"Retry import from {private_path}",
    )

    presentation = AssistantResponsePresentation(
        text=(
            f"Could not read {private_path}\r\n"
            f"Review subject_id={private_subject} and retry."
        ),
        correlation=_CORRELATION,
        actions=(action,),
    )

    serialized = repr(presentation)
    assert private_path not in serialized
    assert private_subject not in serialized
    assert "events.tsv" in presentation.text
    assert "Review" in presentation.text
    assert "\r" not in presentation.text
    assert "\x00" not in presentation.text
    assert "[REDACTED_PATH]" in serialized
    assert "[SUBJECT_REF:" in serialized


def test_interaction_outcome_message_redacts_backend_failure_detail() -> None:
    private_path = r"\\research-nas\patient-share\sub-P001\recording.gdf"
    outcome = AgentInteractionOutcome(
        status=AgentInteractionStatus.BLOCKED,
        command_name="scan_source",
        message=f"Could not inspect {private_path}; subject_id=Alice.",
    )

    visible = interaction_outcome_message(outcome)

    assert private_path not in visible
    assert "sub-P001" not in visible
    assert "Alice" not in visible
    assert ".gdf" in visible
    assert "Could not inspect" in visible
