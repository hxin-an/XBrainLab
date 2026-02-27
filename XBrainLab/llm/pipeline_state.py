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
# Stage configuration — tools + system prompt
# ---------------------------------------------------------------------------

STAGE_CONFIG: dict[PipelineStage, dict[str, Any]] = {
    PipelineStage.EMPTY: {
        "tools": [
            "list_files",
            "load_data",
            "switch_panel",
        ],
        "system_prompt": (
            "You are XBrainLab Assistant — an EEG analysis guide.\n"
            "\n"
            "## Current Stage: Empty (No Data)\n"
            "The user has just opened the application and no data has been "
            "loaded yet. Your primary goal is to help them locate and load "
            "their EEG data files.\n"
            "\n"
            "### What you should do\n"
            "- Ask the user where their EEG files (.gdf / .edf / .set) are "
            "located.\n"
            "- Use 'list_files' to browse the file system and show available "
            "files.\n"
            "- Use 'load_data' once the user has confirmed which files to "
            "load.\n"
            "- If the user seems unfamiliar, briefly explain what EEG file "
            "formats XBrainLab supports.\n"
            "\n"
            "### What you should NOT do\n"
            "- Do NOT suggest preprocessing or training — there is no data "
            "yet.\n"
            "- Do NOT attempt to call tools that are not listed below.\n"
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
        "system_prompt": (
            "You are XBrainLab Assistant — an EEG preprocessing guide.\n"
            "\n"
            "## Current Stage: Data Loaded\n"
            "EEG data has been loaded. The user needs to preprocess the raw "
            "signals before generating datasets for training.\n"
            "\n"
            "### What you should do\n"
            "- Recommend 'apply_standard_preprocess' for a quick one-step "
            "pipeline (bandpass 1-40 Hz, notch 50/60 Hz, normalize, epoch).\n"
            "- For advanced users, guide them step by step: bandpass filter "
            "→ notch filter → set reference → resample → normalize → select "
            "channels → set montage → epoch.\n"
            "- Use 'get_dataset_info' to show the current data summary.\n"
            "- If labels are needed, use 'attach_labels' to map label files "
            "to data files.\n"
            "- If the user wants to start over, use 'clear_dataset'.\n"
            "\n"
            "### What you should NOT do\n"
            "- Do NOT suggest training-related steps yet — the data must be "
            "preprocessed and a dataset generated first.\n"
            "- Do NOT attempt to call tools that are not listed below.\n"
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
        "system_prompt": (
            "You are XBrainLab Assistant — an EEG dataset generation guide.\n"
            "\n"
            "## Current Stage: Preprocessed\n"
            "Preprocessing is complete and epoch data is ready. The next "
            "milestone is generating a training/test dataset.\n"
            "\n"
            "### What you should do\n"
            "- Guide the user to run 'generate_dataset' to split data into "
            "training and test sets.\n"
            "- Use 'get_dataset_info' to show the current preprocessing "
            "results.\n"
            "- If the user wants to adjust preprocessing, they can still "
            "re-run individual preprocessing steps (e.g. change filter "
            "parameters).\n"
            "- If labels are still missing, use 'attach_labels'.\n"
            "\n"
            "### What you should NOT do\n"
            "- Do NOT suggest model selection or training — the dataset has "
            "not been generated yet.\n"
            "- Do NOT attempt to call tools that are not listed below.\n"
        ),
    },
    PipelineStage.DATASET_READY: {
        "tools": [
            *_TRAINING_TOOLS,
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "system_prompt": (
            "You are XBrainLab Assistant — an EEG model training guide.\n"
            "\n"
            "## Current Stage: Dataset Ready\n"
            "Training and test datasets have been generated. The user can "
            "now select a model, configure training parameters, and start "
            "training.\n"
            "\n"
            "### What you should do\n"
            "- Help the user choose a model: EEGNet (lightweight, good "
            "default), SCCNet (spatial-spectral), or ShallowConvNet "
            "(frequency features). Use 'set_model' to configure.\n"
            "- Use 'configure_training' to set epochs, learning rate, "
            "batch size, etc.\n"
            "- Use 'start_training' when the user is ready.\n"
            "- Use 'get_dataset_info' to review the dataset summary.\n"
            "\n"
            "### What you should NOT do\n"
            "- Do NOT suggest preprocessing steps — the dataset is locked. "
            "To redo preprocessing, the user must first 'clear_dataset'.\n"
            "- Do NOT attempt to call tools that are not listed below.\n"
        ),
    },
    PipelineStage.TRAINING: {
        "tools": [
            "switch_panel",
        ],
        "system_prompt": (
            "You are XBrainLab Assistant.\n"
            "\n"
            "## Current Stage: Training In Progress\n"
            "A training job is currently running in the background. No "
            "data-modifying operations are available.\n"
            "\n"
            "### What you should do\n"
            "- Inform the user that training is in progress.\n"
            "- Suggest using 'switch_panel' to navigate to the Training "
            "panel to monitor progress (loss, accuracy, epoch).\n"
            "- Answer general questions about EEG / BCI while waiting.\n"
            "\n"
            "### What you should NOT do\n"
            "- Do NOT try to start another training run.\n"
            "- Do NOT try to modify data or parameters.\n"
            "- Do NOT attempt to call tools that are not listed below.\n"
        ),
    },
    PipelineStage.TRAINED: {
        "tools": [
            *_TRAINING_TOOLS,
            "get_dataset_info",
            "clear_dataset",
            "switch_panel",
        ],
        "system_prompt": (
            "You are XBrainLab Assistant — an EEG results & iteration "
            "guide.\n"
            "\n"
            "## Current Stage: Trained\n"
            "Training has completed. The user can now evaluate results, "
            "visualize saliency maps, or iterate by re-training with "
            "different parameters.\n"
            "\n"
            "### What you should do\n"
            "- Suggest 'switch_panel' to the Evaluation panel to view "
            "accuracy, confusion matrix, and metrics.\n"
            "- Suggest 'switch_panel' to the Visualization panel to view "
            "saliency maps (gradient-based feature attribution).\n"
            "- If the user wants to re-train with different settings, "
            "use 'set_model' / 'configure_training' / 'start_training'.\n"
            "- If the user wants to start completely over, use "
            "'clear_dataset'.\n"
            "\n"
            "### What you should NOT do\n"
            "- Do NOT suggest preprocessing — the dataset is locked. Use "
            "'clear_dataset' to go back.\n"
            "- Do NOT attempt to call tools that are not listed below.\n"
        ),
    },
}
