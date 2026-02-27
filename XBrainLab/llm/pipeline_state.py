"""Pipeline state machine for stage-based agent prompting.

Defines the :class:`PipelineStage` enum and :data:`STAGE_CONFIG` mapping
that drive which tools and system-prompt context the LLM agent receives
at each stage of the EEG analysis pipeline.

The stage is computed from the ``Study`` object (see
:func:`compute_pipeline_stage`) — it is **never** stored or manually
advanced, so it cannot drift from the actual application state.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class PipelineStage(Enum):
    """Stages of the EEG analysis pipeline.

    The pipeline follows a linear progression with a training loop::

        EMPTY → DATA_LOADED → PREPROCESSED → DATASET_READY ⇄ TRAINED
                                                   ↕
                                                TRAINING

    ``clear_dataset`` resets any stage back to ``EMPTY``.
    """

    EMPTY = "empty"
    DATA_LOADED = "data_loaded"
    PREPROCESSED = "preprocessed"
    DATASET_READY = "dataset_ready"
    TRAINING = "training"
    TRAINED = "trained"

    @property
    def label(self) -> str:
        """Human-friendly display name for prompt usage."""
        return {
            PipelineStage.EMPTY: "Empty (No Data)",
            PipelineStage.DATA_LOADED: "Data Loaded",
            PipelineStage.PREPROCESSED: "Preprocessed",
            PipelineStage.DATASET_READY: "Dataset Ready",
            PipelineStage.TRAINING: "Training In Progress",
            PipelineStage.TRAINED: "Trained",
        }[self]


def compute_pipeline_stage(study: Any) -> PipelineStage:
    """Derive the current pipeline stage from *study* state.

    The check order matters — more advanced stages are tested first so
    that the most specific match wins (e.g. ``TRAINING`` before
    ``TRAINED``).

    Args:
        study: The global ``Study`` instance.

    Returns:
        The current :class:`PipelineStage`.

    """
    # Training in progress — highest-priority lock
    if (
        study.trainer is not None
        and hasattr(study.trainer, "is_running")
        and study.trainer.is_running()
    ):
        return PipelineStage.TRAINING

    # Trainer exists but not running → training completed
    if study.trainer is not None:
        return PipelineStage.TRAINED

    # Datasets generated → ready to configure & train
    if study.datasets:
        return PipelineStage.DATASET_READY

    # Epoch data exists → preprocessing done
    if study.epoch_data is not None:
        return PipelineStage.PREPROCESSED

    # Raw data loaded
    if study.loaded_data_list:
        return PipelineStage.DATA_LOADED

    return PipelineStage.EMPTY


# ---------------------------------------------------------------------------
# Tools allowed per stage
# ---------------------------------------------------------------------------

_PREPROCESS_TOOLS: list[str] = [
    "apply_standard_preprocess",
    "apply_bandpass_filter",
    "apply_notch_filter",
    "resample_data",
    "normalize_data",
    "set_reference",
    "select_channels",
    "set_montage",
    "epoch_data",
]

_TRAINING_TOOLS: list[str] = [
    "set_model",
    "configure_training",
    "start_training",
]

_COMMON_READONLY: list[str] = [
    "get_dataset_info",
    "switch_panel",
]


# ---------------------------------------------------------------------------
# Stage configuration — tools + prompt guidance
# ---------------------------------------------------------------------------

STAGE_CONFIG: dict[PipelineStage, dict[str, Any]] = {
    PipelineStage.EMPTY: {
        "tools": [
            "list_files",
            "load_data",
            "switch_panel",
        ],
        "guidance": (
            "No data is loaded yet. "
            "Guide the user to select EEG files and load them. "
            "Ask which folder their .gdf / .edf / .set files are in."
        ),
    },
    PipelineStage.DATA_LOADED: {
        "tools": [
            *_PREPROCESS_TOOLS,
            "attach_labels",
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "guidance": (
            "EEG data has been loaded. "
            "The next step is preprocessing. "
            "Recommend 'apply_standard_preprocess' for a one-step pipeline, "
            "or guide the user through individual steps (bandpass → notch → "
            "rereference → normalize → epoch)."
        ),
    },
    PipelineStage.PREPROCESSED: {
        "tools": [
            *_PREPROCESS_TOOLS,
            "attach_labels",
            "generate_dataset",
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "guidance": (
            "Preprocessing is complete and epoch data is ready. "
            "The next step is to generate a training/test dataset with "
            "'generate_dataset'. "
            "The user may also re-run preprocessing steps if adjustments "
            "are needed."
        ),
    },
    PipelineStage.DATASET_READY: {
        "tools": [
            *_TRAINING_TOOLS,
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "guidance": (
            "Datasets have been generated. "
            "Guide the user to select a model (EEGNet / SCCNet / "
            "ShallowConvNet), configure training parameters, and start "
            "training. "
            "If the user wants to redo preprocessing, they must first "
            "'clear_dataset' to go back."
        ),
    },
    PipelineStage.TRAINING: {
        "tools": [
            "switch_panel",
        ],
        "guidance": (
            "Training is currently in progress. "
            "The user can switch to the Training panel to monitor progress. "
            "No data-modifying operations are available until training "
            "finishes."
        ),
    },
    PipelineStage.TRAINED: {
        "tools": [
            *_TRAINING_TOOLS,
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "guidance": (
            "Training has completed. "
            "The user can view results or saliency maps via 'switch_panel' "
            "to the Evaluation or Visualization panel. "
            "They may also adjust model/training parameters and re-train, "
            "or 'clear_dataset' to start over."
        ),
    },
}
