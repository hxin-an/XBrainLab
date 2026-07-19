#!/usr/bin/env python3
"""Run public local-only cross-source training plus epoch-only smoke evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from XBrainLab.backend.application import (
    ConfigureTrainingCommand,
    CreateEpochCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    SaliencyCommand,
    TrainCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
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
        "split_ratio": 0.2,
    },
    {
        "name": "bbci-gdf",
        "filename": "bbci-competition-iii-O3VR.gdf",
        "source_family": "BBCI",
        "event_ids": ["769", "770"],
        "tmin": 0,
        "tmax": 2,
        "split_ratio": 0.2,
    },
)

PUBLIC_EPOCH_ONLY_FIXTURES = (
    {
        "name": "sccn-eeglab",
        "filename": "sccn-eeglab_data.set",
        "source_family": "SCCN / EEGLAB",
        # The public tutorial file exposes these annotation values, but the
        # fixture does not carry a protocol ground truth that defines them as
        # supervised classes.
        "event_ids": ["rt", "square"],
        "tmin": 0,
        "tmax": 1.5,
        "boundary_reason": (
            "public fixture lacks protocol ground truth for supervised classes"
        ),
    },
    {
        "name": "mne-cnt",
        "filename": "scan41_short.cnt",
        "source_family": "MNE testing-data",
        # Marker 0 is exactly at the recording boundary and 109 has a
        # near-terminal occurrence. The interior task marker proves epoch
        # support without bypassing the product's boundary protection.
        "event_ids": ["7"],
        "tmin": 0,
        "tmax": 1.5,
        "boundary_reason": (
            "fixture is too small for class-balanced training evidence"
        ),
    },
)

REQUIRED_PUBLIC_SMOKE_PROTOCOLS = {
    "physionet-edf": "training",
    "bbci-gdf": "training",
    "sccn-eeglab": "epoch-only",
    "mne-cnt": "epoch-only",
}
REQUIRED_PUBLIC_SMOKE_CASE_IDS = frozenset(REQUIRED_PUBLIC_SMOKE_PROTOCOLS)


@dataclass
class SmokeResult:
    """One row in the public cross-source training-smoke report."""

    name: str
    filename: str
    source_family: str
    status: str
    dataset_count: int
    message: str
    protocol: str = "training"


def _raise_if_failed(result) -> None:
    if result.failed:
        raise RuntimeError(result.message)


def _require_epoch_count(epoch_count: int) -> None:
    if epoch_count <= 0:
        raise RuntimeError("epoch creation produced no usable epochs")


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
        split_ratio = float(cast(float | int | str, fixture.get("split_ratio", 0.2)))
        dataset_result = service.execute(
            GenerateDatasetCommand(
                test_ratio=split_ratio,
                val_ratio=split_ratio,
                split_strategy="trial",
                training_mode="individual",
            ),
        )
        _raise_if_failed(dataset_result)

        dataset_count = int(dataset_result.state.dataset.count or 0)
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
                output_dir="test_public_output",
                device="cpu",
                epoch=1,
                batch_size=8,
                learning_rate=0.001,
                save_checkpoints_every=1,
                evaluation_option="val_acc",
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
            train_result = service.execute(
                TrainCommand(confirmed=True, interactive=False),
            )
        _raise_if_failed(train_result)

        if train_result.state.training.run_count <= 0:
            return SmokeResult(
                name=str(fixture["name"]),
                filename=str(fixture["filename"]),
                source_family=str(fixture["source_family"]),
                status="failed",
                dataset_count=dataset_count,
                message="training produced no trainer",
            )
        history = service.execute(
            QueryStateCommand(query="training_history", include_objects=True),
        )
        _raise_if_failed(history)
        rows = cast(list[dict[str, Any]], history.runtime.get("rows", []))
        if not rows:
            return SmokeResult(
                name=str(fixture["name"]),
                filename=str(fixture["filename"]),
                source_family=str(fixture["source_family"]),
                status="failed",
                dataset_count=dataset_count,
                message="training history did not include a run record",
            )
        record = rows[0]["record"]
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


def run_fixture_epoch_smoke(fixture: dict[str, object]) -> SmokeResult:
    """Execute load/preprocess/epoch evidence for fixtures too small for training."""
    filepath = PUBLIC_DATA_DIR / str(fixture["filename"])
    if not filepath.exists():
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="missing",
            dataset_count=0,
            message=f"fixture not downloaded: {filepath}",
            protocol="epoch-only",
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
            protocol="epoch-only",
        )

    try:
        _raise_if_failed(
            service.execute(
                PreprocessCommand(
                    operation=PreprocessOperation.BANDPASS,
                    low_freq=4,
                    high_freq=38,
                ),
            )
        )
        _raise_if_failed(
            service.execute(
                PreprocessCommand(
                    operation=PreprocessOperation.NORMALIZE,
                    method="z score",
                ),
            )
        )
        event_ids = [str(item) for item in cast(list[object], fixture["event_ids"])]
        epoch_result = service.execute(
            CreateEpochCommand(
                t_min=float(cast(float | int | str, fixture["tmin"])),
                t_max=float(cast(float | int | str, fixture["tmax"])),
                event_ids=event_ids,
            ),
        )
        _raise_if_failed(epoch_result)
        epoch_count = int(epoch_result.state.epoch.epoch_count or 0)
        _require_epoch_count(epoch_count)
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="passed",
            dataset_count=0,
            message=(
                f"load/preprocess/epoch smoke passed with {epoch_count} epochs; "
                f"{fixture['boundary_reason']}"
            ),
            protocol="epoch-only",
        )
    except Exception as exc:
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="failed",
            dataset_count=0,
            message=f"{type(exc).__name__}: {exc}",
            protocol="epoch-only",
        )


def build_snapshot(repo_root: Path = ROOT) -> dict[str, Any]:
    """Run the current public cross-source smoke protocol and summarize it."""
    results = [
        asdict(run_fixture_smoke(fixture)) for fixture in PUBLIC_TRAINING_FIXTURES
    ]
    results.extend(
        asdict(run_fixture_epoch_smoke(fixture))
        for fixture in PUBLIC_EPOCH_ONLY_FIXTURES
    )
    passed = sum(1 for result in results if result["status"] == "passed")
    missing = sum(1 for result in results if result["status"] == "missing")
    failed = sum(1 for result in results if result["status"] == "failed")
    results_by_id = {str(result["name"]): result for result in results}
    missing_required_case_ids = sorted(
        REQUIRED_PUBLIC_SMOKE_CASE_IDS - results_by_id.keys()
    )
    wrong_protocol_case_ids = sorted(
        case_id
        for case_id, required_protocol in REQUIRED_PUBLIC_SMOKE_PROTOCOLS.items()
        if case_id in results_by_id
        and results_by_id[case_id]["protocol"] != required_protocol
    )
    failed_required_case_ids = sorted(
        case_id
        for case_id in REQUIRED_PUBLIC_SMOKE_CASE_IDS
        if case_id in results_by_id and results_by_id[case_id]["status"] == "failed"
    )
    missing_fixture_case_ids = sorted(
        case_id
        for case_id in REQUIRED_PUBLIC_SMOKE_CASE_IDS
        if case_id in results_by_id and results_by_id[case_id]["status"] == "missing"
    )
    passed_required_case_ids = sorted(
        case_id
        for case_id, required_protocol in REQUIRED_PUBLIC_SMOKE_PROTOCOLS.items()
        if case_id in results_by_id
        and results_by_id[case_id]["status"] == "passed"
        and results_by_id[case_id]["protocol"] == required_protocol
    )
    all_required_passed = (
        len(passed_required_case_ids) == len(REQUIRED_PUBLIC_SMOKE_CASE_IDS)
        and not missing_required_case_ids
        and not wrong_protocol_case_ids
        and not failed_required_case_ids
        and not missing_fixture_case_ids
    )
    return {
        "repo_root": str(repo_root),
        "public_data_dir": str(repo_root / "tests" / "fixtures" / "data" / "public"),
        "results": results,
        "summary": {
            "passed": passed,
            "missing": missing,
            "failed": failed,
            "required_case_count": len(REQUIRED_PUBLIC_SMOKE_CASE_IDS),
            "required_case_ids": sorted(REQUIRED_PUBLIC_SMOKE_CASE_IDS),
            "passed_required_case_count": len(passed_required_case_ids),
            "passed_required_case_ids": passed_required_case_ids,
            "missing_required_case_ids": missing_required_case_ids,
            "missing_fixture_case_ids": missing_fixture_case_ids,
            "failed_required_case_ids": failed_required_case_ids,
            "wrong_protocol_case_ids": wrong_protocol_case_ids,
            "all_required_passed": all_required_passed,
            "message": (
                "PhysioNet EDF and BBCI GDF provide class-grounded training smoke. "
                "SCCN EEGLAB and MNE CNT provide load/preprocess/epoch-only evidence; "
                "their annotation values are not claimed as supervised classes."
            ),
        },
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    """Render the current public training-smoke snapshot in Markdown."""
    lines = [
        "# Public Cross-Source Training Smoke",
        "",
        "| Fixture | Source family | Protocol | Status | Datasets | Message |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in snapshot["results"]:
        lines.append(
            "| {filename} | {source_family} | {protocol} | {status} | {dataset_count} | {message} |".format(
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
            "- fixed required cases passed: "
            f"`{summary['passed_required_case_count']} / "
            f"{summary['required_case_count']}`",
            f"- strict result: `{summary['all_required_passed']}`",
            f"- {summary['message']}",
        ]
    )
    return "\n".join(lines)


def build_snapshot_for_json_output() -> dict[str, Any]:
    """Run the smoke while keeping noisy library stdout out of JSON stdout."""
    original_stdout = sys.stdout
    saved_stdout_fd = os.dup(1)
    try:
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as runner_stdout:
            original_stdout.flush()
            os.dup2(runner_stdout.fileno(), 1)
            sys.stdout = runner_stdout
            try:
                snapshot = build_snapshot()
                runner_stdout.flush()
            finally:
                os.dup2(saved_stdout_fd, 1)
                sys.stdout = original_stdout
            runner_stdout.seek(0)
            captured = runner_stdout.read()
    finally:
        os.close(saved_stdout_fd)
        sys.stdout = original_stdout

    if captured:
        print(captured, end="", file=sys.stderr)
    return snapshot


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

    if args.format == "json":
        snapshot = build_snapshot_for_json_output()
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    else:
        snapshot = build_snapshot()
        print(render_markdown(snapshot))

    summary = snapshot["summary"]
    if args.strict and not summary["all_required_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
