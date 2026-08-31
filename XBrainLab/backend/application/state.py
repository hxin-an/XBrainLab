"""Serializable state snapshots for the backend application service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingTerminalOutcome,
)

if TYPE_CHECKING:
    from .training_recommendation import TrainingRecommendation

from .serialization import serialize_json_value


@dataclass(frozen=True)
class RawStateSnapshot:
    """Snapshot of loaded raw data."""

    loaded: bool = False
    count: int = 0
    files: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    metadata: list[dict[str, str]] = field(default_factory=list)
    event_total: int = 0
    unique_events: list[str] = field(default_factory=list)
    locked: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreprocessedStateSnapshot:
    """Snapshot of preprocessed data."""

    available: bool = False
    count: int = 0
    files: list[str] = field(default_factory=list)
    is_epoched: bool = False
    channel_names: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EpochStateSnapshot:
    """Snapshot of generated epoch data."""

    available: bool = False
    exists: bool = False
    epoch_count: int | None = None
    n_channels: int | None = None
    n_times: int | None = None
    sfreq: float | None = None
    event_names: list[str] = field(default_factory=list)
    event_ids: dict[str, int] | None = None
    channel_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ElectrodeLayoutStateSnapshot:
    """Shared, identity-preserving electrode-layout publication."""

    source: str | None = None
    status: str = "not_configured"
    positioned_channel_count: int = 0
    channel_count: int = 0
    coordinate_summary: str | None = None
    name: str | None = None
    bids_restore_available: bool = False
    channel_names: list[str] = field(default_factory=list)
    electrode_names: list[str] = field(default_factory=list)


class DatasetSplitLifecycle(str, Enum):
    """Authoritative lifecycle for one saved dataset split specification."""

    UNCONFIGURED = "unconfigured"
    SAVED = "saved"
    MATERIALIZING = "materializing"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass(frozen=True)
class DatasetStateSnapshot:
    """Snapshot of saved split intent and generated training datasets."""

    available: bool = False
    count: int = 0
    names: list[str] = field(default_factory=list)
    locked: bool = False
    generator_exists: bool = False
    split_spec_saved: bool = False
    split_specification: dict[str, Any] = field(default_factory=dict)
    split_specification_fingerprint: str | None = None
    split_epoch_revision: int | None = None
    split_preview_summary: dict[str, Any] = field(default_factory=dict)
    split_lifecycle: DatasetSplitLifecycle = DatasetSplitLifecycle.UNCONFIGURED
    split_materialized: bool = False
    active_split_summary: dict[str, Any] = field(default_factory=dict)
    last_split_attempt: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingStateSnapshot:
    """Snapshot of model/training configuration and runtime status."""

    has_model: bool = False
    model_name: str | None = None
    model_params: dict[str, Any] = field(default_factory=dict)
    has_training_option: bool = False
    training_option: dict[str, Any] = field(default_factory=dict)
    recommendation: TrainingRecommendation | None = None
    has_trainer: bool = False
    is_running: bool = False
    plan_count: int = 0
    run_count: int = 0
    finished_run_count: int = 0
    read_generation: int = 0
    progress_message: str | None = None
    terminal_outcome: TrainingTerminalOutcome = field(
        default_factory=lambda: TrainingTerminalOutcome(
            state=TrainingOutcomeState.UNKNOWN,
        )
    )
    missing_requirements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationStateSnapshot:
    """Snapshot of training/evaluation run counts."""

    available: bool = False
    total_plans: int = 0
    total_runs: int = 0
    finished_runs: int = 0
    metrics_available: bool = False


@dataclass(frozen=True)
class SaliencyClassCoverageSnapshot:
    """Availability of one renderable saliency method/class combination."""

    class_index: int
    display_name: str
    event_code: Any | None = None
    store_key: Any | None = None
    available: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class SaliencyMethodCoverageSnapshot:
    """Per-class coverage for one saliency method in one finished run."""

    method: str
    available: bool = False
    complete: bool = False
    classes: list[SaliencyClassCoverageSnapshot] = field(default_factory=list)


@dataclass(frozen=True)
class SaliencyRunCoverageSnapshot:
    """Structured saliency coverage for one plan/run evaluation record."""

    plan_index: int
    run_index: int
    plan_name: str = ""
    model_name: str = ""
    run_name: str = ""
    methods: list[SaliencyMethodCoverageSnapshot] = field(default_factory=list)


@dataclass(frozen=True)
class VisualizationStateSnapshot:
    """Snapshot of visualization readiness."""

    saliency_configured: bool = False
    saliency_available: bool = False
    montage_available: bool = False
    channel_positions_available: bool = False
    three_dimensional_positions_available: bool = False
    channel_count: int = 0
    saliency_params: dict[str, Any] = field(default_factory=dict)
    montage_channels: list[str] = field(default_factory=list)
    montage_positions: list[list[float]] = field(default_factory=list)
    montage_source: str | None = None
    montage_preparation_state: str = "not_applicable"
    montage_preparation_reason: str | None = None
    saliency_coverage: list[SaliencyRunCoverageSnapshot] = field(
        default_factory=list,
    )
    post_training_saliency: PostTrainingSaliencyStatus = field(
        default_factory=PostTrainingSaliencyStatus.idle,
    )


@dataclass(frozen=True)
class InterpretationStateSnapshot:
    """Snapshot of Data Interpretation lifecycle state."""

    has_scan_result: bool = False
    has_candidate: bool = False
    has_preview: bool = False
    has_validation_decision: bool = False
    has_applied_interpretation: bool = False
    has_pending_candidate: bool = False
    has_recipe: bool = False
    latest_scan_id: str | None = None
    latest_candidate_id: str | None = None
    latest_preview_id: str | None = None
    latest_interpretation_id: str | None = None
    latest_recipe_id: str | None = None
    source_path: str | None = None
    source_kind: str | None = None
    label_sources: list[str] = field(default_factory=list)
    validation_decision: str | None = None
    pending_confirmation: bool = False
    blocked_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    action_items: list[dict[str, str]] = field(default_factory=list)
    summary: str | None = None
    metadata_preview: list[dict[str, Any]] = field(default_factory=list)
    label_carriers: list[str] = field(default_factory=list)
    bids: dict[str, Any] = field(default_factory=dict)
    label_carrier_plan: list[dict[str, Any]] = field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = field(default_factory=list)
    event_roles: dict[str, str] = field(default_factory=dict)
    class_map: dict[str, str] = field(default_factory=dict)
    run_event_mappings: dict[str, dict[str, str]] = field(default_factory=dict)
    epoch_handoff: dict[str, Any] = field(default_factory=dict)
    label_import_count: int = 0
    label_imports: list[dict[str, Any]] = field(default_factory=list)
    recipe_path: str | None = None


@dataclass(frozen=True)
class ActiveDatasetSnapshot:
    """Compact active-dataset view for command policy decisions."""

    has_raw_data: bool = False
    has_preprocessed_data: bool = False
    has_epoch_data: bool = False
    has_datasets: bool = False
    has_saved_split: bool = False
    is_locked: bool = False


@dataclass(frozen=True)
class ActiveTrainingSnapshot:
    """Compact active-training view for command policy decisions."""

    has_model: bool = False
    has_training_option: bool = False
    has_trainer: bool = False
    is_running: bool = False
    finished_run_count: int = 0


@dataclass(frozen=True)
class ErrorSnapshot:
    """Last application-level error, if any."""

    error_type: str | None = None
    message: str | None = None
    recoverable: bool = True


@dataclass(frozen=True)
class ApplicationStateSnapshot:
    """Full serializable application state."""

    pipeline_stage: str
    raw: RawStateSnapshot
    preprocessed: PreprocessedStateSnapshot
    epoch: EpochStateSnapshot
    dataset: DatasetStateSnapshot
    training: TrainingStateSnapshot
    evaluation: EvaluationStateSnapshot
    visualization: VisualizationStateSnapshot
    interpretation: InterpretationStateSnapshot
    active_dataset: ActiveDatasetSnapshot
    active_training: ActiveTrainingSnapshot
    electrode_layout: ElectrodeLayoutStateSnapshot = field(
        default_factory=ElectrodeLayoutStateSnapshot
    )
    last_error: ErrorSnapshot | None = None
    state_reliable: bool = True
    training_liveness_reliable: bool = True
    read_errors: list[str] = field(default_factory=list)

    @classmethod
    def empty(
        cls,
        *,
        last_error: ErrorSnapshot | None = None,
        read_errors: list[str] | None = None,
    ) -> ApplicationStateSnapshot:
        """Return a safe empty snapshot when live state cannot be acquired."""
        errors = list(read_errors or [])
        return cls(
            pipeline_stage="unavailable" if errors else "empty",
            raw=RawStateSnapshot(locked=bool(errors)),
            preprocessed=PreprocessedStateSnapshot(),
            epoch=EpochStateSnapshot(),
            dataset=DatasetStateSnapshot(locked=bool(errors)),
            training=TrainingStateSnapshot(is_running=bool(errors)),
            evaluation=EvaluationStateSnapshot(),
            visualization=VisualizationStateSnapshot(),
            interpretation=InterpretationStateSnapshot(),
            active_dataset=ActiveDatasetSnapshot(is_locked=bool(errors)),
            active_training=ActiveTrainingSnapshot(is_running=bool(errors)),
            last_error=last_error,
            state_reliable=not errors,
            training_liveness_reliable=not errors,
            read_errors=errors,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return serialize_json_value(self)
