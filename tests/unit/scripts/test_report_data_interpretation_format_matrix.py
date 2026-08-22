from __future__ import annotations

import json
import sys
from pathlib import Path

import mne
import numpy as np
import pytest

from scripts.dev import report_data_interpretation_format_matrix as format_matrix
from scripts.dev.report_data_interpretation_format_matrix import (
    REAL_WORKFLOW_CASES,
    REQUIRED_EXTERNAL_LABEL_CONTRACTS,
    REQUIRED_INTERNAL_EVENT_PROFILES,
    REQUIRED_REVIEWED_LABEL_CASE_IDS,
    REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS,
    REQUIRED_TIER_FORMATS,
    RealWorkflowCase,
    _reviewed_choice_evidence,
    _workflow_choices,
    build_format_capability_snapshot,
    build_import_loading_profile,
    build_real_workflow_snapshot,
    capture_public_fixture_facts,
    render_markdown,
    run_real_workflow_case,
    summarize_real_workflow_results,
)


def test_source_entry_resolution_rewrites_only_repo_public_fixture_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XBRAINLAB_DATA_DIR", str(tmp_path))

    assert (
        format_matrix._resolve_source_entry(
            "tests/fixtures/data/public/example.edf",
            format_matrix.ROOT,
        )
        == (tmp_path / "datasets/public-fixtures/example.edf").resolve()
    )
    assert (
        format_matrix._resolve_source_entry(
            "tests/fixtures/data/A01T.gdf",
            format_matrix.ROOT,
        )
        == (format_matrix.ROOT / "tests/fixtures/data/A01T.gdf").resolve()
    )
    assert (
        format_matrix._resolve_source_entry(
            "generated_csv_event_order",
            tmp_path / "generated-workflows",
        )
        == (tmp_path / "generated-workflows/generated_csv_event_order").resolve()
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
    assert snapshot["summary"]["all_expected_capabilities_match"] is True

    rows_by_label = {str(row["coverage_label"]): row for row in snapshot["rows"]}
    assert rows_by_label["GDF recording"]["status"] == "needs_review"
    assert rows_by_label["GDF recording"]["validation_decision"] == (
        "needs_confirmation"
    )
    assert "trial anchor" in rows_by_label["GDF recording"]["message"]
    assert rows_by_label["BIDS events.tsv"]["format"] == "BIDS events"
    assert rows_by_label["BIDS events.tsv"]["role"] == "external_labels"
    assert rows_by_label["BIDS events.tsv"]["validation_decision"] == "blocked"
    assert rows_by_label["MNE FIF"]["status"] == "supported"
    assert rows_by_label["MNE FIF"]["validation_decision"] == "safe"
    assert rows_by_label["BrainVision VMRK"]["status"] == "context"
    assert rows_by_label["CSV labels"]["validation_decision"] == "blocked"
    assert any(
        "Label carrier pairing is incomplete" in reason
        for reason in rows_by_label["CSV labels"]["blocked_reasons"]
    )
    assert rows_by_label["TSV labels"]["validation_decision"] == "blocked"
    assert rows_by_label["TXT labels"]["validation_decision"] == "blocked"
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


@pytest.mark.parametrize(("strict_ok", "expected_exit_code"), [(True, 0), (False, 1)])
def test_cli_strict_exit_code_tracks_full_validation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    strict_ok: bool,
    expected_exit_code: int,
):
    snapshot = {"strict_validation": {"ok": strict_ok}}
    monkeypatch.setattr(
        format_matrix,
        "build_data_interpretation_validation_snapshot",
        lambda: snapshot,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_data_interpretation_format_matrix.py",
            "--format",
            "json",
            "--strict",
        ],
    )

    assert format_matrix.main() == expected_exit_code
    assert json.loads(capsys.readouterr().out) == snapshot


def test_cli_strict_write_artifacts_keeps_failure_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
):
    snapshot = {"strict_validation": {"ok": False}}
    json_path = tmp_path / "matrix.json"
    markdown_path = tmp_path / "matrix.md"
    monkeypatch.setattr(
        format_matrix,
        "build_data_interpretation_validation_snapshot",
        lambda: snapshot,
    )
    monkeypatch.setattr(
        format_matrix,
        "write_artifacts",
        lambda _snapshot, _output_dir: (json_path, markdown_path),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_data_interpretation_format_matrix.py",
            "--strict",
            "--write-artifacts",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert format_matrix.main() == 1
    assert capsys.readouterr().out.splitlines() == [
        f"Wrote {json_path}",
        f"Wrote {markdown_path}",
    ]


def test_empty_synthetic_matrix_cannot_vacuously_pass(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(format_matrix, "FORMAT_CASES", ())

    snapshot = build_format_capability_snapshot()

    assert snapshot["summary"]["case_count"] == 0
    assert snapshot["summary"]["row_count"] == 0
    assert snapshot["summary"]["all_expected_capabilities_observed"] is False
    assert snapshot["summary"]["all_expected_capabilities_match"] is False


def test_real_workflow_case_proves_scan_preview_validate_and_apply(tmp_path: Path):
    fixture = tmp_path / "tiny_raw.fif"
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, 500)), info, verbose="ERROR")
    raw.save(fixture, overwrite=True, verbose="ERROR")
    case = RealWorkflowCase(
        case_id="tiny_fif",
        title="Tiny real FIF lifecycle",
        evidence_scope="test",
        dataset_source_id="unit-test-source",
        source_family="unit test",
        format_name="FIF",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry="tiny_raw.fif",
    )

    result = run_real_workflow_case(case, tmp_path)

    assert result["status"] == "passed"
    assert result["evidence_level"] == "real_application_workflow"
    assert result["stages"] == {
        "scan": {"ok": True, "message": "Scanned source and found 1 EEG file(s)."},
        "preview": {"ok": True, "message": "Interpretation preview ready."},
        "validate": {
            "ok": True,
            "message": "Interpretation validation: needs_confirmation.",
        },
        "apply": {
            "ok": True,
            "message": "Applied interpretation and loaded 1 file(s).",
        },
    }
    assert result["observations"]["raw_file_count"] == 1
    assert result["observations"]["label_apply_status"] == "not_applicable"


def test_real_workflow_timing_is_opt_in_and_records_each_command(tmp_path: Path):
    fixture = tmp_path / "timed_raw.fif"
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    mne.io.RawArray(np.zeros((1, 500)), info, verbose="ERROR").save(
        fixture,
        overwrite=True,
        verbose="ERROR",
    )
    case = RealWorkflowCase(
        case_id="timed_fif",
        title="Timed real FIF lifecycle",
        evidence_scope="test",
        dataset_source_id="unit-test-source",
        source_family="unit test",
        format_name="FIF",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry=fixture.name,
    )

    result = run_real_workflow_case(case, tmp_path, collect_timing=True)

    assert result["status"] == "passed"
    assert set(result["timings"]) == {"scan", "preview", "validate", "apply"}
    assert all(
        timing["wall_seconds"] >= 0
        and timing["cpu_seconds"] >= 0
        and timing["rss_bytes"] > 0
        for timing in result["timings"].values()
    )


def test_import_loading_profile_labels_fresh_service_passes_without_cache_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = tmp_path / "tests/fixtures/data/multiformat/A01T-mini-real.edf"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"fixture")
    observed: list[tuple[str, bool]] = []

    def _run(case, repo_root, *, collect_timing):
        observed.append((case.case_id, collect_timing))
        return {
            "status": "passed",
            "failed_stage": "",
            "timings": {"scan": {"wall_seconds": 0.0}},
        }

    monkeypatch.setattr(format_matrix, "run_real_workflow_case", _run)

    profile = build_import_loading_profile(tmp_path)

    assert len(profile["samples"]) == 6
    assert [sample["pass"] for sample in profile["samples"]] == [
        "first_fresh_service_pass",
        "repeat_fresh_service_pass",
    ] * 3
    assert profile["repeat_pass_definition"].startswith("fresh ApplicationService")
    assert profile["repeat_pass_definition"].endswith("same process")
    assert all(collect_timing for _case_id, collect_timing in observed)


def test_nonempty_fake_fixture_does_not_count_as_real_workflow_evidence(
    tmp_path: Path,
):
    fixture = tmp_path / "looks-real.edf"
    fixture.write_bytes(b"not an EDF file")
    case = RealWorkflowCase(
        case_id="invalid_edf",
        title="Invalid EDF must fail lifecycle",
        evidence_scope="test",
        dataset_source_id="unit-test-source",
        source_family="unit test",
        format_name="EDF",
        tier_category="Generic EEG files with internal events / annotations",
        source_entry=fixture.name,
    )

    result = run_real_workflow_case(case, tmp_path)

    assert result["status"] == "failed"
    assert result["failed_stage"] in {"preview", "apply"}
    assert result["stages"]["apply"]["ok"] is False


def test_real_workflow_snapshot_exercises_hermetic_label_contracts(
    monkeypatch: pytest.MonkeyPatch,
):
    public_case_ids = {
        case.case_id
        for case in REAL_WORKFLOW_CASES
        if case.evidence_scope == "public_source"
    }
    hermetic_cases = tuple(
        case for case in REAL_WORKFLOW_CASES if case.evidence_scope != "public_source"
    )
    monkeypatch.setattr(format_matrix, "REAL_WORKFLOW_CASES", hermetic_cases)

    snapshot = build_real_workflow_snapshot()
    summary = snapshot["summary"]
    cases = {
        case["case_id"]: case
        for case in snapshot["cases"]
        if case["evidence_scope"] == "generated_contract"
    }

    assert {
        "generated_csv_event_order",
        "generated_csv_sample_time",
        "generated_tsv_interval",
        "generated_csv_event_code",
        "generated_txt_event_order",
    } == set(cases)
    assert all(case["status"] == "passed" for case in cases.values())
    assert all(
        all(
            case["stages"][stage]["ok"]
            for stage in ("scan", "preview", "validate", "apply")
        )
        for case in cases.values()
    )
    assert set(summary["passed_external_label_contracts"]) == (
        set(REQUIRED_EXTERNAL_LABEL_CONTRACTS) - {"bids_interval"}
    )
    assert summary["missing_external_label_contracts"] == ["bids_interval"]
    assert summary["missing_required_formats"] == [
        "BIDS EEG / BrainVision",
        "CNT",
        "GDF",
    ]
    assert set(summary["missing_internal_event_profiles"]) == set(
        REQUIRED_INTERNAL_EVENT_PROFILES
    )
    assert summary["required_reviewed_label_case_count"] == 11
    assert set(summary["required_reviewed_label_case_ids"]) == set(
        REQUIRED_REVIEWED_LABEL_CASE_IDS
    )
    public_reviewed_case_ids = {
        case_id
        for case_id in REQUIRED_REVIEWED_LABEL_CASE_IDS
        if case_id.startswith("public_")
    }
    assert set(summary["passed_required_reviewed_label_case_ids"]) == (
        set(REQUIRED_REVIEWED_LABEL_CASE_IDS) - public_reviewed_case_ids
    )
    assert set(summary["missing_required_reviewed_label_case_ids"]) == (
        public_reviewed_case_ids
    )
    assert summary["downgraded_required_reviewed_label_case_ids"] == []
    assert summary["choice_preservation_failure_case_ids"] == []
    assert summary["public_source_families"] == []
    assert summary["all_required_passed"] is False
    assert summary["evidence_layers"] == {
        "checked_in_and_derived_formats": {
            "required_case_count": 8,
            "passed_required_case_count": 8,
            "missing_required_case_ids": [],
            "failed_required_case_ids": [],
            "evidence_scopes": ["checked_in_source", "derived_format"],
            "counts_toward_public_source_diversity": False,
        },
        "generated_contracts": {
            "required_case_count": 5,
            "passed_required_case_count": 5,
            "missing_required_case_ids": [],
            "failed_required_case_ids": [],
            "evidence_scopes": ["generated_contract"],
            "counts_toward_public_source_diversity": False,
        },
        "public_source_workflows": {
            "required_case_count": 7,
            "passed_required_case_count": 0,
            "missing_required_case_ids": sorted(public_case_ids),
            "failed_required_case_ids": [],
            "evidence_scopes": ["public_source"],
            "counts_toward_public_source_diversity": True,
        },
    }
    generated_cases = [
        case
        for case in snapshot["cases"]
        if case["evidence_scope"] == "generated_contract"
    ]
    assert {case["reviewed_evidence_tier"] for case in generated_cases} == {
        "generated_supervised_contract"
    }


def test_empty_workflow_selection_cannot_vacuously_pass_required_contracts(
    tmp_path: Path,
):
    snapshot = build_real_workflow_snapshot(tmp_path, cases=())
    summary = snapshot["summary"]

    assert summary["all_required_passed"] is False
    assert set(summary["missing_required_formats"]) == set(REQUIRED_TIER_FORMATS)
    assert set(summary["missing_external_label_contracts"]) == set(
        REQUIRED_EXTERNAL_LABEL_CONTRACTS
    )
    assert set(summary["missing_internal_event_profiles"]) == set(
        REQUIRED_INTERNAL_EVENT_PROFILES
    )
    assert summary["required_reviewed_label_case_count"] == 11
    assert set(summary["missing_required_reviewed_label_case_ids"]) == set(
        REQUIRED_REVIEWED_LABEL_CASE_IDS
    )


def test_required_reviewed_label_case_ids_are_fixed_and_include_cnt():
    assert (
        frozenset(
            {
                "checked_in_graz_gdf_mat",
                "generated_csv_event_code",
                "generated_csv_event_order",
                "generated_csv_sample_time",
                "generated_tsv_interval",
                "generated_txt_event_order",
                "public_bbci_gdf",
                "public_mne_bids_eeg",
                "public_mne_cnt",
                "public_physionet_motor_edf",
                "public_sccn_eeglab",
            }
        )
        == REQUIRED_REVIEWED_LABEL_CASE_IDS
    )
    assert (
        REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS["public_mne_cnt"].evidence_tier
        == "io_epoch_only"
    )
    assert (
        REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS["public_sccn_eeglab"].evidence_tier
        == "io_epoch_only"
    )
    assert {
        REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS[case_id].evidence_tier
        for case_id in REQUIRED_REVIEWED_LABEL_CASE_IDS
        if case_id.startswith("generated_")
    } == {"generated_supervised_contract"}


def test_reviewed_label_summary_cannot_shrink_or_accept_downgrade():
    results = [
        {
            "case_id": case_id,
            "status": "passed",
            "reviewed_evidence_tier": requirement.evidence_tier,
            "reviewed_choice_preserved": True,
        }
        for case_id, requirement in REQUIRED_REVIEWED_LABEL_CASE_REQUIREMENTS.items()
        if case_id != "public_mne_cnt"
    ]
    results_by_id = {result["case_id"]: result for result in results}
    results_by_id["public_physionet_motor_edf"]["reviewed_evidence_tier"] = (
        "io_epoch_only"
    )
    results_by_id["public_bbci_gdf"]["reviewed_choice_preserved"] = False

    summary = summarize_real_workflow_results(results)

    assert summary["required_reviewed_label_case_count"] == 11
    assert summary["missing_required_reviewed_label_case_ids"] == ["public_mne_cnt"]
    assert summary["downgraded_required_reviewed_label_case_ids"] == [
        "public_physionet_motor_edf"
    ]
    assert summary["choice_preservation_failure_case_ids"] == ["public_bbci_gdf"]
    assert summary["all_required_passed"] is False


def test_summary_rejects_duplicate_and_misclassified_required_evidence():
    summary = summarize_real_workflow_results(
        [
            {
                "case_id": "public_sccn_eeglab",
                "evidence_scope": "generated_contract",
                "status": "passed",
                "reviewed_evidence_tier": "io_epoch_only",
                "reviewed_choice_preserved": True,
            },
            {
                "case_id": "public_sccn_eeglab",
                "evidence_scope": "generated_contract",
                "status": "passed",
                "reviewed_evidence_tier": "io_epoch_only",
                "reviewed_choice_preserved": True,
            },
        ]
    )

    assert summary["duplicate_case_ids"] == ["public_sccn_eeglab"]
    assert summary["evidence_scope_mismatch_case_ids"] == ["public_sccn_eeglab"]
    assert any(
        "Duplicate workflow evidence" in failure
        for failure in summary["strict_failures"]
    )
    assert any(
        "Evidence scope does not match" in failure
        for failure in summary["strict_failures"]
    )
    assert summary["all_required_passed"] is False


def test_passed_contract_numerator_excludes_nonrequired_contracts():
    summary = summarize_real_workflow_results(
        [
            {
                "case_id": "unrequired_contract",
                "status": "passed",
                "label_contract": "invented_contract",
            }
        ]
    )

    assert summary["passed_external_label_contract_count"] == 0
    assert summary["passed_external_label_contracts"] == []
    assert set(summary["missing_external_label_contracts"]) == set(
        REQUIRED_EXTERNAL_LABEL_CONTRACTS
    )


def test_sccn_review_marks_rt_and_square_as_non_class_events():
    case = next(
        case for case in REAL_WORKFLOW_CASES if case.case_id == "public_sccn_eeglab"
    )
    choices = _workflow_choices(case, Path.cwd())

    assert case.expected_supervised_ready is False
    assert choices["internal_event_selection"] == {
        "label_event_codes": [],
        "not_label_event_codes": ["rt", "square"],
        "class_map": {},
    }


def test_sccn_choice_preservation_requires_both_non_class_codes():
    applied = {
        "internal_event_selection": {
            "label_event_codes": [],
            "not_label_event_codes": ["square", "rt"],
        },
        "class_map": {},
        "run_event_mappings": {},
    }

    preserved = _reviewed_choice_evidence("public_sccn_eeglab", applied)
    applied["internal_event_selection"]["not_label_event_codes"] = ["rt"]
    dropped_choice = _reviewed_choice_evidence("public_sccn_eeglab", applied)

    assert preserved["preserved"] is True
    assert dropped_choice["preserved"] is False


def test_public_fixture_fact_contract_compares_loaded_source_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from XBrainLab.backend.load_data import raw_data_loader

    source = tmp_path / "tests/fixtures/data/public/sccn-eeglab_data.set"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"loader-boundary fixture")
    info = mne.create_info(
        [f"EEG {index:03d}" for index in range(32)],
        sfreq=128.0,
        ch_types="eeg",
    )
    mne_data = mne.io.RawArray(
        np.zeros((32, 30504)),
        info,
        verbose="ERROR",
    )

    class LoadedRaw:
        def get_mne(self):
            return mne_data

        def get_event_summary(self, *, allow_scan: bool):
            assert allow_scan is True
            return {"count": 154, "labels": ["square", "rt"]}

    loaded_paths: list[str] = []

    def load_raw_data(path: str):
        loaded_paths.append(path)
        return LoadedRaw()

    monkeypatch.setattr(raw_data_loader, "load_raw_data", load_raw_data)
    facts = capture_public_fixture_facts(
        "public_sccn_eeglab",
        tmp_path,
    )

    assert loaded_paths == [str(source.resolve())]
    assert facts["status"] == "passed"
    assert facts["sampling_frequency_hz"] == 128.0
    assert facts["channel_count"] == 32
    assert facts["channel_type_counts"] == {"eeg": 32}
    assert facts["channel_unit_counts"] == {"V": 32}
    assert facts["source_unit_counts"] == {"unknown": 32}
    assert facts["sample_count"] == 30504
    assert facts["embedded_event_count"] == 154
    assert facts["embedded_event_labels"] == ["rt", "square"]
    assert facts["import_warnings"] == []
    assert facts["mismatches"] == []
