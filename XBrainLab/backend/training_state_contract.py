"""Small backend contract for consistent reads of mutable training state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol


class TrainingOutcomeState(str, Enum):
    """Typed lifecycle states for one trainer execution."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STOP_REQUESTED = "stop_requested"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrainingRunIdentity:
    """Stable identity for one execution of one trainer instance."""

    trainer_id: str
    run_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.trainer_id, str) or not self.trainer_id.strip():
            raise TypeError("trainer_id must be a non-empty string")
        if (
            isinstance(self.run_id, bool)
            or not isinstance(self.run_id, int)
            or self.run_id < 1
        ):
            raise TypeError("run_id must be a positive integer")

    def to_dict(self) -> dict[str, str | int]:
        """Return a JSON-safe run identity."""
        return {"trainer_id": self.trainer_id, "run_id": self.run_id}


class PostTrainingSaliencyPhase(str, Enum):
    """Observable phases of one automatic post-training saliency job."""

    IDLE = "idle"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        """Return whether this phase cannot transition again."""
        return self in {
            PostTrainingSaliencyPhase.SUCCEEDED,
            PostTrainingSaliencyPhase.FAILED,
            PostTrainingSaliencyPhase.CANCELLED,
        }


class PostTrainingSaliencyScheduleDisposition(str, Enum):
    """Result category for one automatic saliency scheduling request."""

    SCHEDULED = "scheduled"
    REJECTED = "rejected"
    STALE = "stale"


class PostTrainingSaliencyScheduleReason(str, Enum):
    """Stable reason codes for automatic saliency scheduling outcomes."""

    SCHEDULED = "scheduled"
    TRAINER_UNAVAILABLE = "trainer_unavailable"
    UNSUPPORTED_PROFILE = "unsupported_profile"
    TRAINING_NOT_COMPLETED = "training_not_completed"
    TRAINING_RUN_CHANGED = "training_run_changed"
    TRAINING_STATE_UNAVAILABLE = "training_state_unavailable"
    TRAINING_STATE_UNSTABLE = "training_state_unstable"
    FINISHED_RUN_COUNT_CHANGED = "finished_run_count_changed"
    NO_NEW_FINISHED_RUNS = "no_new_finished_runs"
    NO_FINISHED_RECORDS = "no_finished_records"
    PLAN_PREPARATION_FAILED = "plan_preparation_failed"
    TRAINING_GENERATION_CHANGED = "training_generation_changed"
    REQUEST_SUPERSEDED = "request_superseded"
    PREVIOUS_JOB_NOT_CANCELLED = "previous_job_not_cancelled"
    TRAINER_REPLACED = "trainer_replaced"
    THREAD_START_FAILED = "thread_start_failed"


_ALLOWED_POST_TRAINING_SALIENCY_TRANSITIONS = {
    PostTrainingSaliencyPhase.PENDING: frozenset(
        {
            PostTrainingSaliencyPhase.RUNNING,
            PostTrainingSaliencyPhase.FAILED,
            PostTrainingSaliencyPhase.CANCELLED,
        }
    ),
    PostTrainingSaliencyPhase.RUNNING: frozenset(
        {
            PostTrainingSaliencyPhase.SUCCEEDED,
            PostTrainingSaliencyPhase.FAILED,
            PostTrainingSaliencyPhase.CANCELLED,
        }
    ),
}


@dataclass(frozen=True, slots=True)
class PostTrainingSaliencyStatus:
    """Immutable, generation-bound status for automatic saliency computation."""

    phase: PostTrainingSaliencyPhase
    generation: int
    run: TrainingRunIdentity | None
    training_generation: int | None
    methods: tuple[str, ...]
    error_code: str | None = None
    message: str | None = None
    diagnostic_type: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.phase, PostTrainingSaliencyPhase):
            raise TypeError("saliency phase must be a PostTrainingSaliencyPhase")
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise TypeError("saliency generation must be a non-negative integer")
        if self.run is not None and not isinstance(self.run, TrainingRunIdentity):
            raise TypeError("saliency run must be a TrainingRunIdentity")
        if self.training_generation is not None and (
            isinstance(self.training_generation, bool)
            or not isinstance(self.training_generation, int)
            or self.training_generation < 0
        ):
            raise TypeError(
                "saliency training generation must be a non-negative integer"
            )
        if not isinstance(self.methods, tuple) or any(
            not isinstance(method, str) or not method.strip() for method in self.methods
        ):
            raise TypeError("saliency methods must be a tuple of non-empty strings")
        for field_name, value in (
            ("error_code", self.error_code),
            ("message", self.message),
            ("diagnostic_type", self.diagnostic_type),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise TypeError(f"{field_name} must be a non-empty string or None")
        if self.phase is PostTrainingSaliencyPhase.IDLE:
            if self.run is not None or self.training_generation is not None:
                raise ValueError("idle saliency status cannot identify a training run")
        elif self.run is None:
            raise ValueError("non-idle saliency status requires a training run")
        elif (
            self.phase
            in {
                PostTrainingSaliencyPhase.PENDING,
                PostTrainingSaliencyPhase.RUNNING,
                PostTrainingSaliencyPhase.SUCCEEDED,
            }
            and self.training_generation is None
        ):
            raise ValueError("active saliency status requires a training generation")
        if self.phase is PostTrainingSaliencyPhase.FAILED:
            if self.error_code is None or self.message is None:
                raise ValueError("failed saliency status requires a safe error")
        elif self.error_code is not None or self.diagnostic_type is not None:
            raise ValueError(
                "only failed saliency status can contain error diagnostics"
            )

    @classmethod
    def idle(cls, *, generation: int = 0) -> PostTrainingSaliencyStatus:
        """Return the status before any automatic job is scheduled."""
        return cls(
            phase=PostTrainingSaliencyPhase.IDLE,
            generation=generation,
            run=None,
            training_generation=None,
            methods=(),
        )

    @classmethod
    def pending(
        cls,
        *,
        generation: int,
        run: TrainingRunIdentity,
        training_generation: int,
        methods: tuple[str, ...],
    ) -> PostTrainingSaliencyStatus:
        """Start one generation after scheduling preconditions are captured."""
        return cls(
            phase=PostTrainingSaliencyPhase.PENDING,
            generation=generation,
            run=run,
            training_generation=training_generation,
            methods=methods,
            message="Saliency is waiting to start.",
        )

    def transition(
        self,
        *,
        generation: int,
        phase: PostTrainingSaliencyPhase,
        error_code: str | None = None,
        message: str | None = None,
        diagnostic_type: str | None = None,
    ) -> PostTrainingSaliencyStatus:
        """Compare-and-transition; stale generations are harmless no-ops."""
        if generation != self.generation:
            return self
        allowed = _ALLOWED_POST_TRAINING_SALIENCY_TRANSITIONS.get(
            self.phase,
            frozenset(),
        )
        if phase not in allowed:
            raise ValueError(
                "invalid post-training saliency transition: "
                f"{self.phase.value} -> {phase.value}"
            )
        return replace(
            self,
            phase=phase,
            error_code=error_code,
            message=message,
            diagnostic_type=diagnostic_type,
        )

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe lifecycle diagnostics."""
        return {
            "phase": self.phase.value,
            "generation": self.generation,
            "run": self.run.to_dict() if self.run is not None else None,
            "training_generation": self.training_generation,
            "methods": list(self.methods),
            "error_code": self.error_code,
            "message": self.message,
            "diagnostic_type": self.diagnostic_type,
        }


@dataclass(frozen=True, slots=True)
class PostTrainingSaliencyScheduleOutcome:
    """Typed acknowledgement for one automatic saliency scheduling request."""

    disposition: PostTrainingSaliencyScheduleDisposition
    reason: PostTrainingSaliencyScheduleReason
    message: str
    status: PostTrainingSaliencyStatus

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, PostTrainingSaliencyScheduleDisposition):
            raise TypeError("saliency schedule disposition is invalid")
        if not isinstance(self.reason, PostTrainingSaliencyScheduleReason):
            raise TypeError("saliency schedule reason is invalid")
        if not isinstance(self.message, str) or not self.message.strip():
            raise TypeError("saliency schedule message must be a non-empty string")
        if not isinstance(self.status, PostTrainingSaliencyStatus):
            raise TypeError("saliency schedule status is invalid")
        if self.status.message != self.message:
            raise ValueError("saliency schedule outcome and status messages must match")

        expected_phase = {
            PostTrainingSaliencyScheduleDisposition.SCHEDULED: (
                PostTrainingSaliencyPhase.PENDING
            ),
            PostTrainingSaliencyScheduleDisposition.REJECTED: (
                PostTrainingSaliencyPhase.FAILED
            ),
            PostTrainingSaliencyScheduleDisposition.STALE: (
                PostTrainingSaliencyPhase.CANCELLED
            ),
        }[self.disposition]
        if self.status.phase is not expected_phase:
            raise ValueError(
                "saliency schedule disposition does not match lifecycle phase"
            )
        if self.disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED:
            if self.reason is not PostTrainingSaliencyScheduleReason.SCHEDULED:
                raise ValueError("scheduled saliency outcome requires scheduled reason")
        elif self.reason is PostTrainingSaliencyScheduleReason.SCHEDULED:
            raise ValueError("terminal saliency outcome requires a rejection reason")
        if (
            self.disposition is PostTrainingSaliencyScheduleDisposition.REJECTED
            and self.status.error_code != self.reason.value
        ):
            raise ValueError("rejected saliency status must publish its reason code")

    @property
    def scheduled(self) -> bool:
        """Return whether a background job was accepted and started."""
        return self.disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe command diagnostics."""
        return {
            "disposition": self.disposition.value,
            "reason": self.reason.value,
            "message": self.message,
            "status": self.status.to_dict(),
        }


@dataclass(frozen=True)
class TrainingTerminalOutcome:
    """Verified lifecycle outcome for the current or most recent run."""

    state: TrainingOutcomeState
    run: TrainingRunIdentity | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, TrainingOutcomeState):
            raise TypeError("training outcome state must be a TrainingOutcomeState")
        if self.run is not None and not isinstance(self.run, TrainingRunIdentity):
            raise TypeError("training outcome run must be a TrainingRunIdentity")
        if self.detail is not None and not isinstance(self.detail, str):
            raise TypeError("training outcome detail must be a string")

    @property
    def is_terminal(self) -> bool:
        """Return whether no worker transition remains for this run."""
        return self.state in {
            TrainingOutcomeState.COMPLETED,
            TrainingOutcomeState.FAILED,
            TrainingOutcomeState.CANCELLED,
        }

    @property
    def is_quiescent(self) -> bool:
        """Return whether pipeline replacement can safely retire this trainer."""
        return self.state is TrainingOutcomeState.NOT_STARTED or self.is_terminal

    @property
    def successful(self) -> bool:
        """Return whether this run reached verified completion."""
        return self.state is TrainingOutcomeState.COMPLETED

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe diagnostics for command consumers."""
        return {
            "state": self.state.value,
            "run": self.run.to_dict() if self.run is not None else None,
            "detail": self.detail,
        }


def read_training_terminal_outcome(source: object | None) -> TrainingTerminalOutcome:
    """Read the typed contract from a trainer/adapter and fail closed to unknown."""
    getter = getattr(source, "get_terminal_outcome", None)
    if not callable(getter):
        return TrainingTerminalOutcome(
            state=TrainingOutcomeState.UNKNOWN,
            detail="Typed training outcome is unavailable.",
        )
    try:
        outcome = getter()
    except Exception as exc:
        return TrainingTerminalOutcome(
            state=TrainingOutcomeState.UNKNOWN,
            detail=str(exc) or exc.__class__.__name__,
        )
    if not isinstance(outcome, TrainingTerminalOutcome):
        return TrainingTerminalOutcome(
            state=TrainingOutcomeState.UNKNOWN,
            detail="Training backend returned an invalid typed outcome.",
        )
    return outcome


@dataclass(frozen=True)
class TrainingStateToken:
    """One generation of training state and whether it is safe to read."""

    generation: int
    stable: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise TypeError("training state generation must be a non-negative integer")
        if not isinstance(self.stable, bool):
            raise TypeError("training state stability must be a boolean")


@dataclass(frozen=True, slots=True)
class TrainingLifecycleEvent:
    """Generation-bound training truth shared across backend boundaries."""

    token: TrainingStateToken
    outcome: TrainingTerminalOutcome
    publication_generation: int | None = None
    publication_revision: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.token, TrainingStateToken):
            raise TypeError("training lifecycle token is invalid")
        if not isinstance(self.outcome, TrainingTerminalOutcome):
            raise TypeError("training lifecycle outcome is invalid")
        generation = self.publication_generation
        if generation is not None and (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
        ):
            raise TypeError(
                "training lifecycle publication generation must be positive"
            )
        revision = self.publication_revision
        if revision is not None and (
            isinstance(revision, bool) or not isinstance(revision, int) or revision < 1
        ):
            raise TypeError("training lifecycle publication revision must be positive")


@dataclass(frozen=True)
class TrainingReadBoundary:
    """Trainer identity plus generation for one object-bearing read boundary."""

    trainer_identity: str | None
    token: TrainingStateToken

    @classmethod
    def no_trainer(cls) -> TrainingReadBoundary:
        """Return the stable read boundary before any trainer exists."""
        return cls(
            trainer_identity=None,
            token=TrainingStateToken(generation=0, stable=True),
        )

    def __post_init__(self) -> None:
        if self.trainer_identity is not None and (
            not isinstance(self.trainer_identity, str)
            or not self.trainer_identity.strip()
        ):
            raise TypeError("trainer identity must be a non-empty string or None")
        if not isinstance(self.token, TrainingStateToken):
            raise TypeError("training read boundary token is invalid")

    @property
    def stable(self) -> bool:
        """Return whether the captured trainer generation is readable."""
        return self.token.stable


@dataclass(frozen=True, slots=True)
class TrainingPipelineMutationBoundary:
    """Training and saliency truth captured before a pipeline mutation."""

    read_boundary: TrainingReadBoundary
    terminal_outcome: TrainingTerminalOutcome
    saliency_status: PostTrainingSaliencyStatus
    saliency_work_active: bool
    training_work_active: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.read_boundary, TrainingReadBoundary):
            raise TypeError("read_boundary must be a TrainingReadBoundary")
        if not isinstance(self.terminal_outcome, TrainingTerminalOutcome):
            raise TypeError("terminal_outcome must be a TrainingTerminalOutcome")
        if not isinstance(self.saliency_status, PostTrainingSaliencyStatus):
            raise TypeError("saliency_status must be a PostTrainingSaliencyStatus")
        if not isinstance(self.saliency_work_active, bool):
            raise TypeError("saliency_work_active must be a boolean")
        if not isinstance(self.training_work_active, bool):
            raise TypeError("training_work_active must be a boolean")


class TrainingStateTokenProvider(Protocol):
    """Runtime objects visible to state snapshots must implement this contract."""

    def get_state_snapshot_token(self) -> TrainingStateToken:
        """Return the current training-state generation and stability."""
        ...

    def get_state_snapshot_identity(self) -> str:
        """Return the stable identity shared by every token from this trainer."""
        ...
