"""Built-in case catalog for the Agent tool-call showcase.

This catalog is intentionally small and product-oriented. It is not the frozen
case set, scorer, or repeat protocol for a thesis benchmark.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SHOWCASE_SOURCE_PLACEHOLDER = "<SHOWCASE_SOURCE_PATH>"
SHOWCASE_SOURCE_DIR_PLACEHOLDER = "<SHOWCASE_SOURCE_DIR>"
SHOWCASE_RECIPE_PATH_PLACEHOLDER = "<SHOWCASE_RECIPE_PATH>"
_CASE_ALIASES = {
    "navigation.open_preprocess": "navigation.list_source_folder",
}

Preparation = Literal[
    "empty",
    "scanned",
    "previewed",
    "validated",
    "loaded",
    "recipe_saved",
    "preprocessed",
    "epoched",
    "dataset_ready",
    "training_configured",
]
TerminalExpectation = Literal[
    "command_ok",
    "blocked",
    "confirmation_cancelled",
    "ui_handoff",
    "typed_ui_request",
    "stale_revision",
    "retry_ok",
]
FlowKind = Literal["standard", "stale_revision", "runtime_retry"]
ConfirmationResolution = Literal["approve", "cancel"]


@dataclass(frozen=True, slots=True)
class ShowcaseCase:
    """One stable showcase case and its diagnostic expectations."""

    case_id: str
    title: str
    area: str
    prompt: str
    tool_name: str
    params: dict[str, Any]
    preparation: Preparation = "empty"
    expected_terminal: TerminalExpectation = "command_ok"
    expected_error_type: str | None = None
    confirmation: ConfirmationResolution | None = None
    expected_confirmation_kind: str | None = None
    expected_ui_request_kind: str | None = None
    expected_ui_params: tuple[tuple[str, Any], ...] = ()
    expected_state_after: tuple[tuple[str, Any], ...] = ()
    flow: FlowKind = "standard"
    expected_changed_state: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def rendered_prompt(self, source_path: str) -> str:
        """Resolve the runtime source token for one user-authored prompt."""
        return _replace_runtime_tokens(self.prompt, source_path)

    def rendered_params(self, source_path: str) -> dict[str, Any]:
        """Resolve source tokens without mutating the catalog entry."""
        return _replace_source_token(self.params, source_path)

    def identity(self) -> str:
        """Return a stable identity for resume compatibility checks."""
        payload = {
            "case_id": self.case_id,
            "area": self.area,
            "prompt": self.prompt,
            "tool_name": self.tool_name,
            "params": self.params,
            "preparation": self.preparation,
            "expected_terminal": self.expected_terminal,
            "expected_error_type": self.expected_error_type,
            "confirmation": self.confirmation,
            "expected_confirmation_kind": self.expected_confirmation_kind,
            "expected_ui_request_kind": self.expected_ui_request_kind,
            "expected_ui_params": self.expected_ui_params,
            "expected_state_after": self.expected_state_after,
            "flow": self.flow,
            "expected_changed_state": self.expected_changed_state,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def prompt_identity(self) -> str:
        """Return the stable identity of the user-authored prompt template."""
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()


def _replace_source_token(value: Any, source_path: str) -> Any:
    if isinstance(value, str):
        return _replace_runtime_tokens(value, source_path)
    if isinstance(value, list):
        return [_replace_source_token(item, source_path) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _replace_source_token(item, source_path)
            for key, item in value.items()
        }
    return value


def _replace_runtime_tokens(value: str, source_path: str) -> str:
    return (
        value.replace(
            SHOWCASE_RECIPE_PATH_PLACEHOLDER,
            str(Path(source_path).with_name("showcase_recipe.json")),
        )
        .replace(
            SHOWCASE_SOURCE_DIR_PLACEHOLDER,
            str(Path(source_path).parent),
        )
        .replace(SHOWCASE_SOURCE_PLACEHOLDER, source_path)
    )


SHOWCASE_CASES: tuple[ShowcaseCase, ...] = (
    ShowcaseCase(
        case_id="navigation.list_source_folder",
        title="List a source folder",
        area="data import/navigation",
        prompt=f"List the files in this folder: {SHOWCASE_SOURCE_DIR_PLACEHOLDER}",
        tool_name="list_files",
        params={"directory": SHOWCASE_SOURCE_DIR_PLACEHOLDER},
        tags=("navigation", "read-only", "success"),
    ),
    ShowcaseCase(
        case_id="navigation.switch_dataset_panel",
        title="Request the Dataset panel",
        area="data import/navigation",
        prompt="切換到 Dataset 面板。",
        tool_name="switch_panel",
        params={"panel_name": "dataset"},
        expected_terminal="typed_ui_request",
        expected_ui_request_kind="switch_panel",
        expected_ui_params=(("panel", "dataset"), ("view_mode", None)),
        tags=("navigation", "ui-request", "success"),
    ),
    ShowcaseCase(
        case_id="blocked.preprocess_without_data",
        title="Block preprocessing before import",
        area="preprocess",
        prompt="Apply standard preprocessing with the default settings now.",
        tool_name="apply_standard_preprocess",
        params={"l_freq": 4.0, "h_freq": 40.0, "normalize_method": "z-score"},
        expected_terminal="blocked",
        expected_error_type="precondition",
        tags=("blocked", "wrong-stage"),
    ),
    ShowcaseCase(
        case_id="import.scan_source",
        title="Scan an EEG source",
        area="data import/navigation",
        prompt=(
            "Scan this EEG source with Data Interpretation: "
            f"{SHOWCASE_SOURCE_PLACEHOLDER}"
        ),
        tool_name="scan_source",
        params={"source_path": SHOWCASE_SOURCE_PLACEHOLDER},
        expected_changed_state=("interpretation_changed",),
        tags=("import", "success"),
    ),
    ShowcaseCase(
        case_id="import.preview_interpretation",
        title="Preview the interpretation",
        area="data import/navigation",
        prompt="Preview the current Data Interpretation candidate now.",
        tool_name="preview_interpretation",
        params={},
        preparation="scanned",
        expected_changed_state=("interpretation_changed",),
        tags=("import", "success"),
    ),
    ShowcaseCase(
        case_id="import.validate_interpretation",
        title="Validate the interpretation",
        area="data import/navigation",
        prompt="Validate the current Data Interpretation candidate.",
        tool_name="validate_interpretation",
        params={},
        preparation="previewed",
        expected_changed_state=("interpretation_changed",),
        tags=("import", "success"),
    ),
    ShowcaseCase(
        case_id="import.apply_review_handoff",
        title="Hand off unresolved import review",
        area="data import/navigation",
        prompt="Apply the validated Data Interpretation and import the recording.",
        tool_name="apply_interpretation",
        params={},
        preparation="validated",
        expected_terminal="ui_handoff",
        tags=("import", "handoff", "review"),
    ),
    ShowcaseCase(
        case_id="import.save_recipe",
        title="Save the applied interpretation recipe",
        area="data import/navigation",
        prompt=(
            "Save the current interpretation recipe to "
            f"{SHOWCASE_RECIPE_PATH_PLACEHOLDER}"
        ),
        tool_name="save_interpretation_recipe",
        params={"recipe_path": SHOWCASE_RECIPE_PATH_PLACEHOLDER},
        preparation="loaded",
        expected_changed_state=("interpretation_changed",),
        expected_state_after=(("interpretation.has_recipe", True),),
        tags=("import", "recipe", "write", "success"),
    ),
    ShowcaseCase(
        case_id="import.reload_recipe",
        title="Reload an interpretation recipe",
        area="data import/navigation",
        prompt=(
            f"Reload the interpretation recipe from {SHOWCASE_RECIPE_PATH_PLACEHOLDER}"
        ),
        tool_name="reload_interpretation_recipe",
        params={"recipe_path": SHOWCASE_RECIPE_PATH_PLACEHOLDER},
        preparation="recipe_saved",
        expected_changed_state=("interpretation_changed",),
        expected_state_after=(
            ("interpretation.has_scan_result", True),
            ("interpretation.has_preview", True),
            ("interpretation.has_validation_decision", True),
        ),
        tags=("import", "recipe", "reload", "success"),
    ),
    ShowcaseCase(
        case_id="preprocess.standard",
        title="Apply standard preprocessing",
        area="preprocess",
        prompt=(
            "Apply standard preprocessing with a 4 to 40 Hz bandpass and "
            "z-score normalization."
        ),
        tool_name="apply_standard_preprocess",
        params={"l_freq": 4.0, "h_freq": 40.0, "normalize_method": "z-score"},
        preparation="loaded",
        expected_changed_state=("preprocessed_changed",),
        tags=("preprocess", "success"),
    ),
    ShowcaseCase(
        case_id="epoch.create",
        title="Create EEG epochs",
        area="epoch",
        prompt="Create epoch from 0.0 to 0.25 seconds for events left and right.",
        tool_name="epoch_data",
        params={
            "event_id": ["left", "right"],
            "t_min": 0.0,
            "t_max": 0.25,
        },
        preparation="preprocessed",
        expected_changed_state=("epoch_changed",),
        tags=("epoch", "success"),
    ),
    ShowcaseCase(
        case_id="visualization.montage_request",
        title="Request Montage Settings",
        area="evaluation and saliency",
        prompt="Use the standard_1020 montage for channel positions.",
        tool_name="set_montage",
        params={"montage_name": "standard_1020"},
        preparation="epoched",
        expected_terminal="typed_ui_request",
        expected_ui_request_kind="confirm_montage",
        expected_ui_params=(("montage_name", "standard_1020"),),
        tags=("montage", "ui-request", "success"),
    ),
    ShowcaseCase(
        case_id="split.generate_trial",
        title="Save a trial-split specification",
        area="split",
        prompt=(
            "Create an individual dataset split by trial, with "
            "20 percent validation, and 20 percent test data."
        ),
        tool_name="configure_dataset_split",
        params={
            "training_mode": "individual",
            "split_strategy": "trial",
            "val_ratio": 0.2,
            "test_ratio": 0.2,
        },
        preparation="epoched",
        confirmation="approve",
        expected_changed_state=("datasets_changed",),
        tags=("split", "confirmation", "deferred", "success"),
    ),
    ShowcaseCase(
        case_id="settings.model_approved",
        title="Approve a model-setting change",
        area="model/training settings",
        prompt="Use EEGNet as the model.",
        tool_name="set_model",
        params={"model_name": "EEGNet"},
        preparation="dataset_ready",
        confirmation="approve",
        expected_changed_state=("training_changed",),
        tags=("model", "confirmation", "success"),
    ),
    ShowcaseCase(
        case_id="settings.training_handoff",
        title="Hand off incomplete training settings",
        area="model/training settings",
        prompt="Configure training.",
        tool_name="configure_training",
        params={},
        preparation="dataset_ready",
        expected_terminal="ui_handoff",
        tags=("training-settings", "handoff"),
    ),
    ShowcaseCase(
        case_id="settings.complete_training_approved",
        title="Approve a complete training configuration",
        area="model/training settings",
        prompt=(
            "Configure braindecode.deep4net for 5 epochs with batch size 16 "
            "and learning rate 0.0005."
        ),
        tool_name="configure_training",
        params={
            "model_name": "braindecode.deep4net",
            "epoch": 5,
            "batch_size": 16,
            "learning_rate": 0.0005,
        },
        preparation="training_configured",
        confirmation="approve",
        expected_changed_state=("training_changed",),
        tags=("training-settings", "confirmation", "complete-intent", "success"),
    ),
    ShowcaseCase(
        case_id="training.start_cancelled",
        title="Cancel start training",
        area="start/stop training",
        prompt="Start training now.",
        tool_name="start_training",
        params={},
        preparation="training_configured",
        expected_terminal="confirmation_cancelled",
        confirmation="cancel",
        tags=("training", "confirmation", "cancellation"),
    ),
    ShowcaseCase(
        case_id="training.stop_when_idle",
        title="Block stop when training is idle",
        area="start/stop training",
        prompt="Stop the active training run.",
        tool_name="stop_training",
        params={},
        preparation="training_configured",
        expected_terminal="blocked",
        expected_error_type="precondition",
        tags=("training", "blocked"),
    ),
    ShowcaseCase(
        case_id="analysis.evaluate_before_run",
        title="Block evaluation before a finished run",
        area="evaluation and saliency",
        prompt="Evaluate the trained model results.",
        tool_name="evaluate",
        params={},
        preparation="training_configured",
        expected_terminal="blocked",
        expected_error_type="precondition",
        tags=("evaluation", "blocked"),
    ),
    ShowcaseCase(
        case_id="analysis.visualize_before_run",
        title="Summarize visualization readiness before a finished run",
        area="evaluation and saliency",
        prompt="Visualize the current training results summary.",
        tool_name="visualize",
        params={"view": "summary"},
        preparation="training_configured",
        expected_state_after=(("visualization.saliency_available", False),),
        tags=("visualization", "readiness", "success"),
    ),
    ShowcaseCase(
        case_id="analysis.saliency_before_run",
        title="Configure saliency before a finished run",
        area="evaluation and saliency",
        prompt="Configure Gradient saliency for the next training run.",
        tool_name="saliency",
        params={"method": "Gradient"},
        preparation="training_configured",
        expected_changed_state=("visualization_changed",),
        tags=("saliency", "settings", "success"),
    ),
    ShowcaseCase(
        case_id="preprocess.reset_approved",
        title="Approve resetting derived preprocessing state",
        area="preprocess",
        prompt=(
            "Reset preprocessing and discard derived epochs, the dataset split, "
            "and training runs while retaining the loaded raw data and settings."
        ),
        tool_name="reset_preprocess",
        params={},
        preparation="training_configured",
        confirmation="approve",
        expected_confirmation_kind="command_confirmation",
        expected_changed_state=(
            "preprocessed_changed",
            "epoch_changed",
            "datasets_changed",
            "training_changed",
        ),
        expected_state_after=(
            ("raw.loaded", True),
            ("preprocessed.operations", []),
            ("epoch.available", False),
            ("dataset.split_spec_saved", False),
            ("training.has_model", True),
            ("training.has_training_option", True),
            ("training.has_trainer", False),
            ("training.plan_count", 0),
            ("training.run_count", 0),
            ("training.finished_run_count", 0),
        ),
        tags=("preprocess", "reset", "confirmation", "success"),
    ),
    ShowcaseCase(
        case_id="safety.stale_revision",
        title="Reject a stale workflow revision",
        area="safety and recovery",
        prompt=(
            "Scan this EEG source with Data Interpretation: "
            f"{SHOWCASE_SOURCE_PLACEHOLDER}"
        ),
        tool_name="scan_source",
        params={"source_path": SHOWCASE_SOURCE_PLACEHOLDER},
        expected_terminal="stale_revision",
        expected_error_type="stale_publication",
        flow="stale_revision",
        tags=("stale-revision", "blocked"),
    ),
    ShowcaseCase(
        case_id="recovery.runtime_error_retry",
        title="Retry a recoverable runtime error",
        area="safety and recovery",
        prompt="Show the current XBrainLab workflow state.",
        tool_name="query_state",
        params={"query": "state"},
        expected_terminal="retry_ok",
        flow="runtime_retry",
        tags=("runtime-error", "retry", "success"),
    ),
)


def filter_cases(
    patterns: list[str] | tuple[str, ...] | None,
    *,
    cases: tuple[ShowcaseCase, ...] = SHOWCASE_CASES,
) -> list[ShowcaseCase]:
    """Return cases matching any case-insensitive glob or substring pattern."""
    normalized = [
        _CASE_ALIASES.get(item.strip().casefold(), item.strip().casefold())
        for item in patterns or []
        if item.strip()
    ]
    if not normalized:
        return list(cases)

    matched: list[ShowcaseCase] = []
    for case in cases:
        haystacks = (
            case.case_id.casefold(),
            case.title.casefold(),
            case.area.casefold(),
            *(tag.casefold() for tag in case.tags),
        )
        if any(
            any(
                pattern in value or fnmatch.fnmatchcase(value, pattern)
                for value in haystacks
            )
            for pattern in normalized
        ):
            matched.append(case)
    return matched
