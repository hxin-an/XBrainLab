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
    expected_blocked: bool = False
    expected_confirmation_required: bool = False
    expected_reason_terms: list[str] = field(default_factory=list)
    expected_recovery: bool = False
    expected_result_interpretation: str | None = None
    expected_runtime_safe: bool = True


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

    def trajectory_signature(self) -> dict[str, Any]:
        """Return stable fields used for reliability comparison."""
        return {
            "intent": self.intent,
            "tool_calls": [asdict(call) for call in self.tool_calls],
            "blocked": self.blocked,
            "confirmation_required": self.confirmation_required,
            "blocked_reason": self.blocked_reason,
            "asks_clarification": self.asks_clarification,
            "result_interpretation": self.result_interpretation,
        }


@dataclass(frozen=True)
class CaseScore:
    """Per-case scores for eval dimensions."""

    case_id: str
    passed: bool
    intent: bool
    tool_selection: bool
    argument_correctness: bool
    state_aware: bool
    blocked_command: bool
    recovery: bool
    tool_result_interpretation: bool
    trajectory_quality: bool
    runtime_safety: bool
    local_llm_reliability: bool
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
            "Empty state load data with explicit path",
            "empty",
            ["Load /data/S01.gdf"],
            "load_data",
            [ExpectedToolCall("load_data", {"paths": ["/data/S01.gdf"]})],
        ),
        EvalCase(
            "empty-load-missing-path",
            "Load data request without path asks for clarification",
            "empty",
            ["Load my EEG file."],
            "load_data",
            expected_blocked=True,
            expected_reason_terms=["file path"],
            expected_recovery=True,
        ),
        EvalCase(
            "multi-turn-load-recovery",
            "Missing load path is recovered in second turn",
            "empty",
            ["Load my EEG file.", "Use /data/S02.edf"],
            "load_data",
            [ExpectedToolCall("load_data", {"paths": ["/data/S02.edf"]})],
            expected_recovery=True,
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
            "Loading new raw data after epoch requires reset boundary",
            "epoched",
            ["Load /data/new_subject.gdf"],
            "load_data",
            expected_blocked=True,
            expected_reason_terms=["Reset the session before loading new raw data"],
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
            "Bad load path fails gracefully",
            "empty",
            ["Load /missing/file.gdf"],
            "load_data",
            [ExpectedToolCall("load_data", {"paths": ["/missing/file.gdf"]})],
            expected_result_interpretation="recoverable_failure",
            expected_reason_terms=["path"],
        ),
        EvalCase(
            "successful-load-summary",
            "Successful tool result is summarized as state change",
            "empty",
            ["Load /data/S03.fif"],
            "load_data",
            [ExpectedToolCall("load_data", {"paths": ["/data/S03.fif"]})],
            expected_result_interpretation="success_summary",
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
        "total_cases": len(cases),
        "summary": summary,
        "cases": [asdict(score) for score in scores],
    }


def write_artifacts(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Write latest JSON and Markdown reports."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest.json"
    md_path = output_dir / "latest.md"
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
    intent = infer_intent(text)

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
        )

    if intent == "preprocess":
        blocked = block_from_policy(policy, CommandName.PREPROCESS)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        return Prediction(
            intent=intent,
            tool_calls=[
                PredictedToolCall(
                    "apply_standard_preprocess",
                    extract_filter_args(text),
                )
            ],
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
        )

    if intent == "generate_dataset":
        blocked = block_from_policy(policy, CommandName.GENERATE_DATASET)
        if blocked:
            return blocked_prediction(intent, [], blocked)
        return Prediction(
            intent=intent,
            tool_calls=[
                PredictedToolCall(
                    "generate_dataset",
                    {
                        "test_ratio": 0.2,
                        "val_ratio": 0.2,
                        "training_mode": "individual",
                    },
                )
            ],
        )

    if intent == "configure_training":
        return Prediction(
            intent=intent,
            tool_calls=[PredictedToolCall(*training_tool_call(text))],
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
                "reset_session requires confirmation."
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

    passed = all(
        [
            intent_ok,
            tool_ok,
            args_ok,
            state_ok,
            blocked_ok,
            recovery_ok,
            result_ok,
            trajectory_ok,
            safety_ok,
            reliability_ok,
        ]
    )
    return CaseScore(
        case_id=case.case_id,
        passed=passed,
        intent=intent_ok,
        tool_selection=tool_ok,
        argument_correctness=args_ok,
        state_aware=state_ok,
        blocked_command=blocked_ok,
        recovery=recovery_ok,
        tool_result_interpretation=result_ok,
        trajectory_quality=trajectory_ok,
        runtime_safety=safety_ok,
        local_llm_reliability=reliability_ok,
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
        "blocked_command",
        "recovery",
        "tool_result_interpretation",
        "trajectory_quality",
        "runtime_safety",
        "local_llm_reliability",
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
    }
    preprocessed = name in {
        "preprocessed",
        "epoched",
        "dataset_without_training_config",
        "training_ready",
        "trained",
    }
    epoch = name in {
        "epoched",
        "dataset_without_training_config",
        "training_ready",
        "trained",
    }
    dataset = name in {"dataset_without_training_config", "training_ready", "trained"}
    has_model = name in {"training_ready", "trained"}
    has_training_option = name in {"training_ready", "trained"}
    has_trainer = name in {"trained"}
    finished_runs = 1 if name == "trained" else 0
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
        interpretation=InterpretationStateSnapshot(),
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


def infer_intent(text: str) -> str:
    """Infer intent from simple deterministic patterns."""
    if "reset" in text or "clear the dataset" in text:
        return "reset_session"
    if "saliency" in text:
        return "saliency"
    if "visualize" in text or "visualise" in text:
        return "visualize"
    if "preprocess" in text or "bandpass" in text or "filter" in text:
        return "preprocess"
    if "generate" in text and "dataset" in text:
        return "generate_dataset"
    if "create epoch" in text or "epochs from" in text or "epoch data" in text:
        return "create_epoch"
    if "configure training" in text or "epochs" in text or "batch size" in text:
        return "configure_training"
    if "train" in text or "training" in text:
        return "train"
    if "eegnet" in text or ("model" in text and "use" in text):
        return "configure_training"
    if "load" in text:
        return "load_data"
    return "unknown"


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
    return re.findall(r"/[^\s,;]+", text)


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


def training_tool_call(text: str) -> tuple[str, dict[str, Any]]:
    """Return deterministic training config/model tool call."""
    if "eegnet" in text:
        return "set_model", {"model_name": "EEGNet"}
    args: dict[str, Any] = {}
    epoch = re.search(r"(\d+)\s+epochs?", text)
    batch = re.search(r"batch size\s+(\d+)", text)
    lr = re.search(r"learning rate\s+([0-9]+(?:\.[0-9]+)?)", text)
    if epoch:
        args["epoch"] = int(epoch.group(1))
    if batch:
        args["batch_size"] = int(batch.group(1))
    if lr:
        args["learning_rate"] = float(lr.group(1))
    return "configure_training", args


def result_interpretation_for(case: EvalCase) -> str | None:
    """Return simulated tool-result interpretation for result-focused cases."""
    if case.expected_result_interpretation:
        return case.expected_result_interpretation
    return None


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
            if predicted_call.arguments.get(key) != value:
                return False
    return True


def blocked_matches(case: EvalCase, prediction: Prediction) -> bool:
    """Return whether blocked handling matches expectations."""
    if case.expected_confirmation_required:
        return prediction.confirmation_required is True
    if case.expected_blocked != prediction.blocked:
        return False
    if case.expected_blocked:
        return all(
            term.lower() in prediction.blocked_reason.lower()
            for term in case.expected_reason_terms
        )
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
