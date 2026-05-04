from __future__ import annotations

from scripts.dev.capture_chatpanel_local_walkthrough import (
    VisibleMessage,
    has_raw_debug_text,
    render_markdown,
)


def test_has_raw_debug_text_flags_tool_syntax() -> None:
    assert has_raw_debug_text(['{"tool_name": "scan_source"}']) is True
    assert (
        has_raw_debug_text(["Preprocessing prepares EEG data for modeling."]) is False
    )


def test_render_markdown_includes_visible_transcript() -> None:
    payload = {
        "status": "passed",
        "failure_reason": "",
        "prompt": "Explain preprocessing.",
        "runtime": {
            "classification": "gpu-ready",
            "model_id": "microsoft/Phi-4-mini-instruct",
            "cache_usage": "15.34 GB",
        },
        "hf_offline": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "screenshots": {
            "ready": "artifacts/ui/chatpanel-local-ready.png",
            "response": "artifacts/ui/chatpanel-local-response.png",
        },
        "elapsed_seconds": 12.3,
        "visible_messages": [
            VisibleMessage("user", "Explain preprocessing.").__dict__,
            VisibleMessage(
                "assistant",
                "Preprocessing prepares EEG data for modeling.",
            ).__dict__,
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

    assert "ChatPanel Local Model Walkthrough" in rendered
    assert "Preprocessing prepares EEG data for modeling." in rendered
    assert "tool_name" not in rendered
