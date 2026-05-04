from __future__ import annotations

import json
import subprocess
import sys

from scripts.dev.report_data_interpretation_format_matrix import (
    build_format_capability_snapshot,
    render_markdown,
)


def test_build_format_capability_snapshot_covers_import_boundary_formats():
    snapshot = build_format_capability_snapshot()

    labels = set(snapshot["summary"]["coverage_labels"])
    assert {
        "GDF recording",
        "EDF recording",
        "BDF recording",
        "EEGLAB SET",
        "BrainVision VHDR",
        "BrainVision VMRK",
        "MNE FIF",
        "MAT labels",
        "CSV labels",
        "TSV labels",
        "BIDS events.tsv",
        "TXT labels",
        "XDF / LSL stream export",
    } <= labels
    assert snapshot["summary"]["case_count"] >= 8
    assert snapshot["summary"]["all_expected_capabilities_observed"] is True

    rows_by_label = {str(row["coverage_label"]): row for row in snapshot["rows"]}
    assert rows_by_label["GDF recording"]["status"] == "needs_review"
    assert rows_by_label["GDF recording"]["validation_decision"] == (
        "needs_confirmation"
    )
    assert "trial anchor" in rows_by_label["GDF recording"]["message"]
    assert rows_by_label["BIDS events.tsv"]["format"] == "BIDS events"
    assert rows_by_label["BIDS events.tsv"]["role"] == "external_labels"
    assert rows_by_label["MNE FIF"]["status"] == "supported"
    assert rows_by_label["MNE FIF"]["validation_decision"] == "safe"
    assert rows_by_label["BrainVision VMRK"]["status"] == "context"
    assert rows_by_label["XDF / LSL stream export"]["status"] == "blocked"
    assert rows_by_label["XDF / LSL stream export"]["validation_decision"] == (
        "blocked"
    )
    assert "stream selection" in rows_by_label["XDF / LSL stream export"]["message"]


def test_render_markdown_lists_claim_boundary_and_blocked_xdf():
    rendered = render_markdown(build_format_capability_snapshot())

    assert "# Data Interpretation Format Capability Matrix" in rendered
    assert (
        "| Coverage | Source fixture | Detected format | Role | Status | Validation | Boundary |"
        in rendered
    )
    assert "XDF / LSL stream export" in rendered
    assert "stream selection is not available" in rendered
    assert "does not implement an XDF / LSL stream parser" in rendered


def test_cli_json_output_is_machine_readable():
    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/dev/report_data_interpretation_format_matrix.py",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["summary"]["all_expected_capabilities_observed"] is True
    assert "Study initialized" not in completed.stdout
