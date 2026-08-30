"""Typed, view-only state for active assistant turns."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from XBrainLab.llm.agent.assistant_activity import (
    AssistantDecisionOwner,
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.ui_handoff import workflow_ui_handoff_route_for
from XBrainLab.product_language import tool_action_label


class ChatTurnPresentationPhase(str, Enum):
    """Visible phase of the current assistant turn."""

    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    APPLICATION_COMMAND = "application_command"
    STOPPING = "stopping"
    NEEDS_ATTENTION = "needs_attention"


class ChatTurnCancelability(str, Enum):
    """Whether the composer may offer a Stop action."""

    NONE = "none"
    CANCELLABLE = "cancellable"
    NOT_CANCELLABLE = "not_cancellable"
    STOPPING = "stopping"


@dataclass(frozen=True, slots=True)
class ChatTurnPresentation:
    """Complete progress state rendered by ``ChatPanel`` without text inference."""

    phase: ChatTurnPresentationPhase
    primary_status: str = ""
    step: str = ""
    cancelability: ChatTurnCancelability = ChatTurnCancelability.NONE
    cancelability_text: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.phase, ChatTurnPresentationPhase):
            raise TypeError("Chat turn presentation phase must be typed.")
        if not isinstance(self.cancelability, ChatTurnCancelability):
            raise TypeError("Chat turn cancelability must be typed.")
        for field_name in (
            "primary_status",
            "step",
            "cancelability_text",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"Chat turn {field_name} must be a string.")
            object.__setattr__(self, field_name, " ".join(value.split()))
        active = self.phase in {
            ChatTurnPresentationPhase.WORKING,
            ChatTurnPresentationPhase.WAITING,
            ChatTurnPresentationPhase.APPLICATION_COMMAND,
            ChatTurnPresentationPhase.STOPPING,
        }
        if active and (not self.primary_status or not self.step):
            raise ValueError("Active chat turns require a primary status and step.")
        if active and self.cancelability is ChatTurnCancelability.NONE:
            raise ValueError("Active chat turns require explicit cancelability.")
        if not active and self.cancelability is not ChatTurnCancelability.NONE:
            raise ValueError("Inactive chat turns cannot expose cancelability.")

    @property
    def is_busy(self) -> bool:
        """Return whether the current turn still owns work or a decision boundary."""
        return self.phase in {
            ChatTurnPresentationPhase.WORKING,
            ChatTurnPresentationPhase.WAITING,
            ChatTurnPresentationPhase.APPLICATION_COMMAND,
            ChatTurnPresentationPhase.STOPPING,
        }

    @property
    def is_visible(self) -> bool:
        """Return whether the progress surface should be shown."""
        return self.is_busy

    @classmethod
    def idle(cls) -> ChatTurnPresentation:
        return cls(phase=ChatTurnPresentationPhase.IDLE)

    @classmethod
    def restored_busy(cls) -> ChatTurnPresentation:
        """Fail closed when legacy history retained only a boolean busy flag."""
        return cls(
            phase=ChatTurnPresentationPhase.APPLICATION_COMMAND,
            primary_status="Request still in progress",
            step="Waiting for the current XBrainLab work to finish",
            cancelability=ChatTurnCancelability.NOT_CANCELLABLE,
            cancelability_text=(
                "Cancellation is unavailable because the active step could not be "
                "restored safely."
            ),
        )

    @classmethod
    def application_command(
        cls,
        step: str = "Run the current XBrainLab action",
    ) -> ChatTurnPresentation:
        """Present the hard boundary after an Application command has started."""
        return cls(
            phase=ChatTurnPresentationPhase.APPLICATION_COMMAND,
            primary_status="XBrainLab action in progress",
            step=step,
            cancelability=ChatTurnCancelability.NOT_CANCELLABLE,
            cancelability_text=(
                "This action has already started and cannot be stopped safely."
            ),
        )

    @classmethod
    def stopping(cls) -> ChatTurnPresentation:
        """Present an accepted cancellation while worker acknowledgement is pending."""
        return cls(
            phase=ChatTurnPresentationPhase.STOPPING,
            primary_status="Stopping request",
            step="Waiting for the local assistant to stop",
            cancelability=ChatTurnCancelability.STOPPING,
            cancelability_text="No new action will start.",
        )


def present_assistant_activity(
    activity: AssistantTurnActivity,
    *,
    application_command_in_flight: bool = False,
) -> ChatTurnPresentation:
    """Translate one typed runtime activity into explicit product presentation."""
    if not isinstance(activity, AssistantTurnActivity):
        raise TypeError("Assistant activity presentation requires a typed activity.")
    phase = activity.phase
    if (
        application_command_in_flight
        or phase is AssistantTurnActivityPhase.RUNNING_COMMAND
    ):
        step = (
            tool_action_label(activity.command_name)
            if activity.command_name
            else "Run the current XBrainLab action"
        )
        return ChatTurnPresentation.application_command(step)
    if phase is AssistantTurnActivityPhase.PREPARING:
        return ChatTurnPresentation(
            phase=ChatTurnPresentationPhase.WORKING,
            primary_status="Preparing your request",
            step="Checking the current EEG workflow",
            cancelability=ChatTurnCancelability.CANCELLABLE,
            cancelability_text=("You can stop before an XBrainLab action starts."),
        )
    if phase is AssistantTurnActivityPhase.THINKING:
        return ChatTurnPresentation(
            phase=ChatTurnPresentationPhase.WORKING,
            primary_status="Working on your request",
            step="Planning the next safe step",
            cancelability=ChatTurnCancelability.CANCELLABLE,
            cancelability_text=("You can stop before an XBrainLab action starts."),
        )
    if phase is AssistantTurnActivityPhase.WAITING_FOR_DECISION:
        owner = activity.decision_owner
        if owner is AssistantDecisionOwner.CONFIRMATION_CARD:
            primary_status = "Waiting for your confirmation"
            step = tool_action_label(activity.command_name)
            decision_text = "Use the confirmation card to continue or cancel."
        else:
            primary_status = "Waiting for your input"
            route = workflow_ui_handoff_route_for(activity.command_name)
            if route is not None:
                step = route.presentation_step
                decision_text = route.decision_copy
            elif owner is AssistantDecisionOwner.GUI_DIALOG:
                step = tool_action_label(activity.command_name)
                decision_text = "Finish or cancel in the open XBrainLab dialog."
            else:
                step = tool_action_label(activity.command_name)
                decision_text = "Continue in the opened XBrainLab panel."
        return ChatTurnPresentation(
            phase=ChatTurnPresentationPhase.WAITING,
            primary_status=primary_status,
            step=step,
            cancelability=ChatTurnCancelability.NOT_CANCELLABLE,
            cancelability_text=decision_text,
        )
    if phase is AssistantTurnActivityPhase.STOPPING:
        return ChatTurnPresentation.stopping()
    if phase is AssistantTurnActivityPhase.NEEDS_ATTENTION:
        return ChatTurnPresentation(phase=ChatTurnPresentationPhase.NEEDS_ATTENTION)
    return ChatTurnPresentation.idle()
