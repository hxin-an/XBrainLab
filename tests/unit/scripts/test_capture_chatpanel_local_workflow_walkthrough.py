from __future__ import annotations

from scripts.dev.capture_chatpanel_local_workflow_walkthrough import render_markdown


def test_render_markdown_lists_turns_and_tools() -> None:
    payload = {
        "status": "passed",
        "failure_reason": "",
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
        "elapsed_seconds": 42.0,
        "turns": [
            {
                "index": 1,
                "prompt": "Check state.",
                "assistant_text": "Application state snapshot ready.",
                "new_tool_count": 1,
                "screenshot": "turn-1.png",
            },
            {
                "index": 2,
                "prompt": "Create epochs.",
                "assistant_text": "Epoch creation is not available yet.",
                "new_tool_count": 0,
                "screenshot": "turn-2.png",
            },
        ],
        "executed_tools": [
            {
                "name": "query_state",
                "success": True,
                "duration_ms": 1.0,
                "error": None,
            }
        ],
        "ui_state": {
            "send_button_text": "Send",
            "send_button_enabled": True,
            "input_enabled": True,
            "chat_processing": False,
            "controller_processing": False,
        },
    }

    rendered = render_markdown(payload)

    assert "Turn 1" in rendered
    assert "Turn 2" in rendered
    assert "`query_state`: `ok`" in rendered
    assert "Epoch creation is not available yet." in rendered
