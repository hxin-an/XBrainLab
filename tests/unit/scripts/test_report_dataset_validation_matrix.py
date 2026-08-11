from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.dev.report_data_interpretation_format_matrix import (
    REQUIRED_EXTERNAL_LABEL_CONTRACTS,
    REQUIRED_INTERNAL_EVENT_PROFILES,
    REQUIRED_REVIEWED_LABEL_CASE_IDS,
    REQUIRED_TIER_FORMATS,
)
from scripts.dev.report_dataset_validation_matrix import (
    PUBLIC_EPOCH_ONLY_FIXTURES,
    PUBLIC_EVENT_RICH_TRAINING_FIXTURES,
    build_dataset_validation_rows,
    build_snapshot,
    render_markdown,
    validate_required_dataset_matrix,
)
from scripts.dev.run_public_cross_source_training_smoke import (
    PUBLIC_EPOCH_ONLY_FIXTURES as RUNNER_EPOCH_ONLY_FIXTURES,
)
from scripts.dev.run_public_cross_source_training_smoke import (
    PUBLIC_TRAINING_FIXTURES as RUNNER_TRAINING_FIXTURES,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture", encoding="utf-8")


def test_canonical_direct_script_entrypoint_can_start_from_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = subprocess.run(  # noqa: S603 - fixed interpreter and script path
        [
            sys.executable,
            "scripts/dev/report_dataset_validation_matrix.py",
            "--help",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "report_dataset_validation_matrix.py" in result.stdout
    assert "--strict" in result.stdout


def _workflow_snapshot(*, passed: bool = True) -> dict[str, object]:
    return {
        "summary": {
            "all_required_passed": passed,
            "required_case_count": 20,
            "passed_required_case_count": 20 if passed else 19,
            "public_source_family_count": 5,
            "passed_public_case_count": 7,
            "public_source_families": [
                "BBCI",
                "MNE testing-data",
                "MNE-BIDS",
                "PhysioNet",
                "SCCN / EEGLAB",
            ],
            "missing_public_source_families": [],
            "required_format_count": len(REQUIRED_TIER_FORMATS),
            "passed_required_format_count": (
                len(REQUIRED_TIER_FORMATS) if passed else len(REQUIRED_TIER_FORMATS) - 1
            ),
            "passed_required_formats": (
                sorted(REQUIRED_TIER_FORMATS)
                if passed
                else sorted(REQUIRED_TIER_FORMATS)[:-1]
            ),
            "missing_required_formats": (
                [] if passed else [sorted(REQUIRED_TIER_FORMATS)[-1]]
            ),
            "required_external_label_contract_count": len(
                REQUIRED_EXTERNAL_LABEL_CONTRACTS
            ),
            "passed_external_label_contract_count": (
                len(REQUIRED_EXTERNAL_LABEL_CONTRACTS)
                if passed
                else len(REQUIRED_EXTERNAL_LABEL_CONTRACTS) - 1
            ),
            "passed_external_label_contracts": (
                sorted(REQUIRED_EXTERNAL_LABEL_CONTRACTS)
                if passed
                else sorted(REQUIRED_EXTERNAL_LABEL_CONTRACTS)[:-1]
            ),
            "missing_external_label_contracts": (
                [] if passed else [sorted(REQUIRED_EXTERNAL_LABEL_CONTRACTS)[-1]]
            ),
            "required_internal_event_profile_count": len(
                REQUIRED_INTERNAL_EVENT_PROFILES
            ),
            "passed_internal_event_profile_count": (
                len(REQUIRED_INTERNAL_EVENT_PROFILES)
                if passed
                else len(REQUIRED_INTERNAL_EVENT_PROFILES) - 1
            ),
            "passed_internal_event_profiles": (
                sorted(REQUIRED_INTERNAL_EVENT_PROFILES)
                if passed
                else sorted(REQUIRED_INTERNAL_EVENT_PROFILES)[:-1]
            ),
            "missing_internal_event_profiles": (
                [] if passed else [sorted(REQUIRED_INTERNAL_EVENT_PROFILES)[-1]]
            ),
            "reviewed_label_case_count": 11,
            "passed_reviewed_label_case_count": 11 if passed else 10,
            "required_reviewed_label_case_count": 11,
            "required_reviewed_label_case_ids": sorted(
                REQUIRED_REVIEWED_LABEL_CASE_IDS
            ),
            "passed_required_reviewed_label_case_count": 11 if passed else 10,
            "passed_required_reviewed_label_case_ids": (
                sorted(REQUIRED_REVIEWED_LABEL_CASE_IDS)
                if passed
                else sorted(REQUIRED_REVIEWED_LABEL_CASE_IDS)[:-1]
            ),
            "missing_required_reviewed_label_case_ids": (
                [] if passed else [sorted(REQUIRED_REVIEWED_LABEL_CASE_IDS)[-1]]
            ),
            "downgraded_required_reviewed_label_case_ids": [],
            "choice_preservation_failure_case_ids": [],
        },
        "cases": [],
    }


def test_matrix_protocol_matches_strict_cross_source_runner():
    assert {fixture["filename"] for fixture in PUBLIC_EVENT_RICH_TRAINING_FIXTURES} == {
        fixture["filename"] for fixture in RUNNER_TRAINING_FIXTURES
    }
    assert {fixture["filename"] for fixture in PUBLIC_EPOCH_ONLY_FIXTURES} == {
        fixture["filename"] for fixture in RUNNER_EPOCH_ONLY_FIXTURES
    }
    assert {fixture["filename"] for fixture in PUBLIC_EVENT_RICH_TRAINING_FIXTURES} == {
        "physionet-eegmmidb-S008R04.edf",
        "bbci-competition-iii-O3VR.gdf",
    }
    assert {fixture["filename"] for fixture in PUBLIC_EPOCH_ONLY_FIXTURES} == {
        "sccn-eeglab_data.set",
        "scan41_short.cnt",
    }


def test_build_dataset_validation_rows_reports_checked_in_and_public_layers(
    tmp_path: Path,
):
    _touch(tmp_path / "tests" / "fixtures" / "data" / "A01T.gdf")
    _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / "A01T.mat")
    _touch(
        tmp_path / "tests" / "fixtures" / "data" / "multiformat" / "A01T-mini-real.edf"
    )
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "physionet-eegmmidb-S008R01.edf"
    )
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "physionet-eegmmidb-S008R04.edf"
    )
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "bbci-competition-iii-O3VR.gdf"
    )
    _touch(tmp_path / "tests" / "fixtures" / "data" / "public" / "sccn-eeglab_data.set")
    _touch(tmp_path / "tests" / "fixtures" / "data" / "public" / "scan41_short.cnt")
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "mne-bids-tiny-eeg"
        / "sub-01"
        / "ses-eeg"
        / "eeg"
        / "sub-01_ses-eeg_task-rest_eeg.vhdr"
    )

    rows = build_dataset_validation_rows(tmp_path)

    assert rows[0].layer == "checked-in core GDF + MAT"
    assert rows[0].representative_data == "A01T"
    assert rows[0].import_facade == "workflow not run"
    assert rows[0].training_smoke == "separate one-epoch runner"
    assert rows[1].layer == "checked-in compact multiformat"
    assert rows[1].representative_data == "1 derived files from A01T"
    assert rows[2].layer == "public local-only event-rich fixtures"
    assert rows[2].training_smoke == "separate strict cross-source runner"
    assert "BBCI" in rows[2].source_families
    assert "PhysioNet" in rows[2].source_families
    assert rows[3].layer == "public local-only import/preprocess boundary fixtures"
    assert rows[3].representative_data == "EEGLAB .set, CNT"
    assert rows[3].dataset_generation == "no; epoch creation checked separately"
    assert rows[3].training_smoke == "supervised epoch blocked by contract"
    assert rows[4].layer == "public local-only import-only fixtures"
    assert "PhysioNet" in rows[4].source_families
    assert rows[5].layer == "public local-only BIDS EEG fixture"
    assert rows[5].representative_data == "BIDS EEG"
    assert rows[5].label_attach == "workflow not run"
    assert rows[2].reproducibility_class == "local-only"
    assert rows[3].reproducibility_class == "local-only"
    assert rows[4].reproducibility_class == "local-only"
    assert rows[5].reproducibility_class == "local-only downloaded"


def test_render_markdown_includes_current_truth(tmp_path: Path):
    _touch(tmp_path / "tests" / "fixtures" / "data" / "A01T.gdf")
    _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / "A01T.mat")

    snapshot = build_snapshot(tmp_path)
    rendered = render_markdown(snapshot)

    assert snapshot["tests_data_dir"] == str(tmp_path / "tests" / "fixtures" / "data")
    assert "# Dataset Validation Matrix" in rendered
    assert "checked-in core GDF + MAT" in rendered
    assert "public local-only event-rich fixtures" in rendered
    assert "public local-only import/preprocess boundary fixtures" in rendered
    assert "public local-only BIDS EEG fixture" in rendered
    assert "Required Multi-Dataset Gate" in rendered
    assert "Real Data Interpretation Lifecycle" in rendered
    assert "scan -> preview -> validate -> apply" in rendered
    assert "public cases from" in rendered
    assert "generated csv/tsv/txt cases prove parser" in rendered.lower()


def test_dataset_validation_rows_ignore_empty_public_fixture(tmp_path: Path):
    public_dir = tmp_path / "tests" / "fixtures" / "data" / "public"
    public_dir.mkdir(parents=True)
    (public_dir / "physionet-eegmmidb-S008R04.edf").write_bytes(b"")

    rows = build_dataset_validation_rows(tmp_path)

    assert rows[2].layer == "public local-only event-rich fixtures"
    assert rows[2].representative_data == "not downloaded"
    assert rows[2].training_smoke == "separate strict cross-source runner"


def test_cnt_fixture_is_reported_as_import_preprocess_boundary_not_training(
    tmp_path: Path,
):
    _touch(tmp_path / "tests" / "fixtures" / "data" / "public" / "scan41_short.cnt")

    rows = build_dataset_validation_rows(tmp_path)

    assert rows[2].representative_data == "not downloaded"
    assert rows[2].training_smoke == "separate strict cross-source runner"
    assert rows[3].layer == "public local-only import/preprocess boundary fixtures"
    assert rows[3].representative_data == "CNT"
    assert rows[3].dataset_generation == "no; epoch creation checked separately"
    assert rows[3].training_smoke == "supervised epoch blocked by contract"
    assert "too small for class-balanced training" in rows[3].notes


def test_required_dataset_matrix_passes_only_with_source_diverse_fixtures(
    tmp_path: Path,
):
    for stem in ("A01T", "A02T", "A03T"):
        _touch(tmp_path / "tests" / "fixtures" / "data" / f"{stem}.gdf")
        _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / f"{stem}.mat")
    for filename in (
        "A01T-mini-real_raw.fif",
        "A01T-mini-real_raw.fif.gz",
        "A01T-mini-real-epo.fif",
        "A01T-mini-real.edf",
        "A01T-mini-real.bdf",
        "A01T-mini-real.vhdr",
        "A01T-mini-real.eeg",
        "A01T-mini-real.vmrk",
        "A01T-mini-real.set",
    ):
        _touch(tmp_path / "tests" / "fixtures" / "data" / "multiformat" / filename)
    for filename in (
        "physionet-eegmmidb-S008R04.edf",
        "bbci-competition-iii-O3VR.gdf",
        "sccn-eeglab_data.set",
        "scan41_short.cnt",
    ):
        _touch(tmp_path / "tests" / "fixtures" / "data" / "public" / filename)
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "mne-bids-tiny-eeg"
        / "sub-01"
        / "ses-eeg"
        / "eeg"
        / "sub-01_ses-eeg_task-rest_eeg.vhdr"
    )

    requirements = validate_required_dataset_matrix(
        tmp_path,
        workflow_snapshot=_workflow_snapshot(),
    )

    assert [requirement.key for requirement in requirements] == [
        "checked_in_gdf_mat",
        "compact_multiformat",
        "public_event_rich_sources",
        "public_epoch_only_sources",
        "public_bids_eeg",
        "real_data_interpretation_lifecycle",
        "real_public_source_diversity",
        "tier_format_apply_coverage",
        "external_label_placement_contracts",
        "reviewed_internal_event_contracts",
        "reviewed_label_apply_coverage",
    ]
    assert all(requirement.ok for requirement in requirements)


def test_required_dataset_matrix_rejects_single_source_only(tmp_path: Path):
    _touch(tmp_path / "tests" / "fixtures" / "data" / "A01T.gdf")
    _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / "A01T.mat")
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "physionet-eegmmidb-S008R04.edf"
    )

    requirements = validate_required_dataset_matrix(
        tmp_path,
        workflow_snapshot=_workflow_snapshot(passed=False),
    )
    by_key = {requirement.key: requirement for requirement in requirements}

    assert by_key["checked_in_gdf_mat"].ok is False
    assert by_key["compact_multiformat"].ok is False
    assert by_key["public_event_rich_sources"].ok is False
    assert by_key["public_epoch_only_sources"].ok is False
    assert by_key["public_bids_eeg"].ok is False
    assert by_key["real_data_interpretation_lifecycle"].ok is False
    assert by_key["tier_format_apply_coverage"].ok is False
    assert by_key["external_label_placement_contracts"].ok is False
    assert by_key["reviewed_internal_event_contracts"].ok is False
    assert by_key["reviewed_label_apply_coverage"].ok is False


def test_required_dataset_matrix_rejects_reviewed_case_denominator_shrink(
    tmp_path: Path,
):
    workflow_snapshot = _workflow_snapshot()
    summary = workflow_snapshot["summary"]
    assert isinstance(summary, dict)
    summary["required_reviewed_label_case_count"] = 10
    summary["required_reviewed_label_case_ids"] = sorted(
        REQUIRED_REVIEWED_LABEL_CASE_IDS - {"public_mne_cnt"}
    )
    summary["passed_required_reviewed_label_case_count"] = 10
    summary["passed_required_reviewed_label_case_ids"] = sorted(
        REQUIRED_REVIEWED_LABEL_CASE_IDS - {"public_mne_cnt"}
    )
    summary["missing_required_reviewed_label_case_ids"] = []

    requirements = validate_required_dataset_matrix(
        tmp_path,
        workflow_snapshot=workflow_snapshot,
    )
    by_key = {requirement.key: requirement for requirement in requirements}

    assert by_key["reviewed_label_apply_coverage"].ok is False


def test_required_public_fixture_message_uses_bounded_ci_profile(tmp_path: Path):
    requirements = validate_required_dataset_matrix(
        tmp_path,
        workflow_snapshot=_workflow_snapshot(passed=False),
    )
    by_key = {requirement.key: requirement for requirement in requirements}

    assert "--profile required-ci" in by_key["public_event_rich_sources"].required


def test_inventory_presence_cannot_override_failed_real_workflow(tmp_path: Path):
    for stem in ("A01T", "A02T", "A03T"):
        _touch(tmp_path / "tests" / "fixtures" / "data" / f"{stem}.gdf")
        _touch(tmp_path / "tests" / "fixtures" / "data" / "label" / f"{stem}.mat")
    for filename in (
        "A01T-mini-real_raw.fif",
        "A01T-mini-real_raw.fif.gz",
        "A01T-mini-real-epo.fif",
        "A01T-mini-real.edf",
        "A01T-mini-real.bdf",
        "A01T-mini-real.vhdr",
        "A01T-mini-real.eeg",
        "A01T-mini-real.vmrk",
        "A01T-mini-real.set",
    ):
        _touch(tmp_path / "tests" / "fixtures" / "data" / "multiformat" / filename)
    for filename in (
        "physionet-eegmmidb-S008R04.edf",
        "bbci-competition-iii-O3VR.gdf",
        "sccn-eeglab_data.set",
        "scan41_short.cnt",
    ):
        _touch(tmp_path / "tests" / "fixtures" / "data" / "public" / filename)
    _touch(
        tmp_path
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "mne-bids-tiny-eeg"
        / "sub-01"
        / "ses-eeg"
        / "eeg"
        / "sub-01_ses-eeg_task-rest_eeg.vhdr"
    )

    requirements = validate_required_dataset_matrix(
        tmp_path,
        workflow_snapshot=_workflow_snapshot(passed=False),
    )
    by_key = {requirement.key: requirement for requirement in requirements}

    assert by_key["checked_in_gdf_mat"].ok is True
    assert by_key["compact_multiformat"].ok is True
    assert by_key["public_event_rich_sources"].ok is True
    assert by_key["real_data_interpretation_lifecycle"].ok is False


def test_rendered_dataset_matrix_rows_match_the_declared_columns(tmp_path: Path):
    snapshot = build_snapshot(tmp_path, workflow_snapshot=_workflow_snapshot())
    rendered = render_markdown(snapshot)
    header = next(line for line in rendered.splitlines() if line.startswith("| Layer"))
    first_row = next(
        line
        for line in rendered.splitlines()
        if line.startswith("| checked-in core GDF + MAT")
    )

    assert header.count("|") == 10
    assert first_row.count("|") == header.count("|")
