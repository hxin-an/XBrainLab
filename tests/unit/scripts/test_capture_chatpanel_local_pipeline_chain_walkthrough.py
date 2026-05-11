from scripts.dev.capture_chatpanel_local_pipeline_chain_walkthrough import (
    EXPECTED_TOOLS,
    render_markdown,
    validate_pipeline_payload,
)


def test_validate_pipeline_payload_requires_tool_sequence_and_final_state():
    ok, reason = validate_pipeline_payload(
        {
            "expected_tools": EXPECTED_TOOLS,
            "executed_tools": [
                {"name": name, "success": True} for name in EXPECTED_TOOLS
            ],
            "confirmation_dialogs": [{"title": "Confirm Action"}],
            "final_state": {
                "raw": {"loaded": True},
                "interpretation": {"has_applied_interpretation": True},
                "epoch": {"available": True},
                "dataset": {"available": True},
            },
        },
    )

    assert ok is True
    assert reason == ""


def test_validate_pipeline_payload_rejects_missing_dataset():
    ok, reason = validate_pipeline_payload(
        {
            "expected_tools": EXPECTED_TOOLS,
            "executed_tools": [
                {"name": name, "success": True} for name in EXPECTED_TOOLS
            ],
            "confirmation_dialogs": [{"title": "Confirm Action"}],
            "final_state": {
                "raw": {"loaded": True},
                "interpretation": {"has_applied_interpretation": True},
                "epoch": {"available": True},
                "dataset": {"available": False},
            },
        },
    )

    assert ok is False
    assert "dataset" in reason


def test_render_markdown_records_confirmation_and_dataset_state():
    markdown = render_markdown(
        {
            "status": "passed",
            "failure_reason": "",
            "source_path": "/tmp/source.fif",
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
            "expected_tools": EXPECTED_TOOLS,
            "confirmation_dialogs": [{"title": "Confirm Action"}],
            "elapsed_seconds": 42.0,
            "turns": [
                {
                    "index": 1,
                    "prompt": "Scan.",
                    "expected_tool": "scan_source",
                    "assistant_text": "Scanned source.",
                    "new_tools": [{"name": "scan_source"}],
                    "screenshot": "turn-1.png",
                },
            ],
            "executed_tools": [
                {"name": "scan_source", "success": True, "duration_ms": 1.0},
            ],
            "final_state": {
                "interpretation": {
                    "has_applied_interpretation": True,
                    "validation_decision": "needs_confirmation",
                },
                "epoch": {"available": True, "epoch_count": 3},
                "dataset": {"available": True, "count": 1},
            },
            "ui_state": {
                "send_button_text": "Send",
                "send_button_enabled": True,
                "input_enabled": True,
                "chat_processing": False,
                "controller_processing": False,
            },
        },
    )

    assert "# ChatPanel Local Pipeline-Chain Walkthrough" in markdown
    assert "confirmation dialogs observed: `1`" in markdown
    assert "dataset available: `True`" in markdown
