"""Typed lifecycle and mutable evidence state for one walkthrough run."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scripts.dev.chatpanel_pipeline_chain.contracts import EventBucket


class PipelinePhase(str, Enum):
    """Lifecycle phases for one event-loop-owned walkthrough run."""

    CREATED = "created"
    STARTING = "starting"
    WAITING_FOR_READY = "waiting_for_ready"
    RUNNING_TURNS = "running_turns"
    FINALIZING = "finalizing"
    SHUTTING_DOWN = "shutting_down"
    COMPLETED = "completed"


_PHASE_TRANSITIONS: dict[PipelinePhase, frozenset[PipelinePhase]] = {
    PipelinePhase.CREATED: frozenset(
        {PipelinePhase.STARTING, PipelinePhase.FINALIZING}
    ),
    PipelinePhase.STARTING: frozenset(
        {PipelinePhase.WAITING_FOR_READY, PipelinePhase.FINALIZING}
    ),
    PipelinePhase.WAITING_FOR_READY: frozenset(
        {PipelinePhase.RUNNING_TURNS, PipelinePhase.FINALIZING}
    ),
    PipelinePhase.RUNNING_TURNS: frozenset({PipelinePhase.FINALIZING}),
    PipelinePhase.FINALIZING: frozenset({PipelinePhase.SHUTTING_DOWN}),
    PipelinePhase.SHUTTING_DOWN: frozenset({PipelinePhase.COMPLETED}),
    PipelinePhase.COMPLETED: frozenset(),
}


@dataclass
class PipelineWalkthroughState:
    """Mutable runtime state and evidence owned by one walkthrough run."""

    source_path: str
    prompt_style: str
    expected_tools: list[str]
    started_at: float
    status: str = "running"
    failure_reason: str = ""
    exception: str = ""
    ready_screenshot: str = ""
    terminal_screenshot: str = ""
    failure_screenshot: str = ""
    turns: list[dict[str, Any]] = field(default_factory=list)
    model_generations: list[str] = field(default_factory=list)
    model_generation_request_ids: list[int] = field(default_factory=list)
    active_model_request_id: int | None = None
    visible_messages: list[dict[str, Any]] = field(default_factory=list)
    executed_tools: list[dict[str, Any]] = field(default_factory=list)
    setup_dialogs: list[dict[str, Any]] = field(default_factory=list)
    confirmation_dialogs: list[dict[str, Any]] = field(default_factory=list)
    confirmation_requests: list[Any] = field(default_factory=list)
    interaction_events: list[Any] = field(default_factory=list)
    workflow_handoffs: list[Any] = field(default_factory=list)
    application_results: list[Any] = field(default_factory=list)
    turn_terminals: list[Any] = field(default_factory=list)
    controller_history: Any = field(default_factory=list)
    final_state: dict[str, Any] = field(default_factory=dict)
    final_publication: dict[str, Any] = field(default_factory=dict)
    runtime_snapshot: dict[str, Any] = field(default_factory=dict)
    send_button_text: str = ""
    send_button_enabled: bool = False
    input_enabled: bool = False
    chat_processing: bool = True
    controller_processing: bool = True
    shutdown: dict[str, str] = field(
        default_factory=lambda: {"status": "pending", "detail": ""}
    )
    elapsed_seconds: float = 0.0
    phase: PipelinePhase = PipelinePhase.CREATED
    phase_history: list[PipelinePhase] = field(
        default_factory=lambda: [PipelinePhase.CREATED]
    )
    terminal_started: bool = False
    shutdown_deadline: float = 0.0
    observed_controller_id: int | None = None
    handled_dialog_ids: set[int] = field(default_factory=set)

    def advance(self, next_phase: PipelinePhase) -> None:
        """Move to the next legal lifecycle phase or fail loudly."""
        if next_phase not in _PHASE_TRANSITIONS[self.phase]:
            raise RuntimeError(
                "Invalid walkthrough phase transition: "
                f"{self.phase.value} -> {next_phase.value}"
            )
        self.phase = next_phase
        self.phase_history.append(next_phase)

    def append_event(
        self,
        bucket: EventBucket,
        payload: object,
        *,
        structured_value: Callable[[Any], Any],
    ) -> None:
        target = getattr(self, bucket)
        target.append(structured_value(payload))

    def event_counts(self) -> dict[EventBucket, int]:
        return {
            bucket: len(getattr(self, bucket))
            for bucket in (
                "confirmation_requests",
                "interaction_events",
                "workflow_handoffs",
                "application_results",
                "turn_terminals",
            )
        }

    def begin_model_generation(self, generation_id: object) -> bool:
        """Open one evidence buffer for a valid correlated worker request."""
        if (
            isinstance(generation_id, bool)
            or not isinstance(generation_id, int)
            or generation_id <= 0
        ):
            self.active_model_request_id = None
            return False
        self.active_model_request_id = generation_id
        self.model_generation_request_ids.append(generation_id)
        self.model_generations.append("")
        return True

    def append_model_chunk(self, generation_id: object, chunk: object) -> bool:
        """Append only output correlated to the currently active request ID."""
        if generation_id != self.active_model_request_id or not self.model_generations:
            return False
        self.model_generations[-1] += str(chunk)
        return True

    def end_model_generation(self, generation_id: object) -> bool:
        """Close only the generation matching the active request ID."""
        if generation_id != self.active_model_request_id:
            return False
        self.active_model_request_id = None
        return True

    def event_slice(
        self,
        bucket: EventBucket,
        counts: Mapping[EventBucket, int],
    ) -> list[Any]:
        return list(getattr(self, bucket)[counts[bucket] :])

    def validation_payload(self) -> dict[str, Any]:
        """Return the deterministic evidence consumed by the existing validator."""
        return {
            "status": self.status,
            "failure_reason": self.failure_reason,
            "expected_tools": self.expected_tools,
            "turns": self.turns,
            "model_generations": self.model_generations,
            "model_generation_request_ids": self.model_generation_request_ids,
            "executed_tools": self.executed_tools,
            "confirmation_dialogs": self.confirmation_dialogs,
            "confirmation_requests": self.confirmation_requests,
            "interaction_events": self.interaction_events,
            "workflow_handoffs": self.workflow_handoffs,
            "application_results": self.application_results,
            "turn_terminals": self.turn_terminals,
            "final_state": self.final_state,
            "final_publication": self.final_publication,
        }


@dataclass(frozen=True)
class PipelineTurnContext:
    """Evidence boundaries captured immediately before one assistant turn."""

    before_messages: int
    before_tools: int
    before_metric_turns: int
    publication_before: dict[str, Any]
    event_counts: Mapping[EventBucket, int]
    started_at: float
