from scripts.dev.capture_chatpanel_local_tool_chain_walkthrough import (
    EXPECTED_TOOLS,
    render_markdown,
    tool_chain_status,
)


def test_tool_chain_status_accepts_expected_successful_sequence():
    ok, reason = tool_chain_status(
        [
            {"name": "scan_source", "success": True},
            {"name": "preview_interpretation", "success": True},
            {"name": "validate_interpretation", "success": True},
        ],
        EXPECTED_TOOLS,
    )

    assert ok is True
    assert reason == ""


def test_tool_chain_status_rejects_missing_or_failed_tools():
    ok, reason = tool_chain_status(
        [
            {"name": "scan_source", "success": True},
            {"name": "preview_interpretation", "success": False},
        ],
        EXPECTED_TOOLS,
    )

    assert ok is False
    assert "preview_interpretation" in reason


def test_render_markdown_records_tool_sequence_and_final_state():
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
            "elapsed_seconds": 12.3,
            "turns": [
                {
                    "index": 1,
                    "prompt": "Scan the source.",
                    "expected_tool": "scan_source",
                    "assistant_text": "Scanned source and found 1 EEG file.",
                    "new_tools": [{"name": "scan_source"}],
                    "screenshot": "turn-1.png",
                },
            ],
            "executed_tools": [
                {"name": "scan_source", "success": True, "duration_ms": 1.0},
            ],
            "final_interpretation_state": {
                "has_scan_result": True,
                "has_candidate": True,
                "has_preview": True,
                "has_validation_decision": True,
                "validation_decision": "needs_confirmation",
                "pending_confirmation": True,
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

    assert "# ChatPanel Local Tool-Chain Walkthrough" in markdown
    assert "scan_source, preview_interpretation, validate_interpretation" in markdown
    assert "has validation decision: `True`" in markdown
