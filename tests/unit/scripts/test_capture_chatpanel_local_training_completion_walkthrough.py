from pathlib import Path
from types import SimpleNamespace

import mne
import pytest

from scripts.dev.capture_chatpanel_local_training_completion_walkthrough import (
    TURN_SPECS,
    build_prompts,
    prepare_training_dataset_ready_state,
    render_markdown,
    validate_training_completion_payload,
    write_synthetic_training_raw_fif,
)
from scripts.dev.local_assistant_capture_runtime import seal_evidence_identity
from XBrainLab.backend.application import (
    ConfigureTrainingCommand,
    PreviewInterpretationCommand,
)
from XBrainLab.llm.core.model_catalog import (
    PRIMARY_LOCAL_MODEL_ID,
    PRIMARY_LOCAL_MODEL_REVISION,
)


def test_synthetic_training_fixture_has_balanced_split_coverage():
    source_path = write_synthetic_training_raw_fif()
    raw = mne.io.read_raw_fif(source_path, preload=False, verbose=False)

    assert len(raw.annotations) == 12
    assert set(raw.annotations.description) == {"left", "right"}
    assert list(raw.annotations.description).count("left") == 6
    assert list(raw.annotations.description).count("right") == 6


def _base_payload():
    return {
        "status": "passed",
        "failure_reason": "",
        "source_path": "/tmp/source.fif",
        "training_output_dir": "/tmp/xbrainlab-training-output",
        "dataset_preparation": {
            "ok": True,
            "commands": [
                {"command": "scan_source", "ok": True},
                {"command": "generate_dataset", "ok": True},
            ],
        },
        "runtime": {
            "classification": "gpu-ready",
            "model_id": "ibm-granite/granite-3.3-2b-instruct",
            "cache_usage": "5.07 GB",
        },
        "hf_offline": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "screenshots": {"ready": "ready.png", "trained": "trained.png"},
        "turns": [
            {
                "index": 1,
                "prompt": "Use EEGNet.",
                "kind": "tool",
                "expected_tool": "set_model",
                "assistant_text": "Model set.",
                "new_tools": [
                    {"name": "set_model", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-1.png",
            },
            {
                "index": 2,
                "prompt": "Configure training.",
                "kind": "tool",
                "expected_tool": "configure_training",
                "assistant_text": "Training configured.",
                "new_tools": [
                    {
                        "name": "configure_training",
                        "success": True,
                        "duration_ms": 1.0,
                    }
                ],
                "screenshot": "turn-2.png",
            },
            {
                "index": 3,
                "prompt": "Start training.",
                "kind": "confirmation",
                "expected_tool": "start_training",
                "assistant_text": "Training started.",
                "new_tools": [
                    {
                        "name": "start_training",
                        "success": True,
                        "duration_ms": 1.0,
                    }
                ],
                "screenshot": "turn-3.png",
            },
            {
                "index": 4,
                "prompt": "Evaluate.",
                "kind": "tool",
                "expected_tool": "evaluate",
                "assistant_text": "Evaluation summary ready.",
                "new_tools": [
                    {"name": "evaluate", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-4.png",
            },
            {
                "index": 5,
                "prompt": "Configure saliency.",
                "kind": "tool",
                "expected_tool": "saliency",
                "assistant_text": "Saliency parameters configured.",
                "new_tools": [
                    {"name": "saliency", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-5.png",
            },
            {
                "index": 6,
                "prompt": "Visualize.",
                "kind": "tool",
                "expected_tool": "visualize",
                "assistant_text": "Visualization summary ready.",
                "new_tools": [
                    {"name": "visualize", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-6.png",
            },
            {
                "index": 7,
                "prompt": "Saliency readiness.",
                "kind": "tool",
                "expected_tool": "saliency",
                "assistant_text": "Saliency summary ready.",
                "new_tools": [
                    {"name": "saliency", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-7.png",
            },
        ],
        "visible_messages": [
            {
                "sender": "assistant",
                "text": "Training completed. Results are ready in Evaluation.",
            }
        ],
        "executed_tools": [
            {"name": "set_model", "success": True, "duration_ms": 1.0},
            {"name": "configure_training", "success": True, "duration_ms": 1.0},
            {"name": "start_training", "success": True, "duration_ms": 1.0},
            {"name": "evaluate", "success": True, "duration_ms": 1.0},
            {"name": "saliency", "success": True, "duration_ms": 1.0},
            {"name": "visualize", "success": True, "duration_ms": 1.0},
            {"name": "saliency", "success": True, "duration_ms": 1.0},
        ],
        "confirmation_events": [
            {
                "surface": "inline_card",
                "request_id": "confirmation-1",
                "action": "Start training",
                "approved": True,
            }
        ],
        "training_completion": {
            "finished_run_count": 1,
            "metrics_available": True,
            "assistant_terminal_text": (
                "Training completed. Results are ready in Evaluation."
            ),
        },
        "final_state": {
            "dataset": {"available": True},
            "training": {
                "has_model": True,
                "has_training_option": True,
                "training_option": {
                    "epoch": 1,
                    "batch_size": 2,
                    "learning_rate": 0.001,
                    "output_dir": "/tmp/xbrainlab-training-output",
                },
                "has_trainer": True,
                "is_running": False,
                "finished_run_count": 1,
            },
            "evaluation": {
                "available": True,
                "metrics_available": True,
                "total_plans": 1,
            },
            "visualization": {
                "saliency_configured": True,
                "saliency_available": True,
                "saliency_params": {
                    "SmoothGrad": {
                        "nt_samples": 2,
                        "nt_samples_batch_size": 1,
                        "stdevs": 1.0,
                    },
                    "_methods": ["SmoothGrad"],
                },
            },
        },
        "ui_state": {
            "send_button_text": "Send",
            "send_button_enabled": True,
            "input_enabled": True,
            "chat_processing": False,
            "controller_processing": False,
        },
        "shutdown": {"status": "completed", "detail": ""},
        "elapsed_seconds": 42.0,
    }


def _strict_workflow_payload() -> dict:
    payload = _base_payload()
    payload.pop("source_path")
    source_identity = seal_evidence_identity(
        "source",
        {
            "branch": "stabilize/product-quality-closure",
            "commit_sha": "a" * 40,
            "head_tree_sha": "b" * 40,
            "dirty": False,
            "dirty_fingerprint": "c" * 64,
            "source_content_sha256": "d" * 64,
        },
    )
    model_identity = seal_evidence_identity(
        "model",
        {
            "requested_model_id": PRIMARY_LOCAL_MODEL_ID,
            "loaded_model_id": PRIMARY_LOCAL_MODEL_ID,
            "loaded_revision": PRIMARY_LOCAL_MODEL_REVISION,
            "snapshot_manifest_sha256": "e" * 64,
            "snapshot_file_count": 8,
            "snapshot_total_bytes": 5_000_000_000,
            "cache_complete": True,
            "loader_policy": "pinned-local-files-only",
        },
    )
    screenshots = {
        "ready": {
            "relative_path": "ready.png",
            "sha256": "f" * 64,
            "byte_size": 123,
            "dimensions": [1280, 900],
        },
        "trained": {
            "relative_path": "trained.png",
            "sha256": "1" * 64,
            "byte_size": 456,
            "dimensions": [1280, 900],
        },
    }
    payload["runtime"].update(
        {
            "requested_model_id": PRIMARY_LOCAL_MODEL_ID,
            "loaded_model_id": PRIMARY_LOCAL_MODEL_ID,
            "model_identity": model_identity,
        }
    )
    payload["source_identity"] = source_identity
    payload["capture_source"] = {
        "identity_at_start": source_identity["identity_sha256"],
        "identity_at_completion": source_identity["identity_sha256"],
        "stable": True,
    }
    payload["host_assistance"] = {
        "classification": "host-assisted",
        "used": True,
        "actions": ["approved the visible training confirmation card"],
    }
    payload["screenshot_artifacts"] = {
        "artifacts": screenshots,
        "aggregate_sha256": seal_evidence_identity("screenshots", screenshots)[
            "identity_sha256"
        ],
    }
    runtime_inputs = {
        "training_eeg_fixture": {
            "kind": "deterministic-eeg-fixture",
            "display_name": "training_completion_raw.fif",
            "sha256": "2" * 64,
            "byte_size": 2048,
            "retained": False,
        }
    }
    runtime_input_evidence = {
        "artifacts": runtime_inputs,
        "aggregate_sha256": seal_evidence_identity(
            "runtime-inputs",
            runtime_inputs,
        )["identity_sha256"],
    }
    payload["runtime_input_artifacts"] = runtime_input_evidence
    payload["capture_runtime_inputs"] = {
        "identity_at_start": runtime_input_evidence["aggregate_sha256"],
        "identity_at_completion": runtime_input_evidence["aggregate_sha256"],
        "stable": True,
    }
    return payload


def test_turn_specs_capture_training_completion_and_analysis_tools():
    assert [turn["expected_tool"] for turn in TURN_SPECS] == [
        "set_model",
        "configure_training",
        "start_training",
        "evaluate",
        "saliency",
        "visualize",
        "saliency",
    ]


def test_build_prompts_keep_host_controlled_output_dir_out_of_model_prompt():
    output_dir = Path("/tmp/xbrainlab-output")

    prompts = build_prompts()

    assert str(output_dir) not in prompts[1]
    assert "output_dir" not in prompts[1]
    assert "1 epoch" in prompts[1]
    assert "device cpu" in prompts[1]
    assert (
        prompts[4] == "Configure SmoothGrad saliency with nt_samples 2, "
        "nt_samples_batch_size 1, and stdevs 1.0. Reply with one short "
        "result sentence."
    )


def test_prepare_dataset_ready_state_confirms_internal_event_labels(monkeypatch):
    commands = []

    class FakeState:
        def to_dict(self):
            return {"pipeline_stage": "dataset"}

    class FakeService:
        def execute(self, command):
            commands.append(command)
            return SimpleNamespace(
                ok=True,
                failed=False,
                message="ok",
                error_type=None,
                diagnostics={},
            )

        def get_state(self):
            return FakeState()

    monkeypatch.setattr(
        "scripts.dev.capture_chatpanel_local_training_completion_walkthrough."
        "get_application_service",
        lambda _study: FakeService(),
    )

    output_dir = Path("/tmp/xbrainlab-training-output")
    result = prepare_training_dataset_ready_state(
        object(),
        Path("/tmp/source.fif"),
        output_dir,
    )

    preview = next(
        command
        for command in commands
        if isinstance(command, PreviewInterpretationCommand)
    )
    configure = next(
        command for command in commands if isinstance(command, ConfigureTrainingCommand)
    )
    assert result["ok"] is True
    assert preview.choices == {"label_carrier": "embedded_events"}
    assert configure.output_dir == str(output_dir)
    assert configure.epoch == 1
    assert configure.batch_size == 2
    assert configure.learning_rate == 0.001
    assert configure.device == "cpu"


def test_validate_training_completion_payload_accepts_finished_training():
    ok, reason = validate_training_completion_payload(_strict_workflow_payload())

    assert ok is True
    assert reason == ""


def test_validate_training_completion_payload_requires_bound_fixture_identity():
    payload = _strict_workflow_payload()
    payload.pop("runtime_input_artifacts")
    payload.pop("capture_runtime_inputs")

    ok, reason = validate_training_completion_payload(payload)

    assert ok is False
    assert "runtime input" in reason.lower()


def test_validate_training_completion_payload_requires_finished_run():
    payload = _base_payload()
    payload["final_state"]["training"]["finished_run_count"] = 0

    ok, reason = validate_training_completion_payload(payload)

    assert ok is False
    assert "completed training run" in reason


def test_validate_training_completion_payload_requires_visible_terminal_result():
    payload = _base_payload()
    payload["training_completion"]["assistant_terminal_text"] = ""
    payload["visible_messages"] = []

    ok, reason = validate_training_completion_payload(payload)

    assert ok is False
    assert "terminal" in reason.lower()


def test_validate_training_completion_payload_requires_output_dir_match():
    payload = _base_payload()
    payload["final_state"]["training"]["training_option"]["output_dir"] = "./output"

    ok, reason = validate_training_completion_payload(payload)

    assert ok is False
    assert "output_dir" in reason


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("_methods", ["Gradient", "Gradient * Input"]),
        ("nt_samples", 5),
        ("nt_samples_batch_size", None),
        ("stdevs", 0.5),
    ],
)
def test_validate_training_completion_payload_requires_exact_saliency_request(
    field: str,
    value: object,
) -> None:
    payload = _base_payload()
    saliency_params = payload["final_state"]["visualization"]["saliency_params"]
    if field == "_methods":
        saliency_params[field] = value
    else:
        saliency_params["SmoothGrad"][field] = value

    ok, reason = validate_training_completion_payload(payload)

    assert ok is False
    assert field in reason


def test_render_markdown_records_metrics_and_saliency_state():
    markdown = render_markdown(_base_payload())

    assert "# ChatPanel Local Training Completion Walkthrough" in markdown
    assert "confirmation approved: `True`" in markdown
    assert "finished runs: `1`" in markdown
    assert "evaluation metrics available: `True`" in markdown
    assert "saliency available: `True`" in markdown
    assert "shutdown: `completed`" in markdown
    assert "/tmp/source.fif" not in markdown
