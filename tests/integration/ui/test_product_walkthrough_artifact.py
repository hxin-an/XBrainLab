"""Linux-authored visible artifact gate for the human-like product walkthrough."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.dev.capture_human_like_product_walkthrough import REQUIRED_PHASES


def test_human_like_capture_script_is_a_real_exit_code_gate(tmp_path) -> None:
    """Execute the product capture itself so helper-only tests cannot mask failure."""
    root = Path(__file__).resolve().parents[3]
    output_dir = tmp_path / "human-like-walkthrough-runs" / "current"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(  # noqa: S603 - fixed repository script path
        [
            sys.executable,
            "scripts/dev/capture_human_like_product_walkthrough.py",
            "--output-dir",
            str(output_dir),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=180,
    )
    reports = sorted(output_dir.parent.glob("*/human-like-walkthrough.md"))
    report_text = reports[-1].read_text(encoding="utf-8") if reports else ""

    assert completed.returncode == 0, (
        "Human-like walkthrough process failed.\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}\n"
        f"report:\n{report_text}"
    )
    payload = json.loads(
        (output_dir / "human-like-walkthrough.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "passed"
    expected_phase_count = len(REQUIRED_PHASES)
    assert payload["pass_fail_summary"]["observed_phase_count"] == expected_phase_count
    assert payload["pass_fail_summary"]["required_phase_count"] == expected_phase_count
    assert payload["artifact_run"]["source_fingerprint"]
    assert isinstance(payload["artifact_run"]["working_tree_dirty"], bool)

    phases = {phase["phase"]: phase for phase in payload["phases"]}
    for phase_name in (
        "data_interpretation_apply",
        "data_interpretation_reapply_recipe",
    ):
        handoff = phases[phase_name]["notes"]["strict_review_handoff"]
        candidate_id = handoff["candidate_id"]
        assert candidate_id
        assert handoff["validation_candidate_id"] == candidate_id
        assert handoff["applied_candidate_id"] == candidate_id
        assert handoff["validation_publication_generation"] > 0
        assert handoff["apply_publication_generation"] > 0

    saved_split = phases["dataset_generation"]["workflow_state"]["dataset"]
    assert saved_split["available"] is False
    assert saved_split["count"] == 0
    assert saved_split["generator_exists"] is False
    assert saved_split["split_spec_saved"] is True
    assert saved_split["split_materialized"] is False
    assert saved_split["split_lifecycle"] == "saved"
    assert saved_split["split_specification_fingerprint"]
    assert saved_split["split_epoch_revision"] > 0
    assert saved_split["split_preview_summary"]["rows"]

    materialized_split = phases["training_readiness"]["workflow_state"]["dataset"]
    assert materialized_split["available"] is True
    assert materialized_split["count"] > 0
    assert materialized_split["generator_exists"] is True
    assert materialized_split["split_spec_saved"] is True
    assert materialized_split["split_materialized"] is True
    assert materialized_split["split_lifecycle"] == "verified"
