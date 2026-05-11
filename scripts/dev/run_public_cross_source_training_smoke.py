#!/usr/bin/env python3
"""Run the current public local-only cross-source training smoke protocol."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import torch

from XBrainLab.backend.application import (
    ConfigureTrainingCommand,
    CreateEpochCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    SaliencyCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    TrainingEvaluation,
    TrainingOption,
)
from XBrainLab.backend.training.record import RecordKey

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DATA_DIR = ROOT / "tests" / "fixtures" / "data" / "public"

PUBLIC_TRAINING_FIXTURES = (
    {
        "name": "physionet-edf",
        "filename": "physionet-eegmmidb-S008R04.edf",
        "source_family": "PhysioNet",
        "event_ids": ["T1", "T2"],
        "tmin": 0,
        "tmax": 2,
    },
    {
        "name": "bbci-gdf",
        "filename": "bbci-competition-iii-O3VR.gdf",
        "source_family": "BBCI",
        "event_ids": ["769", "770"],
        "tmin": 0,
        "tmax": 2,
    },
    {
        "name": "sccn-eeglab",
        "filename": "sccn-eeglab_data.set",
        "source_family": "SCCN / EEGLAB",
        "event_ids": ["rt", "square"],
        "tmin": 0,
        "tmax": 2,
    },
    {
        "name": "mne-cnt",
        "filename": "scan41_short.cnt",
        "source_family": "MNE testing-data",
        "event_ids": ["0", "109", "7"],
        "tmin": 0,
        "tmax": 2,
    },
)


@dataclass
class SmokeResult:
    """One row in the public cross-source training-smoke report."""

    name: str
    filename: str
    source_family: str
    status: str
    dataset_count: int
    message: str


def _raise_if_failed(result) -> None:
    if result.failed:
        raise RuntimeError(result.message)


def run_fixture_smoke(fixture: dict[str, object]) -> SmokeResult:
    """Execute one public-fixture training smoke and return structured status."""
    filepath = PUBLIC_DATA_DIR / str(fixture["filename"])
    if not filepath.exists():
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="missing",
            dataset_count=0,
            message=f"fixture not downloaded: {filepath}",
        )

    study = Study()
    service = get_application_service(study)
    load_result = service.execute(LoadDataCommand(paths=[str(filepath)]))
    if load_result.failed or load_result.diagnostics.get("success_count") != 1:
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="failed",
            dataset_count=0,
            message=f"load failed: {load_result.message}",
        )

    try:
        filter_result = service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS,
                low_freq=4,
                high_freq=38,
            ),
        )
        _raise_if_failed(filter_result)
        normalize_result = service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z score",
            ),
        )
        _raise_if_failed(normalize_result)
        event_ids = [str(item) for item in cast(list[object], fixture["event_ids"])]
        epoch_result = service.execute(
            CreateEpochCommand(
                t_min=float(cast(float | int | str, fixture["tmin"])),
                t_max=float(cast(float | int | str, fixture["tmax"])),
                event_ids=event_ids,
            ),
        )
        _raise_if_failed(epoch_result)
        dataset_result = service.execute(
            GenerateDatasetCommand(
                test_ratio=0.2,
                val_ratio=0.2,
                split_strategy="trial",
                training_mode="individual",
            ),
        )
        _raise_if_failed(dataset_result)

        datasets = study.datasets
        dataset_count = len(datasets) if datasets is not None else 0
        if dataset_count <= 0:
            return SmokeResult(
                name=str(fixture["name"]),
                filename=str(fixture["filename"]),
                source_family=str(fixture["source_family"]),
                status="failed",
                dataset_count=0,
                message="dataset generation produced no datasets",
            )

        configure_model = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
        _raise_if_failed(configure_model)
        configure_training = service.execute(
            ConfigureTrainingCommand(
                training_option=TrainingOption(
                    output_dir="test_public_output",
                    optim=torch.optim.Adam,
                    optim_params={},
                    use_cpu=True,
                    gpu_idx=None,
                    epoch=1,
                    bs=8,
                    lr=0.001,
                    checkpoint_epoch=1,
                    evaluation_option=TrainingEvaluation.TEST_ACC,
                    repeat_num=1,
                ),
            ),
        )
        _raise_if_failed(configure_training)
        saliency_result = service.execute(
            SaliencyCommand(
                params={
                    "SmoothGrad": {"nt_samples": 1, "stdevs": 0.1},
                    "SmoothGrad_Squared": {"nt_samples": 1, "stdevs": 0.1},
                    "VarGrad": {"nt_samples": 1, "stdevs": 0.1},
                },
            ),
        )
        _raise_if_failed(saliency_result)

        with (
            patch("matplotlib.pyplot.savefig"),
            patch("torch.save"),
            patch("numpy.savetxt"),
            patch("os.makedirs"),
        ):
            study.generate_plan()
            study.train(interact=False)

        trainer = study.trainer
        if trainer is None:
            return SmokeResult(
                name=str(fixture["name"]),
                filename=str(fixture["filename"]),
                source_family=str(fixture["source_family"]),
                status="failed",
                dataset_count=dataset_count,
                message="training produced no trainer",
            )
        plan_holders = trainer.get_training_plan_holders()
        record = plan_holders[0].train_record_list[0]
        if RecordKey.LOSS not in record.train or RecordKey.ACC not in record.train:
            return SmokeResult(
                name=str(fixture["name"]),
                filename=str(fixture["filename"]),
                source_family=str(fixture["source_family"]),
                status="failed",
                dataset_count=dataset_count,
                message="training record missing loss/acc metrics",
            )

        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="passed",
            dataset_count=dataset_count,
            message="one-epoch CPU smoke passed",
        )
    except Exception as exc:
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="failed",
            dataset_count=0,
            message=f"{type(exc).__name__}: {exc}",
        )


def build_snapshot(repo_root: Path = ROOT) -> dict[str, Any]:
    """Run the current public cross-source smoke protocol and summarize it."""
    results = [
        asdict(run_fixture_smoke(fixture)) for fixture in PUBLIC_TRAINING_FIXTURES
    ]
    passed = sum(1 for result in results if result["status"] == "passed")
    missing = sum(1 for result in results if result["status"] == "missing")
    failed = sum(1 for result in results if result["status"] == "failed")
    return {
        "repo_root": str(repo_root),
        "public_data_dir": str(repo_root / "tests" / "fixtures" / "data" / "public"),
        "results": results,
        "summary": {
            "passed": passed,
            "missing": missing,
            "failed": failed,
            "message": (
                "Event-rich public local-only fixtures now provide a repeatable "
                "cross-source one-epoch training-smoke protocol."
            ),
        },
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    """Render the current public training-smoke snapshot in Markdown."""
    lines = [
        "# Public Cross-Source Training Smoke",
        "",
        "| Fixture | Source family | Status | Datasets | Message |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in snapshot["results"]:
        lines.append(
            "| {filename} | {source_family} | {status} | {dataset_count} | {message} |".format(
                **result,
            )
        )
    summary = snapshot["summary"]
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- passed: `{summary['passed']}`",
            f"- missing: `{summary['missing']}`",
            f"- failed: `{summary['failed']}`",
            f"- {summary['message']}",
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
        help="Return non-zero when any fixture is missing or failed.",
    )
    args = parser.parse_args()

    snapshot = build_snapshot()
    if args.format == "json":
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(snapshot))

    summary = snapshot["summary"]
    if args.strict and (summary["missing"] or summary["failed"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
