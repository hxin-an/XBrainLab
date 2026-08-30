from __future__ import annotations

import json
from copy import deepcopy

from scripts.dev import capture_epoching_dialog as capture_script


def _identity() -> dict[str, object]:
    return {
        "version": 3,
        "repo_root": str(capture_script.ROOT),
        "branch": "test-branch",
        "commit_sha": "a" * 40,
        "head_tree_sha": "b" * 40,
        "dirty": True,
        "dirty_digest": "c" * 64,
        "source_content_digest": "d" * 64,
        "source_digest": "e" * 64,
        "untracked_source_count": 1,
        "excluded_generated_prefixes": ["artifacts/"],
        "excluded_local_paths": ["settings.json"],
        "included_file_policy": "all-non-generated-tracked-and-untracked-files",
        "error": "",
    }


def test_epoch_capture_manifest_records_exact_source_and_invalid_states(
    qapp,
    tmp_path,
    monkeypatch,
) -> None:
    identity = _identity()
    monkeypatch.setattr(
        capture_script,
        "collect_source_identity",
        lambda *_args, **_kwargs: deepcopy(identity),
    )

    assert capture_script.main(["--output-dir", str(tmp_path)]) == 0

    payload = json.loads(
        (tmp_path / capture_script.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["passed"] is True
    assert payload["source_capture"] == {
        "branch": "test-branch",
        "commit_sha": "a" * 40,
        "head_tree_sha": "b" * 40,
        "dirty": True,
        "dirty_digest": "c" * 64,
        "source_content_digest": "d" * 64,
        "source_digest_at_start": "e" * 64,
        "source_digest_at_end": "e" * 64,
    }
    states = {item["state"]: item for item in payload["captures"]}
    assert set(states) == {
        "interval-import",
        "event-code-anchor",
        "internal-events",
        "baseline-enabled",
        "baseline-disabled",
        "baseline-order-invalid",
        "time-window-invalid",
    }
    assert states["baseline-enabled"]["semantic_checks"]["baseline_enabled"] is True
    assert states["baseline-disabled"]["semantic_checks"]["baseline_enabled"] is False
    assert states["baseline-disabled"]["semantic_checks"]["create_enabled"] is True
    event_code_hint = states["event-code-anchor"]["semantic_checks"]["import_hint"]
    assert event_code_hint["expected_pairs"] == [
        {"key": "Event anchor", "value": "719"},
    ]
    assert event_code_hint["contains_expected_pairs"] is True
    assert event_code_hint["has_timing_key"] is False
    assert event_code_hint["passed"] is True
    assert states["baseline-order-invalid"]["semantic_checks"]["invalid"] is True
    assert (
        states["baseline-order-invalid"]["semantic_checks"]["create_enabled"] is False
    )
    assert states["time-window-invalid"]["semantic_checks"]["invalid"] is True
    assert states["time-window-invalid"]["semantic_checks"]["create_enabled"] is False
    assert all(item["geometry_checks"]["passed"] for item in states.values())
    assert all(
        item["geometry_checks"]["primary_action"] == "Confirm"
        for item in states.values()
    )
    assert all(
        item["geometry_checks"]["primary_text_fits"] is True for item in states.values()
    )
    assert states["baseline-enabled"]["baseline_surface"]["passed"] is True
    assert states["baseline-disabled"]["baseline_surface"]["passed"] is True
    assert states["baseline-disabled"]["baseline_surface"]["near_black_fraction"] < 0.01
    assert all(item["dpi"]["device_pixel_ratio"] > 0 for item in states.values())
    assert all((tmp_path / item["screenshot"]).is_file() for item in states.values())
