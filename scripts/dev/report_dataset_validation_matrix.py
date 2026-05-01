#!/usr/bin/env python3
"""Report the current dataset validation matrix for thesis-facing validation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_DATA_DIR = ROOT / "tests" / "data"

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


def build_dataset_validation_rows(
    repo_root: Path = ROOT,
) -> list[DatasetLayerRow]:
    """Build the current dataset validation matrix from known repo fixtures."""
    tests_data_dir = repo_root / "tests" / "data"
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
        if (tests_data_dir / "public" / fixture["filename"]).exists()
    ]
    public_import_only_fixtures = [
        fixture
        for fixture in PUBLIC_IMPORT_ONLY_FIXTURES
        if (tests_data_dir / "public" / fixture["filename"]).exists()
    ]
    public_training_source_families = sorted(
        {str(fixture["source_family"]) for fixture in public_training_fixtures}
    )
    public_import_only_source_families = sorted(
        {str(fixture["source_family"]) for fixture in public_import_only_fixtures}
    )
    public_training_formats = [
        str(fixture["format"]) for fixture in public_training_fixtures
    ]
    public_import_only_formats = [
        str(fixture["format"]) for fixture in public_import_only_fixtures
    ]

    return [
        DatasetLayerRow(
            layer="checked-in core GDF + MAT",
            representative_data=", ".join(checked_in_stems) or "missing",
            reproducibility_class="checked-in",
            source_families="1 (Graz / BCI Competition IV 2a)",
            import_facade="yes",
            label_attach="yes",
            dataset_generation="yes",
            training_smoke=(
                f"yes ({len(checked_in_stems)} stems)"
                if checked_in_stems
                else "missing"
            ),
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
            import_facade="yes",
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
            import_facade="yes" if public_training_fixtures else "pending",
            label_attach="no",
            dataset_generation="yes" if public_training_fixtures else "pending",
            training_smoke=(
                f"yes ({len(public_training_fixtures)} fixtures)"
                if public_training_fixtures
                else "pending"
            ),
            notes=(
                "Extends training smoke into non-Graz sources using intrinsic event"
                " structure, but remains local-only."
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
            import_facade="yes" if public_import_only_fixtures else "pending",
            label_attach="no",
            dataset_generation="no",
            training_smoke="no",
            notes=(
                "Still useful for source/format breadth, but these fixtures do not"
                " currently provide a training-smoke path."
            ),
        ),
    ]


def build_snapshot(repo_root: Path = ROOT) -> dict[str, object]:
    """Return the current machine-readable dataset validation snapshot."""
    rows = build_dataset_validation_rows(repo_root)
    return {
        "repo_root": str(repo_root),
        "tests_data_dir": str(repo_root / "tests" / "data"),
        "rows": [asdict(row) for row in rows],
        "current_truth": {
            "checked_in_depth": (
                "checked-in Graz-family fixtures now support import, label attach, "
                "dataset generation, and one-epoch training smoke"
            ),
            "cross_source_breadth": (
                "event-rich public local-only fixtures now extend one-epoch training "
                "smoke into PhysioNet, BBCI, SCCN / EEGLAB, and MNE testing-data "
                "CNT sources, while rest-style PhysioNet EDF and BrainVision stay "
                "at import/facade-only"
            ),
            "main_limit": (
                "cross-source evidence is stronger, but part of it remains local-only "
                "and therefore weaker than fully checked-in thesis-grade reproducibility"
            ),
        },
    }


def render_markdown(snapshot: dict[str, object]) -> str:
    """Render the dataset validation snapshot in Markdown."""
    lines = [
        "# Dataset Validation Matrix",
        "",
        "| Layer | Representative data | Reproducibility | Source families | Import / facade | Label attach | Dataset generation | Training smoke | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in snapshot["rows"]:
        lines.append(
            "| {layer} | {representative_data} | {reproducibility_class} | "
            "{source_families} | {import_facade} | {label_attach} | "
            "{dataset_generation} | {training_smoke} | {notes} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Current Truth",
            "",
            f"- {snapshot['current_truth']['checked_in_depth']}",
            f"- {snapshot['current_truth']['cross_source_breadth']}",
            f"- {snapshot['current_truth']['main_limit']}",
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
    args = parser.parse_args()

    snapshot = build_snapshot()
    if args.format == "json":
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
