"""Serializable state snapshots for the backend application service."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, cast


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
    event_names: list[str] = field(default_factory=list)
    event_ids: dict[str, int] | None = None
    channel_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DatasetStateSnapshot:
    """Snapshot of generated training datasets."""

    available: bool = False
    count: int = 0
    names: list[str] = field(default_factory=list)
    locked: bool = False
    generator_exists: bool = False
    split_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingStateSnapshot:
    """Snapshot of model/training configuration and runtime status."""

    has_model: bool = False
    model_name: str | None = None
    has_training_option: bool = False
    training_option: dict[str, Any] = field(default_factory=dict)
    has_trainer: bool = False
    is_running: bool = False
    plan_count: int = 0
    run_count: int = 0
    finished_run_count: int = 0
    progress_message: str | None = None
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
class VisualizationStateSnapshot:
    """Snapshot of visualization readiness."""

    saliency_configured: bool = False
    saliency_available: bool = False
    montage_available: bool = False
    channel_positions_available: bool = False
    channel_count: int = 0


@dataclass(frozen=True)
class InterpretationStateSnapshot:
    """Snapshot of Data Interpretation lifecycle state."""

    has_scan_result: bool = False
    has_candidate: bool = False
    has_preview: bool = False
    has_validation_decision: bool = False
    has_applied_interpretation: bool = False
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
    label_carrier_plan: list[dict[str, Any]] = field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = field(default_factory=list)
    event_roles: dict[str, str] = field(default_factory=dict)
    class_map: dict[str, str] = field(default_factory=dict)
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
    is_locked: bool = False


@dataclass(frozen=True)
class ActiveTrainingSnapshot:
    """Compact active-training view for command policy decisions."""

    has_model: bool = False
    has_training_option: bool = False
    has_trainer: bool = False
    is_running: bool = False


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
    last_error: ErrorSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return _serialize(self)


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: _serialize(v) for k, v in asdict(cast(Any, value)).items()}
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value
