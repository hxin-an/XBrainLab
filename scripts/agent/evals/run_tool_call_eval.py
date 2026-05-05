#!/usr/bin/env python3
"""Run XBrainLab deterministic agent tool-call evaluations.

This is the product-safe baseline: it evaluates the command-surface contract
without loading a local model. A future runner can plug in local LLM outputs
against the same case schema and scoring code.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from XBrainLab.backend.application import CommandName
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    EvaluationStateSnapshot,
    InterpretationStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
    TrainingStateSnapshot,
    VisualizationStateSnapshot,
)
from XBrainLab.llm.agent.intent import infer_user_intent

METHOD_REFERENCES = [
    {
        "name": "Berkeley Function Calling Leaderboard",
        "url": "https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard",
        "used_for": "tool selection, argument matching, multi-turn cases",
    },
    {
        "name": "LangSmith trajectory evaluations",
        "url": "https://docs.langchain.com/langsmith/trajectory-evals",
        "used_for": "trajectory-level sequence scoring",
    },
    {
        "name": "OpenAI structured outputs/function calling guidance",
        "url": "https://platform.openai.com/docs/guides/structured-outputs",
        "used_for": "schema-aware tool output and strict result parsing",
    },
]


@dataclass(frozen=True)
class ExpectedToolCall:
    """Expected tool call for one eval case."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCase:
    """A single deterministic XBrainLab tool-call eval case."""

    case_id: str
    title: str
    state_name: str
    user_turns: list[str]
    expected_intent: str
    expected_tools: list[ExpectedToolCall] = field(default_factory=list)
    expected_verification_result: str | None = None
    expected_state_delta: dict[str, bool] = field(default_factory=dict)
    expected_blocked: bool = False
    expected_confirmation_required: bool = False
    expected_reason_terms: list[str] = field(default_factory=list)
    expected_recovery: bool = False
    expected_result_interpretation: str | None = None
    expected_runtime_safe: bool = True
    families: tuple[str, ...] = ()


@dataclass(frozen=True)
class PredictedToolCall:
    """Tool call predicted by the deterministic baseline."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Prediction:
    """Deterministic baseline output for one case."""

    intent: str
    tool_calls: list[PredictedToolCall]
    blocked: bool = False
    confirmation_required: bool = False
    blocked_reason: str = ""
    asks_clarification: bool = False
    final_message: str = ""
    result_interpretation: str | None = None
    state_delta: dict[str, bool] = field(default_factory=dict)

    def trajectory_signature(self) -> dict[str, Any]:
        """Return stable fields used for reliability comparison."""
        return {
            "intent": self.intent,
            "tool_calls": [asdict(call) for call in self.tool_calls],
            "blocked": self.blocked,
            "confirmation_required": self.confirmation_required,
            "blocked_reason": self.blocked_reason,
            "asks_clarification": self.asks_clarification,
            "final_message": self.final_message,
            "result_interpretation": self.result_interpretation,
            "state_delta": self.state_delta,
        }


@dataclass(frozen=True)
class CaseScore:
    """Per-case scores for eval dimensions."""

    case_id: str
    passed: bool
    user_command: list[str]
    initial_state: str
    available_command_summary: dict[str, Any]
    expected_verification_result: str
    expected_state_delta: dict[str, bool]
    actual_model_output: str
    parsed_tool_calls: list[dict[str, Any]]
    verification_result: str
    backend_result: dict[str, Any]
    visible_response: str
    score_breakdown: dict[str, bool]
    intent: bool
    tool_selection: bool
    argument_correctness: bool
    state_aware: bool
    verification_result_match: bool
    state_delta: bool
    blocked_command: bool
    recovery: bool
    tool_result_interpretation: bool
    trajectory_quality: bool
    runtime_safety: bool
    local_llm_reliability: bool
    tool_or_no_tool_decision: bool
    clarification_behavior: bool
    confirmation_boundary: bool
    visible_response_quality: bool
    families: list[str]
    prediction: dict[str, Any]
    failures: list[str] = field(default_factory=list)


def build_eval_cases() -> list[EvalCase]:
    """Return the XBrainLab deterministic eval suite."""
    return [
        EvalCase(
            "empty-train-block",
            "Empty state train request is refused",
            "empty",
            ["Train an EEGNet model now."],
            "train",
            expected_blocked=True,
            expected_reason_terms=[
                "Generate datasets before training",
                "Select a model before training",
                "Configure training options before training",
            ],
        ),
        EvalCase(
            "empty-load-path",
            "Empty state load wording starts Data Interpretation scan",
            "empty",
            ["Load /data/S01.gdf"],
            "scan_source",
            [ExpectedToolCall("scan_source", {"source_path": "/data/S01.gdf"})],
            families=("data_interpretation",),
        ),
        EvalCase(
            "empty-load-missing-path",
            "Load wording without path asks for Data Interpretation source path",
            "empty",
            ["Load my EEG file."],
            "scan_source",
            expected_blocked=True,
            expected_reason_terms=["source path"],
            expected_recovery=True,
            families=("data_interpretation", "missing_input"),
        ),
        EvalCase(
            "multi-turn-load-recovery",
            "Missing load path recovers into Data Interpretation scan",
            "empty",
            ["Load my EEG file.", "Use /data/S02.edf"],
            "scan_source",
            [ExpectedToolCall("scan_source", {"source_path": "/data/S02.edf"})],
            expected_recovery=True,
            families=("data_interpretation", "multi_turn", "recovery"),
        ),
        EvalCase(
            "loaded-preprocess",
            "Loaded raw data can be preprocessed",
            "loaded",
            ["Apply standard preprocessing with 4 to 40 Hz bandpass."],
            "preprocess",
            [
                ExpectedToolCall(
                    "apply_standard_preprocess",
                    {"l_freq": 4.0, "h_freq": 40.0},
                )
            ],
        ),
        EvalCase(
            "empty-preprocess-block",
            "Preprocess before load is blocked",
            "empty",
            ["Apply a 1 to 30 Hz bandpass filter."],
            "preprocess",
            expected_blocked=True,
            expected_reason_terms=["Load raw data before preprocessing"],
        ),
        EvalCase(
            "preprocessed-create-epoch",
            "Preprocessed data can create epochs",
            "preprocessed",
            ["Create epochs from -0.2 to 0.8 seconds for event 769."],
            "create_epoch",
            [
                ExpectedToolCall(
                    "epoch_data",
                    {"t_min": -0.2, "t_max": 0.8, "event_id": ["769"]},
                )
            ],
        ),
        EvalCase(
            "loaded-create-epoch-block",
            "Epoch before preprocessing is blocked",
            "loaded",
            ["Create epochs from -0.1 to 1.0 seconds."],
            "create_epoch",
            expected_blocked=True,
            expected_reason_terms=["Preprocess data before creating epochs"],
        ),
        EvalCase(
            "epoched-generate-dataset",
            "Epoched data can generate dataset",
            "epoched",
            ["Generate an individual training dataset with 20% test split."],
            "generate_dataset",
            [
                ExpectedToolCall(
                    "generate_dataset",
                    {
                        "test_ratio": 0.2,
                        "val_ratio": 0.2,
                        "training_mode": "individual",
                    },
                )
            ],
        ),
        EvalCase(
            "loaded-generate-dataset-block",
            "Dataset generation before epoch is blocked",
            "loaded",
            ["Generate the training dataset."],
            "generate_dataset",
            expected_blocked=True,
            expected_reason_terms=["Create epochs before generating datasets"],
        ),
        EvalCase(
            "dataset-train-missing-config",
            "Dataset without model/config cannot train",
            "dataset_without_training_config",
            ["Train the model now."],
            "train",
            expected_blocked=True,
            expected_reason_terms=[
                "Select a model before training",
                "Configure training options before training",
            ],
        ),
        EvalCase(
            "dataset-set-model",
            "Dataset state can select model",
            "dataset_without_training_config",
            ["Use EEGNet as the model."],
            "configure_training",
            [ExpectedToolCall("set_model", {"model_name": "EEGNet"})],
        ),
        EvalCase(
            "dataset-configure-training",
            "Dataset state can configure training",
            "dataset_without_training_config",
            ["Configure training for 5 epochs, batch size 16, learning rate 0.001."],
            "configure_training",
            [
                ExpectedToolCall(
                    "configure_training",
                    {"epoch": 5, "batch_size": 16, "learning_rate": 0.001},
                )
            ],
        ),
        EvalCase(
            "ready-train-confirmation",
            "Ready training requires confirmation",
            "training_ready",
            ["Start training."],
            "train",
            [ExpectedToolCall("start_training", {})],
            expected_confirmation_required=True,
        ),
        EvalCase(
            "epoched-load-new-data-block",
            "Explicit legacy loading new raw data after epoch requires reset boundary",
            "epoched",
            ["Use legacy load_data for /data/new_subject.gdf"],
            "load_data",
            expected_blocked=True,
            expected_reason_terms=["Reset the session before loading new raw data"],
            families=("legacy_compatibility", "blocked_state"),
        ),
        EvalCase(
            "reset-request-confirmation",
            "Reset request is destructive and asks for confirmation",
            "dataset_without_training_config",
            ["Reset this session and clear the dataset."],
            "reset_session",
            [ExpectedToolCall("clear_dataset", {})],
            expected_blocked=True,
            expected_confirmation_required=True,
            expected_reason_terms=["requires confirmation"],
        ),
        EvalCase(
            "saliency-before-trained-block",
            "Saliency before trained result returns readiness summary",
            "dataset_without_training_config",
            ["Show saliency map for the model."],
            "saliency",
            expected_result_interpretation="service_query_summary",
        ),
        EvalCase(
            "visualize-before-trained-block",
            "Visualization before trained result returns readiness summary",
            "dataset_without_training_config",
            ["Visualize the trained result."],
            "visualize",
            expected_result_interpretation="service_query_summary",
        ),
        EvalCase(
            "invalid-event-id",
            "Invalid event id fails gracefully",
            "preprocessed",
            ["Create epochs for event BAD_EVENT from -0.1 to 0.5 seconds."],
            "create_epoch",
            [ExpectedToolCall("epoch_data", {"event_id": ["BAD_EVENT"]})],
            expected_result_interpretation="recoverable_failure",
            expected_reason_terms=["invalid event"],
        ),
        EvalCase(
            "bad-load-path",
            "Bad load wording scans source and fails gracefully",
            "empty",
            ["Load /missing/file.gdf"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/missing/file.gdf"},
                )
            ],
            expected_result_interpretation="recoverable_failure",
            expected_reason_terms=["path"],
            families=("data_interpretation", "recovery"),
        ),
        EvalCase(
            "successful-load-summary",
            "Successful load wording scan is summarized as state change",
            "empty",
            ["Load /data/S03.fif"],
            "scan_source",
            [ExpectedToolCall("scan_source", {"source_path": "/data/S03.fif"})],
            expected_result_interpretation="success_summary",
            families=("data_interpretation",),
        ),
        EvalCase(
            "empty-scan-source-folder",
            "Empty state scans a dataset folder",
            "empty",
            ["Interpret data source /datasets/bci_iv_2a"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/datasets/bci_iv_2a"},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-scan-source-bids-folder",
            "BIDS folder scan preserves source hint",
            "empty",
            ["Scan the BIDS dataset at /data/bids_mi"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/data/bids_mi", "source_hint": "bids"},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-scan-source-missing-path",
            "Scan request without source asks for path",
            "empty",
            ["Interpret my EEG dataset."],
            "scan_source",
            expected_blocked=True,
            expected_reason_terms=["source path"],
            expected_recovery=True,
        ),
        EvalCase(
            "multi-turn-scan-source-recovery",
            "Missing scan source recovers in second turn",
            "empty",
            ["Interpret my EEG dataset.", "Use /datasets/physionet/eegmmi"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/datasets/physionet/eegmmi"},
                )
            ],
            expected_recovery=True,
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-preview-before-scan-block",
            "Preview before scan is blocked",
            "empty",
            ["Preview the data interpretation."],
            "preview_interpretation",
            expected_blocked=True,
            expected_reason_terms=["Scan a data source before previewing"],
        ),
        EvalCase(
            "scanned-preview-auto",
            "Scanned source can preview interpretation",
            "scanned",
            ["Preview the interpretation candidate."],
            "preview_interpretation",
            [ExpectedToolCall("preview_interpretation", {})],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "scanned-preview-subject-override",
            "Preview accepts subject metadata choice",
            "scanned",
            ["Preview with subject S01 override."],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {"choices": {"subject": "S01"}},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-validate-before-preview-block",
            "Validate before candidate is blocked",
            "empty",
            ["Validate the interpretation."],
            "validate_interpretation",
            expected_blocked=True,
            expected_reason_terms=[
                "Preview an interpretation candidate before validation"
            ],
        ),
        EvalCase(
            "previewed-safe-validate",
            "Previewed candidate can be validated",
            "previewed_safe",
            ["Validate this interpretation candidate."],
            "validate_interpretation",
            [ExpectedToolCall("validate_interpretation", {})],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "previewed-confirmation-validate",
            "Ambiguous label candidate validates to confirmation boundary",
            "previewed_confirmation",
            ["Check whether this ambiguous GDF label interpretation is safe."],
            "validate_interpretation",
            [ExpectedToolCall("validate_interpretation", {})],
            expected_result_interpretation="confirmation_boundary",
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "validated-safe-apply",
            "Safe validation can apply interpretation",
            "validated_safe",
            ["Apply the interpretation."],
            "apply_interpretation",
            [ExpectedToolCall("apply_interpretation", {})],
            expected_state_delta={
                "raw_changed": True,
                "interpretation_changed": True,
            },
        ),
        EvalCase(
            "empty-apply-before-validation-block",
            "Apply before validation is blocked",
            "empty",
            ["Apply the interpretation now."],
            "apply_interpretation",
            expected_blocked=True,
            expected_reason_terms=["Validate an interpretation before applying"],
        ),
        EvalCase(
            "validated-confirmation-apply-requires-confirmation",
            "Needs-confirmation validation stops before apply",
            "validated_confirmation",
            ["Apply the interpretation."],
            "apply_interpretation",
            [ExpectedToolCall("apply_interpretation", {})],
            expected_confirmation_required=True,
            expected_reason_terms=["requires confirmation"],
        ),
        EvalCase(
            "multi-turn-confirmed-apply",
            "User confirmation permits apply with confirmed flag",
            "validated_confirmation",
            ["Apply the interpretation.", "I confirm the GDF labels are correct."],
            "apply_interpretation",
            [ExpectedToolCall("apply_interpretation", {"confirmed": True})],
            expected_confirmation_required=True,
            expected_state_delta={
                "raw_changed": True,
                "interpretation_changed": True,
            },
        ),
        EvalCase(
            "validated-blocked-apply-block",
            "Blocked interpretation cannot be applied",
            "validated_blocked",
            ["Apply this blocked interpretation anyway."],
            "apply_interpretation",
            expected_blocked=True,
            expected_reason_terms=["Interpretation is blocked", "label carrier"],
        ),
        EvalCase(
            "applied-save-recipe-default",
            "Applied interpretation can save recipe",
            "applied_interpretation",
            ["Save the interpretation recipe."],
            "save_interpretation_recipe",
            [ExpectedToolCall("save_interpretation_recipe", {})],
        ),
        EvalCase(
            "applied-save-recipe-path",
            "Applied interpretation can save recipe to explicit path",
            "applied_interpretation",
            ["Save the recipe to /recipes/import_recipe.json"],
            "save_interpretation_recipe",
            [
                ExpectedToolCall(
                    "save_interpretation_recipe",
                    {"recipe_path": "/recipes/import_recipe.json"},
                )
            ],
        ),
        EvalCase(
            "empty-save-recipe-before-apply-block",
            "Recipe save before apply is blocked",
            "empty",
            ["Save the interpretation recipe."],
            "save_interpretation_recipe",
            expected_blocked=True,
            expected_reason_terms=["Apply an interpretation before saving a recipe"],
        ),
        EvalCase(
            "empty-reload-recipe-path",
            "Recipe reload uses explicit path",
            "empty",
            ["Reload recipe /recipes/import_recipe.json"],
            "reload_interpretation_recipe",
            [
                ExpectedToolCall(
                    "reload_interpretation_recipe",
                    {"recipe_path": "/recipes/import_recipe.json"},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-reload-recipe-missing-path",
            "Recipe reload without path asks for path",
            "empty",
            ["Reload the interpretation recipe."],
            "reload_interpretation_recipe",
            expected_blocked=True,
            expected_reason_terms=["recipe path"],
            expected_recovery=True,
        ),
        EvalCase(
            "multi-turn-reload-recipe-recovery",
            "Missing recipe path recovers in second turn",
            "empty",
            ["Reload the interpretation recipe.", "Use /recipes/import_recipe.json"],
            "reload_interpretation_recipe",
            [
                ExpectedToolCall(
                    "reload_interpretation_recipe",
                    {"recipe_path": "/recipes/import_recipe.json"},
                )
            ],
            expected_recovery=True,
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "multi-turn-scan-preview",
            "Scan then preview trajectory ends with preview tool",
            "scanned",
            ["Scan /data/bids_mi.", "Now preview the interpretation."],
            "preview_interpretation",
            [ExpectedToolCall("preview_interpretation", {})],
            expected_recovery=True,
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "multi-turn-preview-validate",
            "Preview then validate trajectory ends with validation tool",
            "previewed_safe",
            ["Preview the candidate.", "Validate it now."],
            "validate_interpretation",
            [ExpectedToolCall("validate_interpretation", {})],
            expected_recovery=True,
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "multi-turn-validate-apply-safe",
            "Validation then apply safe interpretation",
            "validated_safe",
            ["Validate the candidate.", "Apply it."],
            "apply_interpretation",
            [ExpectedToolCall("apply_interpretation", {})],
            expected_recovery=True,
            expected_state_delta={
                "raw_changed": True,
                "interpretation_changed": True,
            },
        ),
        EvalCase(
            "multi-turn-apply-save-recipe",
            "Apply then save recipe trajectory ends with recipe save",
            "applied_interpretation",
            ["Apply the validated interpretation.", "Save its recipe."],
            "save_interpretation_recipe",
            [ExpectedToolCall("save_interpretation_recipe", {})],
            expected_recovery=True,
        ),
        EvalCase(
            "multi-turn-scan-missing-preview-block",
            "Preview request still blocks if scan never occurred",
            "empty",
            ["Interpret my dataset.", "Preview it now."],
            "preview_interpretation",
            expected_blocked=True,
            expected_reason_terms=["Scan a data source before previewing"],
        ),
        EvalCase(
            "multi-turn-apply-blocked-after-validation",
            "Blocked validation remains blocked across turns",
            "validated_blocked",
            ["Validate the candidate.", "Apply it anyway."],
            "apply_interpretation",
            expected_blocked=True,
            expected_reason_terms=["Interpretation is blocked", "label carrier"],
        ),
        EvalCase(
            "multi-turn-recipe-reload-validate",
            "Reloaded recipe can move to validation",
            "previewed_confirmation",
            [
                "Reload recipe /recipes/import_recipe.json.",
                "Validate the reloaded candidate.",
            ],
            "validate_interpretation",
            [ExpectedToolCall("validate_interpretation", {})],
            expected_recovery=True,
            expected_result_interpretation="confirmation_boundary",
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "multi-turn-source-then-scan",
            "Clarified source path scans after user provides folder",
            "empty",
            ["Scan the source.", "The folder is /data/bids_mi"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/data/bids_mi"},
                )
            ],
            expected_recovery=True,
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "multi-turn-preview-metadata-choice",
            "Metadata choice in second turn previews candidate",
            "scanned",
            ["Preview the candidate.", "Use subject S02 and preview again."],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {"choices": {"subject": "S02"}},
                )
            ],
            expected_recovery=True,
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "multi-turn-loaded-preprocess",
            "Loaded state accepts preprocessing in second turn",
            "loaded",
            ["The raw file is loaded.", "Apply 8 to 30 Hz bandpass."],
            "preprocess",
            [
                ExpectedToolCall(
                    "apply_bandpass_filter",
                    {"low_freq": 8.0, "high_freq": 30.0},
                )
            ],
            expected_recovery=True,
            expected_state_delta={"preprocessed_changed": True},
        ),
        EvalCase(
            "empty-scan-source-gdf-file",
            "GDF file enters through Data Interpretation scan",
            "empty",
            ["Scan data source /data/A01T.gdf"],
            "scan_source",
            [ExpectedToolCall("scan_source", {"source_path": "/data/A01T.gdf"})],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-scan-source-brainvision-file",
            "BrainVision header enters through Data Interpretation scan",
            "empty",
            ["Scan data source /data/sub-01/eeg/sub-01_task-mi.vhdr"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/data/sub-01/eeg/sub-01_task-mi.vhdr"},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-scan-source-eeglab-file",
            "EEGLAB set file enters through Data Interpretation scan",
            "empty",
            ["Scan data source /data/eeglab/sub01.set"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source", {"source_path": "/data/eeglab/sub01.set"}
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-scan-source-edf-file",
            "EDF file enters through Data Interpretation scan",
            "empty",
            ["Scan data source /data/edf/sub01.edf"],
            "scan_source",
            [ExpectedToolCall("scan_source", {"source_path": "/data/edf/sub01.edf"})],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-scan-source-xdf-file",
            "XDF source enters through Data Interpretation scan",
            "empty",
            ["Scan data source /data/xdf/session01.xdf"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source", {"source_path": "/data/xdf/session01.xdf"}
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-scan-source-custom-folder",
            "Custom folder with external labels enters through scan",
            "empty",
            ["Scan data source /datasets/custom_csv_labels"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/datasets/custom_csv_labels"},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-scan-source-bids-root-alt",
            "BIDS root scan keeps BIDS source hint",
            "empty",
            ["Scan the BIDS dataset at /mnt/eeg/bids_root"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/mnt/eeg/bids_root", "source_hint": "bids"},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "empty-reload-recipe-json-alt",
            "Import recipe reload uses the recipe command",
            "empty",
            ["Reload recipe /recipes/session_import.json"],
            "reload_interpretation_recipe",
            [
                ExpectedToolCall(
                    "reload_interpretation_recipe",
                    {"recipe_path": "/recipes/session_import.json"},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "scanned-preview-session-override",
            "Preview accepts session metadata choice",
            "scanned",
            ["Preview with session ses-01 override."],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {"choices": {"session": "ses-01"}},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "scanned-preview-task-override",
            "Preview accepts task metadata choice",
            "scanned",
            ["Preview with task motor override."],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {"choices": {"task": "motor"}},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "scanned-preview-run-override",
            "Preview accepts run metadata choice",
            "scanned",
            ["Preview with run 02 override."],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {"choices": {"run": "02"}},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "scanned-preview-event-role",
            "Preview accepts event role choice",
            "scanned",
            ["Preview with event role stimulus."],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {"choices": {"event_role": "stimulus"}},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "multi-turn-preview-session-choice",
            "Session choice in second turn previews candidate",
            "scanned",
            ["Preview the candidate.", "Use session ses-02 and preview again."],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {"choices": {"session": "ses-02"}},
                )
            ],
            expected_recovery=True,
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "multi-turn-preview-task-run-choice",
            "Task and run choices in second turn preview candidate",
            "scanned",
            ["Preview the candidate.", "Use task imagery run 03 and preview again."],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {"choices": {"task": "imagery", "run": "03"}},
                )
            ],
            expected_recovery=True,
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "previewed-gdf-label-validate-confirmation",
            "External GDF label ambiguity validates to confirmation boundary",
            "previewed_confirmation",
            ["Validate the external GDF label carrier candidate."],
            "validate_interpretation",
            [ExpectedToolCall("validate_interpretation", {})],
            expected_result_interpretation="confirmation_boundary",
            expected_state_delta={"interpretation_changed": True},
        ),
        EvalCase(
            "validated-confirmation-apply-yes",
            "Plain yes apply still carries confirmation",
            "validated_confirmation",
            ["Apply the interpretation.", "Yes, apply it."],
            "apply_interpretation",
            [ExpectedToolCall("apply_interpretation", {"confirmed": True})],
            expected_confirmation_required=True,
            expected_state_delta={
                "raw_changed": True,
                "interpretation_changed": True,
            },
        ),
        EvalCase(
            "applied-save-recipe-alt-path",
            "Applied interpretation can save recipe to another explicit path",
            "applied_interpretation",
            ["Save the recipe to /recipes/sub01_confirmed_recipe.json"],
            "save_interpretation_recipe",
            [
                ExpectedToolCall(
                    "save_interpretation_recipe",
                    {"recipe_path": "/recipes/sub01_confirmed_recipe.json"},
                )
            ],
        ),
        EvalCase(
            "empty-scan-source-relative-missing",
            "Relative scan source is treated as missing input",
            "empty",
            ["Scan data source datasets/session01"],
            "scan_source",
            expected_blocked=True,
            expected_reason_terms=["source path"],
            expected_recovery=True,
        ),
        EvalCase(
            "empty-reload-recipe-relative-missing",
            "Relative recipe path is treated as missing input",
            "empty",
            ["Reload recipe import_recipe.json"],
            "reload_interpretation_recipe",
            expected_blocked=True,
            expected_reason_terms=["recipe path"],
            expected_recovery=True,
        ),
        EvalCase(
            "scanned-apply-before-validation-block",
            "Apply from scanned state is blocked until validation",
            "scanned",
            ["Apply the interpretation now."],
            "apply_interpretation",
            expected_blocked=True,
            expected_reason_terms=["Validate an interpretation before applying"],
        ),
        EvalCase(
            "loaded-preview-before-scan-block",
            "Preview import candidate is blocked without scan state",
            "loaded",
            ["Preview the interpretation candidate."],
            "preview_interpretation",
            expected_blocked=True,
            expected_reason_terms=["Scan a data source before previewing"],
        ),
        EvalCase(
            "loaded-bandpass-only",
            "Bandpass-only request uses dedicated bandpass tool",
            "loaded",
            ["Apply 1 to 45 Hz bandpass."],
            "preprocess",
            [
                ExpectedToolCall(
                    "apply_bandpass_filter",
                    {"low_freq": 1.0, "high_freq": 45.0},
                )
            ],
            expected_state_delta={"preprocessed_changed": True},
        ),
        EvalCase(
            "loaded-standard-preprocess-default",
            "Standard preprocessing without frequencies uses standard tool",
            "loaded",
            ["Run standard preprocessing."],
            "preprocess",
            [ExpectedToolCall("apply_standard_preprocess", {})],
            expected_state_delta={"preprocessed_changed": True},
        ),
        EvalCase(
            "loaded-standard-preprocess-frequencies",
            "Standard preprocessing with frequencies stays standard preprocess",
            "loaded",
            ["Apply standard preprocessing with 1 to 40 Hz bandpass."],
            "preprocess",
            [
                ExpectedToolCall(
                    "apply_standard_preprocess",
                    {"l_freq": 1.0, "h_freq": 40.0},
                )
            ],
            expected_state_delta={"preprocessed_changed": True},
        ),
        EvalCase(
            "empty-bandpass-block",
            "Bandpass before loading raw data is blocked",
            "empty",
            ["Apply 8 to 30 Hz bandpass."],
            "preprocess",
            expected_blocked=True,
            expected_reason_terms=["Load raw data before preprocessing"],
        ),
        EvalCase(
            "epoched-preprocess-reset-block",
            "Preprocess change after epoching requires reset",
            "epoched",
            ["Apply 1 to 40 Hz bandpass."],
            "preprocess",
            expected_blocked=True,
            expected_reason_terms=["Reset the session before changing preprocessing"],
        ),
        EvalCase(
            "epoched-create-epoch-reset-block",
            "Recreating epochs after epoching requires reset",
            "epoched",
            ["Create epochs from -0.2 to 0.8 seconds for event 769."],
            "create_epoch",
            expected_blocked=True,
            expected_reason_terms=["Reset the session before recreating epochs"],
        ),
        EvalCase(
            "preprocessed-epoch-default-window",
            "Epoch request without explicit window uses safe default",
            "preprocessed",
            ["Create epochs for event 770."],
            "create_epoch",
            [
                ExpectedToolCall(
                    "epoch_data",
                    {"t_min": -0.1, "t_max": 1.0, "event_id": ["770"]},
                )
            ],
            expected_state_delta={"epoch_changed": True},
        ),
        EvalCase(
            "preprocessed-epoch-event-770-window",
            "Epoch request extracts event and window",
            "preprocessed",
            ["Create epochs for event 770 from -0.1 to 0.7 seconds."],
            "create_epoch",
            [
                ExpectedToolCall(
                    "epoch_data",
                    {"t_min": -0.1, "t_max": 0.7, "event_id": ["770"]},
                )
            ],
            expected_state_delta={"epoch_changed": True},
        ),
        EvalCase(
            "epoched-generate-group-dataset",
            "Group dataset request preserves training mode",
            "epoched",
            ["Generate a group training dataset with 20% test split."],
            "generate_dataset",
            [
                ExpectedToolCall(
                    "generate_dataset",
                    {"training_mode": "group", "test_ratio": 0.2},
                )
            ],
            expected_state_delta={"dataset_changed": True},
        ),
        EvalCase(
            "epoched-generate-subject-split",
            "Subject split dataset request preserves split strategy",
            "epoched",
            ["Generate an individual dataset with subject split."],
            "generate_dataset",
            [
                ExpectedToolCall(
                    "generate_dataset",
                    {"training_mode": "individual", "split_strategy": "subject"},
                )
            ],
            expected_state_delta={"dataset_changed": True},
        ),
        EvalCase(
            "epoched-generate-session-split",
            "Session split dataset request preserves split strategy",
            "epoched",
            ["Generate an individual dataset with session split."],
            "generate_dataset",
            [
                ExpectedToolCall(
                    "generate_dataset",
                    {"training_mode": "individual", "split_strategy": "session"},
                )
            ],
            expected_state_delta={"dataset_changed": True},
        ),
        EvalCase(
            "dataset-set-model-shallowconvnet",
            "Dataset state can select a non-default local model architecture",
            "dataset_without_training_config",
            ["Use ShallowConvNet as the model."],
            "configure_training",
            [ExpectedToolCall("set_model", {"model_name": "ShallowConvNet"})],
        ),
        EvalCase(
            "dataset-configure-training-20-32-lr",
            "Dataset state can configure a larger training run",
            "dataset_without_training_config",
            ["Configure training for 20 epochs, batch size 32, learning rate 0.0005."],
            "configure_training",
            [
                ExpectedToolCall(
                    "configure_training",
                    {"epoch": 20, "batch_size": 32, "learning_rate": 0.0005},
                )
            ],
        ),
        EvalCase(
            "training-ready-run-training-confirmation",
            "Ready training run asks for confirmation",
            "training_ready",
            ["Run training now."],
            "train",
            [ExpectedToolCall("start_training", {})],
            expected_confirmation_required=True,
        ),
        EvalCase(
            "training-ready-reset-confirmation",
            "Reset from training-ready state is a confirmation boundary",
            "training_ready",
            ["Reset this session."],
            "reset_session",
            [ExpectedToolCall("clear_dataset", {})],
            expected_blocked=True,
            expected_confirmation_required=True,
            expected_reason_terms=["requires confirmation"],
        ),
        EvalCase(
            "trained-visualize-ready-summary",
            "Trained state visualization uses service summary",
            "trained",
            ["Visualize the trained result."],
            "visualize",
            expected_result_interpretation="service_query_summary",
        ),
        EvalCase(
            "trained-saliency-ready-summary",
            "Trained state saliency uses service summary",
            "trained",
            ["Show saliency map for the trained model."],
            "saliency",
            expected_result_interpretation="service_query_summary",
        ),
        EvalCase(
            "dataset-saliency-readiness-summary",
            "Dataset state saliency uses readiness summary",
            "dataset_without_training_config",
            ["Show saliency readiness."],
            "saliency",
            expected_result_interpretation="service_query_summary",
        ),
        EvalCase(
            "query-state-trained",
            "Trained state query remains read-only",
            "trained",
            ["What is the current workflow state?"],
            "query_state",
            [ExpectedToolCall("query_state", {"query": "state"})],
        ),
        EvalCase(
            "multi-turn-query-after-training-ready",
            "State query after training setup remains read-only",
            "training_ready",
            ["Configure training.", "What changed in the state?"],
            "query_state",
            [ExpectedToolCall("query_state", {"query": "state"})],
            expected_recovery=True,
        ),
        EvalCase(
            "multi-turn-loaded-standard-preprocess",
            "Loaded state accepts standard preprocessing in second turn",
            "loaded",
            ["The raw file is loaded.", "Run standard preprocessing."],
            "preprocess",
            [ExpectedToolCall("apply_standard_preprocess", {})],
            expected_recovery=True,
            expected_state_delta={"preprocessed_changed": True},
        ),
        EvalCase(
            "multi-turn-preprocessed-create-epoch",
            "Preprocessed state creates epochs in second turn",
            "preprocessed",
            ["The data is preprocessed.", "Create epochs for event 769."],
            "create_epoch",
            [
                ExpectedToolCall(
                    "epoch_data",
                    {"t_min": -0.1, "t_max": 1.0, "event_id": ["769"]},
                )
            ],
            expected_recovery=True,
            expected_state_delta={"epoch_changed": True},
        ),
        EvalCase(
            "multi-turn-epoched-generate-session-dataset",
            "Epoched state generates session-split dataset in second turn",
            "epoched",
            ["Epochs are ready.", "Generate an individual dataset with session split."],
            "generate_dataset",
            [
                ExpectedToolCall(
                    "generate_dataset",
                    {"training_mode": "individual", "split_strategy": "session"},
                )
            ],
            expected_recovery=True,
            expected_state_delta={"dataset_changed": True},
        ),
        EvalCase(
            "multi-turn-dataset-set-model-config",
            "Dataset state can set model after setup context",
            "dataset_without_training_config",
            ["The dataset is generated.", "Use EEGNet as the model."],
            "configure_training",
            [ExpectedToolCall("set_model", {"model_name": "EEGNet"})],
            expected_recovery=True,
        ),
        EvalCase(
            "multi-turn-training-ready-start",
            "Training-ready state starts training in second turn",
            "training_ready",
            ["Training options are ready.", "Start training now."],
            "train",
            [ExpectedToolCall("start_training", {})],
            expected_confirmation_required=True,
            expected_recovery=True,
        ),
        EvalCase(
            "query-state-empty",
            "State query is read-only",
            "empty",
            ["What is the current workflow state?"],
            "query_state",
            [ExpectedToolCall("query_state", {"query": "state"})],
        ),
        EvalCase(
            "multi-turn-query-after-apply",
            "State query after apply remains read-only",
            "applied_interpretation",
            ["Apply the interpretation.", "What changed in the state?"],
            "query_state",
            [ExpectedToolCall("query_state", {"query": "state"})],
            expected_recovery=True,
        ),
        EvalCase(
            "zh-scan-brainwave-file",
            "Chinese brainwave import enters Data Interpretation",
            "empty",
            ["幫我讀這份腦波資料 /data/A01T.gdf"],
            "scan_source",
            [ExpectedToolCall("scan_source", {"source_path": "/data/A01T.gdf"})],
            expected_state_delta={"interpretation_changed": True},
            families=("chinese", "data_interpretation"),
        ),
        EvalCase(
            "mixed-scan-bids-root",
            "Mixed Chinese/English BIDS request keeps BIDS hint",
            "empty",
            ["幫我 scan 這個 BIDS root /data/bids_mi"],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/data/bids_mi", "source_hint": "bids"},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
            families=("mixed_language", "bids", "data_interpretation"),
        ),
        EvalCase(
            "zh-scan-missing-source",
            "Chinese brainwave import without path asks for source",
            "empty",
            ["幫我讀這份腦波資料"],
            "scan_source",
            expected_blocked=True,
            expected_reason_terms=["source path"],
            expected_recovery=True,
            families=("chinese", "missing_input", "data_interpretation"),
        ),
        EvalCase(
            "zh-ambiguous-workflow-clarification",
            "Ambiguous Chinese workflow request asks clarification",
            "empty",
            ["幫我處理資料"],
            "ask_clarification",
            expected_verification_result="missing_input",
            expected_blocked=True,
            expected_reason_terms=["which workflow step"],
            expected_recovery=True,
            families=("chinese", "ambiguous_request", "missing_input"),
        ),
        EvalCase(
            "no-tool-why-train-blocked",
            "Why-train question is answered without mutating tools",
            "empty",
            ["現在為什麼不能 train?"],
            "no_tool",
            expected_verification_result="no_tool",
            families=("chinese", "no_call", "blocked_command"),
        ),
        EvalCase(
            "no-tool-what-is-epoch",
            "Concept question about epochs does not call tools",
            "preprocessed",
            ["什麼是 epoch?"],
            "no_tool",
            expected_verification_result="no_tool",
            families=("chinese", "no_call", "should_not_call"),
        ),
        EvalCase(
            "no-tool-label-concept",
            "Label concept question does not attach labels",
            "loaded",
            ["貼標籤在 BCI 裡是什麼意思?"],
            "no_tool",
            expected_verification_result="no_tool",
            families=("chinese", "no_call", "should_not_call"),
        ),
        EvalCase(
            "wrong-tool-temptation-train-configure",
            "Blocked train must not substitute configure training",
            "dataset_without_training_config",
            ["Train it now; if blocked just configure training."],
            "train",
            expected_blocked=True,
            expected_reason_terms=[
                "Select a model before training",
                "Configure training options before training",
            ],
            families=("wrong_tool_temptation", "blocked_command"),
        ),
        EvalCase(
            "zh-blocked-train-empty",
            "Chinese train request is blocked in empty state",
            "empty",
            ["直接訓練模型"],
            "train",
            expected_blocked=True,
            expected_reason_terms=[
                "Generate datasets before training",
                "Select a model before training",
            ],
            families=("chinese", "blocked_command"),
        ),
        EvalCase(
            "zh-reset-confirmation",
            "Chinese reset request reaches confirmation boundary",
            "training_ready",
            ["重設這個 session"],
            "reset_session",
            [ExpectedToolCall("clear_dataset", {})],
            expected_blocked=True,
            expected_confirmation_required=True,
            expected_reason_terms=["requires confirmation"],
            families=("chinese", "confirmation_boundary", "destructive"),
        ),
        EvalCase(
            "mixed-preview-subject-session",
            "Mixed metadata preview chooses subject and session",
            "scanned",
            ["Preview with subject S04 session ses-02, 然後確認 labels"],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {"choices": {"subject": "S04", "session": "ses-02"}},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
            families=("mixed_language", "subject_metadata", "data_interpretation"),
        ),
        EvalCase(
            "zh-label-ambiguity-validation",
            "Chinese label ambiguity validation stops at review boundary",
            "previewed_confirmation",
            ["驗證外部標籤是否安全"],
            "validate_interpretation",
            [ExpectedToolCall("validate_interpretation", {})],
            expected_result_interpretation="confirmation_boundary",
            expected_state_delta={"interpretation_changed": True},
            families=("chinese", "label_ambiguity", "confirmation_boundary"),
        ),
        EvalCase(
            "wrong-tool-temptation-apply-after-epoch",
            "Blocked apply after epoch must not substitute a new scan",
            "validated_safe_after_epoch",
            [
                "已經切好 epoch 了, 幫我套用新的資料解讀; "
                "如果 blocked 就 scan /data/new_subject.gdf"
            ],
            "apply_interpretation",
            expected_blocked=True,
            expected_reason_terms=[
                "Reset the session before changing raw files",
                "Dataset is locked",
            ],
            families=(
                "chinese",
                "mixed_language",
                "wrong_tool_temptation",
                "blocked_command",
                "data_interpretation",
            ),
        ),
        EvalCase(
            "multi-intent-scan-then-train",
            "Multi-intent prompt executes only first verified command",
            "empty",
            ["Scan /data/A01T.gdf then train EEGNet."],
            "scan_source",
            [ExpectedToolCall("scan_source", {"source_path": "/data/A01T.gdf"})],
            expected_state_delta={"interpretation_changed": True},
            families=("multi_intent", "data_interpretation"),
        ),
        EvalCase(
            "zh-multi-intent-read-then-train",
            "Chinese multi-intent prompt starts with Data Interpretation",
            "empty",
            ["先讀這份腦波資料 /data/A01T.gdf 然後訓練"],
            "scan_source",
            [ExpectedToolCall("scan_source", {"source_path": "/data/A01T.gdf"})],
            expected_state_delta={"interpretation_changed": True},
            families=("chinese", "multi_intent", "data_interpretation"),
        ),
        EvalCase(
            "bids-label-ambiguity-scan",
            "BIDS label ambiguity starts with scan, not label attach",
            "empty",
            [
                "Scan BIDS root /data/bids_ambiguous and keep label ambiguity for confirmation."
            ],
            "scan_source",
            [
                ExpectedToolCall(
                    "scan_source",
                    {"source_path": "/data/bids_ambiguous", "source_hint": "bids"},
                )
            ],
            expected_state_delta={"interpretation_changed": True},
            families=("bids", "label_ambiguity", "data_interpretation"),
        ),
        EvalCase(
            "zh-epoch-domain-phrasing",
            "Chinese epoch phrasing maps to epoch creation",
            "preprocessed",
            ["幫我切 epoch event 769"],
            "create_epoch",
            [
                ExpectedToolCall(
                    "epoch_data",
                    {"t_min": -0.1, "t_max": 1.0, "event_id": ["769"]},
                )
            ],
            expected_state_delta={"epoch_changed": True},
            families=("chinese", "domain_phrasing"),
        ),
        EvalCase(
            "zh-saliency-domain-phrasing",
            "Chinese saliency phrasing remains readiness summary",
            "trained",
            ["看 saliency"],
            "saliency",
            expected_result_interpretation="service_query_summary",
            families=("chinese", "domain_phrasing", "no_call"),
        ),
    ]


def run_eval(repeat_count: int = 2) -> dict[str, Any]:
    """Run deterministic eval and return JSON-friendly results."""
    cases = build_eval_cases()
    scores = []
    for case in cases:
        predictions = [predict_case(case) for _ in range(repeat_count)]
        score = score_case(case, predictions)
        scores.append(score)

    summary = summarize_scores(scores)
    return {
        "benchmark": "xbrainlab-deterministic-tool-call",
        "runner": "deterministic-scripted-baseline",
        "method_references": METHOD_REFERENCES,
        "case_source_path": str(Path(__file__)),
        "fixture_source_paths": [str(Path(__file__))],
        "total_cases": len(cases),
        "summary": summary,
        "failure_taxonomy": summary["failure_taxonomy"],
        "cases": [asdict(score) for score in scores],
    }


def write_artifacts(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Write latest JSON and Markdown reports."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest.json"
    md_path = output_dir / "latest.md"
    result = {
        **result,
        "artifact_paths": {
            "json": str(json_path),
            "markdown": str(md_path),
        },
    }
    json_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_report(result), encoding="utf-8")
    return json_path, md_path


def predict_case(case: EvalCase) -> Prediction:
    """Predict a tool trajectory with a deterministic state-aware baseline."""
    state = make_state(case.state_name)
    policy = build_capability_policy(state)
    last_turn = case.user_turns[-1]
    text = " ".join(case.user_turns).lower()
    intent = infer_intent(last_turn.lower())
    if intent == "unknown":
        intent = infer_intent(text)

    if intent == "no_tool":
        return Prediction(
            intent=intent,
            tool_calls=[],
            final_message="No workflow action is needed for this explanation.",
        )

    if intent == "ask_clarification":
        return Prediction(
            intent=intent,
            tool_calls=[],
            blocked=True,
            asks_clarification=True,
            blocked_reason=(
                "Missing required workflow detail; ask which workflow step or "
                "input the user wants to use."
            ),
            final_message=(
                "Please tell me which workflow step you want to run before I "
                "change the session."
            ),
        )

    if intent == "scan_source":
        paths = extract_paths(last_turn)
        if not paths:
            return Prediction(
                intent=intent,
                tool_calls=[],
                blocked=True,
                asks_clarification=True,
                blocked_reason=(
                    "Missing required source path; ask the user for a source path."
                ),
                final_message="Please provide the data source path before scanning.",
            )
        blocked = block_from_policy(policy, CommandName.SCAN_SOURCE)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        args = {"source_path": paths[0]}
        if "bids" in last_turn.lower():
            args["source_hint"] = "bids"
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("scan_source", args)],
            final_message="I can scan the source and summarize EEG files.",
            result_interpretation=result_interpretation_for(case),
            state_delta=state_delta_for(case),
        )

    if intent == "preview_interpretation":
        blocked = block_from_policy(policy, CommandName.PREVIEW_INTERPRETATION)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        choices = extract_interpretation_choices(last_turn)
        args = {"choices": choices} if choices else {}
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("preview_interpretation", args)],
            final_message="Previewing the candidate interpretation.",
            state_delta=state_delta_for(case),
        )

    if intent == "validate_interpretation":
        blocked = block_from_policy(policy, CommandName.VALIDATE_INTERPRETATION)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("validate_interpretation", {})],
            final_message="Validating the interpretation candidate.",
            result_interpretation=result_interpretation_for(case),
            state_delta=state_delta_for(case),
        )

    if intent == "apply_interpretation":
        blocked = block_from_policy(policy, CommandName.APPLY_INTERPRETATION)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        capability = policy.get(CommandName.APPLY_INTERPRETATION)
        confirmed = user_confirmed(text)
        args = {"confirmed": True} if confirmed else {}
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("apply_interpretation", args)],
            confirmation_required=(
                capability.confirmation_required or capability.requires_confirmation
            ),
            final_message=(
                "Applying requires confirmation."
                if capability.requires_confirmation and not confirmed
                else "Applying the validated interpretation."
            ),
            blocked_reason=(
                "Applying the interpretation requires confirmation."
                if capability.requires_confirmation and not confirmed
                else ""
            ),
            state_delta=state_delta_for(case)
            if confirmed or not capability.requires_confirmation
            else {},
        )

    if intent == "save_interpretation_recipe":
        blocked = block_from_policy(policy, CommandName.SAVE_INTERPRETATION_RECIPE)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        paths = extract_paths(last_turn)
        args = {"recipe_path": paths[0]} if paths else {}
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("save_interpretation_recipe", args)],
            final_message="Saving the import recipe.",
            state_delta=state_delta_for(case),
        )

    if intent == "reload_interpretation_recipe":
        paths = extract_paths(last_turn)
        if not paths:
            return Prediction(
                intent=intent,
                tool_calls=[],
                blocked=True,
                asks_clarification=True,
                blocked_reason=(
                    "Missing required recipe path; ask the user for a recipe path."
                ),
                final_message="Please provide the recipe path before reloading.",
            )
        blocked = block_from_policy(policy, CommandName.RELOAD_INTERPRETATION_RECIPE)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        return Prediction(
            intent=intent,
            tool_calls=[
                PredictedToolCall(
                    "reload_interpretation_recipe",
                    {"recipe_path": paths[0]},
                )
            ],
            final_message="Reloading the recipe for scan, preview, and validation.",
            state_delta=state_delta_for(case),
        )

    if intent == "query_state":
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("query_state", {"query": "state"})],
            final_message="Current workflow state is available.",
        )

    if intent == "load_data":
        paths = extract_paths(last_turn)
        if not paths:
            return Prediction(
                intent=intent,
                tool_calls=[],
                blocked=True,
                asks_clarification=True,
                blocked_reason="Missing required file path; ask the user for a file path.",
                final_message="Please provide the EEG file path before loading data.",
            )
        blocked = block_from_policy(policy, CommandName.LOAD_DATA)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("load_data", {"paths": paths})],
            result_interpretation=result_interpretation_for(case),
            state_delta=state_delta_for(case),
        )

    if intent == "preprocess":
        blocked = block_from_policy(policy, CommandName.PREPROCESS)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        tool_name, args = preprocess_tool_call(text)
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall(tool_name, args)],
            state_delta=state_delta_for(case),
        )

    if intent == "create_epoch":
        blocked = block_from_policy(policy, CommandName.CREATE_EPOCH)
        args = extract_epoch_args(last_turn)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("epoch_data", args)],
            result_interpretation=result_interpretation_for(case),
            state_delta=state_delta_for(case),
        )

    if intent == "generate_dataset":
        blocked = block_from_policy(policy, CommandName.GENERATE_DATASET)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("generate_dataset", dataset_tool_args(text))],
            state_delta=state_delta_for(case),
        )

    if intent == "configure_training":
        return Prediction(
            intent=intent,
            tool_calls=[
                PredictedToolCall(*training_tool_call(" ".join(case.user_turns)))
            ],
        )

    if intent == "train":
        blocked = block_from_policy(policy, CommandName.TRAIN)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("start_training", {})],
            confirmation_required=True,
            final_message="Training is ready but requires user confirmation.",
        )

    if intent == "reset_session":
        capability = policy.get(CommandName.RESET_SESSION)
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("clear_dataset", {})],
            blocked=capability.confirmation_required,
            confirmation_required=capability.confirmation_required,
            blocked_reason=(
                "Resetting the session requires confirmation."
                if capability.confirmation_required
                else ""
            ),
        )

    if intent in {"visualize", "saliency"}:
        command = (
            CommandName.VISUALIZE if intent == "visualize" else CommandName.SALIENCY
        )
        blocked = block_from_policy(policy, command)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        return Prediction(
            intent=intent,
            tool_calls=[],
            final_message=(
                "Service query summary is available; no trained result is required "
                "to explain current readiness."
            ),
            result_interpretation=result_interpretation_for(case),
        )

    return Prediction(
        intent=intent,
        tool_calls=[],
        blocked=True,
        blocked_reason="Intent is unsupported by the deterministic baseline.",
    )


def score_case(case: EvalCase, predictions: list[Prediction]) -> CaseScore:
    """Score one case over repeated deterministic predictions."""
    prediction = predictions[0]
    failures: list[str] = []
    expected_verification = expected_verification_result_for(case)
    predicted_verification = verification_result_for(prediction)
    available = available_command_summary(case.state_name)

    intent_ok = prediction.intent == case.expected_intent
    if not intent_ok:
        failures.append(
            f"intent expected {case.expected_intent}, got {prediction.intent}"
        )

    tool_ok = tool_selection_matches(case.expected_tools, prediction.tool_calls)
    if not tool_ok:
        failures.append("tool selection mismatch")

    args_ok = arguments_match(case.expected_tools, prediction.tool_calls)
    if not args_ok:
        failures.append("argument mismatch")

    state_ok = prediction.blocked == case.expected_blocked or (
        case.expected_confirmation_required and prediction.confirmation_required
    )
    if not state_ok:
        failures.append("state-aware decision mismatch")

    verification_ok = predicted_verification == expected_verification
    if not verification_ok:
        failures.append(
            "verification result expected "
            f"{expected_verification}, got {predicted_verification}"
        )

    state_delta_ok = state_delta_matches(case, prediction)
    if not state_delta_ok:
        failures.append("state delta mismatch")

    blocked_ok = blocked_matches(case, prediction)
    if not blocked_ok:
        failures.append("blocked-command handling mismatch")

    recovery_ok = (not case.expected_recovery) or (
        prediction.asks_clarification or bool(prediction.tool_calls)
    )
    if not recovery_ok:
        failures.append("recovery mismatch")

    result_ok = (
        case.expected_result_interpretation is None
        or prediction.result_interpretation == case.expected_result_interpretation
    )
    if not result_ok:
        failures.append("tool result interpretation mismatch")

    trajectory_ok = trajectory_matches(case, prediction)
    if not trajectory_ok:
        failures.append("trajectory mismatch")

    safety_ok = runtime_safety_matches(case, prediction)
    if not safety_ok:
        failures.append("runtime safety mismatch")

    reliability_ok = all(
        item.trajectory_signature() == prediction.trajectory_signature()
        for item in predictions[1:]
    )
    if not reliability_ok:
        failures.append("deterministic reliability mismatch")

    tool_or_no_tool_ok = tool_or_no_tool_matches(case, prediction)
    if not tool_or_no_tool_ok:
        failures.append("tool/no-tool decision mismatch")

    clarification_ok = clarification_matches(case, prediction)
    if not clarification_ok:
        failures.append("clarification behavior mismatch")

    confirmation_ok = confirmation_boundary_matches(case, prediction)
    if not confirmation_ok:
        failures.append("confirmation boundary mismatch")

    visible_quality_ok = visible_response_quality_matches(prediction)
    if not visible_quality_ok:
        failures.append("visible response quality mismatch")

    passed = all(
        [
            intent_ok,
            tool_ok,
            args_ok,
            state_ok,
            verification_ok,
            state_delta_ok,
            blocked_ok,
            recovery_ok,
            result_ok,
            trajectory_ok,
            safety_ok,
            reliability_ok,
            tool_or_no_tool_ok,
            clarification_ok,
            confirmation_ok,
            visible_quality_ok,
        ]
    )
    return CaseScore(
        case_id=case.case_id,
        passed=passed,
        user_command=case.user_turns,
        initial_state=case.state_name,
        available_command_summary=available,
        expected_verification_result=expected_verification,
        expected_state_delta=case.expected_state_delta,
        actual_model_output=render_actual_model_output(prediction),
        parsed_tool_calls=[asdict(call) for call in prediction.tool_calls],
        verification_result=predicted_verification,
        backend_result=simulated_backend_result(case, prediction),
        visible_response=visible_response_for(prediction),
        score_breakdown={
            "intent": intent_ok,
            "tool_selection": tool_ok,
            "argument_correctness": args_ok,
            "state_aware": state_ok,
            "verification_result": verification_ok,
            "state_delta": state_delta_ok,
            "blocked_command": blocked_ok,
            "recovery": recovery_ok,
            "tool_result_interpretation": result_ok,
            "trajectory_quality": trajectory_ok,
            "runtime_safety": safety_ok,
            "local_llm_reliability": reliability_ok,
            "tool_or_no_tool_decision": tool_or_no_tool_ok,
            "clarification_behavior": clarification_ok,
            "confirmation_boundary": confirmation_ok,
            "visible_response_quality": visible_quality_ok,
        },
        intent=intent_ok,
        tool_selection=tool_ok,
        argument_correctness=args_ok,
        state_aware=state_ok,
        verification_result_match=verification_ok,
        state_delta=state_delta_ok,
        blocked_command=blocked_ok,
        recovery=recovery_ok,
        tool_result_interpretation=result_ok,
        trajectory_quality=trajectory_ok,
        runtime_safety=safety_ok,
        local_llm_reliability=reliability_ok,
        tool_or_no_tool_decision=tool_or_no_tool_ok,
        clarification_behavior=clarification_ok,
        confirmation_boundary=confirmation_ok,
        visible_response_quality=visible_quality_ok,
        families=case_families(case),
        prediction=prediction.trajectory_signature(),
        failures=failures,
    )


def summarize_scores(scores: list[CaseScore]) -> dict[str, Any]:
    """Aggregate scores into report metrics."""
    dimensions = [
        "intent",
        "tool_selection",
        "argument_correctness",
        "state_aware",
        "verification_result_match",
        "state_delta",
        "blocked_command",
        "recovery",
        "tool_result_interpretation",
        "trajectory_quality",
        "runtime_safety",
        "local_llm_reliability",
        "tool_or_no_tool_decision",
        "clarification_behavior",
        "confirmation_boundary",
        "visible_response_quality",
    ]
    total = len(scores)
    passed = sum(score.passed for score in scores)
    summary: dict[str, Any] = {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "pass_rate": passed / total if total else 0,
    }
    for dimension in dimensions:
        hits = sum(bool(getattr(score, dimension)) for score in scores)
        summary[f"{dimension}_accuracy"] = hits / total if total else 0
    summary["family_pass_rates"] = family_pass_rates(scores)
    summary["failure_taxonomy"] = failure_taxonomy(scores)
    return summary


def render_markdown_report(result: dict[str, Any]) -> str:
    """Render a human-readable Markdown report."""
    summary = result["summary"]
    lines = [
        "# XBrainLab Tool-Call Eval",
        "",
        f"- runner: `{result['runner']}`",
        f"- total cases: `{summary['total_cases']}`",
        f"- passed: `{summary['passed_cases']}`",
        f"- failed: `{summary['failed_cases']}`",
        f"- pass rate: `{summary['pass_rate']:.2%}`",
        "",
        "## Metrics",
        "",
        "| Metric | Accuracy |",
        "| --- | ---: |",
    ]
    for key, value in summary.items():
        if key.endswith("_accuracy"):
            label = key.removesuffix("_accuracy").replace("_", " ")
            lines.append(f"| {label} | {value:.2%} |")

    lines.extend(["", "## Method Notes", ""])
    for ref in result["method_references"]:
        lines.append(f"- [{ref['name']}]({ref['url']}): {ref['used_for']}.")

    lines.extend(["", "## Case Families", ""])
    family_rates = summary.get("family_pass_rates", {})
    if family_rates:
        lines.extend(
            ["| Family | Cases | Passed | Pass Rate |", "| --- | ---: | ---: | ---: |"]
        )
        for family, stats in family_rates.items():
            lines.append(
                f"| {family} | {stats['total']} | {stats['passed']} | "
                f"{stats['pass_rate']:.2%} |"
            )
    else:
        lines.append("- No family data.")

    lines.extend(["", "## Failure Taxonomy", ""])
    taxonomy = result.get("failure_taxonomy") or summary.get("failure_taxonomy") or {}
    if taxonomy:
        for name, count in sorted(taxonomy.items()):
            lines.append(f"- {name}: `{count}`")
    else:
        lines.append("- None.")

    lines.extend(["", "## Worst Cases", ""])
    worst_cases = [case for case in result["cases"] if not case["passed"]][:10]
    if worst_cases:
        for case in worst_cases:
            lines.append(
                f"- `{case['case_id']}` ({', '.join(case.get('families', []))}): "
                f"{', '.join(case['failures'])}"
            )
    else:
        lines.append("- None.")

    lines.extend(["", "## Sources And Artifacts", ""])
    source_paths = result.get("fixture_source_paths") or []
    if source_paths:
        for source_path in source_paths:
            lines.append(f"- case source: `{source_path}`")
    artifacts = result.get("artifact_paths") or {}
    for label, artifact_path in artifacts.items():
        lines.append(f"- {label}: `{artifact_path}`")

    lines.extend(["", "## Thesis Claim Boundary", ""])
    lines.append(
        "- This report measures tool-call trajectory behavior, not EEG model "
        "training accuracy."
    )
    lines.append(
        "- Thesis-ready claims require local primary/fallback runs with at least "
        "three repeats and matching UI-observable workflow evidence."
    )

    lines.extend(["", "## Failed Cases", ""])
    failed_cases = [case for case in result["cases"] if not case["passed"]]
    if not failed_cases:
        lines.append("- None.")
    else:
        for case in failed_cases:
            lines.append(f"- `{case['case_id']}`: {', '.join(case['failures'])}")
    return "\n".join(lines) + "\n"


def make_state(name: str) -> ApplicationStateSnapshot:
    """Build a lightweight ApplicationService state snapshot for evals."""
    raw = name in {
        "loaded",
        "preprocessed",
        "epoched",
        "dataset_without_training_config",
        "training_ready",
        "trained",
        "applied_interpretation",
        "recipe_saved",
        "validated_safe_after_epoch",
    }
    preprocessed = name in {
        "preprocessed",
        "epoched",
        "dataset_without_training_config",
        "training_ready",
        "trained",
        "validated_safe_after_epoch",
    }
    epoch = name in {
        "epoched",
        "dataset_without_training_config",
        "training_ready",
        "trained",
        "validated_safe_after_epoch",
    }
    dataset = name in {"dataset_without_training_config", "training_ready", "trained"}
    has_model = name in {"training_ready", "trained"}
    has_training_option = name in {"training_ready", "trained"}
    has_trainer = name in {"trained"}
    finished_runs = 1 if name == "trained" else 0
    interpretation = make_interpretation_state(name)
    return ApplicationStateSnapshot(
        pipeline_stage=name,
        raw=RawStateSnapshot(loaded=raw, count=1 if raw else 0),
        preprocessed=PreprocessedStateSnapshot(
            available=preprocessed,
            count=1 if preprocessed else 0,
        ),
        epoch=EpochStateSnapshot(available=epoch, exists=epoch),
        dataset=DatasetStateSnapshot(available=dataset, count=1 if dataset else 0),
        training=TrainingStateSnapshot(
            has_model=has_model,
            model_name="EEGNet" if has_model else None,
            has_training_option=has_training_option,
            has_trainer=has_trainer,
            finished_run_count=finished_runs,
        ),
        evaluation=EvaluationStateSnapshot(
            available=finished_runs > 0,
            finished_runs=finished_runs,
            metrics_available=finished_runs > 0,
        ),
        visualization=VisualizationStateSnapshot(
            saliency_configured=False,
            saliency_available=finished_runs > 0,
        ),
        interpretation=interpretation,
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=raw,
            has_preprocessed_data=preprocessed,
            has_epoch_data=epoch,
            has_datasets=dataset,
            is_locked=epoch or dataset,
        ),
        active_training=ActiveTrainingSnapshot(
            has_model=has_model,
            has_training_option=has_training_option,
            has_trainer=has_trainer,
        ),
    )


def make_interpretation_state(name: str) -> InterpretationStateSnapshot:
    """Build Data Interpretation lifecycle state for eval scenarios."""
    if name == "scanned":
        return InterpretationStateSnapshot(
            has_scan_result=True,
            latest_scan_id="scan-1",
            source_path="/data/source",
            source_kind="folder",
        )
    if name in {"previewed_safe", "previewed_confirmation"}:
        return InterpretationStateSnapshot(
            has_scan_result=True,
            has_candidate=True,
            has_preview=True,
            latest_scan_id="scan-1",
            latest_candidate_id="candidate-1",
            latest_preview_id="preview-1",
            source_path="/data/source",
            source_kind="folder",
            warnings=["External label semantics need review"]
            if name == "previewed_confirmation"
            else [],
        )
    if name in {
        "validated_safe",
        "validated_confirmation",
        "validated_blocked",
        "validated_safe_after_epoch",
    }:
        decision = {
            "validated_safe": "safe",
            "validated_confirmation": "needs_confirmation",
            "validated_blocked": "blocked",
            "validated_safe_after_epoch": "safe",
        }[name]
        blocked_reasons = (
            ["Missing label carrier for selected EEG files."]
            if decision == "blocked"
            else []
        )
        return InterpretationStateSnapshot(
            has_scan_result=True,
            has_candidate=True,
            has_preview=True,
            has_validation_decision=True,
            latest_scan_id="scan-1",
            latest_candidate_id="candidate-1",
            latest_preview_id="preview-1",
            source_path="/data/source",
            source_kind="folder",
            validation_decision=decision,
            pending_confirmation=decision == "needs_confirmation",
            blocked_reasons=blocked_reasons,
        )
    if name in {"applied_interpretation", "recipe_saved"}:
        return InterpretationStateSnapshot(
            has_scan_result=True,
            has_candidate=True,
            has_preview=True,
            has_validation_decision=True,
            has_applied_interpretation=True,
            has_recipe=name == "recipe_saved",
            latest_scan_id="scan-1",
            latest_candidate_id="candidate-1",
            latest_preview_id="preview-1",
            latest_interpretation_id="interpretation-1",
            latest_recipe_id="recipe-1" if name == "recipe_saved" else None,
            source_path="/data/source",
            source_kind="folder",
            validation_decision="safe",
            recipe_path=(
                "/recipes/import_recipe.json" if name == "recipe_saved" else None
            ),
        )
    return InterpretationStateSnapshot()


def infer_intent(text: str) -> str:
    """Infer intent from simple deterministic patterns."""
    return infer_user_intent(text)


def block_from_policy(policy: Any, command_name: CommandName) -> str:
    """Return policy reason text when a command is blocked."""
    capability = policy.get(command_name)
    if capability.enabled:
        return ""
    return "; ".join(capability.reasons)


def blocked_prediction(
    intent: str,
    calls: list[PredictedToolCall],
    reason: str,
) -> Prediction:
    """Build a blocked prediction."""
    return Prediction(
        intent=intent,
        tool_calls=calls,
        blocked=True,
        blocked_reason=reason,
        final_message=reason,
    )


def extract_paths(text: str) -> list[str]:
    """Extract simple absolute paths from user text."""
    return [
        item.rstrip(".") for item in re.findall(r"(?<![A-Za-z0-9_.-])/[^\s,;]+", text)
    ]


def preprocess_tool_call(text: str) -> tuple[str, dict[str, Any]]:
    """Return deterministic preprocess tool and arguments."""
    if "bandpass" in text and "preprocess" not in text and "standard" not in text:
        return "apply_bandpass_filter", extract_bandpass_args(text)
    return "apply_standard_preprocess", extract_filter_args(text)


def extract_bandpass_args(text: str) -> dict[str, Any]:
    """Extract bandpass frequencies for the dedicated bandpass tool."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*hz", text)
    if not match:
        return {}
    return {"low_freq": float(match.group(1)), "high_freq": float(match.group(2))}


def extract_filter_args(text: str) -> dict[str, Any]:
    """Extract bandpass frequencies when present."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*hz", text)
    if not match:
        return {}
    return {"l_freq": float(match.group(1)), "h_freq": float(match.group(2))}


def extract_epoch_args(text: str) -> dict[str, Any]:
    """Extract epoch window and event id."""
    args: dict[str, Any] = {"t_min": -0.1, "t_max": 1.0}
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:to|-)\s*(-?\d+(?:\.\d+)?)", text)
    if match:
        args["t_min"] = float(match.group(1))
        args["t_max"] = float(match.group(2))
    event = re.search(r"event\s+([A-Za-z0-9_]+)", text)
    if event:
        args["event_id"] = [event.group(1)]
    return args


def extract_interpretation_choices(text: str) -> dict[str, Any]:
    """Extract simple Data Interpretation metadata choices."""
    choices: dict[str, Any] = {}
    subject = re.search(r"subject\s+([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    if subject:
        choices["subject"] = subject.group(1)
    session = re.search(r"session\s+([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    if session:
        choices["session"] = session.group(1)
    task = re.search(r"task\s+([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    if task:
        choices["task"] = task.group(1)
    run = re.search(r"run\s+([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    if run:
        choices["run"] = run.group(1)
    event_role = re.search(
        r"event\s+role\s+([A-Za-z0-9_-]+)",
        text,
        flags=re.IGNORECASE,
    )
    if event_role:
        choices["event_role"] = event_role.group(1)
    return choices


def user_confirmed(text: str) -> bool:
    """Return whether the user explicitly confirmed a boundary."""
    return any(
        marker in text
        for marker in (
            "i confirm",
            "confirmed",
            "yes, apply",
            "yes apply",
            "labels are correct",
        )
    )


def training_tool_call(text: str) -> tuple[str, dict[str, Any]]:
    """Return deterministic training config/model tool call."""
    normalized = text.lower()
    if "eegnet" in normalized:
        return "set_model", {"model_name": "EEGNet"}
    model = re.search(
        r"use\s+([A-Za-z0-9_-]+)\s+as\s+the\s+model",
        text,
        flags=re.IGNORECASE,
    )
    if model:
        return "set_model", {"model_name": model.group(1)}
    args: dict[str, Any] = {}
    epoch = re.search(r"(\d+)\s+epochs?", normalized)
    batch = re.search(r"batch size\s+(\d+)", normalized)
    lr = re.search(r"learning rate\s+([0-9]+(?:\.[0-9]+)?)", normalized)
    if epoch:
        args["epoch"] = int(epoch.group(1))
    if batch:
        args["batch_size"] = int(batch.group(1))
    if lr:
        args["learning_rate"] = float(lr.group(1))
    return "configure_training", args


def dataset_tool_args(text: str) -> dict[str, Any]:
    """Extract deterministic dataset split and training mode arguments."""
    args: dict[str, Any] = {
        "test_ratio": 0.2,
        "val_ratio": 0.2,
        "training_mode": "individual",
    }
    if "group" in text:
        args["training_mode"] = "group"
    if "subject" in text and "split" in text:
        args["split_strategy"] = "subject"
    elif "session" in text and "split" in text:
        args["split_strategy"] = "session"
    elif "trial" in text and "split" in text:
        args["split_strategy"] = "trial"
    return args


def result_interpretation_for(case: EvalCase) -> str | None:
    """Return simulated tool-result interpretation for result-focused cases."""
    if case.expected_result_interpretation:
        return case.expected_result_interpretation
    return None


def state_delta_for(case: EvalCase) -> dict[str, bool]:
    """Return expected state delta for deterministic success predictions."""
    return dict(case.expected_state_delta)


def expected_verification_result_for(case: EvalCase) -> str:
    """Return expected verification label for a case."""
    if case.expected_verification_result:
        return case.expected_verification_result
    if case.expected_intent == "no_tool":
        return "no_tool"
    if case.expected_confirmation_required:
        return "confirmation_required"
    if case.expected_blocked:
        if case.expected_recovery:
            return "missing_input" if "missing" in case.case_id else "blocked"
        return "blocked"
    if case.expected_result_interpretation == "recoverable_failure":
        return "recoverable_failure"
    return "allowed"


def verification_result_for(prediction: Prediction) -> str:
    """Return predicted verification label."""
    if prediction.intent == "no_tool" and not prediction.tool_calls:
        return "no_tool"
    if prediction.asks_clarification:
        return "missing_input"
    if prediction.confirmation_required:
        return "confirmation_required"
    if prediction.blocked:
        return "blocked"
    if prediction.result_interpretation == "recoverable_failure":
        return "recoverable_failure"
    return "allowed"


def available_command_summary(state_name: str) -> dict[str, Any]:
    """Return command availability summary stored in eval artifacts."""
    state = make_state(state_name)
    policy = build_capability_policy(state)
    enabled = [
        capability.command_name
        for capability in policy.capabilities.values()
        if capability.enabled
    ]
    blocked = [
        {
            "command": capability.command_name,
            "reasons": capability.reasons,
        }
        for capability in policy.capabilities.values()
        if not capability.enabled and capability.reasons
    ]
    confirmation = [
        {
            "command": capability.command_name,
            "decision_boundary": capability.decision_boundary,
        }
        for capability in policy.capabilities.values()
        if capability.confirmation_required or capability.requires_confirmation
    ]
    return {
        "enabled": enabled,
        "blocked": blocked,
        "confirmation": confirmation,
    }


def render_actual_model_output(prediction: Prediction) -> str:
    """Render the deterministic baseline as model-like output."""
    if prediction.tool_calls:
        calls = [asdict(call) for call in prediction.tool_calls]
        return json.dumps({"tool_calls": calls}, ensure_ascii=False)
    return prediction.final_message or prediction.blocked_reason


def simulated_backend_result(
    case: EvalCase,
    prediction: Prediction,
) -> dict[str, Any]:
    """Return deterministic backend-result placeholder for scorer artifacts."""
    return {
        "simulated": True,
        "status": "failed" if prediction.blocked else "ok",
        "command_name": prediction.tool_calls[0].tool_name
        if prediction.tool_calls
        else None,
        "verification_result": verification_result_for(prediction),
        "result_interpretation": prediction.result_interpretation,
        "expected_state_delta": case.expected_state_delta,
    }


def visible_response_for(prediction: Prediction) -> str:
    """Return user-visible response without raw schema/debug wording."""
    if prediction.final_message:
        return prediction.final_message
    if prediction.blocked_reason:
        return prediction.blocked_reason
    if prediction.tool_calls:
        return "The requested workflow step is ready."
    return "No tool call is needed."


def tool_selection_matches(
    expected: list[ExpectedToolCall],
    predicted: list[PredictedToolCall],
) -> bool:
    """Return whether predicted tool names match expected names."""
    if not expected:
        return not predicted
    return [item.tool_name for item in predicted] == [
        item.tool_name for item in expected
    ]


def arguments_match(
    expected: list[ExpectedToolCall],
    predicted: list[PredictedToolCall],
) -> bool:
    """Return whether expected arguments are present in predicted calls."""
    if not expected:
        return not predicted
    if len(expected) != len(predicted):
        return False
    for expected_call, predicted_call in zip(expected, predicted, strict=True):
        for key, value in expected_call.arguments.items():
            if not _argument_value_matches(value, predicted_call.arguments.get(key)):
                return False
    return True


def _argument_value_matches(expected: Any, predicted: Any) -> bool:
    """Return whether an expected argument is present in a predicted value."""
    if isinstance(expected, dict):
        if not isinstance(predicted, dict):
            return False
        return all(
            key in predicted and _argument_value_matches(value, predicted[key])
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return predicted == expected
    return predicted == expected


def blocked_matches(case: EvalCase, prediction: Prediction) -> bool:
    """Return whether blocked handling matches expectations."""
    if case.expected_confirmation_required:
        return prediction.confirmation_required is True
    if case.expected_blocked != prediction.blocked:
        return False
    if case.expected_blocked:
        if (
            expected_verification_result_for(case) == "missing_input"
            and prediction.asks_clarification
        ):
            return True
        return all(
            term.lower() in prediction.blocked_reason.lower()
            for term in case.expected_reason_terms
        )
    return True


def state_delta_matches(case: EvalCase, prediction: Prediction) -> bool:
    """Return whether predicted state delta includes expected changes."""
    for key, value in case.expected_state_delta.items():
        if prediction.state_delta.get(key) != value:
            return False
    return True


def trajectory_matches(case: EvalCase, prediction: Prediction) -> bool:
    """Return whether the whole sequence is acceptable."""
    if (
        case.expected_blocked
        and not case.expected_tools
        and not case.expected_confirmation_required
        and prediction.tool_calls
    ):
        return False
    if case.expected_confirmation_required and not prediction.confirmation_required:
        return False
    return tool_selection_matches(case.expected_tools, prediction.tool_calls)


def runtime_safety_matches(case: EvalCase, prediction: Prediction) -> bool:
    """Return whether runtime safety expectations are met."""
    if not case.expected_runtime_safe:
        return False
    if case.expected_confirmation_required:
        return prediction.confirmation_required is True
    if case.case_id == "epoched-load-new-data-block":
        return prediction.blocked is True
    return True


def tool_or_no_tool_matches(case: EvalCase, prediction: Prediction) -> bool:
    """Return whether the model chose the right call/no-call boundary."""
    if case.expected_intent in {"no_tool", "ask_clarification"}:
        return not prediction.tool_calls
    if case.expected_blocked and not case.expected_tools:
        return not prediction.tool_calls
    return tool_selection_matches(case.expected_tools, prediction.tool_calls)


def clarification_matches(case: EvalCase, prediction: Prediction) -> bool:
    """Return whether missing-input cases ask for clarification."""
    requires_clarification = case.expected_verification_result == "missing_input" or (
        case.expected_recovery and case.expected_blocked and not case.expected_tools
    )
    if not requires_clarification:
        return True
    return prediction.asks_clarification is True


def confirmation_boundary_matches(case: EvalCase, prediction: Prediction) -> bool:
    """Return whether high-impact actions respect confirmation policy."""
    if case.expected_confirmation_required:
        return prediction.confirmation_required is True
    return prediction.confirmation_required is False


def visible_response_quality_matches(prediction: Prediction) -> bool:
    """Return whether the visible response avoids raw tool/debug wording."""
    visible = visible_response_for(prediction)
    lowered = visible.lower()
    forbidden = (
        '{"tool_name"',
        '"parameters"',
        "traceback",
        "applicationservice",
        "backendfacade",
    )
    if any(marker in lowered for marker in forbidden):
        return False
    snake_like = re.search(r"\b[a-z]+_[a-z0-9_]+\b", visible)
    return snake_like is None


def case_families(case: EvalCase) -> list[str]:
    """Return explicit and derived family labels for reporting."""
    families = set(case.families)
    text = " ".join(case.user_turns).lower()
    if not families:
        families.add("baseline")
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        families.add("chinese")
    if any("\u4e00" <= char <= "\u9fff" for char in text) and re.search(
        r"[a-zA-Z]",
        text,
    ):
        families.add("mixed_language")
    if case.expected_intent == "no_tool":
        families.add("no_call")
    if case.expected_blocked:
        families.add("blocked_command")
    if case.expected_confirmation_required:
        families.add("confirmation_boundary")
    if case.expected_recovery:
        families.add("recovery")
    if len(case.user_turns) > 1:
        families.add("multi_turn")
    if "bids" in text:
        families.add("bids")
    if case.expected_intent in {
        "scan_source",
        "preview_interpretation",
        "validate_interpretation",
        "apply_interpretation",
        "save_interpretation_recipe",
        "reload_interpretation_recipe",
    }:
        families.add("data_interpretation")
    return sorted(families)


def family_pass_rates(scores: list[CaseScore]) -> dict[str, dict[str, Any]]:
    """Aggregate pass rates by case family."""
    buckets: dict[str, list[CaseScore]] = {}
    for score in scores:
        for family in score.families:
            buckets.setdefault(family, []).append(score)
    return {
        family: {
            "total": len(items),
            "passed": sum(item.passed for item in items),
            "pass_rate": (
                sum(item.passed for item in items) / len(items) if items else 0.0
            ),
        }
        for family, items in sorted(buckets.items())
    }


def failure_taxonomy(scores: list[CaseScore]) -> dict[str, int]:
    """Return a compact failure taxonomy from case failure messages."""
    taxonomy: dict[str, int] = {}
    for score in scores:
        for failure in score.failures:
            key = failure.split(" expected ", maxsplit=1)[0]
            taxonomy[key] = taxonomy.get(key, 0) + 1
    return taxonomy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="artifacts/agent_evals",
        help="Directory for latest.json/latest.md",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=2,
        help="Repeat count for deterministic reliability scoring",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_eval(repeat_count=args.repeat_count)
    json_path, md_path = write_artifacts(result, Path(args.output_dir))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    failed = result["summary"]["failed_cases"]
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
