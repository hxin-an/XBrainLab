#!/usr/bin/env python3
"""Report the dataset validation matrix used by CI and handoff validation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from scripts.dev.report_data_interpretation_format_matrix import (
    REQUIRED_EXTERNAL_LABEL_CONTRACTS,
    REQUIRED_INTERNAL_EVENT_PROFILES,
    REQUIRED_PUBLIC_SOURCE_FAMILIES,
    REQUIRED_PUBLIC_SOURCE_FAMILY_COUNT,
    REQUIRED_REVIEWED_LABEL_CASE_IDS,
    REQUIRED_TIER_FORMATS,
    build_real_workflow_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
TEST_DATA_DIR = ROOT / "tests" / "fixtures" / "data"

CHECKED_IN_GDF_STEMS = ("A01T", "A02T", "A03T")
MULTIFORMAT_FILES = (
    "A01T-mini-real_raw.fif",
    "A01T-mini-real_raw.fif.gz",
    "A01T-mini-real-epo.fif",
    "A01T-mini-real.edf",
    "A01T-mini-real.bdf",
    "A01T-mini-real.vhdr",
    "A01T-mini-real.eeg",
    "A01T-mini-real.vmrk",
    "A01T-mini-real.set",
)
PUBLIC_EVENT_RICH_TRAINING_FIXTURES = (
    {
        "filename": "physionet-eegmmidb-S008R04.edf",
        "source_family": "PhysioNet",
        "format": "EDF",
    },
    {
        "filename": "bbci-competition-iii-O3VR.gdf",
        "source_family": "BBCI",
        "format": "GDF",
    },
)
PUBLIC_EPOCH_ONLY_FIXTURES = (
    {
        "filename": "sccn-eeglab_data.set",
        "source_family": "SCCN / EEGLAB",
        "format": "EEGLAB .set",
    },
    {
        "filename": "scan41_short.cnt",
        "source_family": "MNE testing-data",
        "format": "CNT",
    },
)
PUBLIC_IMPORT_ONLY_FIXTURES = (
    {
        "filename": "physionet-eegmmidb-S008R01.edf",
        "source_family": "PhysioNet",
        "format": "EDF",
    },
    {
        "filename": "test_NO.vhdr",
        "source_family": "MNE testing-data",
        "format": "BrainVision .vhdr",
    },
)
PUBLIC_BIDS_FIXTURES = (
    {
        "entrypoint": (
            "mne-bids-tiny-eeg/sub-01/ses-eeg/eeg/sub-01_ses-eeg_task-rest_eeg.vhdr"
        ),
        "source_family": "MNE-BIDS",
        "format": "BIDS EEG",
    },
)


@dataclass
class DatasetLayerRow:
    """One row in the current dataset validation matrix."""

    layer: str
    representative_data: str
    reproducibility_class: str
    source_families: str
    import_facade: str
    label_attach: str
    dataset_generation: str
    training_smoke: str
    notes: str


@dataclass
class DatasetMatrixRequirement:
    """One required dataset breadth check for hand-test/release preflight."""

    key: str
    label: str
    ok: bool
    observed: str
    required: str


def _nonempty_file(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def build_dataset_validation_rows(
    repo_root: Path = ROOT,
    *,
    workflow_snapshot: dict[str, Any] | None = None,
) -> list[DatasetLayerRow]:
    """Build the current dataset validation matrix from known repo fixtures."""
    tests_data_dir = repo_root / "tests" / "fixtures" / "data"
    checked_in_stems = [
        stem
        for stem in CHECKED_IN_GDF_STEMS
        if (tests_data_dir / f"{stem}.gdf").exists()
        and (tests_data_dir / "label" / f"{stem}.mat").exists()
    ]
    multiformat_files = [
        filename
        for filename in MULTIFORMAT_FILES
        if (tests_data_dir / "multiformat" / filename).exists()
    ]
    public_training_fixtures = [
        fixture
        for fixture in PUBLIC_EVENT_RICH_TRAINING_FIXTURES
        if _nonempty_file(tests_data_dir / "public" / fixture["filename"])
    ]
    public_epoch_only_fixtures = [
        fixture
        for fixture in PUBLIC_EPOCH_ONLY_FIXTURES
        if _nonempty_file(tests_data_dir / "public" / fixture["filename"])
    ]
    public_import_only_fixtures = [
        fixture
        for fixture in PUBLIC_IMPORT_ONLY_FIXTURES
        if _nonempty_file(tests_data_dir / "public" / fixture["filename"])
    ]
    public_bids_fixtures = [
        fixture
        for fixture in PUBLIC_BIDS_FIXTURES
        if _nonempty_file(tests_data_dir / "public" / fixture["entrypoint"])
    ]
    public_training_source_families = sorted(
        {str(fixture["source_family"]) for fixture in public_training_fixtures}
    )
    public_epoch_only_source_families = sorted(
        {str(fixture["source_family"]) for fixture in public_epoch_only_fixtures}
    )
    public_import_only_source_families = sorted(
        {str(fixture["source_family"]) for fixture in public_import_only_fixtures}
    )
    public_training_formats = [
        str(fixture["format"]) for fixture in public_training_fixtures
    ]
    public_epoch_only_formats = [
        str(fixture["format"]) for fixture in public_epoch_only_fixtures
    ]
    public_import_only_formats = [
        str(fixture["format"]) for fixture in public_import_only_fixtures
    ]
    workflow_cases = _workflow_cases_by_id(workflow_snapshot)

    return [
        DatasetLayerRow(
            layer="checked-in core GDF + MAT",
            representative_data=", ".join(checked_in_stems) or "missing",
            reproducibility_class="checked-in",
            source_families="1 (Graz / BCI Competition IV 2a)",
            import_facade=_workflow_status(
                workflow_cases,
                ("checked_in_graz_gdf_mat",),
            ),
            label_attach=_label_workflow_status(
                workflow_cases,
                ("checked_in_graz_gdf_mat",),
            ),
            dataset_generation="separate pipeline integration gate",
            training_smoke="separate one-epoch runner",
            notes=(
                "Deepest current baseline, but still concentrated in one source family."
            ),
        ),
        DatasetLayerRow(
            layer="checked-in compact multiformat",
            representative_data=(
                f"{len(multiformat_files)} derived files from A01T"
                if multiformat_files
                else "missing"
            ),
            reproducibility_class="checked-in",
            source_families="1 derived source",
            import_facade=_workflow_status(
                workflow_cases,
                (
                    "derived_fif_raw",
                    "derived_fif_gz_raw",
                    "derived_fif_epochs",
                    "derived_edf",
                    "derived_bdf",
                    "derived_brainvision",
                    "derived_eeglab",
                ),
            ),
            label_attach="no",
            dataset_generation="no",
            training_smoke="no",
            notes="Improves format coverage, not source diversity.",
        ),
        DatasetLayerRow(
            layer="public local-only event-rich fixtures",
            representative_data=(
                ", ".join(public_training_formats)
                if public_training_formats
                else "not downloaded"
            ),
            reproducibility_class="local-only",
            source_families=(
                "{} ({})".format(
                    len(public_training_source_families),
                    ", ".join(public_training_source_families),
                )
                if public_training_source_families
                else "not downloaded"
            ),
            import_facade=_workflow_status(
                workflow_cases,
                (
                    "public_physionet_motor_edf",
                    "public_bbci_gdf",
                ),
            ),
            label_attach="reviewed internal events",
            dataset_generation="separate cross-source integration gate",
            training_smoke="separate strict cross-source runner",
            notes=(
                "Extends training smoke into non-Graz sources with public protocol "
                "class semantics, but remains local-only."
            ),
        ),
        DatasetLayerRow(
            layer="public local-only epoch-only fixtures",
            representative_data=(
                ", ".join(public_epoch_only_formats)
                if public_epoch_only_formats
                else "not downloaded"
            ),
            reproducibility_class="local-only",
            source_families=(
                "{} ({})".format(
                    len(public_epoch_only_source_families),
                    ", ".join(public_epoch_only_source_families),
                )
                if public_epoch_only_source_families
                else "not downloaded"
            ),
            import_facade=_workflow_status(
                workflow_cases,
                ("public_sccn_eeglab", "public_mne_cnt"),
            ),
            label_attach="reviewed events; no supervised class claim",
            dataset_generation="no; epoch creation checked separately",
            training_smoke="epoch-only by contract",
            notes=(
                "SCCN rt/square lacks public protocol class ground truth; CNT is too "
                "small for class-balanced training. Both prove load, preprocess, "
                "reviewed event selection, and epoch creation only."
            ),
        ),
        DatasetLayerRow(
            layer="public local-only import-only fixtures",
            representative_data=(
                ", ".join(public_import_only_formats)
                if public_import_only_formats
                else "not downloaded"
            ),
            reproducibility_class="local-only",
            source_families=(
                "{} ({})".format(
                    len(public_import_only_source_families),
                    ", ".join(public_import_only_source_families),
                )
                if public_import_only_source_families
                else "not downloaded"
            ),
            import_facade=_workflow_status(
                workflow_cases,
                ("public_physionet_rest_edf", "public_mne_brainvision"),
            ),
            label_attach="no",
            dataset_generation="no",
            training_smoke="no",
            notes=(
                "Still useful for source/format breadth, but these fixtures do not"
                " currently provide a training-smoke path."
            ),
        ),
        DatasetLayerRow(
            layer="public local-only BIDS EEG fixture",
            representative_data=(
                ", ".join(str(fixture["format"]) for fixture in public_bids_fixtures)
                if public_bids_fixtures
                else "not downloaded"
            ),
            reproducibility_class="local-only downloaded",
            source_families=(
                ", ".join(
                    sorted(
                        {
                            str(fixture["source_family"])
                            for fixture in public_bids_fixtures
                        }
                    )
                )
                if public_bids_fixtures
                else "not downloaded"
            ),
            import_facade=_workflow_status(
                workflow_cases,
                ("public_mne_bids_eeg",),
            ),
            label_attach=_label_workflow_status(
                workflow_cases,
                ("public_mne_bids_eeg",),
            ),
            dataset_generation="epoch handoff; creation checked separately",
            training_smoke="no",
            notes=(
                "Protects folder-level BIDS-EEG scan, events.tsv placement, "
                "events sidecars, recipe replay, and epoch handoff; not a full "
                "BIDS validator claim."
            ),
        ),
    ]


def _workflow_cases_by_id(
    workflow_snapshot: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if workflow_snapshot is None:
        return {}
    cases = workflow_snapshot.get("cases", [])
    return {
        str(case["case_id"]): case
        for case in cases
        if isinstance(case, dict) and case.get("case_id")
    }


def _workflow_status(
    cases: dict[str, dict[str, Any]],
    case_ids: tuple[str, ...],
) -> str:
    if not cases:
        return "workflow not run"
    present = [cases[case_id] for case_id in case_ids if case_id in cases]
    passed = sum(case.get("status") == "passed" for case in present)
    return f"scan/preview/validate/apply: {passed}/{len(case_ids)} passed"


def _label_workflow_status(
    cases: dict[str, dict[str, Any]],
    case_ids: tuple[str, ...],
) -> str:
    if not cases:
        return "workflow not run"
    statuses = [
        str(
            cases.get(case_id, {})
            .get("observations", {})
            .get("label_apply_status", "not run")
        )
        for case_id in case_ids
    ]
    return ", ".join(statuses)


def validate_required_dataset_matrix(
    repo_root: Path = ROOT,
    *,
    workflow_snapshot: dict[str, Any] | None = None,
) -> list[DatasetMatrixRequirement]:
    """Return required dataset diversity checks for hand-test preflight.

    These requirements intentionally check source diversity, not only file
    extension breadth. A single dataset converted into many formats is useful,
    but it is not enough evidence before handing a branch to a human tester.
    """
    tests_data_dir = repo_root / "tests" / "fixtures" / "data"
    if workflow_snapshot is None:
        workflow_snapshot = build_real_workflow_snapshot(repo_root)
    workflow_summary = cast(dict[str, Any], workflow_snapshot["summary"])
    checked_in_stems = [
        stem
        for stem in CHECKED_IN_GDF_STEMS
        if (tests_data_dir / f"{stem}.gdf").exists()
        and (tests_data_dir / "label" / f"{stem}.mat").exists()
    ]
    multiformat_files = [
        filename
        for filename in MULTIFORMAT_FILES
        if (tests_data_dir / "multiformat" / filename).exists()
    ]
    public_training_fixtures = [
        fixture
        for fixture in PUBLIC_EVENT_RICH_TRAINING_FIXTURES
        if _nonempty_file(tests_data_dir / "public" / fixture["filename"])
    ]
    public_training_source_families = sorted(
        {str(fixture["source_family"]) for fixture in public_training_fixtures}
    )
    public_epoch_only_fixtures = [
        fixture
        for fixture in PUBLIC_EPOCH_ONLY_FIXTURES
        if _nonempty_file(tests_data_dir / "public" / fixture["filename"])
    ]
    public_bids_fixtures = [
        fixture
        for fixture in PUBLIC_BIDS_FIXTURES
        if _nonempty_file(tests_data_dir / "public" / fixture["entrypoint"])
    ]
    return [
        DatasetMatrixRequirement(
            key="checked_in_gdf_mat",
            label="Checked-in GDF recordings with external MAT labels",
            ok=len(checked_in_stems) >= len(CHECKED_IN_GDF_STEMS),
            observed=", ".join(checked_in_stems) or "none",
            required=("A01T, A02T, and A03T GDF files with matching label/*.mat files"),
        ),
        DatasetMatrixRequirement(
            key="compact_multiformat",
            label="Compact multi-format import fixtures",
            ok=len(multiformat_files) >= len(MULTIFORMAT_FILES),
            observed=f"{len(multiformat_files)} / {len(MULTIFORMAT_FILES)} files",
            required=(
                "FIF, FIF.GZ, epoched FIF, EDF, BDF, BrainVision, and EEGLAB SET"
            ),
        ),
        DatasetMatrixRequirement(
            key="public_event_rich_sources",
            label="Public class-grounded training source diversity",
            ok=len(public_training_fixtures) == len(PUBLIC_EVENT_RICH_TRAINING_FIXTURES)
            and len(public_training_source_families)
            == len(PUBLIC_EVENT_RICH_TRAINING_FIXTURES),
            observed=(
                f"{len(public_training_fixtures)} fixtures from "
                f"{len(public_training_source_families)} source families"
                if public_training_fixtures
                else "none"
            ),
            required=(
                "the fixed PhysioNet EDF and BBCI GDF training fixtures; "
                "run scripts/dev/fetch_public_eeg_fixtures.py "
                "--profile required-ci when missing"
            ),
        ),
        DatasetMatrixRequirement(
            key="public_epoch_only_sources",
            label="Public IO/epoch-only source diversity",
            ok=len(public_epoch_only_fixtures) == len(PUBLIC_EPOCH_ONLY_FIXTURES),
            observed=(
                ", ".join(
                    str(fixture["filename"]) for fixture in public_epoch_only_fixtures
                )
                if public_epoch_only_fixtures
                else "none"
            ),
            required=(
                "the fixed SCCN EEGLAB and MNE CNT load/preprocess/epoch fixtures; "
                "neither is supervised training evidence"
            ),
        ),
        DatasetMatrixRequirement(
            key="public_bids_eeg",
            label="Public BIDS EEG folder fixture",
            ok=bool(public_bids_fixtures),
            observed=(
                ", ".join(
                    str(fixture["source_family"]) for fixture in public_bids_fixtures
                )
                if public_bids_fixtures
                else "none"
            ),
            required=("downloaded MNE-BIDS tiny EEG root with events.tsv and sidecars"),
        ),
        DatasetMatrixRequirement(
            key="real_data_interpretation_lifecycle",
            label="Real Data Interpretation command lifecycle",
            ok=bool(workflow_summary["all_required_passed"]),
            observed=(
                f"{workflow_summary['passed_required_case_count']} / "
                f"{workflow_summary['required_case_count']} required cases passed"
            ),
            required=(
                "every required checked-in, derived-format, and hash-pinned public "
                "case must complete scan -> preview -> validate -> apply"
            ),
        ),
        DatasetMatrixRequirement(
            key="real_public_source_diversity",
            label="Real public source diversity through apply",
            ok=not workflow_summary["missing_public_source_families"],
            observed=(
                f"{workflow_summary['public_source_family_count']} source families: "
                + ", ".join(workflow_summary["public_source_families"])
            ),
            required=(
                f"at least {REQUIRED_PUBLIC_SOURCE_FAMILY_COUNT} distinct public "
                "source families ("
                + ", ".join(sorted(REQUIRED_PUBLIC_SOURCE_FAMILIES))
                + ") must complete the real lifecycle; converted files from one "
                "source do not count"
            ),
        ),
        DatasetMatrixRequirement(
            key="tier_format_apply_coverage",
            label="Tier 1/2 format apply coverage",
            ok=not workflow_summary["missing_required_formats"],
            observed=(
                f"{workflow_summary['passed_required_format_count']} / "
                f"{workflow_summary['required_format_count']} formats passed"
            ),
            required=(
                "the fixed required set must reach apply: "
                + ", ".join(sorted(REQUIRED_TIER_FORMATS))
                + "; shell/header recognition is insufficient"
            ),
        ),
        DatasetMatrixRequirement(
            key="external_label_placement_contracts",
            label="External label carrier placement contracts",
            ok=not workflow_summary["missing_external_label_contracts"],
            observed=(
                f"{workflow_summary['passed_external_label_contract_count']} / "
                f"{workflow_summary['required_external_label_contract_count']} "
                "contracts passed"
            ),
            required=(
                "the fixed external-label set must preserve reviewed placement "
                "choices and reach its declared evidence tier: "
                + ", ".join(sorted(REQUIRED_EXTERNAL_LABEL_CONTRACTS))
            ),
        ),
        DatasetMatrixRequirement(
            key="reviewed_internal_event_contracts",
            label="Reviewed public internal-event contracts",
            ok=not workflow_summary["missing_internal_event_profiles"],
            observed=(
                f"{workflow_summary['passed_internal_event_profile_count']} / "
                f"{workflow_summary['required_internal_event_profile_count']} "
                "profiles passed"
            ),
            required=(
                "the fixed reviewed-event profiles must preserve selections into "
                "epoch handoff: " + ", ".join(sorted(REQUIRED_INTERNAL_EVENT_PROFILES))
            ),
        ),
        DatasetMatrixRequirement(
            key="reviewed_label_apply_coverage",
            label="Reviewed label and event choice apply coverage",
            ok=(
                int(workflow_summary["required_reviewed_label_case_count"])
                == len(REQUIRED_REVIEWED_LABEL_CASE_IDS)
                and workflow_summary["required_reviewed_label_case_ids"]
                == sorted(REQUIRED_REVIEWED_LABEL_CASE_IDS)
                and workflow_summary["passed_required_reviewed_label_case_count"]
                == len(REQUIRED_REVIEWED_LABEL_CASE_IDS)
                and not workflow_summary["missing_required_reviewed_label_case_ids"]
                and not workflow_summary["downgraded_required_reviewed_label_case_ids"]
                and not workflow_summary["choice_preservation_failure_case_ids"]
            ),
            observed=(
                f"{workflow_summary['passed_required_reviewed_label_case_count']} / "
                f"{workflow_summary['required_reviewed_label_case_count']} fixed "
                "reviewed-label/event cases passed"
            ),
            required=(
                "all 11 fixed external-label/reviewed-event case IDs, including CNT, "
                "must preserve explicit choices at their required evidence tier; "
                "missing, downgrade, or choice mismatch is a strict failure"
            ),
        ),
    ]


def build_snapshot(
    repo_root: Path = ROOT,
    *,
    workflow_snapshot: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Return the current machine-readable dataset validation snapshot."""
    if workflow_snapshot is None:
        workflow_snapshot = build_real_workflow_snapshot(repo_root)
    rows = build_dataset_validation_rows(
        repo_root,
        workflow_snapshot=workflow_snapshot,
    )
    tests_data_dir = repo_root / "tests" / "fixtures" / "data"
    requirements = validate_required_dataset_matrix(
        repo_root,
        workflow_snapshot=workflow_snapshot,
    )
    return {
        "repo_root": str(repo_root),
        "tests_data_dir": str(tests_data_dir),
        "rows": [asdict(row) for row in rows],
        "strict_validation": {
            "ok": all(requirement.ok for requirement in requirements),
            "requirements": [asdict(requirement) for requirement in requirements],
        },
        "data_interpretation_workflows": workflow_snapshot,
        "current_truth": {
            "checked_in_depth": (
                "the matrix directly proves checked-in Graz scan, preview, validate, "
                "apply, and reviewed MAT label application; dataset generation and "
                "training remain separate integration evidence"
            ),
            "cross_source_breadth": (
                f"{workflow_snapshot['summary']['passed_public_case_count']} public "
                "cases from "
                f"{workflow_snapshot['summary']['public_source_family_count']} source "
                "families completed scan, preview, validate, and apply"
            ),
            "main_limit": (
                "public fixtures remain local-only downloads; generated CSV/TSV/TXT "
                "cases prove parser and placement contracts but are deliberately "
                "excluded from public dataset-source diversity"
            ),
        },
    }


def render_markdown(snapshot: dict[str, object]) -> str:
    """Render the dataset validation snapshot in Markdown."""
    rows = cast(list[dict[str, object]], snapshot["rows"])
    strict_validation = cast(dict[str, object], snapshot["strict_validation"])
    requirements = cast(list[dict[str, object]], strict_validation["requirements"])
    current_truth = cast(dict[str, object], snapshot["current_truth"])
    workflow_snapshot = cast(
        dict[str, object],
        snapshot["data_interpretation_workflows"],
    )
    workflow_cases = cast(list[dict[str, object]], workflow_snapshot["cases"])
    lines = [
        "# Dataset Validation Matrix",
        "",
        "| Layer | Representative data | Reproducibility | Source families | Import / facade | Label attach | Dataset generation | Training smoke | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {layer} | {representative_data} | {reproducibility_class} | "
            "{source_families} | {import_facade} | {label_attach} | "
            "{dataset_generation} | {training_smoke} | {notes} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Required Multi-Dataset Gate",
            "",
            f"- overall: `{'pass' if strict_validation['ok'] else 'fail'}`",
            "",
            "| Requirement | Status | Observed | Required |",
            "| --- | --- | --- | --- |",
        ]
    )
    for requirement in requirements:
        lines.append(
            "| {label} | {status} | {observed} | {required} |".format(
                label=requirement["label"],
                status="pass" if requirement["ok"] else "fail",
                observed=requirement["observed"],
                required=requirement["required"],
            )
        )
    lines.extend(
        [
            "",
            "## Real Data Interpretation Lifecycle",
            "",
            "A non-empty file is not enough. Each passing row below completed "
            "`scan -> preview -> validate -> apply` through `ApplicationService`.",
            "",
            "| Scope | Dataset source | Format | Status | Failed stage | Evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in workflow_cases:
        observations = cast(dict[str, object], case.get("observations", {}))
        evidence = (
            f"validation={observations.get('validation_decision', 'not run')}; "
            f"labels={observations.get('label_apply_status', 'not run')}; "
            "evidence_tier="
            f"{observations.get('reviewed_evidence_tier', 'not_required')}; "
            f"supervised_ready={observations.get('supervised_ready', False)}"
        )
        lines.append(
            "| {scope} | {source} | {format_name} | {status} | {failed_stage} | "
            "{evidence} |".format(
                scope=case["evidence_scope"],
                source=case["source_family"],
                format_name=case["format"],
                status=case["status"],
                failed_stage=case.get("failed_stage") or "-",
                evidence=evidence,
            )
        )
    lines.extend(
        [
            "",
            "## Current Truth",
            "",
            f"- {current_truth['checked_in_depth']}",
            f"- {current_truth['cross_source_breadth']}",
            f"- {current_truth['main_limit']}",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Fail unless the required multi-dataset matrix is present. "
            "Used by required CI and before manual handoff."
        ),
    )
    args = parser.parse_args()

    snapshot = build_snapshot()
    if args.format == "json":
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(snapshot))
    strict_validation = cast(dict[str, object], snapshot["strict_validation"])
    return 0 if not args.strict or strict_validation["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
