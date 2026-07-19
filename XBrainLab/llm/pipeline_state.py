"""Pipeline state machine for stage-based agent prompting.

Consumes the backend :class:`PipelineStage` read-model contract and defines the
:data:`STAGE_CONFIG` mapping that drives stage-specific assistant guidance.

For real product sessions, the stage is derived only from the ApplicationService
state snapshot so tool prompts, capability policy, and command execution share
one backend truth. Mock / legacy callers may still fall back to direct
Study-shaped reads for compatibility tests.
"""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application.pipeline_stage import (
    PipelineStage,
    compute_pipeline_stage,
)

__all__ = ["STAGE_CONFIG", "PipelineStage", "compute_pipeline_stage"]


# ---------------------------------------------------------------------------
# Tools allowed per stage
# ---------------------------------------------------------------------------

_PREPROCESS_TOOLS: list[str] = [
    "apply_standard_preprocess",
    "reset_preprocess",
    "apply_bandpass_filter",
    "apply_notch_filter",
    "resample_data",
    "normalize_data",
    "set_reference",
    "select_channels",
    "set_montage",
    "epoch_data",
]

_DATA_INTERPRETATION_TOOLS: list[str] = [
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
    "apply_interpretation",
    "save_interpretation_recipe",
    "reload_interpretation_recipe",
]

_TRAINING_TOOLS: list[str] = [
    "set_model",
    "configure_training",
    "start_training",
]

_ANALYSIS_TOOLS: list[str] = [
    "evaluate",
    "visualize",
    "saliency",
]


def _stage_system_prompt(
    *,
    role: str,
    stage: str,
    status: str,
    boundary: str,
) -> str:
    """Build concise stage context without publishing a second tool policy."""
    return (
        f"You are XBrainLab Assistant, an {role}.\n\n"
        f"## Current Stage: {stage}\n"
        f"{status}\n"
        f"{boundary}\n\n"
        "The request-scoped action contracts below are authoritative. Use only "
        "an action contract listed for this exact turn. Do not infer permission "
        "from the stage description, prior chat, examples, or a recommended "
        "next step. Never replace the user's request with a prerequisite or "
        "substitute action."
    )


# ---------------------------------------------------------------------------
# Stage configuration — tools + system prompt
# ---------------------------------------------------------------------------

STAGE_CONFIG: dict[PipelineStage, dict[str, Any]] = {
    PipelineStage.EMPTY: {
        "tools": [
            "list_files",
            *_DATA_INTERPRETATION_TOOLS,
            "switch_panel",
        ],
        "system_prompt": _stage_system_prompt(
            role="EEG data import guide",
            stage="Empty (No Data)",
            status=(
                "No data is loaded. The workflow is ready to begin Data Interpretation."
            ),
            boundary=(
                "A concrete source path is required before XBrainLab can inspect "
                "an EEG recording or dataset."
            ),
        ),
    },
    PipelineStage.DATA_LOADED: {
        "tools": [
            *_DATA_INTERPRETATION_TOOLS,
            *_PREPROCESS_TOOLS,
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "system_prompt": _stage_system_prompt(
            role="EEG preprocessing guide",
            stage="Data Loaded",
            status="Raw EEG data is available, but preprocessing is not complete.",
            boundary=(
                "Preprocessing must complete before epoching and training dataset "
                "construction."
            ),
        ),
    },
    PipelineStage.PREPROCESSED: {
        "tools": [
            *_DATA_INTERPRETATION_TOOLS,
            *_PREPROCESS_TOOLS,
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "system_prompt": _stage_system_prompt(
            role="EEG epoching guide",
            stage="Preprocessed",
            status="Preprocessing is complete. The workflow is Ready for epoching.",
            boundary=(
                "Epoch creation requires a target event and epoch window before "
                "a training dataset can be built."
            ),
        ),
    },
    PipelineStage.EPOCH_READY: {
        "tools": [
            *_DATA_INTERPRETATION_TOOLS,
            "reset_preprocess",
            "generate_dataset",
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "system_prompt": _stage_system_prompt(
            role="EEG dataset generation guide",
            stage="Epochs Ready",
            status="Preprocessed epoch data is available.",
            boundary=(
                "A split strategy and dataset settings are required before model "
                "training can be configured."
            ),
        ),
    },
    PipelineStage.DATASET_READY: {
        "tools": [
            *_DATA_INTERPRETATION_TOOLS,
            "reset_preprocess",
            *_TRAINING_TOOLS,
            *_ANALYSIS_TOOLS,
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "system_prompt": _stage_system_prompt(
            role="EEG model training guide",
            stage="Dataset Ready",
            status="The training dataset is ready.",
            boundary=(
                "A model and training settings must be resolved before a run can "
                "start, and starting training may require confirmation."
            ),
        ),
    },
    PipelineStage.TRAINING: {
        "tools": [
            "stop_training",
            "switch_panel",
        ],
        "system_prompt": _stage_system_prompt(
            role="EEG training monitor",
            stage="Training In Progress",
            status="A training job is currently running in the background.",
            boundary=(
                "Do not start another run or mutate its data and settings while "
                "the active job is running."
            ),
        ),
    },
    PipelineStage.TRAINED: {
        "tools": [
            *_DATA_INTERPRETATION_TOOLS,
            "reset_preprocess",
            *_TRAINING_TOOLS,
            *_ANALYSIS_TOOLS,
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "system_prompt": _stage_system_prompt(
            role="EEG results & iteration guide",
            stage="Trained",
            status="At least one training run has completed.",
            boundary=(
                "Completed training results can be reviewed; retraining or "
                "resetting derived state remains a separate explicit action."
            ),
        ),
    },
}
