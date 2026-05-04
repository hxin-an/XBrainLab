from scripts.dev.capture_chatpanel_local_training_readiness_walkthrough import (
    TURN_SPECS,
    render_markdown,
    validate_training_readiness_payload,
)


def _base_payload():
    return {
        "status": "passed",
        "failure_reason": "",
        "source_path": "/tmp/source.fif",
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
        "screenshots": {"ready": "ready.png"},
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
                "assistant_text": "Cancelled: Start training.",
                "new_tools": [],
                "screenshot": "turn-3.png",
            },
            {
                "index": 4,
                "prompt": "Visualize readiness.",
                "kind": "tool",
                "expected_tool": "visualize",
                "assistant_text": "Visualization summary ready.",
                "new_tools": [
                    {"name": "visualize", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-4.png",
            },
            {
                "index": 5,
                "prompt": "Saliency readiness.",
                "kind": "tool",
                "expected_tool": "saliency",
                "assistant_text": "Saliency summary ready.",
                "new_tools": [
                    {"name": "saliency", "success": True, "duration_ms": 1.0}
                ],
                "screenshot": "turn-5.png",
            },
            {
                "index": 6,
                "prompt": "Evaluate.",
                "kind": "blocked",
                "expected_tool": "evaluate",
                "assistant_text": "Create a training plan before evaluating results.",
                "new_tools": [
                    {
                        "name": "evaluate",
                        "success": False,
                        "duration_ms": 0.0,
                        "error": "Create a training plan before evaluating results.",
                    }
                ],
                "screenshot": "turn-6.png",
            },
        ],
        "visible_messages": [],
        "executed_tools": [
            {"name": "set_model", "success": True, "duration_ms": 1.0},
            {"name": "configure_training", "success": True, "duration_ms": 1.0},
            {"name": "visualize", "success": True, "duration_ms": 1.0},
            {"name": "saliency", "success": True, "duration_ms": 1.0},
            {
                "name": "evaluate",
                "success": False,
                "duration_ms": 0.0,
                "error": "Create a training plan before evaluating results.",
            },
        ],
        "confirmation_dialogs": [
            {"title": "Confirm Action", "text": "Start training", "approved": False}
        ],
        "final_state": {
            "dataset": {"available": True},
            "training": {
                "has_model": True,
                "has_training_option": True,
                "has_trainer": False,
                "is_running": False,
            },
            "evaluation": {"available": False, "total_plans": 0},
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


def test_turn_specs_capture_training_boundary_and_analysis_tools():
    assert [turn["kind"] for turn in TURN_SPECS] == [
        "tool",
        "tool",
        "confirmation",
        "tool",
        "tool",
        "blocked",
    ]
    assert [turn["expected_tool"] for turn in TURN_SPECS] == [
        "set_model",
        "configure_training",
        "start_training",
        "visualize",
        "saliency",
        "evaluate",
    ]


def test_validate_training_readiness_payload_accepts_boundary():
    ok, reason = validate_training_readiness_payload(_base_payload())

    assert ok is True
    assert reason == ""


def test_validate_training_readiness_payload_requires_training_confirmation():
    payload = _base_payload()
    payload["confirmation_dialogs"] = []

    ok, reason = validate_training_readiness_payload(payload)

    assert ok is False
    assert "confirmation" in reason


def test_render_markdown_records_analysis_boundary():
    markdown = render_markdown(_base_payload())

    assert "# ChatPanel Local Training Readiness Walkthrough" in markdown
    assert "training confirmations observed: `1`" in markdown
    assert "expected tool: `saliency`" in markdown
    assert "evaluate blocked: `True`" in markdown
