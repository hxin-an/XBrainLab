from pathlib import Path

from scripts.dev.capture_chatpanel_local_training_completion_walkthrough import (
    TURN_SPECS,
    build_prompts,
    render_markdown,
    validate_training_completion_payload,
)


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
            "model_id": "microsoft/Phi-4-mini-instruct",
            "cache_usage": "15.34 GB",
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
        "visible_messages": [],
        "executed_tools": [
            {"name": "set_model", "success": True, "duration_ms": 1.0},
            {"name": "configure_training", "success": True, "duration_ms": 1.0},
            {"name": "start_training", "success": True, "duration_ms": 1.0},
            {"name": "evaluate", "success": True, "duration_ms": 1.0},
            {"name": "saliency", "success": True, "duration_ms": 1.0},
            {"name": "visualize", "success": True, "duration_ms": 1.0},
            {"name": "saliency", "success": True, "duration_ms": 1.0},
        ],
        "confirmation_dialogs": [
            {"title": "Confirm Action", "text": "Start training", "approved": True}
        ],
        "training_completion": {
            "finished_run_count": 1,
            "metrics_available": True,
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
            },
        },
        "ui_state": {
            "send_button_text": "Send",
            "send_button_enabled": True,
            "input_enabled": True,
            "chat_processing": False,
            "controller_processing": False,
        },
        "elapsed_seconds": 42.0,
    }


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


def test_build_prompts_includes_controlled_output_dir():
    output_dir = Path("/tmp/xbrainlab-output")

    prompts = build_prompts(output_dir)

    assert str(output_dir) in prompts[1]
    assert "1 epoch" in prompts[1]
    assert "device cpu" in prompts[1]


def test_validate_training_completion_payload_accepts_finished_training():
    ok, reason = validate_training_completion_payload(_base_payload())

    assert ok is True
    assert reason == ""


def test_validate_training_completion_payload_requires_finished_run():
    payload = _base_payload()
    payload["final_state"]["training"]["finished_run_count"] = 0

    ok, reason = validate_training_completion_payload(payload)

    assert ok is False
    assert "completed training run" in reason


def test_validate_training_completion_payload_requires_output_dir_match():
    payload = _base_payload()
    payload["final_state"]["training"]["training_option"]["output_dir"] = "./output"

    ok, reason = validate_training_completion_payload(payload)

    assert ok is False
    assert "output_dir" in reason


def test_render_markdown_records_metrics_and_saliency_state():
    markdown = render_markdown(_base_payload())

    assert "# ChatPanel Local Training Completion Walkthrough" in markdown
    assert "confirmation approved: `True`" in markdown
    assert "finished runs: `1`" in markdown
    assert "evaluation metrics available: `True`" in markdown
    assert "saliency available: `True`" in markdown
