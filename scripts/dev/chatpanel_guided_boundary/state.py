"""Typed lifecycle state for the real-model Guided Workflow walkthrough."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GuidedBoundaryPhase(str, Enum):
    """Event-loop phases for one typed workflow-UI handoff proof."""

    CREATED = "created"
    STARTING = "starting"
    WAITING_FOR_READY = "waiting_for_ready"
    SELECTING_GUIDED_MODE = "selecting_guided_mode"
    RUNNING_AUTO_CHAIN = "running_auto_chain"
    WAITING_AT_BOUNDARY = "waiting_at_boundary"
    WORKFLOW_HANDOFF_OPEN = "workflow_handoff_open"
    WAITING_AFTER_CANCEL = "waiting_after_cancel"
    FINALIZING = "finalizing"
    SHUTTING_DOWN = "shutting_down"
    COMPLETED = "completed"


_NORMAL_TRANSITIONS: dict[GuidedBoundaryPhase, GuidedBoundaryPhase] = {
    GuidedBoundaryPhase.CREATED: GuidedBoundaryPhase.STARTING,
    GuidedBoundaryPhase.STARTING: GuidedBoundaryPhase.WAITING_FOR_READY,
    GuidedBoundaryPhase.WAITING_FOR_READY: GuidedBoundaryPhase.SELECTING_GUIDED_MODE,
    GuidedBoundaryPhase.SELECTING_GUIDED_MODE: GuidedBoundaryPhase.RUNNING_AUTO_CHAIN,
    GuidedBoundaryPhase.RUNNING_AUTO_CHAIN: GuidedBoundaryPhase.WAITING_AT_BOUNDARY,
    GuidedBoundaryPhase.WAITING_AT_BOUNDARY: GuidedBoundaryPhase.WORKFLOW_HANDOFF_OPEN,
    GuidedBoundaryPhase.WORKFLOW_HANDOFF_OPEN: GuidedBoundaryPhase.WAITING_AFTER_CANCEL,
    GuidedBoundaryPhase.WAITING_AFTER_CANCEL: GuidedBoundaryPhase.FINALIZING,
    GuidedBoundaryPhase.FINALIZING: GuidedBoundaryPhase.SHUTTING_DOWN,
    GuidedBoundaryPhase.SHUTTING_DOWN: GuidedBoundaryPhase.COMPLETED,
}


@dataclass(frozen=True)
class GuidedTurnContext:
    """Evidence boundaries captured before one user-visible assistant turn."""

    before_messages: int
    before_tools: int
    before_metric_turns: int
    before_application_results: int
    before_command_observations: int
    before_turn_terminals: int
    before_tool_attempts: int
    started_at: float


@dataclass
class GuidedBoundaryState:
    """Mutable evidence owned by one Guided Workflow harness process."""

    source_path: str
    model_id: str
    prompts: tuple[str, ...]
    started_at: float
    status: str = "running"
    failure_reason: str = ""
    exception: str = ""
    phase: GuidedBoundaryPhase = GuidedBoundaryPhase.CREATED
    phase_history: list[GuidedBoundaryPhase] = field(
        default_factory=lambda: [GuidedBoundaryPhase.CREATED]
    )
    screenshots: dict[str, str] = field(
        default_factory=lambda: {
            "ready": "",
            "auto_chain_complete": "",
            "workflow_dialog_open": "",
            "post_cancel": "",
            "failure": "",
        }
    )
    mode_selection: dict[str, Any] = field(default_factory=dict)
    initial_publication: dict[str, Any] = field(default_factory=dict)
    command_observations: list[dict[str, Any]] = field(default_factory=list)
    first_turn: dict[str, Any] = field(default_factory=dict)
    boundary: dict[str, Any] = field(default_factory=dict)
    workflow_handoff: dict[str, Any] = field(default_factory=dict)
    wizard: dict[str, Any] = field(default_factory=dict)
    post_cancel: dict[str, Any] = field(default_factory=dict)
    visible_messages: list[dict[str, Any]] = field(default_factory=list)
    executed_tools: list[dict[str, Any]] = field(default_factory=list)
    setup_dialogs: list[dict[str, Any]] = field(default_factory=list)
    workflow_handoff_requests: list[Any] = field(default_factory=list)
    confirmation_requests: list[Any] = field(default_factory=list)
    interaction_events: list[Any] = field(default_factory=list)
    application_results: list[Any] = field(default_factory=list)
    turn_terminals: list[Any] = field(default_factory=list)
    runtime_snapshot: dict[str, Any] = field(default_factory=dict)
    ui_state: dict[str, Any] = field(default_factory=dict)
    transcript_clean: bool = True
    shutdown: dict[str, str] = field(
        default_factory=lambda: {"status": "not_started", "detail": ""}
    )
    elapsed_seconds: float = 0.0
    terminal_started: bool = False
    shutdown_deadline: float = 0.0
    observed_controller_id: int | None = None
    handled_setup_dialog_ids: set[int] = field(default_factory=set)

    def advance(self, next_phase: GuidedBoundaryPhase) -> None:
        """Move through the exact happy path, allowing failure finalization only."""
        if next_phase is GuidedBoundaryPhase.FINALIZING:
            legal = self.phase not in {
                GuidedBoundaryPhase.FINALIZING,
                GuidedBoundaryPhase.SHUTTING_DOWN,
                GuidedBoundaryPhase.COMPLETED,
            }
        else:
            legal = _NORMAL_TRANSITIONS.get(self.phase) is next_phase
        if not legal:
            raise RuntimeError(
                "Invalid guided walkthrough phase transition: "
                f"{self.phase.value} -> {next_phase.value}"
            )
        self.phase = next_phase
        self.phase_history.append(next_phase)


def reconcile_closed_event_loop(
    state: GuidedBoundaryState,
    *,
    window_visible: bool,
    lifecycle_state: str,
) -> bool:
    """Complete shutdown only when both native owners are observably closed."""
    if (
        state.shutdown.get("status") != "closing"
        or window_visible
        or lifecycle_state != "closed"
        or state.phase is not GuidedBoundaryPhase.SHUTTING_DOWN
    ):
        return False
    state.shutdown = {"status": "completed", "detail": ""}
    state.advance(GuidedBoundaryPhase.COMPLETED)
    return True
