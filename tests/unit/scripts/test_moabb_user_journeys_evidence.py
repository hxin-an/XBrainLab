from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.dev.moabb_user_journeys.cli import _finish_manifest
from scripts.dev.moabb_user_journeys.evidence import (
    artifact_record,
    empty_dataset_evidence,
    evaluate_quality_acceptance,
    persist_training_curves,
    showcase_quality_complete,
    validate_evidence_manifest,
)
from scripts.dev.moabb_user_journeys.product import (
    _verify_persisted_training_seeds,
    review_dataset,
    run_dataset_journey,
)
from scripts.dev.moabb_user_journeys.registry import (
    REPO_ROOT,
    load_registry,
    materialize_dataset,
)


class _Result:
    def __init__(
        self,
        command: Any,
        *,
        diagnostics: dict[str, Any] | None = None,
    ):
        self.command_name = command.name.value
        self.ok = True
        self.status = SimpleNamespace(value="success")
        self.message = "ok"
        self.error_type = SimpleNamespace(value="none")
        self.error_message = None
        self.recoverable = False
        self.diagnostics = diagnostics or {}
        self._state = {
            "interpretation": {"has_applied_interpretation": True},
            "preprocessed": {"file_count": 1},
            "epoch": {"epoch_count": 12},
            "dataset": {"has_datasets": True},
            "training": {
                "has_training_option": True,
                "training_option": {"device": "cpu"},
            },
        }

    def to_internal_dict(self) -> dict[str, Any]:
        return {"state": self._state}


class _RecordingService:
    def __init__(self):
        self.commands: list[str] = []
        self.closed = False
        self.wait_timeouts: list[float] = []
        self.configured_seed: int | None = None
        self.configured_repeat = 0
        self.training_output: Path | None = None
        self.evaluation_requests: list[Any] = []

    def execute(self, command: Any) -> _Result:
        name = command.name.value
        self.commands.append(name)
        if name == "save_interpretation_recipe":
            Path(command.recipe_path).write_text('{"recipe": true}\n', encoding="utf-8")
        if name == "configure_training":
            self.configured_seed = command.seed
            self.configured_repeat = command.repeat
            self.training_output = Path(command.output_dir)
            result = _Result(command)
            result._state["training"]["training_option"].update(
                {
                    "seed": command.seed,
                    "repeat_seeds": [
                        command.seed + index for index in range(command.repeat)
                    ],
                }
            )
            return result
        if name == "train":
            self._persist_training_records()
        if name == "validate_interpretation":
            return _Result(command, diagnostics={"validation_decision": "accepted"})
        if name == "query_state":
            return _Result(
                command,
                diagnostics={
                    "payload_type": "training_history",
                    "row_count": 1,
                    "rows": [
                        {
                            "model_name": "EEGNet",
                            "train_loss": [0.9, 0.5],
                            "validation_accuracy": [0.55, 0.7],
                            "test_accuracy": [0.65],
                        }
                    ],
                },
            )
        if name == "evaluate":
            return _Result(
                command,
                diagnostics={
                    "evaluation_splits": ["test"],
                    "plans": [
                        {
                            "identity": {"plan_index": 0},
                            "finished_run_count": 1,
                        }
                    ],
                },
            )
        return _Result(command)

    def _persist_training_records(self) -> None:
        from XBrainLab.backend.training.record.artifact_store import (
            TRAINING_RECORD_ARTIFACT_TYPE,
            write_json_npz_artifact,
        )

        assert self.configured_seed is not None
        assert self.training_output is not None
        for repeat in range(self.configured_repeat):
            output_dir = (
                self.training_output / "dataset" / "model-plan" / f"Repeat-{repeat}"
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            write_json_npz_artifact(
                output_dir / "record",
                artifact_type=TRAINING_RECORD_ARTIFACT_TYPE,
                payload={
                    "record_schema_version": 1,
                    "seed": self.configured_seed + repeat,
                },
                arrays={},
            )

    def get_view_publication(self) -> SimpleNamespace:
        methods = [
            SimpleNamespace(method="Gradient", complete=True),
            SimpleNamespace(method="Gradient * Input", complete=True),
        ]
        coverage = [SimpleNamespace(plan_index=0, run_index=0, methods=methods)]
        return SimpleNamespace(
            generation=1,
            training_boundary=SimpleNamespace(trainer_identity="moabb-journey-trainer"),
            state=SimpleNamespace(
                dataset=SimpleNamespace(
                    split_specification_fingerprint="moabb-journey-split-sha256",
                    split_epoch_revision=1,
                ),
                visualization=SimpleNamespace(saliency_coverage=coverage),
            ),
        )

    def get_evaluation_render(self, request: Any) -> SimpleNamespace:
        import numpy as np

        self.evaluation_requests.append(request)
        labels = np.arange(7)
        outputs = np.eye(7) * 4.0
        return SimpleNamespace(
            request=request,
            data=SimpleNamespace(
                labels=labels,
                outputs=outputs,
                evaluation_split="test",
                metrics={
                    index: {
                        "precision": 1.0,
                        "recall": 1.0,
                        "f1-score": 1.0,
                        "support": 1,
                    }
                    for index in range(7)
                },
                class_labels={index: f"class-{index}" for index in range(7)},
            ),
        )

    def get_saliency_render(self, request: Any) -> SimpleNamespace:
        import numpy as np

        return SimpleNamespace(
            request=request,
            data=SimpleNamespace(
                saliency_by_class={
                    index: np.ones((1, 2, 3), dtype=np.float32) for index in range(7)
                },
                source_split="test",
            ),
        )

    def wait_for_background_tasks(self, timeout: float) -> bool:
        self.wait_timeouts.append(timeout)
        return True

    def close(self) -> None:
        self.closed = True


class _UnverifiableConfiguredSeedService(_RecordingService):
    def execute(self, command: Any) -> _Result:
        result = super().execute(command)
        if command.name.value == "configure_training":
            training_option = result._state["training"]["training_option"]
            training_option.pop("seed", None)
            training_option.pop("repeat_seeds", None)
        return result


def _dataset() -> dict[str, Any]:
    registry = load_registry()
    return materialize_dataset(
        registry["datasets"][0],
        data_root=REPO_ROOT / registry["resource_policy"]["data_root"],
    )


def test_smoke_manifest_can_complete_workflow_but_quality_stays_pending() -> None:
    evidence = empty_dataset_evidence(
        _dataset(),
        source_artifacts=[],
        execution_profile="smoke",
        attempt=1,
        previous_failure=None,
    )
    manifest = {
        "datasets": [evidence],
        "failures": [],
        "quality_evidence_status": "complete",
    }

    _finish_manifest(manifest, "smoke")

    assert manifest["status"] == "completed"
    assert manifest["quality_evidence_status"] == "pending"
    assert evidence["model"]["epochs"] == 1


def test_showcase_requires_actual_device_curve_and_held_out_metric(
    tmp_path: Path,
) -> None:
    evidence = empty_dataset_evidence(
        _dataset(),
        source_artifacts=[],
        execution_profile="showcase",
        attempt=1,
        previous_failure=None,
    )
    history = {
        "rows": [
            {
                "train_loss": [1.0, 0.7, 0.5],
                "validation_accuracy": [0.4, 0.5, 0.6],
                "test_accuracy": [0.55],
            }
        ]
    }
    curve = persist_training_curves(tmp_path / "curves.json", training_history=history)
    assert curve is not None
    evidence["training_curves"] = [curve]
    evidence["metrics"] = {"training_history": history}
    evaluation = {
        "valid": True,
        "split": "test",
        "test_prediction_read_count": 1,
        "metrics": {"balanced_accuracy": 0.7, "accuracy": 0.7},
        "baselines": {"chance_baseline": 1 / 7, "majority_baseline": 0.2},
    }
    evidence["quality_acceptance"] = evaluate_quality_acceptance(
        evidence["quality_acceptance"]["specification"],
        [evaluation],
    )

    assert showcase_quality_complete(evidence) is False

    evidence["model"]["actual_device"] = "cpu"
    for method in evidence["saliency"]["methods"]:
        path = tmp_path / f"{method.replace(' ', '-')}.npz"
        path.write_bytes(method.encode())
        evidence["saliency"]["artifacts"].append(
            artifact_record(
                path,
                source="application_service_saliency_render",
                method=method,
            )
        )
    assert showcase_quality_complete(evidence) is False

    evidence["model"]["reproducibility"] = {
        "base_seed": evidence["seed"],
        "derivation": "base_seed + zero_based_repeat_index",
        "configured_training_state_verified": True,
        "persisted_train_records_verified": True,
        "repeat_seeds": [evidence["seed"]],
    }
    evidence["model"]["resolved_training_state"] = {
        "training_option": {
            "seed": evidence["seed"],
            "repeat_seeds": [evidence["seed"]],
        }
    }
    assert showcase_quality_complete(evidence) is True
    persisted = json.loads((tmp_path / "curves.json").read_text(encoding="utf-8"))
    assert persisted["rows"] == history["rows"]


def test_unmet_showcase_threshold_stays_pending_and_manifest_is_partial() -> None:
    evidence = empty_dataset_evidence(
        _dataset(),
        source_artifacts=[],
        execution_profile="showcase",
        attempt=1,
        previous_failure=None,
    )
    evidence["quality_acceptance"] = evaluate_quality_acceptance(
        evidence["quality_acceptance"]["specification"],
        [
            {
                "valid": True,
                "split": "test",
                "test_prediction_read_count": 1,
                "metrics": {"balanced_accuracy": 1 / 7, "accuracy": 0.2},
                "baselines": {
                    "chance_baseline": 1 / 7,
                    "majority_baseline": 0.2,
                },
            }
        ],
    )
    manifest = {
        "datasets": [evidence],
        "failures": [],
        "quality_evidence_status": "pending",
    }

    _finish_manifest(manifest, "showcase")

    assert evidence["quality_acceptance"]["status"] == "threshold_not_met"
    assert manifest["quality_evidence_status"] == "pending"
    assert manifest["status"] == "partial"


def test_fixed_quality_floor_is_not_derived_from_held_out_baselines() -> None:
    specification = {
        "held_out_split": "test",
        "test_access_policy": "Read test predictions once after selection.",
        "rules": [
            {
                "metric": "balanced_accuracy",
                "operator": ">=",
                "threshold": {
                    "kind": "fixed",
                    "name": "predeclared_meaningful_floor",
                    "value": 0.25,
                },
                "rationale": "Predeclared quality margin above seven-class chance.",
            }
        ],
    }

    result = evaluate_quality_acceptance(
        specification,
        [
            {
                "valid": True,
                "split": "test",
                "test_prediction_read_count": 1,
                "metrics": {"balanced_accuracy": 0.24},
                "baselines": {"chance_baseline": 1 / 7},
            }
        ],
    )

    rule = result["evaluations"][0]["acceptance_rules"][0]
    assert rule["threshold_name"] == "predeclared_meaningful_floor"
    assert rule["threshold_value"] == 0.25
    assert rule["passed"] is False
    assert result["passed"] is False


def test_review_uses_read_only_application_service_import_commands() -> None:
    service = _RecordingService()

    result = review_dataset(
        _dataset(),
        confirm_resource_plan=False,
        service_factory=lambda: service,
    )

    assert result["status"] == "validated"
    assert service.commands == [
        "scan_source",
        "preview_interpretation",
        "validate_interpretation",
    ]
    assert service.closed is True


def test_showcase_journey_records_actual_product_sequence_and_quality_inputs(
    tmp_path: Path,
) -> None:
    service = _RecordingService()

    evidence = run_dataset_journey(
        _dataset(),
        run_root=tmp_path,
        source_artifacts=[],
        execution_profile="showcase",
        confirm_resource_plan=False,
        attempt=1,
        previous_failure=None,
        service_factory=lambda: service,
    )

    assert evidence["failures"] == []
    assert service.evaluation_requests[0].trainer_identity == "moabb-journey-trainer"
    assert service.evaluation_requests[0].split_specification_fingerprint == (
        "moabb-journey-split-sha256"
    )
    assert service.evaluation_requests[0].split_epoch_revision == 1
    assert evidence["model"]["epochs"] == 30
    assert evidence["model"]["actual_device"] == "cpu"
    assert evidence["model"]["resolved_training_state"]["training_option"] == {
        "device": "cpu",
        "seed": evidence["seed"],
        "repeat_seeds": [evidence["seed"]],
    }
    assert evidence["model"]["reproducibility"] == {
        "base_seed": evidence["seed"],
        "derivation": "base_seed + zero_based_repeat_index",
        "configured_training_state_verified": True,
        "persisted_train_records_verified": True,
        "repeat_seeds": [evidence["seed"]],
    }
    assert service.configured_seed == evidence["seed"]
    assert evidence["quality_evidence_status"] == "complete"
    assert evidence["training_curves"][0]["size_bytes"] > 0
    assert evidence["quality_acceptance"]["passed"] is True
    assert {item["method"] for item in evidence["saliency"]["artifacts"]} == {
        "Gradient",
        "Gradient * Input",
    }
    assert service.wait_timeouts == [1800.0, 30.0]
    assert service.commands == [
        "scan_source",
        "preview_interpretation",
        "validate_interpretation",
        "apply_interpretation",
        "save_interpretation_recipe",
        "preprocess",
        "preprocess",
        "preprocess",
        "preprocess",
        "create_epoch",
        "configure_dataset_split",
        "configure_training",
        "saliency",
        "train",
        "query_state",
        "evaluate",
        "saliency",
    ]


def test_showcase_journey_fails_closed_when_configured_seed_is_unverifiable(
    tmp_path: Path,
) -> None:
    service = _UnverifiableConfiguredSeedService()

    evidence = run_dataset_journey(
        _dataset(),
        run_root=tmp_path,
        source_artifacts=[],
        execution_profile="showcase",
        confirm_resource_plan=False,
        attempt=1,
        previous_failure=None,
        service_factory=lambda: service,
    )

    assert evidence["quality_evidence_status"] == "failed"
    assert evidence["failures"] == [
        {
            "stage": "training",
            "type": "RuntimeError",
            "message": (
                "Configured training state does not verify the requested repeat "
                "seeds: expected [1729], observed None."
            ),
            "recoverable": True,
        }
    ]
    assert "train" not in service.commands


def test_persisted_training_seed_verification_fails_closed_on_mismatch(
    tmp_path: Path,
) -> None:
    from XBrainLab.backend.training.record.artifact_store import (
        TRAINING_RECORD_ARTIFACT_TYPE,
        write_json_npz_artifact,
    )

    record_dir = tmp_path / "dataset" / "model-plan" / "Repeat-0"
    record_dir.mkdir(parents=True)
    write_json_npz_artifact(
        record_dir / "record",
        artifact_type=TRAINING_RECORD_ARTIFACT_TYPE,
        payload={"record_schema_version": 1, "seed": 1730},
        arrays={},
    )

    with pytest.raises(RuntimeError, match="Persisted TrainRecord seeds"):
        _verify_persisted_training_seeds(
            tmp_path,
            expected_seeds=[1729],
        )


def test_persisted_training_seed_verification_accepts_each_dataset_plan(
    tmp_path: Path,
) -> None:
    from XBrainLab.backend.training.record.artifact_store import (
        TRAINING_RECORD_ARTIFACT_TYPE,
        write_json_npz_artifact,
    )

    for plan_name in ("model-plan-a", "model-plan-b"):
        record_dir = tmp_path / plan_name / "Repeat-0"
        record_dir.mkdir(parents=True)
        write_json_npz_artifact(
            record_dir / "record",
            artifact_type=TRAINING_RECORD_ARTIFACT_TYPE,
            payload={"record_schema_version": 1, "seed": 1729},
            arrays={},
        )

    assert _verify_persisted_training_seeds(
        tmp_path,
        expected_seeds=[1729],
    ) == [1729]


def test_runtime_manifest_guard_requires_quality_status() -> None:
    manifest = {
        "schema_version": "1.0.0",
        "run_id": "test",
        "status": "planned",
        "application": {},
        "runner": {},
        "resource_policy": {},
        "datasets": [],
        "failures": [],
        "claim_boundary": [],
    }

    try:
        validate_evidence_manifest(manifest)
    except ValueError as exc:
        assert "quality_evidence_status" in str(exc)
    else:
        raise AssertionError("quality_evidence_status must be mandatory")


def test_runtime_manifest_guard_rejects_completed_showcase_with_pending_quality() -> (
    None
):
    manifest = {
        "schema_version": "1.0.0",
        "run_id": "test",
        "status": "completed",
        "quality_evidence_status": "pending",
        "application": {},
        "runner": {"execution_profile": "showcase"},
        "resource_policy": {},
        "datasets": [],
        "failures": [],
        "claim_boundary": [],
    }

    try:
        validate_evidence_manifest(manifest)
    except ValueError as exc:
        assert "completed showcase" in str(exc)
    else:
        raise AssertionError("pending showcase quality must not be completed")
