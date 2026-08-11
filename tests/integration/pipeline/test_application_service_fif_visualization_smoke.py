"""Real command-spine smoke from FIF import through visualization readiness.

This test deliberately proves the ApplicationService workflow and persisted
training artifacts. It does not claim scientific model quality or arbitrary
FIF compatibility.
"""

from __future__ import annotations

from pathlib import Path

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
)


def _write_command_spine_fif(target: Path) -> None:
    sfreq = 128.0
    channel_names = ["C3", "C4", "Cz", "Pz"]
    info = mne.create_info(channel_names, sfreq=sfreq, ch_types="eeg")
    samples = int(sfreq * 26)
    rng = np.random.default_rng(20260730)
    data = rng.standard_normal((len(channel_names), samples))
    raw = mne.io.RawArray(data, info, verbose=False)
    events = np.asarray(
        [
            [second * int(sfreq), 0, 1 if index % 2 == 0 else 2]
            for index, second in enumerate(range(1, 25, 2))
        ],
        dtype=int,
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc={1: "left", 2: "right"},
        )
    )
    raw.save(target, overwrite=True, verbose=False)


def test_application_service_fif_reaches_persisted_visualization_readiness(
    tmp_path: Path,
) -> None:
    """Commands, real EEGNet execution and artifact writes reach visualization."""
    fif_path = tmp_path / "command-spine_raw.fif"
    output_root = tmp_path / "training-output"
    _write_command_spine_fif(fif_path)
    service = ApplicationService()

    try:
        scanned = service.execute(
            ScanSourceCommand(source_path=str(fif_path), source_hint="file")
        )
        previewed = service.execute(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(fif_path)],
                    "label_carrier": "embedded_events",
                    "class_map": {"left": "left", "right": "right"},
                    "internal_event_selection": {
                        "label_event_codes": ["left", "right"],
                        "class_map": {"left": "left", "right": "right"},
                    },
                }
            )
        )
        validated = service.execute(ValidateInterpretationCommand())
        imported = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert scanned.ok, scanned.message
        assert previewed.ok, previewed.message
        assert validated.ok, validated.message
        assert imported.ok, imported.message
        assert imported.state.raw.files == [fif_path.name]
        assert imported.state.interpretation.epoch_handoff["supervised_ready"] is True

        normalized = service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z-score",
            )
        )
        epoched = service.execute(
            CreateEpochCommand(
                t_min=0.0,
                t_max=1.3,
                event_ids=["left", "right"],
            )
        )
        split = service.execute(
            SaveDatasetSplitCommand(
                test_ratio=0.25,
                val_ratio=0.25,
                split_strategy="trial",
                training_mode="individual",
            )
        )
        configured = service.execute(
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=1,
                batch_size=2,
                learning_rate=0.001,
                device="cpu",
                save_checkpoints_every=0,
                output_dir=str(output_root),
                evaluation_option="val_acc",
            )
        )
        trained = service.execute(
            TrainCommand(confirmed=True, interactive=False),
        )
        evaluated = service.execute(EvaluateCommand())
        visualized = service.execute(VisualizeCommand(view="summary"))

        assert normalized.ok, normalized.message
        assert epoched.ok, epoched.message
        assert epoched.state.epoch.epoch_count == 12
        assert split.ok, split.message
        assert split.state.dataset.split_spec_saved is True
        assert split.state.dataset.available is False
        assert configured.ok, configured.message
        assert trained.ok, trained.message
        assert trained.diagnostics["split_preparation"]["split_audit"]["ok"] is True
        assert trained.state.dataset.available is True
        assert trained.state.training.finished_run_count == 1
        assert evaluated.ok, evaluated.message
        assert evaluated.diagnostics["available"] is True
        assert evaluated.diagnostics["finished_run_count"] == 1
        assert visualized.ok, visualized.message
        assert visualized.diagnostics["available"] is True
        assert visualized.diagnostics["trainer_count"] == 1
        assert {"confusion matrix", "metrics", "saliency setup"} <= set(
            visualized.diagnostics["available_views"]
        )

        persisted_files = [path for path in output_root.rglob("*") if path.is_file()]
        assert persisted_files
        assert any(path.name == "record" for path in persisted_files)
        assert any(path.name.startswith("Epoch-1-model") for path in persisted_files)
    finally:
        assert service.wait_for_background_tasks(timeout=30.0)
        service.close()
