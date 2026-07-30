"""Product-safe copy and classification for the in-app assistant."""

from __future__ import annotations

from enum import Enum

from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.ui.components.workflow_surface_router import (
    WorkflowSurfaceOutcome,
    WorkflowSurfaceStatus,
)
from XBrainLab.ui.product_language import tool_action_label


class _RuntimeIssue(str, Enum):
    MODEL_CACHE = "model_cache"
    CUDA_UNAVAILABLE = "cuda_unavailable"
    GPU_MEMORY = "gpu_memory"
    DISABLED = "disabled"
    MODEL_START = "model_start"
    UNKNOWN = "unknown"


class AgentPresentationService:
    """Translate typed assistant events into stable, user-facing language."""

    _LEGACY_CANCELLED_TURN_COPY = (
        "The assistant stopped this request. No further response or action will run."
    )
    _CANCELLED_TURN_COPY = "Request cancelled. You can revise it or ask something else."

    @classmethod
    def assistant_transcript_message(cls, message: str) -> str:
        """Replace one legacy cancellation sentence without reclassifying replies."""
        if not isinstance(message, str):
            raise TypeError("Assistant transcript copy must be a string.")
        if " ".join(message.split()) == cls._LEGACY_CANCELLED_TURN_COPY:
            return cls._CANCELLED_TURN_COPY
        return message

    @classmethod
    def is_cancelled_transcript_message(cls, message: str) -> bool:
        """Identify the one host-owned terminal cancellation presentation."""
        if not isinstance(message, str):
            raise TypeError("Assistant transcript copy must be a string.")
        normalized = " ".join(message.split())
        if normalized in {
            cls._LEGACY_CANCELLED_TURN_COPY,
            cls._CANCELLED_TURN_COPY,
        }:
            return True
        normalized_lower = normalized.lower()
        return " cancelled. " in f" {normalized_lower} " and normalized.endswith(
            (
                "Your current workflow is unchanged.",
                "Your current workspace is unchanged.",
                "Your current history is unchanged.",
            )
        )

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
    def runtime_settings_notice(cls, message: str) -> str:
        """Describe a failed start from inside Assistant Settings."""
        issue = cls._runtime_issue(message)
        if issue is _RuntimeIssue.MODEL_CACHE:
            return (
                "The selected local model is missing. Install it or choose another "
                "model."
            )
        if issue is _RuntimeIssue.CUDA_UNAVAILABLE:
            return (
                "CUDA is unavailable. Check the GPU runtime or select a "
                "CPU-compatible setup."
            )
        if issue is _RuntimeIssue.GPU_MEMORY:
            return (
                "The local model ran out of GPU memory. Close other GPU applications "
                "or select a smaller model."
            )
        if issue is _RuntimeIssue.DISABLED:
            return "Assistant is disabled. Enable Use local assistant to continue."
        return (
            "The local model could not start. Check the installed model and runtime, "
            "then try again."
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
    def workflow_surface_outcome_message(outcome: WorkflowSurfaceOutcome) -> str:
        """Translate a typed product-surface result into concise assistant copy."""
        label = tool_action_label(outcome.command_name)
        if outcome.command_name == "evaluate":
            evaluation_copy = {
                WorkflowSurfaceStatus.COMPLETED: (
                    "Evaluation review is ready in XBrainLab."
                ),
                WorkflowSurfaceStatus.CANCELLED: (
                    "Evaluation review was cancelled. "
                    "Your current workflow is unchanged."
                ),
                WorkflowSurfaceStatus.FAILED: (
                    "XBrainLab could not open Evaluation. "
                    "Try again from the main window."
                ),
            }
            if outcome.status in evaluation_copy:
                return evaluation_copy[outcome.status]
        if outcome.status is WorkflowSurfaceStatus.NAVIGATED:
            if outcome.command_name == "evaluate":
                return "Evaluation is open in the main window. Review results there."
            if outcome.command_name == "visualize":
                return (
                    "Visualization is open in the main window. Review the output there."
                )
            return f"{label} is open in the main window. Continue there."
        if outcome.status is WorkflowSurfaceStatus.COMPLETED:
            return f"{label} is ready in XBrainLab."
        if outcome.status is WorkflowSurfaceStatus.ACCEPTED:
            return (
                f"{label} settings were submitted. "
                "Review the main window for the current result."
            )
        if outcome.status is WorkflowSurfaceStatus.CANCELLED:
            return f"{label} was cancelled. Your current workflow is unchanged."
        if outcome.status is WorkflowSurfaceStatus.CLOSED_WITHOUT_CHANGE:
            return f"{label} closed without changing your workflow."
        if outcome.status is WorkflowSurfaceStatus.BLOCKED:
            return (
                f"{label} is not available yet. Complete the required earlier "
                "workflow step first."
            )
        if outcome.status is WorkflowSurfaceStatus.UNAVAILABLE:
            return f"{label} is not available from the assistant yet."
        return f"XBrainLab could not open {label}. Try again from the main window."

    @staticmethod
    def workflow_error_status(_message: str = "") -> str:
        """Return stable status copy without exposing backend exception details."""
        return "Review the current workflow step and try again."

    @staticmethod
    def status_refresh_error() -> str:
        """Return stable copy for a failed backend-status refresh."""
        return "Workflow status could not be refreshed. Try again."

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
        if "model load" in normalized or "runtime unavailable" in normalized:
            return _RuntimeIssue.MODEL_START
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
