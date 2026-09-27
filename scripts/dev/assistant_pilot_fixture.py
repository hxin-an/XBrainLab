"""Build bounded synthetic Pilot initial states through real application Commands.

Fixtures are engineering evidence, not source-diverse EEG acceptance. CPU jobs
remain owned by the real service; the caller must terminate a live training case.
"""

from __future__ import annotations

import hashlib
import math
import time
from pathlib import Path
from typing import Any

import mne
import numpy as np
from PyQt6.QtCore import QCoreApplication, QThread

from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    ApplyMontageCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    SaliencyCommand,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.llm.pipeline_state import STAGE_CONFIG, PipelineStage
from XBrainLab.llm.tools.application_surface import build_agent_tool_policy

_STAGES = {
    "empty",
    "data_loaded",
    "preprocessed",
    "epoch_ready",
    "dataset_ready",
    "training",
    "trained",
}
_CHANNELS = ["C3", "C4", "Cz", "Fz", "REF"]


def _configuration(fixture: dict) -> tuple[dict, dict, float, list[str], list[str]]:
    if not isinstance(fixture, dict):
        raise ValueError("Expected a normalized fixture")
    conditions, metadata = fixture.get("conditions"), fixture.get("metadata")
    if not isinstance(conditions, dict) or not isinstance(metadata, dict):
        raise ValueError("Expected fixture conditions and original metadata")
    stage = conditions.get("stage")
    if (
        stage not in _STAGES
        or metadata.get("workflow_stage") != stage
        or not isinstance(metadata.get("fixture_id"), str)
        or not metadata["fixture_id"].strip()
    ):
        raise ValueError("Unsupported or mismatched fixture stage/identity")
    if conditions.get("session_history") != "fresh_single_turn":
        raise ValueError("Fixture requires fresh single-turn history")
    defaults = []
    sfreq = conditions.get("raw_sampling_hz")
    if sfreq is None:
        sfreq = 256
        defaults.append("raw_sampling_hz")
    if (
        type(sfreq) not in {int, float}
        or not math.isfinite(sfreq)
        or not 64 <= sfreq <= 2048
    ):
        raise ValueError("Invalid bounded fixture sampling rate")
    channels = conditions.get("channels")
    if channels is None:
        channels = list(_CHANNELS)
        defaults.append("channels")
    if (
        not isinstance(channels, list)
        or not 1 <= len(channels) <= 32
        or any(
            not isinstance(name, str) or not name.strip() or len(name) > 15
            for name in channels
        )
        or len(set(channels)) != len(channels)
    ):
        raise ValueError("Invalid fixture channels")
    if (
        conditions.get("channel_types", "all listed channels are EEG")
        != "all listed channels are EEG"
    ):
        raise ValueError("Only reviewed EEG channel fixtures are supported")
    if (
        conditions.get(
            "labels", "reviewed usable event classes; two classes; sufficient trials"
        )
        != "reviewed usable event classes; two classes; sufficient trials"
    ):
        raise ValueError("Unsupported fixture event semantics")
    if not isinstance(conditions.get("required_callable_tool", ""), str):
        raise ValueError("Invalid fixture capability requirement")
    auxiliary = conditions.get("auxiliary_channels", [])
    if auxiliary not in ([], ["EOG1"]) or set(auxiliary) & set(channels):
        raise ValueError("Unsupported auxiliary channel fixture")
    prior = conditions.get("prior_preprocessing")
    if prior is not None and (
        stage != "preprocessed"
        or prior not in ({"notch": 60}, {"bandpass": {"low_freq": 1, "high_freq": 40}})
    ):
        raise ValueError("Unsupported reviewed prior preprocessing fixture")
    return conditions, metadata, float(sfreq), list(channels), defaults


def _write_source(
    path: Path, sfreq: float, channels: list[str], auxiliary: list[str] | None = None
) -> None:
    auxiliary = auxiliary or []
    info = mne.create_info(
        ch_names=channels + auxiliary,
        sfreq=sfreq,
        ch_types=["eeg"] * len(channels) + ["eog"] * len(auxiliary),
    )
    signal = np.random.default_rng(43).normal(
        scale=1e-5, size=(len(channels) + len(auxiliary), round(sfreq * 25))
    )
    raw = mne.io.RawArray(signal, info, verbose=False)
    events = np.array(
        [
            [round(sfreq * second), 0, 1 + index % 2]
            for index, second in enumerate(range(1, 24, 2))
        ],
        dtype=int,
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events, sfreq=sfreq, event_desc={1: "left", 2: "right"}
        )
    )
    raw.save(path, overwrite=False, verbose=False)


def _prepare_fixture(
    study: Study,
    fixture: dict,
    destination: Path,
    *,
    deadline: float,
    running_training_epochs: int,
    jobs: dict,
) -> dict[str, Any]:
    """Return evidence only after the requested real initial state is published.

    The caller owns the fresh Study and destination parent. Failures preserve
    partial files/state for diagnosis; this function never resets or deletes them.
    History isolation belongs to the runner's fresh Assistant conversation.
    """
    conditions, metadata, sfreq, channels, defaults = _configuration(fixture)
    if conditions["stage"] in {"training", "trained"} and channels != _CHANNELS:
        raise ValueError("Job fixtures require the reviewed five-channel layout")
    if not isinstance(study, Study):
        raise ValueError("Fixture preparation requires a real fresh Study")
    service = get_application_service(study)
    before = service.get_state()
    if (
        before.pipeline_stage != "empty"
        or before.raw.count
        or before.preprocessed.available
        or before.epoch.exists
        or before.dataset.split_spec_saved
        or before.dataset.count
        or before.training.has_model
        or before.training.has_training_option
        or before.training.has_trainer
        or before.interpretation.has_scan_result
    ):
        raise ValueError("Fixture preparation requires a fresh empty Study")
    destination = Path(destination).absolute()
    destination.mkdir()  # Never reuse/overwrite a directory, even if it is empty.
    stage = conditions["stage"]
    results: list[dict[str, Any]] = []
    source = None

    def execute(command):
        if time.monotonic() >= deadline:
            raise TimeoutError("Fixture preparation deadline exceeded")
        result = service.execute(command)
        results.append(
            {"command": command.name.value, "ok": result.ok, "message": result.message}
        )
        if result.failed:
            raise RuntimeError(
                f"Fixture command {command.name.value} failed: {result.message}"
            )

    if stage != "empty":
        path = destination / "fixture_raw.fif"
        _write_source(path, sfreq, channels, conditions.get("auxiliary_channels"))
        source = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "synthetic": True,
        }
        for command in (
            ScanSourceCommand(source_path=str(path)),
            PreviewInterpretationCommand(choices={"label_carrier": "embedded_events"}),
            ValidateInterpretationCommand(),
            ApplyInterpretationCommand(confirmed=True),
        ):
            execute(command)
    if stage in {"preprocessed", "epoch_ready", "dataset_ready", "training", "trained"}:
        prior = conditions.get("prior_preprocessing")
        if prior == {"notch": 60}:
            execute(
                PreprocessCommand(operation=PreprocessOperation.NOTCH, notch_freq=60)
            )
        elif prior is not None:
            execute(
                PreprocessCommand(
                    operation=PreprocessOperation.BANDPASS,
                    low_freq=1,
                    high_freq=40,
                )
            )
        else:
            execute(
                PreprocessCommand(
                    operation=PreprocessOperation.NORMALIZE, method="z-score"
                )
            )
    if stage in {"epoch_ready", "dataset_ready", "training", "trained"}:
        execute(CreateEpochCommand(t_min=0.0, t_max=1.5, event_ids=["left", "right"]))
    if stage in {"dataset_ready", "training", "trained"}:
        execute(
            SaveDatasetSplitCommand(
                test_ratio=0.25,
                val_ratio=0.25,
                split_strategy="trial",
                training_mode="individual",
            )
        )
        execute(
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=running_training_epochs if stage == "training" else 1,
                batch_size=2,
                learning_rate=0.001,
                device="cpu",
                seed=43,
                output_dir=str(destination / "training"),
            )
        )
    if stage in {"training", "trained"}:
        execute(
            ApplyMontageCommand(
                channels=channels,
                positions=[
                    (-0.06, 0.0, 0.04),
                    (0.06, 0.0, 0.04),
                    (0.0, 0.0, 0.08),
                    (0.0, 0.06, 0.06),
                    (0.0, -0.08, 0.02),
                ],
                montage_name="pilot-synthetic-5ch",
            )
        )
        execute(SaliencyCommand(method="Gradient", params={}))
        _run_job(
            service,
            TrainCommand(confirmed=True, interactive=True),
            "training",
            jobs,
            results,
            deadline=deadline,
            wait=stage == "trained",
        )
        jobs["training"]["configured_epochs"] = (
            running_training_epochs if stage == "training" else 1
        )
        if stage == "trained" and conditions.get("saliency_results"):
            if (
                conditions["saliency_results"]
                != "already computed and renderable for current selected run"
            ):
                raise ValueError("Unsupported fixture saliency result requirement")
            _run_job(
                service,
                SaliencyCommand(method="Gradient", params={}),
                "saliency",
                jobs,
                results,
                deadline=deadline,
                wait=True,
            )
    service.get_state()
    publication = service.get_view_publication()
    state = publication.state
    if (
        not publication.usable
        or state.pipeline_stage != stage
        or (stage not in {"training", "trained"} and state.training.has_trainer)
        or state.training.is_running != (stage == "training")
    ):
        raise RuntimeError("Fixture did not publish the requested initial state")
    required_tool = conditions.get("required_callable_tool", "")
    policy = build_agent_tool_policy(study, publication=publication)
    tool_enabled = not required_tool or (
        required_tool in policy
        and policy[required_tool].enabled
        and required_tool in STAGE_CONFIG[PipelineStage(stage)]["tools"]
    )
    if not tool_enabled:
        raise RuntimeError(
            "Fixture required tool is not enabled by the real publication"
        )
    evidence: dict[str, Any] = {
        "defaults_used": defaults,
        "sfreq": None,
        "channels": [],
        "event_count": 0,
        "event_ids": {},
    }
    if stage != "empty":
        raw = study.loaded_data_list[0]
        events, event_ids = raw.get_event_list()
        if (
            len(study.loaded_data_list) != 1
            or raw.get_sfreq() != sfreq
            or raw.get_mne().ch_names
            != channels + conditions.get("auxiliary_channels", [])
            or raw.get_mne().get_channel_types()
            != ["eeg"] * len(channels)
            + ["eog"] * len(conditions.get("auxiliary_channels", []))
            or len(events) != 12
            or set(event_ids) != {"left", "right"}
        ):
            raise RuntimeError("Imported fixture signal/event evidence does not match")
        expected_samples = [round(sfreq * second) for second in range(1, 24, 2)]
        expected_codes = [
            event_ids["left"] if index % 2 == 0 else event_ids["right"]
            for index in range(12)
        ]
        if (
            events[:, 0].tolist() != expected_samples
            or events[:, 2].tolist() != expected_codes
        ):
            raise RuntimeError(
                "Imported fixture event timing/class semantics do not match"
            )
        evidence.update(
            sfreq=raw.get_sfreq(),
            channels=list(raw.get_mne().ch_names),
            event_count=len(events),
            event_ids=event_ids,
        )
    if stage in {"epoch_ready", "dataset_ready", "training", "trained"} and (
        state.epoch.epoch_count != 12
        or state.epoch.sfreq != sfreq
        or state.epoch.channel_names != channels
    ):
        raise RuntimeError("Fixture epochs do not match reviewed signal/event evidence")
    if stage in {"dataset_ready", "training", "trained"} and (
        not state.dataset.split_spec_saved
        or not state.training.has_model
        or not state.training.has_training_option
    ):
        raise RuntimeError("Fixture split/model/training configuration is not ready")
    if stage == "trained" and (
        state.training.finished_run_count != 1
        or not state.evaluation.metrics_available
        or state.training.terminal_outcome.state.value != "completed"
    ):
        raise RuntimeError("Fixture training has no verified completed run and metrics")
    if conditions.get("saliency_results") and (
        not state.visualization.saliency_available
        or not state.visualization.channel_positions_available
        or not state.visualization.saliency_coverage
        or not all(
            any(
                method.method == "Gradient" and method.complete
                for method in run.methods
            )
            for run in state.visualization.saliency_coverage
        )
    ):
        raise RuntimeError(
            "Fixture saliency lacks complete renderable backend coverage"
        )
    return {
        "schema": "xbrainlab.assistant_pilot_fixture.v1",
        "fixture_id": metadata["fixture_id"],
        "stage": stage,
        "destination": str(destination),
        "source": source,
        "commands": results,
        "publication_generation": publication.generation,
        "state": state.to_dict(),
        "evidence": evidence,
        "required_tool_enabled": tool_enabled,
        "jobs": jobs,
    }


def _pump_events() -> None:
    app = QCoreApplication.instance()
    if app is not None and QThread.currentThread() is app.thread():
        app.processEvents()
    time.sleep(0.01)


def _run_job(
    service,
    command,
    name: str,
    jobs: dict,
    commands: list,
    *,
    deadline: float,
    wait: bool,
) -> None:
    if time.monotonic() >= deadline:
        raise TimeoutError("Fixture preparation deadline exceeded")
    started = time.monotonic()
    operation = service.begin_owned_operation(command)
    jobs[name] = {
        "operation_id": operation.operation_id,
        "phase": operation.phase.value,
        "elapsed_seconds": 0.0,
        "device": "cpu",
    }
    result = service.execute(command, operation_id=operation.operation_id)
    commands.append(
        {"command": command.name.value, "ok": result.ok, "message": result.message}
    )
    if result.failed:
        raise RuntimeError(f"Fixture {name} command failed: {result.message}")
    while wait:
        operation = service.get_owned_operation(operation.operation_id)
        if operation.phase.terminal:
            if operation.phase.value != "completed":
                raise RuntimeError(
                    f"Fixture {name} terminated {operation.phase.value}: {operation.message}"
                )
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Fixture {name} deadline exceeded")
        _pump_events()
    operation = service.get_owned_operation(operation.operation_id)
    jobs[name].update(
        phase=operation.phase.value, elapsed_seconds=time.monotonic() - started
    )


def prepare_fixture(
    study: Study,
    fixture: dict,
    destination: Path,
    *,
    timeout_seconds: float = 60.0,
    running_training_epochs: int = 1,
) -> dict[str, Any]:
    """Prepare real state, retaining caller ownership of live training on success.

    The running-case epoch count is explicit (default one, not a promise of
    120-second liveness). The runner checks for drift and stops the operation at
    case completion/timeout. Preparation failures cancel only jobs started here.
    """
    if (
        type(timeout_seconds) not in {int, float}
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 120
        or type(running_training_epochs) is not int
        or not 1 <= running_training_epochs <= 10_000
    ):
        raise ValueError("Invalid bounded fixture job budget")
    jobs: dict[str, dict] = {}
    try:
        return _prepare_fixture(
            study,
            fixture,
            destination,
            deadline=time.monotonic() + timeout_seconds,
            running_training_epochs=running_training_epochs,
            jobs=jobs,
        )
    except BaseException:
        if jobs:
            service = get_application_service(study)
            for job in jobs.values():
                operation_id = job["operation_id"]
                if not service.get_owned_operation(operation_id).phase.terminal:
                    service.cancel_owned_operation(operation_id)
            deadline = time.monotonic() + 10.0
            while any(
                not service.get_owned_operation(job["operation_id"]).phase.terminal
                for job in jobs.values()
            ):
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Fixture owned jobs did not stop within cleanup budget"
                    ) from None
                _pump_events()
        raise
