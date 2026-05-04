from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from scripts.dev.capture_data_interpretation_replay import tree_rows
from scripts.dev.capture_human_like_product_walkthrough import (
    REQUIRED_PHASES,
    apply_review_choices,
    build_observable_evidence_summary,
    build_pass_fail_summary,
    build_ui_quality_review,
    forbidden_visible_text,
    render_markdown,
    validate_walkthrough_payload,
)
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def _base_payload() -> dict:
    phases = [
        {
            "phase": phase,
            "screenshot": f"{phase}.png",
            "visible_text": ["Clean user-facing text"],
            "button_state": [{"text": "Send", "enabled": True}],
            "workflow_state": {},
            "notes": {},
        }
        for phase in REQUIRED_PHASES
    ]
    return {
        "status": "passed",
        "failure_reason": "",
        "claim_boundary": (
            "Automated UI-observable PyQt replay; not human Windows desktop acceptance."
        ),
        "source_path": "<walkthrough_source>",
        "recipe_path": "walkthrough-import.recipe.json",
        "phases": phases,
        "screenshots": {phase: f"{phase}.png" for phase in REQUIRED_PHASES},
        "observable_evidence": build_observable_evidence_summary(phases),
        "tool_transcript": [
            {"command": "query_state", "ok": True, "message": "Ready."}
        ],
        "user_facing_message_transcript": [
            {"role": "assistant", "text": "The dataset is ready."}
        ],
        "resource_notes": [
            {
                "label": "after_close",
                "python_threads": 1,
                "qt_active_threads": 0,
                "max_rss_kb": 123,
            }
        ],
        "pass_fail_summary": {
            "passed": True,
            "failed_checks": [],
            "required_phase_count": len(REQUIRED_PHASES),
            "observed_phase_count": len(REQUIRED_PHASES),
            "screenshot_count": len(REQUIRED_PHASES),
            "human_desktop_acceptance": "not performed",
        },
        "ui_quality_review": {
            "automated_checks_passed": True,
            "phase_snapshot_coverage": True,
            "forbidden_visible_text": [],
            "human_design_review_boundary": "Automated replay only.",
        },
        "elapsed_seconds": 10.0,
    }


def test_validate_walkthrough_payload_accepts_complete_artifact_without_files() -> None:
    ok, reason = validate_walkthrough_payload(_base_payload(), require_files=False)

    assert ok is True
    assert reason == ""


def test_validate_walkthrough_payload_rejects_missing_human_boundary() -> None:
    payload = _base_payload()
    payload["claim_boundary"] = "Automated replay."

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "human acceptance" in reason


def test_forbidden_visible_text_flags_raw_tool_syntax() -> None:
    offenders = forbidden_visible_text(
        ["The dataset is ready.", '{"tool_name": "scan_source"}', "Traceback:"]
    )

    assert '{"tool_name": "scan_source"}' in offenders
    assert "Traceback:" in offenders


def test_build_pass_fail_summary_requires_all_phases() -> None:
    phases = [
        {
            "phase": REQUIRED_PHASES[0],
            "visible_text": [],
        }
    ]

    summary = build_pass_fail_summary(phases, screenshots={})

    assert summary["passed"] is False
    assert "missing phase" in "; ".join(summary["failed_checks"])


def test_build_pass_fail_summary_flags_unsettled_threads() -> None:
    phases = [
        {
            "phase": phase,
            "visible_text": [],
            "button_state": [],
            "workflow_state": {},
            "screenshot": "",
        }
        for phase in REQUIRED_PHASES
    ]

    summary = build_pass_fail_summary(
        phases,
        screenshots={},
        resource_notes=[
            {
                "label": "start",
                "python_threads": 1,
                "qt_active_threads": 0,
                "max_rss_kb": 100,
            },
            {
                "label": "after_close",
                "python_threads": 4,
                "qt_active_threads": 2,
                "max_rss_kb": 900000,
            },
        ],
    )

    assert summary["passed"] is False
    failed = "; ".join(summary["failed_checks"])
    assert "Python threads did not settle" in failed
    assert "Qt thread pool still active" in failed
    assert "RSS smoke delta exceeded" in failed


def test_observable_evidence_summary_indexes_phase_snapshots() -> None:
    payload = _base_payload()

    evidence = payload["observable_evidence"]

    assert set(evidence["visible_text_snapshots"]) == set(REQUIRED_PHASES)
    assert evidence["button_states"][REQUIRED_PHASES[0]][0]["text"] == "Send"
    assert REQUIRED_PHASES[0] in evidence["backend_state_snapshots"]


def test_validate_walkthrough_payload_requires_observable_evidence() -> None:
    payload = _base_payload()
    payload.pop("observable_evidence")

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "observable evidence" in reason


def test_validate_walkthrough_payload_requires_ui_quality_pass() -> None:
    payload = _base_payload()
    payload["ui_quality_review"]["automated_checks_passed"] = False

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "ui quality" in reason


def test_build_ui_quality_review_flags_forbidden_visible_text() -> None:
    phases = [
        {
            "phase": "assistant",
            "screenshot": "",
            "visible_text": ["Traceback: hidden"],
            "button_state": [],
            "workflow_state": {},
        }
    ]

    review = build_ui_quality_review(phases, screenshots={})

    assert review["automated_checks_passed"] is False
    assert review["forbidden_visible_text"][0]["phase"] == "assistant"


def test_render_markdown_keeps_claim_boundary_and_transcripts() -> None:
    rendered = render_markdown(_base_payload())

    assert "Human-Like Product Walkthrough" in rendered
    assert "not human Windows desktop acceptance" in rendered
    assert "Observable Evidence" in rendered
    assert "UI Quality Review" in rendered
    assert "The dataset is ready." in rendered
    assert "Remaining Human Verification" in rendered


def test_apply_review_choices_updates_event_role_selector(qtbot) -> None:
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [
                "/tmp/source/sub-01_task-mi_run-1_raw.fif",
                "/tmp/source/sub-01_task-mi_run-2_raw.fif",
            ],
            "label_carriers": ["/tmp/source/events.tsv"],
        },
        preview={"event_roles": {"trial_type": "class label candidate"}},
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    role_item = None
    for index in range(dialog.event_tree.topLevelItemCount()):
        item = dialog.event_tree.topLevelItem(index)
        if item is not None and item.text(0) == "trial_type":
            role_item = item
            break
    assert role_item is not None
    role_selector = dialog.event_tree.itemWidget(role_item, 2)
    assert isinstance(role_selector, QComboBox)

    apply_review_choices(dialog)

    assert role_selector.currentData() == "class cue"
    assert ["trial_type", "event role", "Class cue"] in tree_rows(dialog.event_tree)
