"""Deterministic training-ready fixture shared by UI evidence scripts."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from scripts.dev.chatpanel_training_fixture import write_training_ready_raw_fif
from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    get_application_service,
)

_SOURCE_DIR = Path(tempfile.gettempdir()) / "xbrainlab_training_evidence"
_SOURCE_PATH = _SOURCE_DIR / "training_ready_raw.fif"


def write_synthetic_training_raw_fif() -> Path:
    """Write a deterministic EEG fixture with epoch duration suitable for EEGNet."""
    if _SOURCE_DIR.exists():
        shutil.rmtree(_SOURCE_DIR)
    return write_training_ready_raw_fif(_SOURCE_PATH)


def prepare_training_dataset_ready_state(
    study: Any,
    source_path: Path,
    training_output_dir: Path,
) -> dict[str, Any]:
    """Prepare dataset-ready state with epoch duration suitable for EEGNet."""
    service = get_application_service(study)
    commands = [
        ScanSourceCommand(source_path=str(source_path)),
        PreviewInterpretationCommand(choices={"label_carrier": "embedded_events"}),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
        PreprocessCommand(
            operation=PreprocessOperation.STANDARD,
            low_freq=4.0,
            high_freq=40.0,
            method="z-score",
        ),
        CreateEpochCommand(t_min=0.0, t_max=1.5, event_ids=["left", "right"]),
        SaveDatasetSplitCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
        ConfigureTrainingCommand(
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
            output_dir=str(training_output_dir),
        ),
    ]
    results: list[dict[str, Any]] = []
    for command in commands:
        result = service.execute(command)
        results.append(
            {
                "command": command.name.value,
                "ok": result.ok,
                "message": result.message,
                "error_type": result.error_type.value if result.failed else None,
                "diagnostics": result.diagnostics,
            },
        )
        if result.failed:
            break
    return {
        "ok": bool(results) and all(item["ok"] for item in results),
        "commands": results,
        "state": service.get_state().to_dict(),
    }
