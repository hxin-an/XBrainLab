"""ApplicationService-backed review and user-journey execution."""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from .evidence import (
    artifact_record,
    collect_existing_artifacts,
    empty_dataset_evidence,
    evaluate_quality_acceptance,
    persist_training_curves,
    showcase_quality_complete,
)
from .storage import utc_now, write_json_atomic


class ProductCommandError(RuntimeError):
    """A structured product command failed."""

    def __init__(self, stage: str, result: Any):
        self.stage = stage
        self.result = result
        super().__init__(f"{stage}: {result.message}")


def review_dataset(
    dataset: dict[str, Any],
    *,
    confirm_resource_plan: bool,
    service_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run scan/preview/validate without applying or mutating downstream state."""
    symbols = _product_symbols()
    factory = service_factory or symbols["ApplicationService"]
    service = factory()
    trace: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        _execute(
            service,
            symbols["ScanSourceCommand"](
                source_path=dataset["import"]["source_path"],
                source_hint=dataset["import"]["source_hint"],
            ),
            stage="scan",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        _execute(
            service,
            symbols["PreviewInterpretationCommand"](
                choices=dataset["import"]["choices"],
            ),
            stage="preview",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        validation = _execute(
            service,
            symbols["ValidateInterpretationCommand"](),
            stage="validate",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        return {
            "dataset_id": dataset["id"],
            "status": "validated",
            "validation_decision": validation.diagnostics.get("validation_decision"),
            "command_trace": trace,
            "duration_seconds": time.perf_counter() - started,
            "failures": [],
        }
    except ProductCommandError as exc:
        return {
            "dataset_id": dataset["id"],
            "status": "failed",
            "validation_decision": None,
            "command_trace": trace,
            "duration_seconds": time.perf_counter() - started,
            "failures": [_failure_from_result(exc.stage, exc.result)],
        }
    except Exception as exc:
        return {
            "dataset_id": dataset["id"],
            "status": "failed",
            "validation_decision": None,
            "command_trace": trace,
            "duration_seconds": time.perf_counter() - started,
            "failures": [_failure_from_exception("review", exc)],
        }
    finally:
        _close_service(service)


def run_dataset_journey(
    dataset: dict[str, Any],
    *,
    run_root: Path,
    source_artifacts: list[dict[str, Any]],
    execution_profile: str,
    confirm_resource_plan: bool,
    attempt: int,
    previous_failure: dict[str, Any] | None,
    service_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Replay one complete user journey through the product command spine."""
    if execution_profile not in {"smoke", "showcase"}:
        raise ValueError("execution_profile must be smoke or showcase")
    symbols = _product_symbols()
    factory = service_factory or symbols["ApplicationService"]
    service = factory()
    dataset_dir = run_root / dataset["id"]
    dataset_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = dataset_dir / "checkpoint.json"
    evidence = empty_dataset_evidence(
        dataset,
        source_artifacts=source_artifacts,
        execution_profile=execution_profile,
        attempt=attempt,
        previous_failure=previous_failure,
    )
    trace = evidence["command_trace"]
    total_started = time.perf_counter()
    current_stage = "initialize"
    try:
        _set_reproducible_seed(int(evidence["seed"]))

        current_stage = "import"
        stage_started = time.perf_counter()
        _execute(
            service,
            symbols["ScanSourceCommand"](
                source_path=dataset["import"]["source_path"],
                source_hint=dataset["import"]["source_hint"],
            ),
            stage="scan",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        _execute(
            service,
            symbols["PreviewInterpretationCommand"](
                choices=dataset["import"]["choices"],
            ),
            stage="preview",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        validated = _execute(
            service,
            symbols["ValidateInterpretationCommand"](),
            stage="validate",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        evidence["import"]["validation_decision"] = validated.diagnostics.get(
            "validation_decision"
        )
        applied = _execute(
            service,
            symbols["ApplyInterpretationCommand"](confirmed=True),
            stage="apply",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        evidence["import"]["applied"] = True
        evidence["import"]["applied_state"] = _state_section(applied, "interpretation")
        recipe_path = dataset_dir / "import-recipe.json"
        _execute(
            service,
            symbols["SaveInterpretationRecipeCommand"](recipe_path=str(recipe_path)),
            stage="save_recipe",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        evidence["import"]["recipe_artifact"] = artifact_record(
            recipe_path, kind="import_recipe"
        )
        evidence["timings"]["import"] = time.perf_counter() - stage_started
        _checkpoint(checkpoint_path, evidence, current_stage, "completed")

        current_stage = "preprocess"
        stage_started = time.perf_counter()
        for operation in dataset["workflow"]["preprocessing"]:
            command_args = dict(operation)
            result = _execute(
                service,
                symbols["PreprocessCommand"](**command_args),
                stage=f"preprocess:{command_args['operation']}",
                trace=trace,
                confirm_resource_plan=confirm_resource_plan,
            )
            evidence["preprocessing"].append(
                {
                    "command": command_args,
                    "state": _state_section(result, "preprocessed"),
                }
            )
        evidence["timings"]["preprocess"] = time.perf_counter() - stage_started
        _checkpoint(checkpoint_path, evidence, current_stage, "completed")

        current_stage = "epoch"
        stage_started = time.perf_counter()
        epoch = _execute(
            service,
            symbols["CreateEpochCommand"](**dataset["workflow"]["epoch"]),
            stage="epoch",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        evidence["epoch"]["state"] = _state_section(epoch, "epoch")
        evidence["epoch"]["diagnostics"] = dict(epoch.diagnostics)
        evidence["timings"]["epoch"] = time.perf_counter() - stage_started
        _checkpoint(checkpoint_path, evidence, current_stage, "completed")

        current_stage = "split"
        stage_started = time.perf_counter()
        split = _execute(
            service,
            symbols["GenerateDatasetCommand"](**dataset["workflow"]["split"]),
            stage="split",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        evidence["split"]["state"] = _state_section(split, "dataset")
        evidence["split"]["diagnostics"] = dict(split.diagnostics)
        evidence["timings"]["split"] = time.perf_counter() - stage_started
        _checkpoint(checkpoint_path, evidence, current_stage, "completed")

        current_stage = "training"
        stage_started = time.perf_counter()
        model = evidence["model"]
        training_output = dataset_dir / "training"
        repeat_count = int(model.get("repeat", 1))
        base_seed = int(evidence["seed"])
        expected_repeat_seeds = [
            base_seed + repeat_index for repeat_index in range(repeat_count)
        ]
        configured = _execute(
            service,
            symbols["ConfigureTrainingCommand"](
                model_name=model["name"],
                device=model["device"],
                epoch=model["epochs"],
                batch_size=model["batch_size"],
                learning_rate=model["learning_rate"],
                optimizer=model["optimizer"],
                evaluation_option=model["evaluation_option"],
                output_dir=str(training_output),
                save_checkpoints_every=0,
                repeat=repeat_count,
                seed=base_seed,
            ),
            stage="configure_training",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        model["resolved_training_state"] = _state_section(configured, "training")
        model["actual_device"] = (
            model["resolved_training_state"].get("training_option", {}).get("device")
            if isinstance(model["resolved_training_state"], dict)
            else None
        )
        _verify_configured_training_seeds(
            model["resolved_training_state"],
            expected_seeds=expected_repeat_seeds,
        )
        existing_training_records = set(training_output.rglob("record"))
        _execute(
            service,
            symbols["SaliencyCommand"](params=dict(evidence["saliency"]["params"])),
            stage="configure_saliency",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        trained = _execute(
            service,
            symbols["TrainCommand"](confirmed=True, interactive=False),
            stage="train",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        model["terminal_training_state"] = _state_section(trained, "training")
        _wait_for_background_tasks(service, timeout=1800.0)
        persisted_repeat_seeds = _verify_persisted_training_seeds(
            training_output,
            expected_seeds=expected_repeat_seeds,
            ignored_record_paths=existing_training_records,
        )
        model["reproducibility"] = {
            "base_seed": base_seed,
            "derivation": "base_seed + zero_based_repeat_index",
            "configured_training_state_verified": True,
            "persisted_train_records_verified": True,
            "repeat_seeds": persisted_repeat_seeds,
        }
        evidence["timings"]["training"] = time.perf_counter() - stage_started
        _checkpoint(checkpoint_path, evidence, current_stage, "completed")

        current_stage = "evaluation"
        stage_started = time.perf_counter()
        history = _execute(
            service,
            symbols["QueryStateCommand"]("training_history"),
            stage="training_history",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        evaluation = _execute(
            service,
            symbols["EvaluateCommand"](),
            stage="evaluate",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        saliency = _execute(
            service,
            symbols["SaliencyCommand"](),
            stage="saliency_query",
            trace=trace,
            confirm_resource_plan=confirm_resource_plan,
        )
        held_out_evaluations = _held_out_evaluations(
            service,
            symbols,
            evaluation.diagnostics,
        )
        evidence["metrics"] = {
            "training_history": dict(history.diagnostics),
            "evaluation_summary": dict(evaluation.diagnostics),
            "held_out_evaluations": held_out_evaluations,
        }
        evidence["quality_acceptance"] = evaluate_quality_acceptance(
            dataset["workflow"]["quality_acceptance"],
            held_out_evaluations,
        )
        curve_artifact = persist_training_curves(
            dataset_dir / "training-curves.json",
            training_history=history.diagnostics,
        )
        if curve_artifact is not None:
            evidence["training_curves"].append(curve_artifact)
        evidence["saliency"]["query"] = dict(saliency.diagnostics)
        saliency_artifacts, saliency_export = _persist_saliency_artifacts(
            service,
            symbols,
            dataset_dir / "saliency",
            requested_methods=evidence["saliency"]["methods"],
            max_artifact_bytes=int(
                dataset["workflow"]["saliency"]["max_artifact_bytes"]
            ),
        )
        evidence["saliency"]["artifacts"] = saliency_artifacts
        evidence["saliency"]["artifact_export"] = saliency_export
        evidence["screenshots"] = collect_existing_artifacts(
            dataset_dir / "screenshots", "*.png", kind="screenshot"
        )
        evidence["timings"]["evaluation"] = time.perf_counter() - stage_started
        evidence["timings"]["total"] = time.perf_counter() - total_started
        if execution_profile == "showcase":
            evidence["quality_evidence_status"] = (
                "complete" if showcase_quality_complete(evidence) else "pending"
            )
        else:
            evidence["quality_evidence_status"] = "pending"
        _checkpoint(checkpoint_path, evidence, "complete", "completed")
        return evidence  # noqa: TRY300
    except ProductCommandError as exc:
        evidence["failures"].append(_failure_from_result(exc.stage, exc.result))
    except Exception as exc:
        evidence["failures"].append(_failure_from_exception(current_stage, exc))
    finally:
        evidence["timings"]["total"] = time.perf_counter() - total_started
        if evidence["failures"] and execution_profile == "showcase":
            evidence["quality_evidence_status"] = "failed"
        _checkpoint(
            checkpoint_path,
            evidence,
            current_stage,
            "failed" if evidence["failures"] else "completed",
        )
        _close_service(service)
    return evidence


def _execute(
    service: Any,
    command: Any,
    *,
    stage: str,
    trace: list[dict[str, Any]],
    confirm_resource_plan: bool,
) -> Any:
    started = time.perf_counter()
    result = service.execute(command)
    trace.append(_trace_result(stage, result, time.perf_counter() - started))
    error_type = getattr(getattr(result, "error_type", None), "value", "")
    if not result.ok and error_type == "confirmation_required":
        challenge = (
            result.diagnostics.get("resource_preflight", {})
            .get("confirmation_challenge", {})
            .get("challenge_id")
        )
        if (
            challenge
            and confirm_resource_plan
            and hasattr(command, "resource_preflight_confirmed")
        ):
            approved = replace(
                command,
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge,
            )
            started = time.perf_counter()
            result = service.execute(approved)
            trace.append(
                _trace_result(
                    f"{stage}:resource_confirmed",
                    result,
                    time.perf_counter() - started,
                )
            )
    if not result.ok:
        raise ProductCommandError(stage, result)
    return result


def _trace_result(stage: str, result: Any, duration: float) -> dict[str, Any]:
    return {
        "stage": stage,
        "command": result.command_name,
        "status": getattr(result.status, "value", str(result.status)),
        "message": result.message,
        "error_type": getattr(result.error_type, "value", str(result.error_type)),
        "recoverable": result.recoverable,
        "duration_seconds": duration,
        "diagnostics": dict(result.diagnostics),
    }


def _state_section(result: Any, section: str) -> dict[str, Any]:
    state = result.to_internal_dict().get("state", {})
    value = state.get(section, {}) if isinstance(state, dict) else {}
    return dict(value) if isinstance(value, dict) else {}


def _failure_from_result(stage: str, result: Any) -> dict[str, Any]:
    return {
        "stage": stage,
        "type": getattr(result.error_type, "value", str(result.error_type)),
        "message": str(result.error_message or result.message),
        "recoverable": bool(result.recoverable),
        "diagnostics": dict(result.diagnostics),
    }


def _failure_from_exception(stage: str, exc: Exception) -> dict[str, Any]:
    return {
        "stage": stage,
        "type": type(exc).__name__,
        "message": str(exc),
        "recoverable": True,
    }


def _checkpoint(
    path: Path,
    evidence: dict[str, Any],
    stage: str,
    status: str,
) -> None:
    previous_failure = evidence["failures"][-1] if evidence["failures"] else None
    write_json_atomic(
        path,
        {
            "schema_version": "1.0.0",
            "dataset_id": evidence["dataset"]["id"],
            "attempt": evidence["resume"]["attempt"],
            "strategy": "replay_from_source",
            "last_stage": stage,
            "status": status,
            "updated_at": utc_now(),
            "failure": previous_failure,
        },
    )


def _set_reproducible_seed(seed: int) -> None:
    random.seed(seed)
    import numpy as np
    import torch

    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def _verify_persisted_training_seeds(
    training_output: Path,
    *,
    expected_seeds: list[int],
    ignored_record_paths: set[Path] | None = None,
) -> list[int]:
    """Read safe TrainRecord artifacts and verify every derived repeat seed."""
    from XBrainLab.backend.training.record.artifact_store import (
        TRAINING_RECORD_ARTIFACT_TYPE,
        read_json_npz_artifact,
    )

    ignored = ignored_record_paths or set()
    record_paths = [
        path for path in sorted(training_output.rglob("record")) if path not in ignored
    ]
    observed_by_repeat: dict[int, list[int]] = {}
    for record_path in record_paths:
        match = re.fullmatch(r"Repeat-(\d+)", record_path.parent.name)
        if match is None:
            continue
        repeat_index = int(match.group(1))
        payload, _arrays = read_json_npz_artifact(
            record_path,
            expected_artifact_type=TRAINING_RECORD_ARTIFACT_TYPE,
        )
        seed = payload.get("seed")
        if type(seed) is not int:
            raise RuntimeError(
                f"Persisted TrainRecord seed is invalid for repeat {repeat_index}."
            )
        observed_by_repeat.setdefault(repeat_index, []).append(seed)

    expected_repeats = set(range(len(expected_seeds)))
    observed_seeds = [
        observed_by_repeat[index][0]
        for index in range(len(expected_seeds))
        if index in observed_by_repeat
    ]
    seeds_match = all(
        index in observed_by_repeat
        and all(seed == expected_seed for seed in observed_by_repeat[index])
        for index, expected_seed in enumerate(expected_seeds)
    )
    if set(observed_by_repeat) != expected_repeats or not seeds_match:
        raise RuntimeError(
            "Persisted TrainRecord seeds do not match the configured repeat seeds: "
            f"expected {expected_seeds}, observed {observed_by_repeat}."
        )
    return observed_seeds


def _verify_configured_training_seeds(
    training_state: dict[str, Any],
    *,
    expected_seeds: list[int],
) -> None:
    """Require the application state to confirm the exact requested seed plan."""
    training_option = training_state.get("training_option")
    observed_seeds = (
        training_option.get("repeat_seeds")
        if isinstance(training_option, dict)
        else None
    )
    observed_base_seed = (
        training_option.get("seed") if isinstance(training_option, dict) else None
    )
    expected_base_seed = expected_seeds[0] if expected_seeds else None
    if observed_base_seed != expected_base_seed or observed_seeds != expected_seeds:
        raise RuntimeError(
            "Configured training state does not verify the requested repeat seeds: "
            f"expected {expected_seeds}, observed {observed_seeds}."
        )


def _held_out_evaluations(
    service: Any,
    symbols: dict[str, Any],
    evaluation_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    import numpy as np
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        f1_score,
        roc_auc_score,
    )

    publication = service.get_view_publication()
    plans = evaluation_summary.get("plans")
    if not isinstance(plans, list):
        return []
    evaluations: list[dict[str, Any]] = []
    for fallback_index, plan in enumerate(plans):
        if not isinstance(plan, dict) or int(plan.get("finished_run_count", 0)) < 1:
            continue
        identity = plan.get("identity")
        plan_index = (
            int(identity["plan_index"])
            if isinstance(identity, dict) and "plan_index" in identity
            else fallback_index
        )
        request = symbols["EvaluationRenderRequest"](
            publication_generation=publication.generation,
            selection=symbols["EvaluationPlanIdentity"](plan_index=plan_index),
            split="test",
        )
        render = service.get_evaluation_render(request)
        labels = np.asarray(render.data.labels)
        outputs = np.asarray(render.data.outputs)
        predicted = outputs.argmax(axis=1)
        class_count = int(outputs.shape[1])
        observed_classes, observed_counts = np.unique(labels, return_counts=True)
        probabilities = _softmax(outputs)
        auc: float | None
        try:
            if class_count == 2:
                auc = float(roc_auc_score(labels, probabilities[:, 1]))
            else:
                auc = float(
                    roc_auc_score(
                        labels,
                        probabilities,
                        labels=np.arange(class_count),
                        multi_class="ovr",
                    )
                )
        except ValueError:
            auc = None
        evaluations.append(
            {
                "plan_index": plan_index,
                "split": render.data.evaluation_split,
                "test_prediction_read_count": 1,
                "sample_count": int(labels.size),
                "model_class_count": class_count,
                "observed_class_count": int(observed_classes.size),
                "class_distribution": {
                    str(int(label)): int(count)
                    for label, count in zip(
                        observed_classes,
                        observed_counts,
                        strict=True,
                    )
                },
                "baselines": {
                    "chance_baseline": 1.0 / class_count,
                    "majority_baseline": float(observed_counts.max() / labels.size),
                    "auc_chance_baseline": 0.5,
                },
                "metrics": {
                    "accuracy": float(accuracy_score(labels, predicted)),
                    "balanced_accuracy": float(
                        balanced_accuracy_score(labels, predicted)
                    ),
                    "macro_f1": float(
                        f1_score(
                            labels,
                            predicted,
                            labels=np.arange(class_count),
                            average="macro",
                            zero_division=0,
                        )
                    ),
                    "roc_auc_ovr": auc,
                },
                "per_class_metrics": {
                    str(key): dict(value) for key, value in render.data.metrics.items()
                },
                "class_labels": {
                    str(key): value for key, value in render.data.class_labels.items()
                },
                "valid": (
                    render.data.evaluation_split == "test"
                    and labels.size > 0
                    and observed_classes.size == class_count
                ),
            }
        )
    return evaluations


def _softmax(outputs: Any) -> Any:
    import numpy as np

    shifted = outputs - np.max(outputs, axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum(axis=1, keepdims=True)


def _persist_saliency_artifacts(
    service: Any,
    symbols: dict[str, Any],
    output_dir: Path,
    *,
    requested_methods: list[str],
    max_artifact_bytes: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import numpy as np

    publication = service.get_view_publication()
    coverage = publication.state.visualization.saliency_coverage
    requested = set(requested_methods)
    artifacts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    estimated_bytes = 0
    output_dir.mkdir(parents=True, exist_ok=True)
    for run in coverage:
        for method in run.methods:
            if method.method not in requested or not method.complete:
                continue
            request = symbols["SaliencyRenderRequest"](
                publication_generation=publication.generation,
                run=symbols["SaliencyRunIdentity"](
                    plan=symbols["SaliencyPlanIdentity"](plan_index=run.plan_index),
                    run_index=run.run_index,
                ),
                method=method.method,
                normalize=False,
            )
            render = service.get_saliency_render(request)
            arrays = {
                f"class_{index:03d}": np.asarray(values)
                for index, values in enumerate(render.data.saliency_by_class.values())
            }
            if not arrays or any(array.size == 0 for array in arrays.values()):
                continue
            method_bytes = sum(int(array.nbytes) for array in arrays.values())
            if estimated_bytes + method_bytes > max_artifact_bytes:
                skipped.append(
                    {
                        "method": method.method,
                        "plan_index": run.plan_index,
                        "run_index": run.run_index,
                        "reason": "saliency_artifact_budget_exceeded",
                        "estimated_uncompressed_bytes": method_bytes,
                    }
                )
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", method.method.casefold()).strip("-")
            path = output_dir / (
                f"plan-{run.plan_index:02d}-run-{run.run_index:02d}-{slug}.npz"
            )
            temporary = path.with_name(f"{path.name}.part")
            try:
                with temporary.open("wb") as handle:
                    np.savez_compressed(handle, **arrays)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            estimated_bytes += method_bytes
            artifacts.append(
                artifact_record(
                    path,
                    kind="saliency",
                    source="application_service_saliency_render",
                    method=method.method,
                    plan_index=run.plan_index,
                    run_index=run.run_index,
                    source_split=render.data.source_split,
                    array_shapes={
                        key: list(value.shape) for key, value in arrays.items()
                    },
                )
            )
    return artifacts, {
        "max_artifact_bytes": max_artifact_bytes,
        "estimated_uncompressed_bytes": estimated_bytes,
        "written_bytes": sum(item["size_bytes"] for item in artifacts),
        "verified_methods": sorted(
            {str(item["method"]) for item in artifacts if item.get("method")}
        ),
        "skipped": skipped,
    }


def _wait_for_background_tasks(service: Any, *, timeout: float) -> None:
    waiter = getattr(service, "wait_for_background_tasks", None)
    if callable(waiter) and waiter(timeout=timeout) is False:
        raise TimeoutError("ApplicationService background work did not become idle")


def _close_service(service: Any) -> None:
    _wait_for_background_tasks(service, timeout=30.0)
    closer = getattr(service, "close", None)
    if callable(closer):
        closer()


def _product_symbols() -> dict[str, Any]:
    from XBrainLab.backend import application

    names = (
        "ApplicationService",
        "ApplyInterpretationCommand",
        "ConfigureTrainingCommand",
        "CreateEpochCommand",
        "EvaluateCommand",
        "EvaluationPlanIdentity",
        "EvaluationRenderRequest",
        "GenerateDatasetCommand",
        "PreprocessCommand",
        "PreviewInterpretationCommand",
        "QueryStateCommand",
        "SaliencyCommand",
        "SaliencyPlanIdentity",
        "SaliencyRenderRequest",
        "SaliencyRunIdentity",
        "SaveInterpretationRecipeCommand",
        "ScanSourceCommand",
        "TrainCommand",
        "ValidateInterpretationCommand",
    )
    return {name: getattr(application, name) for name in names}
