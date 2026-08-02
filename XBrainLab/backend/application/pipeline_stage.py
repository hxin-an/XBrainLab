"""Backend-owned pipeline-stage read-model and workflow-language contract."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from XBrainLab.backend.utils.logger import logger

from .commands import CommandName
from .state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
)
from .view_publication import ApplicationViewPublication


class PipelineStage(str, Enum):
    """Stable stages exposed by the backend application read model."""

    EMPTY = "empty"
    DATA_LOADED = "data_loaded"
    PREPROCESSED = "preprocessed"
    EPOCH_READY = "epoch_ready"
    DATASET_READY = "dataset_ready"
    TRAINING = "training"
    TRAINED = "trained"

    @property
    def label(self) -> str:
        """Return the stable label used in stage-specific model prompts."""
        return pipeline_stage_contract(self).prompt_label

    @property
    def status_label(self) -> str:
        """Return the shared UI/agent status label for this stage."""
        return pipeline_stage_contract(self).status_label

    @property
    def next_command(self) -> str | None:
        """Return the default next workflow command for this stage."""
        return pipeline_stage_contract(self).next_command


@dataclass(frozen=True)
class PipelineStageContract:
    """Shared meaning of one backend-published workflow stage."""

    prompt_label: str
    status_label: str
    next_command: str | None


_PIPELINE_STAGE_CONTRACTS: dict[PipelineStage, PipelineStageContract] = {
    PipelineStage.EMPTY: PipelineStageContract(
        prompt_label="Empty (No Data)",
        status_label="No data loaded",
        next_command=CommandName.SCAN_SOURCE.value,
    ),
    PipelineStage.DATA_LOADED: PipelineStageContract(
        prompt_label="Data Loaded",
        status_label="Ready for preprocessing",
        next_command=CommandName.PREPROCESS.value,
    ),
    PipelineStage.PREPROCESSED: PipelineStageContract(
        prompt_label="Preprocessed",
        status_label="Ready for EEG epoching",
        next_command=CommandName.CREATE_EPOCH.value,
    ),
    PipelineStage.EPOCH_READY: PipelineStageContract(
        prompt_label="EEG epochs ready",
        status_label="Ready to build dataset",
        next_command=CommandName.GENERATE_DATASET.value,
    ),
    PipelineStage.DATASET_READY: PipelineStageContract(
        prompt_label="Dataset Ready",
        status_label="Dataset ready",
        next_command=CommandName.CONFIGURE_TRAINING.value,
    ),
    PipelineStage.TRAINING: PipelineStageContract(
        prompt_label="Training In Progress",
        status_label="Training running",
        next_command=None,
    ),
    PipelineStage.TRAINED: PipelineStageContract(
        prompt_label="Trained",
        status_label="Results available",
        next_command=CommandName.EVALUATE.value,
    ),
}


WORKFLOW_COMMAND_LABELS: dict[str, str] = {
    CommandName.SCAN_SOURCE.value: "Scan data source",
    CommandName.REVIEW_INTERPRETATION.value: "Review data interpretation",
    CommandName.PREVIEW_INTERPRETATION.value: "Preview data interpretation",
    CommandName.VALIDATE_INTERPRETATION.value: "Validate data interpretation",
    CommandName.APPLY_INTERPRETATION.value: "Apply data interpretation",
    CommandName.SAVE_INTERPRETATION_RECIPE.value: "Save interpretation recipe",
    CommandName.RELOAD_INTERPRETATION_RECIPE.value: "Reload interpretation recipe",
    CommandName.LOAD_DATA.value: "Import data",
    CommandName.ATTACH_LABELS.value: "Add labels to loaded data",
    CommandName.PREPROCESS.value: "Preprocess data",
    CommandName.CREATE_EPOCH.value: "Create EEG epochs",
    CommandName.GENERATE_DATASET.value: "Build training dataset",
    CommandName.CONFIGURE_TRAINING.value: "Configure training",
    CommandName.TRAIN.value: "Start training",
    CommandName.STOP_TRAINING.value: "Stop training",
    CommandName.EVALUATE.value: "Review results",
    CommandName.VISUALIZE.value: "Open visualizations",
    CommandName.SALIENCY.value: "Configure saliency analysis",
    CommandName.RESET_SESSION.value: "Reset session",
    CommandName.NEW_SESSION.value: "Start new session",
}


def pipeline_stage_contract(stage: PipelineStage | str) -> PipelineStageContract:
    """Return shared labels and default action for a known stage."""
    resolved = pipeline_stage_from_value(stage)
    if resolved is None:
        raise ValueError(f"Unknown pipeline stage: {stage!r}")
    return _PIPELINE_STAGE_CONTRACTS[resolved]


def pipeline_stage_status_label(stage: PipelineStage | str | None) -> str:
    """Translate a backend stage value into shared UI/agent status language."""
    resolved = pipeline_stage_from_value(stage)
    if resolved is not None:
        return _PIPELINE_STAGE_CONTRACTS[resolved].status_label

    raw = str(getattr(stage, "value", stage) or "").strip()
    if raw.lower().replace(" ", "_") in {"status_unavailable", "unavailable"}:
        return "Workflow status unavailable"
    return raw or _PIPELINE_STAGE_CONTRACTS[PipelineStage.EMPTY].status_label


def workflow_command_label(command_name: str | CommandName) -> str:
    """Return the shared neutral label for an application workflow command."""
    key = command_name.value if isinstance(command_name, CommandName) else command_name
    return WORKFLOW_COMMAND_LABELS.get(key, key.replace("_", " ").title())


def pipeline_stage_readiness_message(
    stage: PipelineStage | str,
    *,
    raw_count: int = 0,
) -> str:
    """Return one concise status-and-next-step sentence for product surfaces."""
    contract = pipeline_stage_contract(stage)
    status = contract.status_label
    if raw_count > 0 and pipeline_stage_from_value(stage) is not PipelineStage.EMPTY:
        noun = "file" if raw_count == 1 else "files"
        status = f"{status}: {raw_count} EEG {noun} loaded"
    if contract.next_command is None:
        return f"{status}."
    return f"{status}. Next: {workflow_command_label(contract.next_command)}."


def pipeline_stage_readiness_summary(snapshot: ApplicationStateSnapshot) -> str:
    """Summarize a published application snapshot without exposing diagnostics."""
    stage = pipeline_stage_from_snapshot(snapshot)
    if stage is None:
        return "Workflow status is available, but the current stage is unknown."
    return pipeline_stage_readiness_message(stage, raw_count=snapshot.raw.count)


def derive_pipeline_stage(
    *,
    has_raw_data: bool = False,
    has_preprocessed_data: bool = False,
    has_epoch_data: bool = False,
    has_datasets: bool = False,
    has_trainer: bool = False,
    is_training: bool = False,
    finished_run_count: int = 0,
) -> PipelineStage:
    """Derive the highest workflow stage from backend read-model facts."""
    del has_trainer  # Trainer construction is not evidence of completed results.
    if is_training:
        return PipelineStage.TRAINING
    if finished_run_count > 0:
        return PipelineStage.TRAINED
    if has_datasets:
        return PipelineStage.DATASET_READY
    if has_epoch_data:
        return PipelineStage.EPOCH_READY
    if has_preprocessed_data:
        return PipelineStage.PREPROCESSED
    if has_raw_data:
        return PipelineStage.DATA_LOADED
    return PipelineStage.EMPTY


def pipeline_stage_from_snapshots(
    active_dataset: ActiveDatasetSnapshot,
    active_training: ActiveTrainingSnapshot,
) -> PipelineStage:
    """Derive a stage from compact ApplicationService state snapshots."""
    return derive_pipeline_stage(
        has_raw_data=bool(active_dataset.has_raw_data),
        has_preprocessed_data=bool(active_dataset.has_preprocessed_data),
        has_epoch_data=bool(active_dataset.has_epoch_data),
        has_datasets=bool(active_dataset.has_datasets),
        has_trainer=bool(active_training.has_trainer),
        is_training=bool(active_training.is_running),
        finished_run_count=max(0, int(active_training.finished_run_count)),
    )


def pipeline_stage_from_snapshot(
    snapshot: ApplicationStateSnapshot,
) -> PipelineStage | None:
    """Map an application state snapshot onto the stable stage enum."""
    return pipeline_stage_from_value(getattr(snapshot, "pipeline_stage", None))


def compute_pipeline_stage(
    study: Any,
    *,
    publication: ApplicationViewPublication | None = None,
) -> PipelineStage:
    """Derive stage from an explicit publication or a compatibility double."""
    if study is None:
        return PipelineStage.EMPTY

    if _is_real_product_study(study):
        return _published_pipeline_stage(publication)

    return _legacy_study_pipeline_stage(study)


def _is_real_product_study(study: Any) -> bool:
    """Distinguish a real Study (including subclasses) from spec-based mocks."""
    from XBrainLab.backend.study import Study  # noqa: PLC0415

    return isinstance(study, Study) and issubclass(type(study), Study)


def _legacy_study_pipeline_stage(study: Any) -> PipelineStage:
    """Adapt Study-shaped compatibility doubles to the backend stage contract."""
    trainer = getattr(study, "trainer", None)
    is_running = getattr(trainer, "is_running", None)
    return derive_pipeline_stage(
        has_raw_data=bool(getattr(study, "loaded_data_list", None)),
        has_preprocessed_data=bool(
            getattr(study, "preprocessed_data_list", None),
        ),
        has_epoch_data=getattr(study, "epoch_data", None) is not None,
        has_datasets=bool(getattr(study, "datasets", None)),
        has_trainer=trainer is not None,
        is_training=bool(is_running()) if callable(is_running) else False,
        finished_run_count=_legacy_finished_run_count(trainer),
    )


def _legacy_finished_run_count(trainer: Any) -> int:
    """Read completed-run evidence from compatibility doubles only."""
    if trainer is None:
        return 0
    get_holders = getattr(trainer, "get_training_plan_holders", None)
    if not callable(get_holders):
        return 0
    try:
        holder_values = get_holders()
    except Exception:
        return 0
    if not isinstance(holder_values, Iterable) or isinstance(
        holder_values,
        (str, bytes),
    ):
        return 0
    holders = list(holder_values)

    finished = 0
    for holder in holders:
        get_runs = getattr(holder, "get_plans", None)
        if not callable(get_runs):
            continue
        try:
            run_values = get_runs()
        except Exception as exc:
            logger.debug(
                "Compatibility training holder did not expose readable runs: %s",
                exc,
            )
            continue
        if not isinstance(run_values, Iterable) or isinstance(
            run_values,
            (str, bytes),
        ):
            continue
        runs = list(run_values)
        for run in runs:
            is_finished = getattr(run, "is_finished", None)
            if not callable(is_finished):
                continue
            try:
                finished += int(bool(is_finished()))
            except Exception as exc:
                logger.debug(
                    "Compatibility training run did not expose completion state: %s",
                    exc,
                )
                continue
    return finished


def _published_pipeline_stage(
    publication: ApplicationViewPublication | None,
) -> PipelineStage:
    """Read a real Study stage only from a caller-supplied publication."""
    if not isinstance(publication, ApplicationViewPublication):
        return PipelineStage.EMPTY
    return pipeline_stage_from_snapshot(publication.state) or PipelineStage.EMPTY


def pipeline_stage_from_value(value: Any) -> PipelineStage | None:
    """Parse a serialized or enum stage value without inferring state."""
    text = getattr(value, "value", value)
    if not isinstance(text, str):
        return None
    try:
        return PipelineStage(text.strip().lower().replace(" ", "_"))
    except ValueError:
        return None
