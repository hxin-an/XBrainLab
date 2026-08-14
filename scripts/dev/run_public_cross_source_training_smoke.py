#!/usr/bin/env python3
"""Run public local-only training plus import/preprocess boundary evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("MNE_DONTWRITE_HOME", "true")

if __package__:
    from scripts.dev.active_checkout import assert_active_checkout_import
else:
    from active_checkout import assert_active_checkout_import

ROOT = Path(__file__).resolve().parents[2]
assert_active_checkout_import(ROOT)

from scripts.dev.fetch_public_eeg_fixtures import resolve_public_fixture_dir
from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    SaliencyCommand,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training.record import EvalRecord, RecordKey
from XBrainLab.backend.training.record.artifact_store import load_model_state_dict

_REPO_PUBLIC_FIXTURE_DIR = Path("tests/fixtures/data/public")


def _public_data_dir(repo_root: Path = ROOT) -> Path:
    """Resolve central storage while preserving isolated repo-root test fixtures."""
    if repo_root.absolute() == ROOT:
        return resolve_public_fixture_dir()
    return repo_root / _REPO_PUBLIC_FIXTURE_DIR


PUBLIC_TRAINING_FIXTURES = (
    {
        "name": "physionet-edf",
        "filename": "physionet-eegmmidb-S008R04.edf",
        "source_family": "PhysioNet",
        "label_event_ids": ["T1", "T2"],
        "epoch_event_ids": ["T1", "T2"],
        "not_label_event_ids": ["T0"],
        "class_map": {"T1": "left fist", "T2": "right fist"},
        "run_event_mappings": {
            "physionet-eegmmidb-S008R04.edf": {
                "T1": "left fist",
                "T2": "right fist",
            },
        },
        "tmin": 0,
        "tmax": 2,
        "split_ratio": 0.2,
    },
    {
        "name": "bbci-gdf",
        "filename": "bbci-competition-iii-O3VR.gdf",
        "source_family": "BBCI",
        "label_event_ids": ["769", "770"],
        "epoch_event_ids": ["769", "770"],
        "not_label_event_ids": ["768", "781", "783", "785"],
        "class_map": {"769": "769", "770": "770"},
        "run_event_mappings": {},
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
        "label_event_ids": [],
        "epoch_event_ids": ["rt", "square"],
        "not_label_event_ids": ["rt", "square"],
        "class_map": {},
        "run_event_mappings": {},
        "tmin": 0,
        "tmax": 1.5,
        "expected_epoch_block": "does not provide event timing",
        "boundary_reason": (
            "public fixture lacks protocol ground truth for supervised classes"
        ),
    },
    {
        "name": "mne-cnt",
        "filename": "scan41_short.cnt",
        "source_family": "MNE testing-data",
        "label_event_ids": ["7"],
        "epoch_event_ids": ["7"],
        "not_label_event_ids": ["0", "109"],
        "class_map": {"7": "7"},
        "run_event_mappings": {},
        "tmin": 0,
        "tmax": 1.5,
        "expected_epoch_block": "at least 2 selected class labels",
        "boundary_reason": (
            "fixture is too small for class-balanced training evidence"
        ),
    },
)

REQUIRED_PUBLIC_SMOKE_PROTOCOLS = {
    "physionet-edf": "training",
    "bbci-gdf": "training",
    "sccn-eeglab": "import-preprocess-only",
    "mne-cnt": "import-preprocess-only",
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
    artifacts_reloaded: bool = False


def _raise_if_failed(result) -> None:
    if result.failed:
        raise RuntimeError(result.message)


def _require_supervised_epoch_block(result, expected_reason: str) -> None:
    if result.ok:
        raise RuntimeError(
            "boundary fixture unexpectedly admitted supervised EEG epoch creation"
        )
    if expected_reason not in result.message:
        raise RuntimeError(
            f"boundary fixture was blocked for an unexpected reason: {result.message}"
        )


def _reload_real_training_artifacts(output_root: Path) -> None:
    """Require one complete, safely reloadable training artifact directory."""
    record_manifests = list(output_root.rglob("record"))
    if len(record_manifests) != 1:
        raise RuntimeError(
            "training persistence did not produce exactly one record manifest"
        )
    artifact_dir = record_manifests[0].parent
    persisted_names = {path.name for path in artifact_dir.iterdir() if path.is_file()}
    required_names = {"record", "record.npz", "eval", "eval.npz"}
    if not required_names <= persisted_names:
        raise RuntimeError("training persistence is missing safe record artifacts")
    checkpoints = [
        path
        for path in artifact_dir.iterdir()
        if path.is_file() and path.name.startswith("Epoch-1-model")
    ]
    if len(checkpoints) != 1 or not load_model_state_dict(checkpoints[0]):
        raise RuntimeError("training checkpoint could not be safely reloaded")
    evaluation = EvalRecord.load(str(artifact_dir))
    if (
        evaluation is None
        or len(evaluation.label) == 0
        or len(evaluation.output) != len(evaluation.label)
    ):
        raise RuntimeError("evaluation artifact could not be safely reloaded")


def _apply_reviewed_internal_event_import(
    service: Any,
    filepath: Path,
    fixture: dict[str, object],
) -> None:
    """Apply one explicit internal-event interpretation through product commands."""
    source_path = str(filepath.resolve())
    label_event_ids = [
        str(item) for item in cast(list[object], fixture["label_event_ids"])
    ]
    not_label_event_ids = [
        str(item) for item in cast(list[object], fixture.get("not_label_event_ids", []))
    ]
    class_map = {
        str(key): str(value)
        for key, value in cast(dict[object, object], fixture["class_map"]).items()
    }
    choices = {
        "selected_eeg_files": [source_path],
        "label_carrier": "embedded_events",
        "class_map": class_map,
        "internal_event_selection": {
            "label_event_codes": label_event_ids,
            "not_label_event_codes": not_label_event_ids,
            "class_map": class_map,
        },
        "run_event_mappings": dict(
            cast(dict[str, dict[str, str]], fixture["run_event_mappings"])
        ),
    }
    scan_result = service.execute(
        ScanSourceCommand(source_path=source_path, source_hint="file")
    )
    _raise_if_failed(scan_result)
    scan = scan_result.diagnostics.get("scan_result")
    scan_id = scan.get("scan_id") if isinstance(scan, dict) else None
    if not isinstance(scan_id, str) or not scan_id:
        raise RuntimeError("reviewed import scan did not publish a scan identity")
    if scan.get("eeg_files") != [source_path]:
        raise RuntimeError("reviewed import scan changed the selected EEG file")
    preview_result = service.execute(
        PreviewInterpretationCommand(scan_id=scan_id, choices=choices)
    )
    _raise_if_failed(preview_result)
    candidate = preview_result.diagnostics.get("candidate")
    if not isinstance(candidate, dict):
        raise RuntimeError("reviewed import preview did not publish a candidate")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise RuntimeError(
            "reviewed import preview did not publish a candidate identity"
        )
    if candidate.get("selected_eeg_files") != [source_path]:
        raise RuntimeError("reviewed import preview changed the selected EEG file")
    selection = candidate.get("internal_event_selection")
    if not isinstance(selection, dict):
        raise RuntimeError("reviewed import preview omitted internal event roles")
    if selection.get("label_event_codes") != label_event_ids:
        raise RuntimeError("reviewed import preview changed label event roles")
    if set(selection.get("not_label_event_codes", [])) != set(not_label_event_ids):
        raise RuntimeError("reviewed import preview changed non-label event roles")
    if selection.get("class_map", {}) != class_map:
        raise RuntimeError("reviewed import preview changed the class map")
    if candidate.get("run_event_mappings") != choices["run_event_mappings"]:
        raise RuntimeError("reviewed import preview changed run event mappings")
    validation_result = service.execute(
        ValidateInterpretationCommand(candidate_id=candidate_id)
    )
    _raise_if_failed(validation_result)
    apply_result = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )
    _raise_if_failed(apply_result)
    if apply_result.state.raw.count != 1:
        raise RuntimeError("reviewed import did not publish exactly one EEG file")
    if apply_result.state.raw.files != [filepath.name]:
        raise RuntimeError("reviewed import published an unexpected EEG file")
    if apply_result.state.interpretation.class_map != class_map:
        raise RuntimeError("reviewed import published an unexpected class map")
    if apply_result.state.interpretation.epoch_handoff.get("label_source") != (
        "internal_events"
    ):
        raise RuntimeError("reviewed import omitted the internal-event epoch handoff")


def run_fixture_smoke(fixture: dict[str, object]) -> SmokeResult:
    """Execute one public-fixture training smoke and return structured status."""
    filepath = _public_data_dir() / str(fixture["filename"])
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
    try:
        _apply_reviewed_internal_event_import(service, filepath, fixture)
    except Exception as exc:
        service.close()
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="failed",
            dataset_count=0,
            message=f"reviewed import failed: {type(exc).__name__}: {exc}",
        )

    validation_root = ROOT / "build" / "validation" / "public-cross-source"
    validation_root.mkdir(parents=True, exist_ok=True)
    output_root = Path(
        tempfile.mkdtemp(
            prefix=f"{fixture['name']}-",
            dir=validation_root,
        )
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
        event_ids = [
            str(item) for item in cast(list[object], fixture["epoch_event_ids"])
        ]
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
            SaveDatasetSplitCommand(
                test_ratio=split_ratio,
                val_ratio=split_ratio,
                split_strategy="trial",
                training_mode="individual",
            ),
        )
        _raise_if_failed(dataset_result)

        if not dataset_result.state.dataset.split_spec_saved:
            return SmokeResult(
                name=str(fixture["name"]),
                filename=str(fixture["filename"]),
                source_family=str(fixture["source_family"]),
                status="failed",
                dataset_count=0,
                message="data splitting specification was not saved",
            )

        configure_model = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
        _raise_if_failed(configure_model)
        configure_training = service.execute(
            ConfigureTrainingCommand(
                output_dir=str(output_root),
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

        train_result = service.execute(
            TrainCommand(confirmed=True, interactive=False),
        )
        _raise_if_failed(train_result)

        dataset_count = int(train_result.state.dataset.count or 0)
        if dataset_count <= 0:
            return SmokeResult(
                name=str(fixture["name"]),
                filename=str(fixture["filename"]),
                source_family=str(fixture["source_family"]),
                status="failed",
                dataset_count=0,
                message="training preparation produced no datasets",
            )

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
            QueryStateCommand(query="training_history"),
        )
        _raise_if_failed(history)
        rows = history.diagnostics.get("rows")
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            return SmokeResult(
                name=str(fixture["name"]),
                filename=str(fixture["filename"]),
                source_family=str(fixture["source_family"]),
                status="failed",
                dataset_count=dataset_count,
                message="training history did not include a run record",
            )
        metrics = rows[0].get("metrics")
        train_metrics = metrics.get("train") if isinstance(metrics, dict) else None
        if not isinstance(train_metrics, dict) or (
            RecordKey.LOSS not in train_metrics or RecordKey.ACC not in train_metrics
        ):
            return SmokeResult(
                name=str(fixture["name"]),
                filename=str(fixture["filename"]),
                source_family=str(fixture["source_family"]),
                status="failed",
                dataset_count=dataset_count,
                message="training record missing loss/acc metrics",
            )
        _reload_real_training_artifacts(output_root)

        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="passed",
            dataset_count=dataset_count,
            message="one-epoch CPU smoke and safe artifact reload passed",
            artifacts_reloaded=True,
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
    finally:
        service.close()
        shutil.rmtree(output_root, ignore_errors=True)


def run_fixture_boundary_smoke(fixture: dict[str, object]) -> SmokeResult:
    """Prove import/preprocess support without inventing supervised class semantics."""
    filepath = _public_data_dir() / str(fixture["filename"])
    if not filepath.exists():
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="missing",
            dataset_count=0,
            message=f"fixture not downloaded: {filepath}",
            protocol="import-preprocess-only",
        )

    study = Study()
    service = get_application_service(study)
    try:
        _apply_reviewed_internal_event_import(service, filepath, fixture)
    except Exception as exc:
        service.close()
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="failed",
            dataset_count=0,
            message=f"reviewed import failed: {type(exc).__name__}: {exc}",
            protocol="import-preprocess-only",
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
        event_ids = [
            str(item) for item in cast(list[object], fixture["epoch_event_ids"])
        ]
        epoch_result = service.execute(
            CreateEpochCommand(
                t_min=float(cast(float | int | str, fixture["tmin"])),
                t_max=float(cast(float | int | str, fixture["tmax"])),
                event_ids=event_ids,
            ),
        )
        _require_supervised_epoch_block(
            epoch_result,
            str(fixture["expected_epoch_block"]),
        )
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="passed",
            dataset_count=0,
            message=(
                "load/preprocess smoke passed and supervised epoch creation was "
                "blocked without inventing class semantics; "
                f"{fixture['boundary_reason']}"
            ),
            protocol="import-preprocess-only",
        )
    except Exception as exc:
        return SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="failed",
            dataset_count=0,
            message=f"{type(exc).__name__}: {exc}",
            protocol="import-preprocess-only",
        )
    finally:
        service.close()


def build_snapshot(repo_root: Path = ROOT) -> dict[str, Any]:
    """Run the current public cross-source smoke protocol and summarize it."""
    configured_case_ids = [
        str(fixture["name"])
        for fixture in (*PUBLIC_TRAINING_FIXTURES, *PUBLIC_EPOCH_ONLY_FIXTURES)
    ]
    results = [
        asdict(run_fixture_smoke(fixture)) for fixture in PUBLIC_TRAINING_FIXTURES
    ]
    results.extend(
        asdict(run_fixture_boundary_smoke(fixture))
        for fixture in PUBLIC_EPOCH_ONLY_FIXTURES
    )
    passed = sum(1 for result in results if result["status"] == "passed")
    missing = sum(1 for result in results if result["status"] == "missing")
    failed = sum(1 for result in results if result["status"] == "failed")
    result_case_ids = [str(result["name"]) for result in results]
    duplicate_configured_case_ids = sorted(
        case_id
        for case_id in set(configured_case_ids)
        if configured_case_ids.count(case_id) > 1
    )
    duplicate_result_case_ids = sorted(
        case_id
        for case_id in set(result_case_ids)
        if result_case_ids.count(case_id) > 1
    )
    results_by_id: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        results_by_id.setdefault(str(result["name"]), []).append(result)
    missing_required_case_ids = sorted(
        REQUIRED_PUBLIC_SMOKE_CASE_IDS - results_by_id.keys()
    )
    wrong_protocol_case_ids = sorted(
        case_id
        for case_id, required_protocol in REQUIRED_PUBLIC_SMOKE_PROTOCOLS.items()
        if case_id in results_by_id
        and any(
            result["protocol"] != required_protocol for result in results_by_id[case_id]
        )
    )
    failed_required_case_ids = sorted(
        case_id
        for case_id in REQUIRED_PUBLIC_SMOKE_CASE_IDS
        if case_id in results_by_id
        and any(result["status"] == "failed" for result in results_by_id[case_id])
    )
    missing_fixture_case_ids = sorted(
        case_id
        for case_id in REQUIRED_PUBLIC_SMOKE_CASE_IDS
        if case_id in results_by_id
        and any(result["status"] == "missing" for result in results_by_id[case_id])
    )
    missing_artifact_reload_case_ids = sorted(
        case_id
        for case_id, required_protocol in REQUIRED_PUBLIC_SMOKE_PROTOCOLS.items()
        if required_protocol == "training"
        and case_id in results_by_id
        and any(
            result["status"] == "passed" and not result.get("artifacts_reloaded", False)
            for result in results_by_id[case_id]
        )
    )
    passed_required_case_ids = sorted(
        case_id
        for case_id, required_protocol in REQUIRED_PUBLIC_SMOKE_PROTOCOLS.items()
        if case_id in results_by_id
        and len(results_by_id[case_id]) == 1
        and results_by_id[case_id][0]["status"] == "passed"
        and results_by_id[case_id][0]["protocol"] == required_protocol
        and (
            required_protocol != "training"
            or results_by_id[case_id][0].get("artifacts_reloaded", False)
        )
    )
    all_required_passed = (
        len(passed_required_case_ids) == len(REQUIRED_PUBLIC_SMOKE_CASE_IDS)
        and not missing_required_case_ids
        and not wrong_protocol_case_ids
        and not failed_required_case_ids
        and not missing_fixture_case_ids
        and not missing_artifact_reload_case_ids
        and not duplicate_configured_case_ids
        and not duplicate_result_case_ids
    )
    return {
        "repo_root": str(repo_root),
        "public_data_dir": str(_public_data_dir(repo_root)),
        "results": results,
        "summary": {
            "passed": passed,
            "missing": missing,
            "failed": failed,
            "required_case_count": len(REQUIRED_PUBLIC_SMOKE_CASE_IDS),
            "required_case_ids": sorted(REQUIRED_PUBLIC_SMOKE_CASE_IDS),
            "configured_case_ids": configured_case_ids,
            "result_case_ids": result_case_ids,
            "duplicate_configured_case_ids": duplicate_configured_case_ids,
            "duplicate_result_case_ids": duplicate_result_case_ids,
            "passed_required_case_count": len(passed_required_case_ids),
            "passed_required_case_ids": passed_required_case_ids,
            "missing_required_case_ids": missing_required_case_ids,
            "missing_fixture_case_ids": missing_fixture_case_ids,
            "missing_artifact_reload_case_ids": missing_artifact_reload_case_ids,
            "failed_required_case_ids": failed_required_case_ids,
            "wrong_protocol_case_ids": wrong_protocol_case_ids,
            "all_required_passed": all_required_passed,
            "message": (
                "PhysioNet EDF and BBCI GDF provide class-grounded training smoke. "
                "SCCN EEGLAB and MNE CNT provide import/preprocess evidence and prove "
                "that supervised epoch creation remains blocked without two reviewed "
                "class labels."
            ),
        },
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    """Render the current public training-smoke snapshot in Markdown."""
    lines = [
        "# Public Cross-Source Training Smoke",
        "",
        "| Fixture | Source family | Protocol | Status | Artifacts reloaded | Datasets | Message |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in snapshot["results"]:
        lines.append(
            "| {filename} | {source_family} | {protocol} | {status} | {artifacts_reloaded} | {dataset_count} | {message} |".format(
                artifacts_reloaded=result.get("artifacts_reloaded", False),
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
