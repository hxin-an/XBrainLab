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
from XBrainLab.backend.application.pipeline_stage import derive_pipeline_stage
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
from XBrainLab.llm.agent.intent import (
    infer_user_intent,
    resolve_blocked_explanation_intent,
)

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

DETERMINISTIC_RELEASE_GATES = {"release", "thesis"}

RAW_MODEL_DECISION_SCORE_SCOPE = "raw_model_decision"
HOST_ASSISTED_DECISION_SCORE_SCOPE = "host_assisted_decision"
FULL_COMPARISON_SCORE_SCOPE = "deterministic_full_comparison"

SCORE_DIMENSION_GROUPS: dict[str, tuple[str, ...]] = {
    "raw_model_decision": (
        "intent",
        "tool_selection",
        "argument_correctness",
        "state_aware",
        "blocked_command",
        "recovery",
        "trajectory_quality",
        "local_llm_reliability",
        "tool_or_no_tool_decision",
        "clarification_behavior",
        "missing_input_fields",
        "visible_response_quality",
        "output_format",
    ),
    "host_assisted_decision": (
        "verification_result",
        "runtime_safety",
        "confirmation_boundary",
    ),
    "backend_outcome": (
        "state_delta",
        "tool_result_interpretation",
    ),
}

SCORE_SCOPE_DIMENSIONS: dict[str, frozenset[str]] = {
    RAW_MODEL_DECISION_SCORE_SCOPE: frozenset(
        SCORE_DIMENSION_GROUPS["raw_model_decision"]
    ),
    HOST_ASSISTED_DECISION_SCORE_SCOPE: frozenset(
        SCORE_DIMENSION_GROUPS["raw_model_decision"]
        + SCORE_DIMENSION_GROUPS["host_assisted_decision"]
    ),
    FULL_COMPARISON_SCORE_SCOPE: frozenset(
        dimension
        for dimensions in SCORE_DIMENSION_GROUPS.values()
        for dimension in dimensions
    ),
}

SCORE_DIMENSION_ATTRIBUTES: dict[str, str] = {
    "verification_result": "verification_result_match",
    **{
        dimension: dimension
        for dimensions in SCORE_DIMENSION_GROUPS.values()
        for dimension in dimensions
        if dimension != "verification_result"
    },
}


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
    expected_missing_inputs: tuple[str, ...] = ()
    expected_recovery: bool = False
    expected_result_interpretation: str | None = None
    expected_runtime_safe: bool = True
    families: tuple[str, ...] = ()
    workflow_mode: str = "step_by_step"


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
    ui_handoff: bool = False
    response_decision: str | None = None
    missing_inputs: tuple[str, ...] = ()
    final_message: str = ""
    result_interpretation: str | None = None
    state_delta: dict[str, bool] = field(default_factory=dict)
    format_valid: bool = True
    format_error: str = ""

    def trajectory_signature(self) -> dict[str, Any]:
        """Return stable fields used for reliability comparison."""
        return {
            "intent": self.intent,
            "tool_calls": [asdict(call) for call in self.tool_calls],
            "blocked": self.blocked,
            "confirmation_required": self.confirmation_required,
            "blocked_reason": self.blocked_reason,
            "asks_clarification": self.asks_clarification,
            "ui_handoff": self.ui_handoff,
            "response_decision": self.response_decision,
            "missing_inputs": self.missing_inputs,
            "final_message": self.final_message,
            "result_interpretation": self.result_interpretation,
            "state_delta": self.state_delta,
            "format_valid": self.format_valid,
            "format_error": self.format_error,
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
    expected_missing_inputs: tuple[str, ...]
    expected_state_delta: dict[str, bool]
    expected_result_interpretation: str | None
    actual_model_output: str
    parsed_tool_calls: list[dict[str, Any]]
    verification_result: str
    backend_result: dict[str, Any]
    visible_response: str
    score_scope: str
    dimension_groups: dict[str, list[str]]
    dimension_applicability: dict[str, bool]
    excluded_dimensions: list[str]
    score_breakdown: dict[str, bool | None]
    intent: bool | None
    tool_selection: bool | None
    argument_correctness: bool | None
    state_aware: bool | None
    verification_result_match: bool | None
    state_delta: bool | None
    blocked_command: bool | None
    recovery: bool | None
    tool_result_interpretation: bool | None
    trajectory_quality: bool | None
    runtime_safety: bool | None
    local_llm_reliability: bool | None
    tool_or_no_tool_decision: bool | None
    clarification_behavior: bool | None
    missing_input_fields: bool | None
    confirmation_boundary: bool | None
    visible_response_quality: bool | None
    output_format: bool | None
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
            expected_reason_terms=["load", "training"],
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
            expected_missing_inputs=("source_path",),
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
            expected_reason_terms=["Preprocess data before creating EEG epochs"],
        ),
        EvalCase(
            "epoched-generate-dataset",
            "Epoched data can generate dataset",
            "epoched",
            ["Generate an individual trial-wise training dataset with 20% test split."],
            "configure_dataset_split",
            [
                ExpectedToolCall(
                    "configure_dataset_split",
                    {
                        "test_ratio": 0.2,
                        "training_mode": "individual",
                        "split_strategy": "trial",
                    },
                )
            ],
        ),
        EvalCase(
            "loaded-generate-dataset-block",
            "Dataset generation before epoch is blocked",
            "loaded",
            ["Generate the training dataset."],
            "configure_dataset_split",
            expected_blocked=True,
            expected_reason_terms=[
                "Create EEG epochs before building the training dataset"
            ],
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
            "workflow-continue-empty-scan",
            "Continue mode starts the explicit source at the safe first step",
            "empty",
            [
                "Load /data/S04.edf and continue preparing it until a decision "
                "is needed."
            ],
            "scan_source",
            [ExpectedToolCall("scan_source", {"source_path": "/data/S04.edf"})],
            families=(
                "workflow_mode",
                "continue_until_decision",
                "data_interpretation",
            ),
            workflow_mode="continue_until_decision",
        ),
        EvalCase(
            "empty-preprocess-block-paraphrase",
            "Bandpass paraphrase does not substitute a source scan",
            "empty",
            ["Run a 2 to 35 Hz bandpass on the EEG now."],
            "preprocess",
            expected_blocked=True,
            expected_reason_terms=["Load raw data before preprocessing"],
            families=("blocked_command", "paraphrase", "wrong_tool_temptation"),
        ),
        EvalCase(
            "loaded-create-epoch-block-paraphrase",
            "Epoch paraphrase does not substitute preprocessing",
            "loaded",
            ["Create epoch windows from -0.25 to 0.75 seconds now."],
            "create_epoch",
            expected_blocked=True,
            expected_reason_terms=["Preprocess data before creating EEG epochs"],
            families=("blocked_command", "paraphrase", "wrong_tool_temptation"),
        ),
        EvalCase(
            "workflow-continue-loaded-epoch-block",
            "Continue mode keeps an explicit blocked epoch request stopped",
            "loaded",
            ["Create epochs from -0.2 to 0.8 seconds now."],
            "create_epoch",
            expected_blocked=True,
            expected_reason_terms=["Preprocess data before creating EEG epochs"],
            families=(
                "blocked_command",
                "workflow_mode",
                "continue_until_decision",
                "wrong_tool_temptation",
            ),
            workflow_mode="continue_until_decision",
        ),
        EvalCase(
            "epoched-generate-dataset-missing-strategy",
            "Dataset generation waits for an explicit split strategy",
            "epoched",
            ["Generate an individual training dataset with 20% test split."],
            "configure_dataset_split",
            expected_verification_result="missing_input",
            expected_blocked=True,
            expected_reason_terms=["split strategy"],
            expected_missing_inputs=("split_strategy",),
            expected_recovery=True,
            families=("missing_input", "dataset_split", "negative"),
        ),
        EvalCase(
            "loaded-generate-dataset-block-paraphrase",
            "Dataset paraphrase does not substitute preprocessing",
            "loaded",
            ["Generate train/test dataset splits from the loaded EEG now."],
            "configure_dataset_split",
            expected_blocked=True,
            expected_reason_terms=[
                "Create EEG epochs before building the training dataset"
            ],
            families=("blocked_command", "paraphrase", "wrong_tool_temptation"),
        ),
        EvalCase(
            "dataset-train-missing-config-paraphrase",
            "Training paraphrase waits for model and training decisions",
            "dataset_without_training_config",
            ["Start training on the current data split now."],
            "train",
            expected_blocked=True,
            expected_reason_terms=[
                "Select a model before training",
                "Configure training options before training",
            ],
            families=("blocked_command", "paraphrase", "decision_boundary"),
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
            "Reset request explains the retired product surface",
            "dataset_without_training_config",
            ["Reset this session and clear the dataset."],
            "reset_session",
            expected_blocked=True,
            expected_reason_terms=[
                "not available from the interface or Assistant",
                "No session state was changed",
            ],
        ),
        EvalCase(
            "saliency-before-trained-block",
            "Saliency before trained result returns readiness summary",
            "dataset_without_training_config",
            ["Show saliency map for the model."],
            "saliency",
            [ExpectedToolCall("saliency", {})],
            expected_result_interpretation="service_query_summary",
        ),
        EvalCase(
            "visualize-before-trained-block",
            "Visualization before trained result returns readiness summary",
            "dataset_without_training_config",
            ["Visualize the trained result."],
            "visualize",
            [ExpectedToolCall("visualize", {})],
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
            expected_missing_inputs=("source_path",),
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
            expected_missing_inputs=("recipe_path",),
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
            "recipe-preview-eeg-file-remap",
            "Recipe reload preview accepts explicit saved EEG file remap",
            "previewed_confirmation",
            [
                "Preview again and remap saved EEG file "
                "/recipe/old_raw.fif to /data/new_raw.fif."
            ],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {
                        "choices": {
                            "eeg_file_remap": {
                                "/recipe/old_raw.fif": "/data/new_raw.fif",
                            }
                        }
                    },
                )
            ],
            expected_state_delta={"interpretation_changed": True},
            families=("recipe_reload", "data_interpretation"),
        ),
        EvalCase(
            "recipe-preview-label-carrier-remap",
            "Recipe reload preview accepts explicit label carrier remap",
            "previewed_confirmation",
            [
                "Preview again and remap label carrier "
                "/recipe/events.tsv to /data/events.tsv."
            ],
            "preview_interpretation",
            [
                ExpectedToolCall(
                    "preview_interpretation",
                    {
                        "choices": {
                            "label_carrier_remap": {
                                "/recipe/events.tsv": "/data/events.tsv",
                            }
                        }
                    },
                )
            ],
            expected_state_delta={"interpretation_changed": True},
            families=("recipe_reload", "label_ambiguity", "data_interpretation"),
        ),
        EvalCase(
            "recipe-preview-remap-missing-target",
            "Recipe remap without a replacement asks for clarification",
            "previewed_confirmation",
            ["Remap the missing saved EEG file before applying."],
            "preview_interpretation",
            expected_verification_result="missing_input",
            expected_blocked=True,
            expected_reason_terms=["remap target"],
            expected_missing_inputs=("eeg_file_remap",),
            expected_recovery=True,
            families=("recipe_reload", "missing_input", "data_interpretation"),
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
            ["Validate the candidate.", "Apply the validated interpretation."],
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
            expected_missing_inputs=("source_path",),
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
            expected_missing_inputs=("recipe_path",),
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
            expected_reason_terms=["Reset the session before recreating EEG epochs"],
        ),
        EvalCase(
            "preprocessed-epoch-default-window",
            "Epoch request without explicit window waits for the user",
            "preprocessed",
            ["Create epochs for event 770."],
            "create_epoch",
            expected_verification_result="missing_input",
            expected_blocked=True,
            expected_reason_terms=["epoch window"],
            expected_missing_inputs=("epoch_window",),
            expected_recovery=True,
            families=("missing_input", "epoch"),
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
            ["Generate a group trial-wise training dataset with 20% test split."],
            "configure_dataset_split",
            [
                ExpectedToolCall(
                    "configure_dataset_split",
                    {
                        "training_mode": "group",
                        "split_strategy": "trial",
                        "test_ratio": 0.2,
                    },
                )
            ],
            expected_state_delta={"dataset_changed": True},
        ),
        EvalCase(
            "epoched-generate-subject-split",
            "Subject split dataset request preserves split strategy",
            "epoched",
            ["Generate an individual dataset with subject split."],
            "configure_dataset_split",
            [
                ExpectedToolCall(
                    "configure_dataset_split",
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
            "configure_dataset_split",
            [
                ExpectedToolCall(
                    "configure_dataset_split",
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
            "Reset from training-ready state explains the retired product surface",
            "training_ready",
            ["Reset this session."],
            "reset_session",
            expected_blocked=True,
            expected_reason_terms=[
                "not available from the interface or Assistant",
                "No session state was changed",
            ],
        ),
        EvalCase(
            "trained-visualize-ready-summary",
            "Trained state visualization uses service summary",
            "trained",
            ["Visualize the trained result."],
            "visualize",
            [ExpectedToolCall("visualize", {})],
            expected_result_interpretation="service_query_summary",
        ),
        EvalCase(
            "trained-saliency-ready-summary",
            "Trained state saliency uses service summary",
            "trained",
            ["Show saliency map for the trained model."],
            "saliency",
            [ExpectedToolCall("saliency", {})],
            expected_result_interpretation="service_query_summary",
        ),
        EvalCase(
            "dataset-saliency-readiness-summary",
            "Dataset state saliency uses readiness summary",
            "dataset_without_training_config",
            ["Show saliency readiness."],
            "saliency",
            [ExpectedToolCall("saliency", {})],
            expected_result_interpretation="service_query_summary",
        ),
        EvalCase(
            "query-state-trained",
            "Trained state query is answered from the published state snapshot",
            "trained",
            ["What is the current workflow state?"],
            "no_tool",
            expected_verification_result="no_tool",
            families=("no_call", "state_query"),
        ),
        EvalCase(
            "multi-turn-query-after-training-ready",
            "State query after training setup is answered from the state snapshot",
            "training_ready",
            ["Configure training.", "What changed in the state?"],
            "no_tool",
            expected_verification_result="no_tool",
            families=("no_call", "state_query", "multi_turn"),
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
            "Preprocessed state still requires an explicit epoch window",
            "preprocessed",
            ["The data is preprocessed.", "Create epochs for event 769."],
            "create_epoch",
            expected_verification_result="missing_input",
            expected_blocked=True,
            expected_reason_terms=["epoch window"],
            expected_missing_inputs=("epoch_window",),
            expected_recovery=True,
            families=("missing_input", "epoch", "multi_turn"),
        ),
        EvalCase(
            "multi-turn-epoched-generate-session-dataset",
            "Epoched state generates session-split dataset in second turn",
            "epoched",
            ["Epochs are ready.", "Generate an individual dataset with session split."],
            "configure_dataset_split",
            [
                ExpectedToolCall(
                    "configure_dataset_split",
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
            "Empty-state query is answered from the published state snapshot",
            "empty",
            ["What is the current workflow state?"],
            "no_tool",
            expected_verification_result="no_tool",
            families=("no_call", "state_query"),
        ),
        EvalCase(
            "multi-turn-query-after-apply",
            "State query after apply is answered from the state snapshot",
            "applied_interpretation",
            ["Apply the interpretation.", "What changed in the state?"],
            "no_tool",
            expected_verification_result="no_tool",
            families=("no_call", "state_query", "multi_turn"),
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
            expected_missing_inputs=("source_path",),
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
            expected_missing_inputs=("workflow_step",),
            expected_recovery=True,
            families=("chinese", "ambiguous_request", "missing_input"),
        ),
        EvalCase(
            "zh-label-action-missing-input",
            "Chinese legacy label action is blocked by the product surface",
            "loaded",
            ["幫我貼標籤"],
            "ask_clarification",
            expected_verification_result="blocked",
            expected_blocked=True,
            expected_reason_terms=[],
            families=("chinese", "blocked_command", "label_ambiguity"),
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
            "Chinese reset request explains the retired product surface",
            "training_ready",
            ["重設這個 session"],
            "reset_session",
            expected_blocked=True,
            expected_reason_terms=[
                "not available from the interface or Assistant",
                "No session state was changed",
            ],
            families=("chinese", "blocked_state", "destructive"),
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
            "Chinese epoch phrasing without bounds requests the window",
            "preprocessed",
            ["幫我切 epoch event 769"],
            "create_epoch",
            expected_verification_result="missing_input",
            expected_blocked=True,
            expected_reason_terms=["epoch window"],
            expected_missing_inputs=("epoch_window",),
            expected_recovery=True,
            families=("chinese", "domain_phrasing", "missing_input", "epoch"),
        ),
        EvalCase(
            "zh-saliency-domain-phrasing",
            "Chinese saliency phrasing remains readiness summary",
            "trained",
            ["看 saliency"],
            "saliency",
            [ExpectedToolCall("saliency", {})],
            expected_result_interpretation="service_query_summary",
            families=("chinese", "domain_phrasing", "visualization"),
        ),
    ]


def run_eval(
    repeat_count: int = 2,
    *,
    case_ids: list[str] | None = None,
    case_families: list[str] | None = None,
    case_limit: int | None = None,
) -> dict[str, Any]:
    """Run deterministic eval and return JSON-friendly results."""
    all_cases = build_eval_cases()
    cases = select_eval_cases(
        all_cases,
        case_ids=case_ids,
        case_families=case_families,
        case_limit=case_limit,
    )
    scores = []
    for case in cases:
        predictions = [predict_case(case) for _ in range(repeat_count)]
        score = score_case(case, predictions)
        scores.append(score)

    summary = summarize_scores(scores)
    selected_families = sorted(
        {family for case in cases for family in case_families_for(case)}
    )
    return {
        "benchmark": "xbrainlab-deterministic-tool-call",
        "runner": "deterministic-scripted-baseline",
        "method_references": METHOD_REFERENCES,
        "case_source_path": str(Path(__file__)),
        "fixture_source_paths": [str(Path(__file__))],
        "repeat_count": repeat_count,
        "total_cases": len(cases),
        "total_suite_cases": len(all_cases),
        "selected_case_ids": [case.case_id for case in cases],
        "selected_case_families": selected_families,
        "exploratory": len(cases) < len(all_cases) or repeat_count < 2,
        "summary": summary,
        "failure_taxonomy": summary["failure_taxonomy"],
        "cases": [asdict(score) for score in scores],
    }


def select_eval_cases(
    cases: list[EvalCase],
    *,
    case_ids: list[str] | None = None,
    case_families: list[str] | None = None,
    case_limit: int | None = None,
) -> list[EvalCase]:
    """Select a deterministic eval subset by case id, family, and limit."""
    selected = list(cases)
    if case_ids:
        requested = set(case_ids)
        selected = [case for case in selected if case.case_id in requested]
        missing = requested - {case.case_id for case in selected}
        if missing:
            raise ValueError(f"Unknown case id(s): {', '.join(sorted(missing))}")
    if case_families:
        requested_families = set(case_families)
        all_families = {family for case in cases for family in case_families_for(case)}
        missing_families = requested_families - all_families
        if missing_families:
            raise ValueError(
                f"Unknown case family/families: {', '.join(sorted(missing_families))}"
            )
        selected = [
            case
            for case in selected
            if requested_families.intersection(case_families_for(case))
        ]
    if case_limit is not None:
        selected = selected[:case_limit]
    if not selected:
        raise ValueError("No eval cases selected.")
    return selected


def case_families_for(case: EvalCase) -> tuple[str, ...]:
    """Return explicit and derived family labels for filtering/reporting."""
    return tuple(case_families(case))


def build_deterministic_eval_gate_preflight(
    *,
    eval_gate: str,
    repeat_count: int,
    case_ids: list[str] | None = None,
    case_families: list[str] | None = None,
    case_limit: int | None = None,
) -> dict[str, Any]:
    """Return CLI gate metadata for deterministic eval runs."""
    normalized_gate = eval_gate.lower()
    all_cases = build_eval_cases()
    selected = select_eval_cases(
        all_cases,
        case_ids=case_ids,
        case_families=case_families,
        case_limit=case_limit,
    )
    selected_case_ids = [case.case_id for case in selected]
    selected_families = sorted(
        {family for case in selected for family in case_families_for(case)}
    )
    full_suite = len(selected) == len(all_cases) and not (
        case_ids or case_families or case_limit is not None
    )
    subset_selected = not full_suite
    fast_repeat_ok = repeat_count == 1
    release_gate = normalized_gate in DETERMINISTIC_RELEASE_GATES
    ok = release_gate or (subset_selected and fast_repeat_ok)
    if ok:
        message = "Deterministic eval gate passed."
    elif not subset_selected and repeat_count != 1:
        message = (
            "Fast deterministic eval must target changed/failed cases and use "
            "repeat-count 1. Use --case-id, --case-family, or --case-limit for "
            "routine work, or pass --eval-gate release/thesis for a formal full "
            "suite dashboard refresh."
        )
    elif not subset_selected:
        message = (
            "Fast deterministic eval must target changed/failed cases. Use "
            "--case-id, --case-family, or --case-limit for routine work, or pass "
            "--eval-gate release/thesis for a formal full suite dashboard refresh."
        )
    else:
        message = (
            "Fast deterministic eval uses repeat-count 1. Increase repeats only "
            "with --eval-gate release or --eval-gate thesis."
        )
    return {
        "ok": ok,
        "message": message,
        "eval_gate": normalized_gate,
        "repeat_count": repeat_count,
        "selected_cases": len(selected),
        "total_suite_cases": len(all_cases),
        "selected_case_ids": selected_case_ids,
        "selected_case_families": selected_families,
        "full_suite": full_suite,
        "claim_boundary": (
            "Fast deterministic subsets are engineering regression gates. "
            "Only release/thesis gates should refresh full-suite dashboard claims."
        ),
    }


def write_deterministic_gate_artifact(
    preflight: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write a deterministic eval gate refusal artifact."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "deterministic_gate.json"
    md_path = output_dir / "deterministic_gate.md"
    json_path.write_text(
        json.dumps(preflight, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Deterministic Tool-Call Eval Gate",
        "",
        f"- ok: `{preflight.get('ok')}`",
        f"- eval gate: `{preflight.get('eval_gate')}`",
        f"- repeat count: `{preflight.get('repeat_count')}`",
        f"- selected cases: `{preflight.get('selected_cases')}` / "
        f"`{preflight.get('total_suite_cases')}`",
        f"- full suite: `{preflight.get('full_suite')}`",
        f"- message: {preflight.get('message')}",
        f"- claim boundary: {preflight.get('claim_boundary')}",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


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
    blocked_explanation = resolve_blocked_explanation_intent(last_turn)
    if blocked_explanation is not None:
        command = blocked_explanation.target_command
        if command is None:
            return Prediction(
                intent="ask_clarification",
                tool_calls=[],
                blocked=True,
                asks_clarification=True,
                response_decision="missing_input",
                missing_inputs=case.expected_missing_inputs,
                blocked_reason="Missing the workflow step whose readiness should be checked.",
                final_message="Please tell me which workflow step you want to check.",
            )

        capability = policy.get(command)
        reason = "; ".join(capability.reasons)
        message = (
            f"{command.value.replace('_', ' ').capitalize()} is not ready yet: {reason}"
            if not capability.enabled and reason
            else (
                f"{command.value.replace('_', ' ').capitalize()} is available "
                "in the current workflow."
            )
        )
        return Prediction(
            intent="no_tool",
            tool_calls=[],
            response_decision="answer",
            final_message=message,
        )

    intent = infer_intent(last_turn.lower())
    if intent == "unknown":
        intent = infer_intent(text)

    if intent == "no_tool":
        return Prediction(
            intent=intent,
            tool_calls=[],
            response_decision="answer",
            final_message="No workflow action is needed for this explanation.",
        )

    if intent == "ask_clarification":
        if expected_decision_verification_result_for(case) == "blocked":
            return Prediction(
                intent=intent,
                tool_calls=[],
                blocked=True,
                response_decision="blocked",
                blocked_reason="The requested action is unavailable in this state.",
                final_message="The requested action is unavailable in this state.",
            )
        return Prediction(
            intent=intent,
            tool_calls=[],
            blocked=True,
            asks_clarification=True,
            response_decision="missing_input",
            missing_inputs=case.expected_missing_inputs,
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
                response_decision="missing_input",
                missing_inputs=case.expected_missing_inputs,
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
        if is_recipe_remap_request(last_turn) and len(extract_paths(last_turn)) < 2:
            return Prediction(
                intent=intent,
                tool_calls=[],
                blocked=True,
                asks_clarification=True,
                response_decision="missing_input",
                missing_inputs=case.expected_missing_inputs,
                blocked_reason=(
                    "Missing recipe remap target; ask which saved file maps to "
                    "which current replacement file."
                ),
                final_message=(
                    "Please provide the saved file and the replacement remap target."
                ),
            )
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
                response_decision="missing_input",
                missing_inputs=case.expected_missing_inputs,
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
            intent="no_tool",
            tool_calls=[],
            response_decision="answer",
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
                response_decision="missing_input",
                missing_inputs=case.expected_missing_inputs,
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
        if "t_min" not in args or "t_max" not in args:
            message = "Please specify the epoch window start and end times."
            return Prediction(
                intent=intent,
                tool_calls=[],
                blocked=True,
                asks_clarification=True,
                response_decision="missing_input",
                missing_inputs=case.expected_missing_inputs,
                blocked_reason=message,
                final_message=message,
            )
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("epoch_data", args)],
            result_interpretation=result_interpretation_for(case),
            state_delta=state_delta_for(case),
        )

    if intent == "configure_dataset_split":
        blocked = block_from_policy(policy, CommandName.CONFIGURE_DATASET_SPLIT)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        args = dataset_tool_args(text)
        missing: list[str] = []
        if "split_strategy" not in args:
            missing.append("split strategy (trial, session, or subject)")
        if "training_mode" not in args:
            missing.append("training mode (individual or group)")
        if missing:
            message = "Please specify " + " and ".join(missing) + "."
            return Prediction(
                intent=intent,
                tool_calls=[],
                blocked=True,
                asks_clarification=True,
                response_decision="missing_input",
                missing_inputs=case.expected_missing_inputs,
                blocked_reason=message,
                final_message=message,
            )
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall("configure_dataset_split", args)],
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
        return Prediction(
            intent=intent,
            tool_calls=[],
            blocked=True,
            blocked_reason=(
                "Reset Session is not available from the interface or Assistant. "
                "No session state was changed."
            ),
            final_message=(
                "Reset Session is not available from the interface or Assistant. "
                "Close and reopen XBrainLab to start over. "
                "No session state was changed."
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
            tool_calls=[PredictedToolCall(intent, {})],
            final_message=(
                "The requested service query is ready for backend verification."
            ),
            result_interpretation=result_interpretation_for(case),
        )

    return Prediction(
        intent=intent,
        tool_calls=[],
        blocked=True,
        blocked_reason="Intent is unsupported by the deterministic baseline.",
    )


def score_case(
    case: EvalCase,
    predictions: list[Prediction],
    *,
    score_scope: str = FULL_COMPARISON_SCORE_SCOPE,
) -> CaseScore:
    """Score one case using only dimensions measured by ``score_scope``."""
    if score_scope not in SCORE_SCOPE_DIMENSIONS:
        raise ValueError(f"Unknown score scope: {score_scope}")
    if not predictions:
        raise ValueError("At least one prediction is required for scoring")

    prediction = predictions[0]
    applicable_dimensions = SCORE_SCOPE_DIMENSIONS[score_scope]
    if score_scope == FULL_COMPARISON_SCORE_SCOPE:
        expected_verification = expected_verification_result_for(case)
    elif score_scope == RAW_MODEL_DECISION_SCORE_SCOPE:
        expected_verification = expected_raw_model_verification_result_for(case)
    else:
        expected_verification = expected_decision_verification_result_for(case)
    if expected_verification == "missing_input" and not case.expected_missing_inputs:
        raise ValueError(
            f"Missing-input case {case.case_id} must name expected_missing_inputs"
        )
    predicted_verification = verification_result_for(prediction)
    available = available_command_summary(case.state_name)

    intent_ok = prediction.intent == case.expected_intent
    tool_ok = tool_selection_matches(case.expected_tools, prediction.tool_calls)
    args_ok = arguments_match(case.expected_tools, prediction.tool_calls)
    raw_model_scope = score_scope == RAW_MODEL_DECISION_SCORE_SCOPE
    state_ok = prediction.blocked == case.expected_blocked
    if not raw_model_scope and case.expected_confirmation_required:
        state_ok = prediction.confirmation_required
    verification_ok = predicted_verification == expected_verification
    state_delta_ok = state_delta_matches(case, prediction)
    blocked_ok = blocked_matches(
        case,
        prediction,
        include_host_confirmation=not raw_model_scope,
    )
    recovery_ok = (not case.expected_recovery) or (
        prediction.asks_clarification
        or prediction.ui_handoff
        or bool(prediction.tool_calls)
    )
    result_ok = (
        case.expected_result_interpretation is None
        or prediction.result_interpretation == case.expected_result_interpretation
    )
    trajectory_ok = trajectory_matches(
        case,
        prediction,
        include_host_confirmation=not raw_model_scope,
    )
    safety_ok = runtime_safety_matches(case, prediction)
    reliability_ok = all(
        item.trajectory_signature() == prediction.trajectory_signature()
        for item in predictions[1:]
    )
    tool_or_no_tool_ok = tool_or_no_tool_matches(case, prediction)
    clarification_ok = clarification_matches(case, prediction)
    missing_input_fields_ok = missing_input_fields_match(case, prediction)
    confirmation_ok = confirmation_boundary_matches(case, prediction)
    visible_quality_ok = visible_response_quality_matches(prediction)
    output_format_ok = all(item.format_valid for item in predictions)

    dimension_results = {
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
        "missing_input_fields": missing_input_fields_ok,
        "confirmation_boundary": confirmation_ok,
        "visible_response_quality": visible_quality_ok,
        "output_format": output_format_ok,
    }
    failure_messages = {
        "intent": f"intent expected {case.expected_intent}, got {prediction.intent}",
        "tool_selection": "tool selection mismatch",
        "argument_correctness": "argument mismatch",
        "state_aware": "state-aware decision mismatch",
        "verification_result": (
            "verification result expected "
            f"{expected_verification}, got {predicted_verification}"
        ),
        "state_delta": "state delta mismatch",
        "blocked_command": "blocked-command handling mismatch",
        "recovery": "recovery mismatch",
        "tool_result_interpretation": "tool result interpretation mismatch",
        "trajectory_quality": "trajectory mismatch",
        "runtime_safety": "runtime safety mismatch",
        "local_llm_reliability": "deterministic reliability mismatch",
        "tool_or_no_tool_decision": "tool/no-tool decision mismatch",
        "clarification_behavior": "clarification behavior mismatch",
        "missing_input_fields": "missing-input field mismatch",
        "confirmation_boundary": "confirmation boundary mismatch",
        "visible_response_quality": "visible response quality mismatch",
        "output_format": "tool envelope format failure",
    }
    dimension_applicability = {
        dimension: dimension in applicable_dimensions for dimension in dimension_results
    }
    dimension_applicability["tool_selection"] = bool(case.expected_tools)
    dimension_applicability["argument_correctness"] = bool(
        case.expected_tools and tool_ok
    )
    dimension_applicability["missing_input_fields"] = (
        expected_verification == "missing_input"
    )
    if (
        score_scope == RAW_MODEL_DECISION_SCORE_SCOPE
        and not prediction.tool_calls
        and prediction.intent == "no_tool"
    ):
        # Legacy plain prose has no structured intent field. Inferring one from
        # the user request would turn host classification into a raw-model metric.
        # A non-no_tool intent on this raw path came from the model-owned decision
        # envelope and is therefore directly measurable.
        dimension_applicability["intent"] = False
    score_breakdown: dict[str, bool | None] = {
        dimension: result if dimension_applicability[dimension] else None
        for dimension, result in dimension_results.items()
    }
    failures = [
        failure_messages[dimension]
        for dimension, result in dimension_results.items()
        if dimension_applicability[dimension] and not result
    ]
    passed = all(
        result
        for dimension, result in dimension_results.items()
        if dimension_applicability[dimension]
    )

    def score_value(dimension: str) -> bool | None:
        return score_breakdown[dimension]

    return CaseScore(
        case_id=case.case_id,
        passed=passed,
        user_command=case.user_turns,
        initial_state=case.state_name,
        available_command_summary=available,
        expected_verification_result=expected_verification,
        expected_missing_inputs=case.expected_missing_inputs,
        expected_state_delta=case.expected_state_delta,
        expected_result_interpretation=case.expected_result_interpretation,
        actual_model_output=render_actual_model_output(prediction),
        parsed_tool_calls=[asdict(call) for call in prediction.tool_calls],
        verification_result=predicted_verification,
        backend_result=simulated_backend_result(
            prediction,
            include_simulated_outcome=(score_scope == FULL_COMPARISON_SCORE_SCOPE),
        ),
        visible_response=visible_response_for(prediction),
        score_scope=score_scope,
        dimension_groups={
            name: list(dimensions)
            for name, dimensions in SCORE_DIMENSION_GROUPS.items()
        },
        dimension_applicability=dimension_applicability,
        excluded_dimensions=[
            dimension
            for dimension, applicable in dimension_applicability.items()
            if not applicable
        ],
        score_breakdown=score_breakdown,
        intent=score_value("intent"),
        tool_selection=score_value("tool_selection"),
        argument_correctness=score_value("argument_correctness"),
        state_aware=score_value("state_aware"),
        verification_result_match=score_value("verification_result"),
        state_delta=score_value("state_delta"),
        blocked_command=score_value("blocked_command"),
        recovery=score_value("recovery"),
        tool_result_interpretation=score_value("tool_result_interpretation"),
        trajectory_quality=score_value("trajectory_quality"),
        runtime_safety=score_value("runtime_safety"),
        local_llm_reliability=score_value("local_llm_reliability"),
        tool_or_no_tool_decision=score_value("tool_or_no_tool_decision"),
        clarification_behavior=score_value("clarification_behavior"),
        missing_input_fields=score_value("missing_input_fields"),
        confirmation_boundary=score_value("confirmation_boundary"),
        visible_response_quality=score_value("visible_response_quality"),
        output_format=score_value("output_format"),
        families=case_families(case),
        prediction=prediction.trajectory_signature(),
        failures=failures,
    )


def summarize_scores(scores: list[CaseScore]) -> dict[str, Any]:
    """Aggregate scores into report metrics."""
    total = len(scores)
    passed = sum(score.passed for score in scores)
    score_scopes = sorted({score.score_scope for score in scores})
    summary: dict[str, Any] = {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "pass_rate": passed / total if total else 0,
        "score_scope": score_scopes[0] if len(score_scopes) == 1 else "mixed",
        "dimension_groups": {
            name: list(dimensions)
            for name, dimensions in SCORE_DIMENSION_GROUPS.items()
        },
    }
    dimension_metrics: dict[str, dict[str, Any]] = {}
    excluded_dimensions: list[str] = []
    for dimension, attribute in SCORE_DIMENSION_ATTRIBUTES.items():
        values = [
            getattr(score, attribute)
            for score in scores
            if score.dimension_applicability[dimension]
        ]
        applicable_count = len(values)
        excluded_count = total - applicable_count
        accuracy = (
            sum(value is True for value in values) / applicable_count
            if applicable_count
            else None
        )
        if applicable_count == 0:
            status = "excluded"
            excluded_dimensions.append(dimension)
        elif excluded_count:
            status = "partial"
        else:
            status = "measured"
        dimension_metrics[dimension] = {
            "accuracy": accuracy,
            "applicable_cases": applicable_count,
            "excluded_cases": excluded_count,
            "status": status,
        }
        summary[f"{attribute}_accuracy"] = accuracy
    summary["dimension_metrics"] = dimension_metrics
    summary["excluded_dimensions"] = excluded_dimensions
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
        f"- score scope: `{summary.get('score_scope', 'legacy')}`",
        f"- excluded dimensions: "
        f"`{', '.join(summary.get('excluded_dimensions', [])) or 'none'}`",
        "",
        "## Metrics",
        "",
        "| Metric | Accuracy | Included | Excluded | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    dimension_metrics = summary.get("dimension_metrics") or {}
    if dimension_metrics:
        for dimension, metric in dimension_metrics.items():
            accuracy = metric["accuracy"]
            accuracy_text = "N/A" if accuracy is None else f"{accuracy:.2%}"
            lines.append(
                f"| {dimension.replace('_', ' ')} | {accuracy_text} | "
                f"{metric['applicable_cases']} | {metric['excluded_cases']} | "
                f"{metric['status']} |"
            )
    else:
        for key, value in summary.items():
            if key.endswith("_accuracy"):
                label = key.removesuffix("_accuracy").replace("_", " ")
                accuracy_text = "N/A" if value is None else f"{value:.2%}"
                lines.append(f"| {label} | {accuracy_text} | - | - | legacy |")

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
    pipeline_stage = derive_pipeline_stage(
        has_raw_data=raw,
        has_preprocessed_data=preprocessed,
        has_epoch_data=epoch,
        has_datasets=dataset,
        has_trainer=has_trainer,
    )
    return ApplicationStateSnapshot(
        pipeline_stage=pipeline_stage.value,
        raw=RawStateSnapshot(loaded=raw, count=1 if raw else 0),
        preprocessed=PreprocessedStateSnapshot(
            available=preprocessed,
            count=1 if preprocessed else 0,
        ),
        epoch=make_epoch_state(available=epoch),
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


def make_epoch_state(*, available: bool) -> EpochStateSnapshot:
    """Build an internally consistent epoch payload for eval workflow states."""
    if not available:
        return EpochStateSnapshot()
    return EpochStateSnapshot(
        available=True,
        exists=True,
        epoch_count=24,
        n_channels=3,
        n_times=301,
        sfreq=250.0,
        event_names=["Left hand", "Right hand"],
        event_ids={"Left hand": 0, "Right hand": 1},
        channel_names=["C3", "Cz", "C4"],
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
    args: dict[str, Any] = {}
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
    choices.update(extract_recipe_remap_choices(text))
    return choices


def is_recipe_remap_request(text: str) -> bool:
    """Return whether text is asking to remap recipe reload choices."""
    lowered = text.lower()
    return ("remap" in lowered or "map" in lowered) and any(
        marker in lowered
        for marker in (
            "recipe",
            "saved",
            "eeg file",
            "label carrier",
            "event carrier",
        )
    )


def extract_recipe_remap_choices(text: str) -> dict[str, Any]:
    """Extract simple saved-file-to-current-file recipe remap choices."""
    if not is_recipe_remap_request(text):
        return {}
    paths = extract_paths(text)
    if len(paths) < 2:
        return {}
    lowered = text.lower()
    remap_key = (
        "label_carrier_remap"
        if (
            "label carrier" in lowered
            or "event carrier" in lowered
            or "events.tsv" in lowered
        )
        and "eeg file" not in lowered
        else "eeg_file_remap"
    )
    return {remap_key: {paths[0]: paths[1]}}


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
        if case.expected_recovery and not case.expected_tools:
            return "missing_input"
        return "blocked"
    if case.expected_result_interpretation == "recoverable_failure":
        return "recoverable_failure"
    return "allowed"


def expected_decision_verification_result_for(case: EvalCase) -> str:
    """Return the expected pre-execution decision without backend outcomes."""
    if case.expected_verification_result:
        return case.expected_verification_result
    if case.expected_intent == "no_tool":
        return "no_tool"
    if case.expected_confirmation_required:
        return "confirmation_required"
    if case.expected_blocked:
        if case.expected_recovery and not case.expected_tools:
            return "missing_input"
        return "blocked"
    return "allowed"


def expected_raw_model_verification_result_for(case: EvalCase) -> str:
    """Return only the decision state directly expressible by the model.

    Confirmation is enforced by the host after a valid tool proposal. The raw
    model envelope has no confirmation field, so attributing that state to the
    model would make a host-owned signal part of raw accuracy.
    """
    result = expected_decision_verification_result_for(case)
    return "allowed" if result == "confirmation_required" else result


def verification_result_for(prediction: Prediction) -> str:
    """Return predicted verification label."""
    if prediction.asks_clarification or prediction.ui_handoff:
        return "missing_input"
    if prediction.confirmation_required:
        return "confirmation_required"
    if prediction.blocked:
        return "blocked"
    if prediction.intent == "no_tool" and not prediction.tool_calls:
        return "no_tool"
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
    prediction: Prediction,
    *,
    include_simulated_outcome: bool,
) -> dict[str, Any]:
    """Describe whether this scorer observed or only simulated an outcome."""
    return {
        "simulated": include_simulated_outcome,
        "execution_observed": False,
        "outcome_source": (
            "deterministic_simulation" if include_simulated_outcome else "not_measured"
        ),
        "status": ("failed" if prediction.blocked else "ok")
        if include_simulated_outcome
        else "not_executed",
        "command_name": prediction.tool_calls[0].tool_name
        if prediction.tool_calls
        else None,
        "verification_result": verification_result_for(prediction),
        "result_interpretation": (
            prediction.result_interpretation if include_simulated_outcome else None
        ),
        "observed_state_delta": (
            dict(prediction.state_delta) if include_simulated_outcome else None
        ),
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


def blocked_matches(
    case: EvalCase,
    prediction: Prediction,
    *,
    include_host_confirmation: bool = True,
) -> bool:
    """Return whether blocked handling matches expectations."""
    if case.expected_confirmation_required and include_host_confirmation:
        return prediction.confirmation_required is True
    if case.expected_blocked != prediction.blocked:
        return False
    if case.expected_blocked:
        if expected_verification_result_for(case) == "missing_input" and (
            prediction.asks_clarification or prediction.ui_handoff
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


def trajectory_matches(
    case: EvalCase,
    prediction: Prediction,
    *,
    include_host_confirmation: bool = True,
) -> bool:
    """Return whether the whole sequence is acceptable."""
    if (
        case.expected_blocked
        and not case.expected_tools
        and not case.expected_confirmation_required
        and prediction.tool_calls
    ):
        return False
    if (
        case.expected_confirmation_required
        and include_host_confirmation
        and not prediction.confirmation_required
    ):
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
    return prediction.asks_clarification is True or prediction.ui_handoff is True


def missing_input_fields_match(case: EvalCase, prediction: Prediction) -> bool:
    """Match missing-input field identifiers exactly, independent of prose."""
    if expected_decision_verification_result_for(case) != "missing_input":
        return not prediction.missing_inputs
    return frozenset(prediction.missing_inputs) == frozenset(
        case.expected_missing_inputs
    )


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="build/dev-artifacts/agent-evals",
        help="Directory for latest.json/latest.md",
    )
    parser.add_argument(
        "--eval-gate",
        choices=("fast", "candidate", "release", "thesis"),
        default="fast",
        help=(
            "Validation gate. Fast/candidate CLI runs must target changed or "
            "affected cases; release/thesis may refresh full-suite dashboard claims."
        ),
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=1,
        help="Repeat count for deterministic reliability scoring",
    )
    parser.add_argument("--case-id", action="append", default=None)
    parser.add_argument("--case-family", action="append", default=None)
    parser.add_argument("--case-limit", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    preflight = build_deterministic_eval_gate_preflight(
        eval_gate=args.eval_gate,
        repeat_count=args.repeat_count,
        case_ids=args.case_id,
        case_families=args.case_family,
        case_limit=args.case_limit,
    )
    if not preflight["ok"]:
        json_path, md_path = write_deterministic_gate_artifact(
            preflight,
            Path(args.output_dir),
        )
        print(preflight["message"])
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
        return 2
    result = run_eval(
        repeat_count=args.repeat_count,
        case_ids=args.case_id,
        case_families=args.case_family,
        case_limit=args.case_limit,
    )
    result = {**result, "eval_gate": args.eval_gate, "gate_preflight": preflight}
    json_path, md_path = write_artifacts(result, Path(args.output_dir))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    failed = result["summary"]["failed_cases"]
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
