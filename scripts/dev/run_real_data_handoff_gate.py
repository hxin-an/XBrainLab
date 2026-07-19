#!/usr/bin/env python3
"""Run the real-data workflows required before an XBrainLab UI handoff."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class GateSlice:
    """One independently meaningful real-data validation slice."""

    name: str
    pytest_target: str
    source_families: tuple[str, ...]
    stages: tuple[str, ...]


GATE_SLICES: tuple[GateSlice, ...] = (
    GateSlice(
        name="graz-external-label-continuous-handoff",
        pytest_target=(
            "tests/integration/pipeline/test_real_data_handoff_gate.py::"
            "test_graz_external_labels_reach_real_training_through_interpretation_spine"
        ),
        source_families=("graz-2a",),
        stages=(
            "data-interpretation",
            "external-label-apply",
            "epoch-materialization",
            "dataset-generation",
            "training-readiness",
            "tiny-training",
        ),
    ),
    GateSlice(
        name="public-bids-continuous-handoff",
        pytest_target=(
            "tests/integration/pipeline/test_real_data_handoff_gate.py::"
            "test_public_bids_reaches_epoch_and_dataset_generation_readiness"
        ),
        source_families=("mne-bids-tiny",),
        stages=(
            "bids-folder-import",
            "events-tsv-apply",
            "epoch-materialization",
            "dataset-generation-readiness",
        ),
    ),
    GateSlice(
        name="bids-duration-boundaries",
        pytest_target="tests/integration/io/test_bids_epoch_duration_handoff.py",
        source_families=("generated-bids-duration-boundary",),
        stages=("bids-duration-review", "epoch-materialization"),
    ),
    GateSlice(
        name="visible-external-label-wizard",
        pytest_target=(
            "tests/integration/ui/test_data_import_action_handler_external_labels.py::"
            "test_dataset_action_handler_imports_real_gdf_with_external_mat_labels"
        ),
        source_families=("graz-2a",),
        stages=("visible-data-import", "external-label-apply"),
    ),
    GateSlice(
        name="label-source-remove-readd-lifecycle",
        pytest_target=(
            "tests/integration/ui/test_data_import_action_handler_external_labels.py::"
            "test_outer_async_review_remove_then_readd_keeps_one_real_label_source"
        ),
        source_families=("graz-2a",),
        stages=("visible-data-import", "outer-async-rescan", "external-label-apply"),
    ),
    GateSlice(
        name="public-cross-source-downstream-smoke",
        pytest_target=(
            "tests/integration/pipeline/test_public_cross_source_training_smoke.py"
        ),
        source_families=(
            "physionet-eegmmidb",
            "bbci-competition-iii",
            "sccn-eeglab",
            "mne-cnt",
        ),
        stages=("real-data-io", "epoch-materialization", "tiny-training"),
    ),
)


def source_families() -> set[str]:
    return {
        source_family
        for gate_slice in GATE_SLICES
        for source_family in gate_slice.source_families
        if not source_family.startswith("generated-")
    }


def pytest_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "--capture=sys",
        "-q",
        "-o",
        "faulthandler_timeout=180",
        *(gate_slice.pytest_target for gate_slice in GATE_SLICES),
    ]


def main() -> int:
    environment = {
        **os.environ,
        "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "offscreen"),
        "MPLBACKEND": os.environ.get("MPLBACKEND", "Agg"),
    }
    completed = subprocess.run(  # noqa: S603 - targets are a fixed local manifest
        pytest_command(),
        cwd=ROOT,
        env=environment,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
