"""Stage-to-tool configuration for Assistant prompt assembly.

Consumes the backend :class:`PipelineStage` read-model contract and defines the
:data:`STAGE_CONFIG` tool mapping consumed by Assistant prompt assembly.

The stage is read only from an explicit ApplicationService state publication so
tool prompts, capability policy, and command execution share one backend truth.
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
    "apply_bandpass_filter",
    "apply_notch_filter",
    "resample_data",
    "set_reference",
    "normalize_data",
]

_SETUP_TOOLS: list[str] = [
    "configure_dataset_split",
    "select_model",
    "configure_training",
]


# ---------------------------------------------------------------------------
# Stage configuration — tools
# ---------------------------------------------------------------------------

STAGE_CONFIG: dict[PipelineStage, dict[str, Any]] = {
    PipelineStage.EMPTY: {
        "tools": [
            "import_eeg_data",
            "switch_panel",
        ],
    },
    PipelineStage.DATA_LOADED: {
        "tools": [
            "select_channels",
            "set_montage",
            *_PREPROCESS_TOOLS,
            "create_epochs",
            "switch_panel",
        ],
    },
    PipelineStage.PREPROCESSED: {
        "tools": [
            "set_montage",
            *_PREPROCESS_TOOLS,
            "create_epochs",
            "reset_preprocessing",
            "switch_panel",
        ],
    },
    PipelineStage.EPOCH_READY: {
        "tools": [
            *_SETUP_TOOLS,
            "start_training",
            "reset_preprocessing",
            "switch_panel",
        ],
    },
    PipelineStage.DATASET_READY: {
        "tools": [
            *_SETUP_TOOLS,
            "start_training",
            "reset_preprocessing",
            "switch_panel",
        ],
    },
    PipelineStage.TRAINING: {
        "tools": [
            "stop_training",
            "switch_panel",
        ],
    },
    PipelineStage.TRAINED: {
        "tools": [
            *_SETUP_TOOLS,
            "start_training",
            "reset_preprocessing",
            "clear_training_history",
            "compute_saliency",
            "switch_panel",
        ],
    },
}
