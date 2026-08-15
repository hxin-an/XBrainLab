from __future__ import annotations

from types import SimpleNamespace

from scripts.dev.capture_chatpanel_local_walkthrough import (
    VisibleMessage,
    collect_executed_tools,
    has_raw_debug_text,
    render_markdown,
)


def test_has_raw_debug_text_flags_tool_syntax() -> None:
    assert has_raw_debug_text(['{"tool_name": "scan_source"}']) is True
    assert (
        has_raw_debug_text(["Preprocessing prepares EEG data for modeling."]) is False
    )


def test_has_raw_debug_text_flags_backend_status_tokens_in_visible_context() -> None:
    assert (
        has_raw_debug_text(["Interpretation validation: needs_confirmation."]) is True
    )
    assert has_raw_debug_text(['{"decision": "needs_confirmation"}']) is True
    assert has_raw_debug_text(["Workflow status = waiting_for_decision"]) is True


def test_has_raw_debug_text_allows_paths_and_general_snake_case_text() -> None:
    assert (
        has_raw_debug_text(
            ["Loaded /tmp/session_01/needs_confirmation.edf successfully."]
        )
        is False
    )
    assert (
        has_raw_debug_text(
            [r"Loaded C:\\EEG_Data\\subject_01\\recording_file.edf successfully."]
        )
        is False
    )
    assert has_raw_debug_text(["snake_case is a common naming convention."]) is False
    assert (
        has_raw_debug_text(
            ["The validation result is false_positive for this example."]
        )
        is False
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
            "ready": "build/dev-artifacts/ui/chatpanel-local-ready.png",
            "response": "build/dev-artifacts/ui/chatpanel-local-response.png",
        },
        "elapsed_seconds": 12.3,
        "visible_messages": [
            VisibleMessage("user", "Explain preprocessing.").__dict__,
            VisibleMessage(
                "assistant",
                "Preprocessing prepares EEG data for modeling.",
            ).__dict__,
        ],
        "executed_tools": [
            {
                "name": "query_state",
                "success": True,
                "duration_ms": 1.2,
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

    assert "ChatPanel Local Model Walkthrough" in rendered
    assert "Preprocessing prepares EEG data for modeling." in rendered
    assert "`query_state`: `ok`" in rendered
    assert "tool_name" not in rendered


def test_collect_executed_tools_reads_completed_turn_metrics() -> None:
    metrics = SimpleNamespace(
        _completed_turns=[
            SimpleNamespace(
                tool_executions=[
                    SimpleNamespace(
                        name="query_state",
                        success=True,
                        duration_ms=1.23456,
                        error=None,
                    )
                ]
            )
        ]
    )

    assert collect_executed_tools(metrics) == [
        {
            "name": "query_state",
            "success": True,
            "duration_ms": 1.235,
            "error": None,
        }
    ]
