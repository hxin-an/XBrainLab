"""Product-safe copy and classification for the in-app assistant."""

from __future__ import annotations

from enum import Enum

from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.controller.chat_controller import ChatMessagePresentationKind
from XBrainLab.backend.training_state_contract import TrainingOutcomeState
from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest
from XBrainLab.llm.agent.response_presentation import AssistantResponseKind
from XBrainLab.ui.product_language import tool_action_label


class _RuntimeIssue(str, Enum):
    MODEL_CACHE = "model_cache"
    CUDA_UNAVAILABLE = "cuda_unavailable"
    GPU_MEMORY = "gpu_memory"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class AgentPresentationService:
    """Translate typed assistant events into stable, user-facing language."""

    @classmethod
    def runtime_unavailable_message(cls, message: str) -> str:
        return f"**Assistant unavailable**: {cls.runtime_status_message(message)}"

    @classmethod
    def runtime_status_message(cls, message: str) -> str:
        """Return a safe runtime reason for bubbles, status, and tooltips."""
        issue = cls._runtime_issue(message)
        if issue is _RuntimeIssue.MODEL_CACHE:
            return (
                "The selected local model is missing from the model cache. Open "
                "assistant settings to install or select a model."
            )
        if issue is _RuntimeIssue.CUDA_UNAVAILABLE:
            return (
                "CUDA is unavailable. Check the GPU runtime or use a CPU-compatible "
                "local assistant setting."
            )
        if issue is _RuntimeIssue.GPU_MEMORY:
            return (
                "The local model ran out of GPU memory. Close other GPU applications "
                "or choose a smaller model in assistant settings."
            )
        if issue is _RuntimeIssue.DISABLED:
            return "Assistant is disabled. Open assistant settings to enable it."
        return (
            "The local model could not start. Open assistant settings to check the "
            "installed model and runtime."
        )

    @classmethod
    def runtime_setup_message(cls, message: str) -> str:
        """Return stable setup copy for an intentionally inactive runtime."""
        normalized = " ".join(str(message or "").split()).lower()
        if "disabled" in normalized:
            return "Assistant is disabled. Open assistant settings to enable it."
        if "defer" in normalized or "later" in normalized:
            return (
                "Assistant setup was deferred. Open assistant settings when you are "
                "ready to continue."
            )
        return (
            "Assistant setup is incomplete. Open assistant settings when you are "
            "ready to continue."
        )

    @staticmethod
    def status_refresh_error() -> str:
        """Return stable copy for a failed backend-status refresh."""
        return "Workflow status could not be refreshed. Try again."

    @staticmethod
    def training_terminal_presentation(
        outcome: TrainingOutcomeState,
    ) -> tuple[str, AssistantResponseKind] | None:
        """Classify the one visible terminal message for an Assistant-started run."""
        return {
            TrainingOutcomeState.COMPLETED: (
                "Training completed. Results are ready in Evaluation.",
                AssistantResponseKind.TOOL_RESULT,
            ),
            TrainingOutcomeState.FAILED: (
                "Training failed. Review the Training panel, adjust the "
                "configuration, and try again.",
                AssistantResponseKind.ERROR,
            ),
            TrainingOutcomeState.CANCELLED: (
                "Training was cancelled.",
                AssistantResponseKind.CANCELLED,
            ),
        }.get(outcome)

    @staticmethod
    def chat_presentation_kind(
        kind: AssistantResponseKind,
    ) -> ChatMessagePresentationKind:
        """Map one authoritative response meaning to transcript presentation."""
        return {
            AssistantResponseKind.TOOL_RESULT: ChatMessagePresentationKind.TOOL_RESULT,
            AssistantResponseKind.CLARIFICATION: (
                ChatMessagePresentationKind.CLARIFICATION
            ),
            AssistantResponseKind.ERROR: ChatMessagePresentationKind.ERROR,
            AssistantResponseKind.BLOCKED: ChatMessagePresentationKind.ATTENTION,
            AssistantResponseKind.CANCELLED: ChatMessagePresentationKind.CANCELLED,
        }.get(kind, ChatMessagePresentationKind.ASSISTANT)

    @staticmethod
    def confirmation_context_changed(
        request: AgentConfirmationRequest,
        publication: ApplicationViewPublication,
    ) -> bool:
        """Report a stale request only against a reliable current publication."""
        request_generation = request.publication_generation
        if not getattr(publication, "usable", False) or not getattr(
            publication.state, "state_reliable", False
        ):
            return False
        return (
            request_generation is not None
            and publication.generation != request_generation
        )

    @staticmethod
    def _runtime_issue(message: str) -> _RuntimeIssue:
        normalized = " ".join(str(message or "").split()).lower()
        if (
            "out of memory" in normalized
            or "cuda oom" in normalized
            or "cuda out of memory" in normalized
        ):
            return _RuntimeIssue.GPU_MEMORY
        if "cuda" in normalized and any(
            marker in normalized
            for marker in (
                "unavailable",
                "not available",
                "driver",
                "initialization",
                "failed",
            )
        ):
            return _RuntimeIssue.CUDA_UNAVAILABLE
        if "cache" in normalized and any(
            marker in normalized for marker in ("missing", "not found", "unavailable")
        ):
            return _RuntimeIssue.MODEL_CACHE
        if "disabled" in normalized:
            return _RuntimeIssue.DISABLED
        return _RuntimeIssue.UNKNOWN

    @staticmethod
    def workflow_status(activity: AssistantTurnActivity) -> str:
        """Render turn-local activity without inferring backend workflow state."""
        if not isinstance(activity, AssistantTurnActivity):
            raise TypeError("Workflow status requires typed assistant turn activity.")

        if activity.phase is AssistantTurnActivityPhase.RUNNING_COMMAND:
            if activity.command_name:
                return f"Running: {tool_action_label(activity.command_name)}"
            return "Running workflow step"

        return {
            AssistantTurnActivityPhase.IDLE: "",
            AssistantTurnActivityPhase.PREPARING: "Checking data",
            AssistantTurnActivityPhase.THINKING: "Thinking",
            AssistantTurnActivityPhase.WAITING_FOR_DECISION: ("Waiting for decision"),
            AssistantTurnActivityPhase.STOPPING: "Stopping",
            AssistantTurnActivityPhase.NEEDS_ATTENTION: "Needs attention",
        }[activity.phase]

    @staticmethod
    def raw_status_diagnostic(raw_status: str) -> str:
        """Normalize raw runtime text for diagnostics without classifying activity."""
        if not isinstance(raw_status, str):
            raise TypeError("Raw assistant status diagnostic must be a string.")
        return " ".join(raw_status.split())
