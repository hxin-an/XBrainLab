"""Typed, user-facing assistant responses with bounded next actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.utils.public_diagnostics import (
    DiagnosticTextLayout,
    public_diagnostic_text,
)
from XBrainLab.chat_contract import (
    MAX_CHAT_ACTION_ID_LENGTH,
    MAX_CHAT_ACTION_LABEL_LENGTH,
    MAX_CHAT_ACTION_PROMPT_LENGTH,
    MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    MAX_CHAT_PRESENTATION_ID_LENGTH,
    MAX_CHAT_RESPONSE_ACTIONS,
    bounded_chat_string,
)
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.product_language import tool_action_label

from .interaction import AgentInteractionOutcome, AgentInteractionStatus
from .turn import AssistantTurnCorrelation


class AssistantResponseKind(str, Enum):
    """User-visible meaning of one assistant response."""

    MESSAGE = "message"
    TOOL_RESULT = "tool_result"
    CLARIFICATION = "clarification"
    BLOCKED = "blocked"
    ERROR = "error"
    CANCELLED = "cancelled"


class AssistantResponseActionKind(str, Enum):
    """Safe host action offered below one response."""

    SEND_MESSAGE = "send_message"
    OPEN_PANEL = "open_panel"
    OPEN_DATA_IMPORT = "open_data_import"


class AssistantPanelTarget(str, Enum):
    """Existing main-window surfaces an assistant response may open."""

    DATASET = "dataset"
    PREPROCESS = "preprocess"
    TRAINING = "training"
    EVALUATION = "evaluation"
    VISUALIZATION = "visualization"


_PANEL_VIEW_MODES: dict[AssistantPanelTarget, frozenset[str]] = {
    AssistantPanelTarget.VISUALIZATION: frozenset(
        {
            "saliency_map",
            "spectrogram",
            "topographic_map",
            "3d_plot",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class AssistantPanelNavigationRequest:
    """One validated request to open an existing product panel or sub-view."""

    target: AssistantPanelTarget
    view_mode: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target, AssistantPanelTarget):
            raise TypeError("Assistant panel target must be typed.")
        if self.view_mode is None:
            return
        if not isinstance(self.view_mode, str):
            raise TypeError("Assistant panel view mode must be a string.")
        normalized = self.view_mode.strip().lower()
        allowed = _PANEL_VIEW_MODES.get(self.target, frozenset())
        if normalized not in allowed:
            raise ValueError(
                f"View mode {normalized or '(empty)'} is not available for "
                f"{self.target.value}."
            )
        object.__setattr__(self, "view_mode", normalized)


_DATASET_PANEL_COMMANDS = frozenset(
    {
        CommandName.SCAN_SOURCE,
        CommandName.REVIEW_INTERPRETATION,
        CommandName.PREVIEW_INTERPRETATION,
        CommandName.VALIDATE_INTERPRETATION,
        CommandName.APPLY_INTERPRETATION,
        CommandName.SAVE_INTERPRETATION_RECIPE,
        CommandName.RELOAD_INTERPRETATION_RECIPE,
        CommandName.LOAD_DATA,
        CommandName.ATTACH_LABELS,
        CommandName.IMPORT_LABELS,
        CommandName.UPDATE_METADATA,
        CommandName.APPLY_SMART_PARSE,
        CommandName.REMOVE_FILES,
        CommandName.RESET_SESSION,
        CommandName.NEW_SESSION,
    }
)
_PREPROCESS_PANEL_COMMANDS = frozenset(
    {
        CommandName.PREPROCESS,
        CommandName.CREATE_EPOCH,
        CommandName.RESET_PREPROCESS,
    }
)
_TRAINING_PANEL_COMMANDS = frozenset(
    {
        CommandName.GENERATE_DATASET,
        CommandName.CLEAR_DATASETS,
        CommandName.CONFIGURE_TRAINING,
        CommandName.TRAIN,
        CommandName.STOP_TRAINING,
        CommandName.CLEAR_TRAINING_HISTORY,
    }
)

_COMMAND_PANEL_TARGETS: dict[CommandName, AssistantPanelTarget] = {
    **dict.fromkeys(_DATASET_PANEL_COMMANDS, AssistantPanelTarget.DATASET),
    **dict.fromkeys(_PREPROCESS_PANEL_COMMANDS, AssistantPanelTarget.PREPROCESS),
    **dict.fromkeys(_TRAINING_PANEL_COMMANDS, AssistantPanelTarget.TRAINING),
    CommandName.EVALUATE: AssistantPanelTarget.EVALUATION,
    CommandName.APPLY_MONTAGE: AssistantPanelTarget.VISUALIZATION,
    CommandName.VISUALIZE: AssistantPanelTarget.VISUALIZATION,
    CommandName.SALIENCY: AssistantPanelTarget.VISUALIZATION,
}

_BLOCKED_COMMAND_PANEL_TARGETS: dict[CommandName, AssistantPanelTarget] = {
    CommandName.EVALUATE: AssistantPanelTarget.TRAINING,
}


def _command_identifier(command_identity: str | CommandName) -> str:
    if isinstance(command_identity, CommandName):
        return command_identity.value
    if type(command_identity) is not str:
        return ""
    return command_identity.strip().lower()


def _canonical_command_identity(
    command_identity: str | CommandName,
) -> CommandName | None:
    identifier = _command_identifier(command_identity)
    if not identifier:
        return None
    try:
        return CommandName(identifier)
    except ValueError:
        contract = AGENT_ACTION_CONTRACTS.contract_for(identifier)
        return contract.command if contract is not None else None


def user_facing_generation_error(raw_error: object) -> str:
    """Return actionable generation failure copy without exposing internals."""
    normalized = " ".join(str(raw_error or "").split()).lower()
    if any(marker in normalized for marker in ("out of memory", "cuda oom")):
        return (
            "The local assistant ran out of GPU memory. Close other GPU "
            "applications or choose a smaller model, then retry."
        )
    if any(
        marker in normalized
        for marker in (
            "model load",
            "failed to load",
            "runtime unavailable",
            "cuda unavailable",
            "cuda initialization",
        )
    ):
        return (
            "The local assistant could not start or continue. Open assistant "
            "settings to check the selected model and runtime, then retry."
        )
    return (
        "The assistant could not complete the request. Try again. Technical "
        "details were written to the application log."
    )


def panel_target_for_command(
    command_name: str | CommandName,
) -> AssistantPanelTarget | None:
    """Return one shared product-surface target for backend and tool names."""
    canonical_command = _canonical_command_identity(command_name)
    return (
        _COMMAND_PANEL_TARGETS.get(canonical_command)
        if canonical_command is not None
        else None
    )


def panel_target_for_blocked_command(
    command_name: str | CommandName,
    blocked_reason: str | None,
) -> AssistantPanelTarget | None:
    """Route a blocked action from command identity, never display copy."""
    # Kept in the signature for the current controller call; presentation copy is
    # deliberately non-authoritative for routing.
    _ = blocked_reason
    canonical_command = _canonical_command_identity(command_name)
    if canonical_command is None:
        return None
    return _BLOCKED_COMMAND_PANEL_TARGETS.get(
        canonical_command,
        _COMMAND_PANEL_TARGETS.get(canonical_command),
    )


def interaction_outcome_message(outcome: AgentInteractionOutcome) -> str:
    """Translate one typed interaction result into stable product copy."""
    if not isinstance(outcome, AgentInteractionOutcome):
        raise TypeError("Interaction outcome copy requires a typed outcome.")
    command_identifier = _command_identifier(outcome.command_name)
    label = tool_action_label(command_identifier)
    if outcome.status is AgentInteractionStatus.CONFIRMED:
        return f"Approved: {label}. XBrainLab is starting the action."
    if outcome.status is AgentInteractionStatus.CANCELLED:
        cancelled_copy = {
            "clear_dataset": (
                "Dataset removal cancelled. Your current workspace is unchanged."
            ),
            "clear_datasets": (
                "Dataset removal cancelled. Your current workspace is unchanged."
            ),
            "clear_training_history": (
                "Training history removal cancelled. Your current history is unchanged."
            ),
            "reset_preprocess": (
                "Preprocessing reset cancelled. Your current workflow is unchanged."
            ),
            "reset_session": (
                "Session reset cancelled. Your current workflow is unchanged."
            ),
            "new_session": (
                "Session reset cancelled. Your current workflow is unchanged."
            ),
            "apply_interpretation": ("Data import was cancelled. No data was added."),
        }
        return cancelled_copy.get(
            command_identifier,
            f"{label} was cancelled. Your current workflow is unchanged.",
        )
    if outcome.status is AgentInteractionStatus.DEFERRED_TO_UI:
        if command_identifier == CommandName.EVALUATE.value:
            return "Evaluation is open in the main window. Review results there."
        return f"{label} is open in the main window. Continue there."
    if outcome.status is AgentInteractionStatus.COMPLETED_IN_UI:
        return f"{label} was completed in XBrainLab."
    detail = public_diagnostic_text(
        outcome.message or "",
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )
    if outcome.status is AgentInteractionStatus.BLOCKED:
        return detail or (
            f"{label} is blocked by the current workflow state. "
            "Complete the required earlier step first."
        )
    if outcome.status is AgentInteractionStatus.UNAVAILABLE:
        return detail or f"{label} is not available from the assistant yet."
    if detail:
        return f"{label} could not be opened. {detail}"
    return f"{label} could not be opened. No action was run."


def interaction_outcome_kind(
    outcome: AgentInteractionOutcome,
) -> AssistantResponseKind:
    """Return the transcript meaning for one typed interaction result."""
    if not isinstance(outcome, AgentInteractionOutcome):
        raise TypeError("Interaction outcome kind requires a typed outcome.")
    if outcome.status is AgentInteractionStatus.FAILED:
        return AssistantResponseKind.ERROR
    if outcome.status is AgentInteractionStatus.CANCELLED:
        return AssistantResponseKind.CANCELLED
    if outcome.status is AgentInteractionStatus.COMPLETED_IN_UI:
        return AssistantResponseKind.TOOL_RESULT
    if outcome.status in {
        AgentInteractionStatus.BLOCKED,
        AgentInteractionStatus.UNAVAILABLE,
    }:
        return AssistantResponseKind.BLOCKED
    return AssistantResponseKind.MESSAGE


@dataclass(frozen=True, slots=True)
class AssistantResponseAction:
    """One bounded action rendered below an assistant response."""

    label: str
    kind: AssistantResponseActionKind
    prompt: str = ""
    panel: AssistantPanelTarget | None = None
    action_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AssistantResponseActionKind):
            raise TypeError("Assistant response action kind must be typed.")
        object.__setattr__(
            self,
            "label",
            bounded_chat_string(
                public_diagnostic_text(self.label),
                field_name="Assistant response action label",
                maximum_length=MAX_CHAT_ACTION_LABEL_LENGTH,
                normalize_whitespace=True,
            ),
        )
        object.__setattr__(
            self,
            "prompt",
            bounded_chat_string(
                public_diagnostic_text(self.prompt),
                field_name="Assistant response action prompt",
                maximum_length=MAX_CHAT_ACTION_PROMPT_LENGTH,
                normalize_whitespace=True,
            ),
        )
        object.__setattr__(
            self,
            "action_id",
            bounded_chat_string(
                self.action_id,
                field_name="Assistant response action id",
                maximum_length=MAX_CHAT_ACTION_ID_LENGTH,
                normalize_whitespace=True,
            ),
        )
        if self.panel is not None and not isinstance(self.panel, AssistantPanelTarget):
            raise TypeError("Assistant response panel target must be typed.")
        if not self.label.strip():
            raise ValueError("Assistant response action label cannot be empty.")
        if not self.action_id.strip():
            raise ValueError("Assistant response action id cannot be empty.")
        if self.kind is AssistantResponseActionKind.SEND_MESSAGE:
            if not self.prompt.strip() or self.panel is not None:
                raise ValueError("Send-message actions require only a prompt.")
        elif self.kind is AssistantResponseActionKind.OPEN_PANEL and (
            self.panel is None or self.prompt.strip()
        ):
            raise ValueError("Open-panel actions require only a panel target.")
        elif self.kind is AssistantResponseActionKind.OPEN_DATA_IMPORT and (
            self.prompt.strip() or self.panel is not None
        ):
            raise ValueError("Open-data-import actions do not accept payload fields.")

    @classmethod
    def send_message(cls, label: str, prompt: str) -> AssistantResponseAction:
        """Build an action that submits visible user text through the agent."""
        return cls(
            label=label,
            kind=AssistantResponseActionKind.SEND_MESSAGE,
            prompt=prompt,
        )

    @classmethod
    def open_panel(
        cls,
        label: str,
        panel: AssistantPanelTarget,
    ) -> AssistantResponseAction:
        """Build an action that opens one existing product panel."""
        return cls(
            label=label,
            kind=AssistantResponseActionKind.OPEN_PANEL,
            panel=panel,
        )

    @classmethod
    def open_data_import(cls, label: str) -> AssistantResponseAction:
        """Build a typed action that opens the existing Data Import surface."""
        return cls(
            label=label,
            kind=AssistantResponseActionKind.OPEN_DATA_IMPORT,
        )


@dataclass(frozen=True, slots=True)
class AssistantResponsePresentation:
    """Typed response copy and a small set of contextual actions."""

    text: str
    correlation: AssistantTurnCorrelation
    kind: AssistantResponseKind = AssistantResponseKind.MESSAGE
    actions: tuple[AssistantResponseAction, ...] = ()
    presentation_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        if not isinstance(self.correlation, AssistantTurnCorrelation):
            raise TypeError("Assistant responses require typed turn correlation.")
        if not isinstance(self.kind, AssistantResponseKind):
            raise TypeError("Assistant response kind must be typed.")
        object.__setattr__(
            self,
            "text",
            bounded_chat_string(
                public_diagnostic_text(self.text),
                field_name="Assistant response text",
                maximum_length=MAX_CHAT_MESSAGE_CONTENT_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "presentation_id",
            bounded_chat_string(
                self.presentation_id,
                field_name="Assistant response presentation id",
                maximum_length=MAX_CHAT_PRESENTATION_ID_LENGTH,
                normalize_whitespace=True,
            ),
        )
        if not isinstance(self.actions, tuple):
            raise TypeError("Assistant response actions must be a tuple.")
        if not all(
            isinstance(action, AssistantResponseAction) for action in self.actions
        ):
            raise TypeError("Assistant responses require typed response actions.")
        if not self.text.strip():
            raise ValueError("Assistant response text cannot be empty.")
        if not self.presentation_id.strip():
            raise ValueError("Assistant response presentation id cannot be empty.")
        if len(self.actions) > MAX_CHAT_RESPONSE_ACTIONS:
            raise ValueError(
                "Assistant responses may expose at most "
                f"{MAX_CHAT_RESPONSE_ACTIONS} actions."
            )
        if len({action.action_id for action in self.actions}) != len(self.actions):
            raise ValueError("Assistant response action ids must be unique.")


@dataclass(frozen=True, slots=True)
class AssistantResponseActionSelection:
    """Correlated user selection from one still-visible presentation."""

    presentation_id: str
    action: AssistantResponseAction

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "presentation_id",
            bounded_chat_string(
                self.presentation_id,
                field_name="Assistant response presentation id",
                maximum_length=MAX_CHAT_PRESENTATION_ID_LENGTH,
                normalize_whitespace=True,
            ),
        )
        if not self.presentation_id.strip():
            raise ValueError("Assistant response presentation id cannot be empty.")
        if not isinstance(self.action, AssistantResponseAction):
            raise TypeError(
                "Assistant response selection requires a typed response action."
            )
