"""Handoff gate for continuous workflows across distinct real EEG sources."""

from __future__ import annotations

from pathlib import Path

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    GenerateDatasetCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.training.record import RecordKey

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "data"
GRAZ_GDF = (FIXTURE_ROOT / "A01T.gdf").resolve()
GRAZ_LABELS = (FIXTURE_ROOT / "label" / "A01T.mat").resolve()
OTHER_GRAZ_LABELS = [
    (FIXTURE_ROOT / "label" / f"{stem}.mat").resolve() for stem in ("A02T", "A03T")
]
PUBLIC_BIDS_ROOT = (FIXTURE_ROOT / "public" / "mne-bids-tiny-eeg").resolve()
PUBLIC_BIDS_EEG = (
    PUBLIC_BIDS_ROOT
    / "sub-01"
    / "ses-eeg"
    / "eeg"
    / "sub-01_ses-eeg_task-rest_eeg.vhdr"
)
PUBLIC_BIDS_EVENTS = PUBLIC_BIDS_EEG.with_name("sub-01_ses-eeg_task-rest_events.tsv")
PHYSIONET_MOTOR_EDF = (
    FIXTURE_ROOT / "public" / "physionet-eegmmidb-S008R04.edf"
).resolve()

GRAZ_CLASS_NAMES = {
    "1": "left hand",
    "2": "right hand",
    "3": "feet",
    "4": "tongue",
}
GRAZ_TARGET_EVENTS = ["769", "770", "771", "772"]


def _class_value_decisions(
    class_names: dict[str, str],
) -> dict[str, dict[str, object]]:
    return {
        raw_value: {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": class_name,
        }
        for raw_value, class_name in class_names.items()
    }


def _close_service(service: ApplicationService) -> None:
    assert service.wait_for_background_tasks(timeout=30.0)
    service.close()


def test_graz_external_labels_reach_real_training_through_interpretation_spine(
    tmp_path: Path,
) -> None:
    """GDF plus external MAT labels must reach a real one-epoch EEGNet run."""
    if not GRAZ_GDF.exists() or not GRAZ_LABELS.exists():
        pytest.skip("Checked-in Graz GDF/MAT fixtures are unavailable.")

    service = ApplicationService()
    choices = {
        "selected_eeg_files": [str(GRAZ_GDF)],
        "excluded_label_carriers": [str(path) for path in OTHER_GRAZ_LABELS],
        "label_carrier_choices": {
            str(GRAZ_LABELS): {
                "label_field": "classlabel",
                "target_event_codes": GRAZ_TARGET_EVENTS,
                "placement_method": "eeg_event",
                "time_model": "trial_order",
                "granularity": "trial",
                "value_decisions": _class_value_decisions(GRAZ_CLASS_NAMES),
            }
        },
    }

    try:
        scan = service.execute(
            ScanSourceCommand(
                source_path=str(FIXTURE_ROOT),
                source_hint="folder",
                label_sources=[str(GRAZ_LABELS)],
            )
        )
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        validation = service.execute(ValidateInterpretationCommand())
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert scan.ok, scan.message
        scan_payload = scan.diagnostics["scan_result"]
        assert scan_payload["source_path"] == str(FIXTURE_ROOT.resolve())
        assert len(scan_payload["eeg_files"]) > len(choices["selected_eeg_files"])
        assert preview.ok, preview.message
        candidate = preview.diagnostics["candidate"]
        assert candidate["selected_eeg_files"] == [str(GRAZ_GDF)]
        assert [
            carrier["path"]
            for carrier in preview.diagnostics["preview"]["label_carrier_preview"]
        ] == [str(GRAZ_LABELS)]
        assert validation.ok, validation.message
        validation_decision = validation.diagnostics["validation_decision"]
        assert validation_decision["decision"] == "needs_confirmation"
        assert validation_decision["blocked_reasons"] == []
        assert validation_decision["required_confirmations"]
        assert applied.ok, applied.message
        assert applied.diagnostics["label_apply"]["mode"] == "sequence"
        assert applied.state.raw.files == [GRAZ_GDF.name]
        assert applied.state.interpretation.label_sources == [str(GRAZ_LABELS)]
        assert applied.state.interpretation.class_map == GRAZ_CLASS_NAMES
        handoff = applied.state.interpretation.epoch_handoff
        assert handoff["label_source"] == "loaded_label_files"
        assert handoff["default_epoch_events"] == sorted(
            GRAZ_CLASS_NAMES.values(),
            key=str.casefold,
        )

        filtered = service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS,
                low_freq=4,
                high_freq=38,
            )
        )
        epoch = service.execute(
            CreateEpochCommand(
                t_min=-0.2,
                t_max=1.0,
                event_ids=list(GRAZ_CLASS_NAMES.values()),
            )
        )
        generated = service.execute(
            GenerateDatasetCommand(
                test_ratio=0.2,
                val_ratio=0.2,
                split_strategy="trial",
                training_mode="individual",
            )
        )

        assert filtered.ok, filtered.message
        assert epoch.ok, epoch.message
        assert epoch.state.epoch.epoch_count == 273
        assert generated.ok, generated.message
        assert generated.diagnostics["split_audit"]["ok"] is True
        assert generated.state.dataset.available is True

        model = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
        options = service.execute(
            ConfigureTrainingCommand(
                output_dir=str(tmp_path / "graz-handoff-training"),
                device="cpu",
                epoch=1,
                batch_size=64,
                learning_rate=0.001,
                save_checkpoints_every=0,
                evaluation_option="val_acc",
            )
        )
        train_capability = service.get_capabilities().get(CommandName.TRAIN)

        assert model.ok, model.message
        assert options.ok, options.message
        assert train_capability.available is True

        trained = service.execute(
            TrainCommand(confirmed=True, interactive=False),
        )
        history = service.execute(
            QueryStateCommand(query="training_history"),
        )

        assert trained.ok, trained.message
        assert trained.state.training.run_count == 1
        assert trained.state.training.finished_run_count == 1
        assert history.ok, history.message
        assert history.diagnostics["row_count"] == 1
        train_metrics = history.diagnostics["rows"][0]["metrics"]["train"]
        assert RecordKey.LOSS in train_metrics
        assert RecordKey.ACC in train_metrics
    finally:
        _close_service(service)


@pytest.mark.optional_public_fixture
def test_public_bids_reaches_epoch_and_dataset_generation_readiness() -> None:
    """A different public source must materialize BIDS timing into real epochs."""
    if not PUBLIC_BIDS_EEG.exists() or not PUBLIC_BIDS_EVENTS.exists():
        pytest.skip(
            "Public MNE-BIDS fixture is unavailable; run the fixture fetcher first."
        )

    service = ApplicationService()
    choices = {
        "selected_eeg_files": [str(PUBLIC_BIDS_EEG)],
        "label_carrier_choices": {
            str(PUBLIC_BIDS_EVENTS): {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "value_decisions": _class_value_decisions(
                    {
                        "show_stimulus": "show_stimulus",
                        "start_experiment": "start_experiment",
                    }
                ),
            }
        },
    }

    try:
        scan = service.execute(
            ScanSourceCommand(
                source_path=str(PUBLIC_BIDS_ROOT),
                source_hint="bids",
            )
        )
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        validation = service.execute(ValidateInterpretationCommand())
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert scan.ok, scan.message
        scan_payload = scan.diagnostics["scan_result"]
        assert scan_payload["source_path"] == str(PUBLIC_BIDS_ROOT)
        assert preview.ok, preview.message
        candidate = preview.diagnostics["candidate"]
        assert candidate["selected_eeg_files"] == [str(PUBLIC_BIDS_EEG)]
        assert preview.diagnostics["preview"]["bids"]["scan_location"] == str(
            PUBLIC_BIDS_ROOT
        )
        assert preview.diagnostics["preview"]["bids"]["selected_scope"][
            "eeg_files"
        ] == [str(PUBLIC_BIDS_EEG)]
        assert validation.ok, validation.message
        assert validation.diagnostics["validation_decision"]["decision"] == "safe"
        assert applied.ok, applied.message

        handoff = applied.state.interpretation.epoch_handoff
        assert handoff["label_source"] == "bids_events"
        assert handoff["label_carrier_plan"][0]["selected_anchor"] == "onset"
        assert handoff["label_carrier_plan"][0]["selected_duration_field"] == (
            "duration"
        )
        assert handoff["label_carrier_plan"][0]["selected_target_file"] == str(
            PUBLIC_BIDS_EEG
        )

        normalized = service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z-score",
            )
        )
        epoch = service.execute(
            CreateEpochCommand(
                t_min=0.0,
                t_max=0.3,
            )
        )

        assert normalized.ok, normalized.message
        assert epoch.ok, epoch.message
        assert epoch.state.epoch.available is True
        assert epoch.state.epoch.epoch_count == 2
        assert set(epoch.state.epoch.event_ids) == {
            "show_stimulus",
            "start_experiment",
        }
        dataset_capability = service.get_capabilities().get(
            CommandName.GENERATE_DATASET
        )
        train_capability = service.get_capabilities().get(CommandName.TRAIN)
        assert dataset_capability.available is True
        assert train_capability.available is False
        assert "Generate datasets before training." in train_capability.reasons
    finally:
        _close_service(service)


@pytest.mark.optional_public_fixture
def test_physionet_internal_events_reach_real_training_through_interpretation_spine(
    tmp_path: Path,
) -> None:
    """A second public source must reach training through reviewed internal events."""
    if not PHYSIONET_MOTOR_EDF.exists():
        pytest.skip(
            "Public PhysioNet EEGMMI fixture is unavailable; run the fixture fetcher "
            "first."
        )

    class_map = {"T1": "left fist", "T2": "right fist"}
    service = ApplicationService()
    choices = {
        "selected_eeg_files": [str(PHYSIONET_MOTOR_EDF)],
        "label_carrier": "embedded_events",
        "class_map": class_map,
        "internal_event_selection": {
            "label_event_codes": list(class_map),
            "class_map": class_map,
        },
        "run_event_mappings": {
            PHYSIONET_MOTOR_EDF.name: class_map,
        },
    }

    try:
        scan = service.execute(
            ScanSourceCommand(
                source_path=str(PHYSIONET_MOTOR_EDF),
                source_hint="file",
            )
        )
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        validation = service.execute(ValidateInterpretationCommand())
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert scan.ok, scan.message
        scan_payload = scan.diagnostics["scan_result"]
        assert scan_payload["source_path"] == str(PHYSIONET_MOTOR_EDF)
        assert scan_payload["eeg_files"] == [str(PHYSIONET_MOTOR_EDF)]
        assert preview.ok, preview.message
        candidate = preview.diagnostics["candidate"]
        assert candidate["selected_eeg_files"] == [str(PHYSIONET_MOTOR_EDF)]
        assert validation.ok, validation.message
        validation_decision = validation.diagnostics["validation_decision"]
        assert validation_decision["blocked_reasons"] == []
        assert applied.ok, applied.message
        assert applied.state.raw.files == [PHYSIONET_MOTOR_EDF.name]
        assert applied.state.interpretation.label_sources == []
        assert applied.state.interpretation.class_map == class_map
        assert applied.state.interpretation.run_event_mappings == {
            PHYSIONET_MOTOR_EDF.name: class_map,
        }
        assert applied.state.interpretation.epoch_handoff["label_source"] == (
            "internal_events"
        )

        filtered = service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS,
                low_freq=4,
                high_freq=38,
            )
        )
        epoch = service.execute(
            CreateEpochCommand(
                t_min=0.0,
                t_max=2.0,
                event_ids=list(class_map),
            )
        )
        generated = service.execute(
            GenerateDatasetCommand(
                test_ratio=0.2,
                val_ratio=0.2,
                split_strategy="trial",
                training_mode="individual",
            )
        )

        assert filtered.ok, filtered.message
        assert epoch.ok, epoch.message
        assert epoch.state.epoch.epoch_count == 15
        assert set(epoch.state.epoch.event_ids) == set(class_map)
        assert generated.ok, generated.message
        assert generated.diagnostics["split_audit"]["ok"] is True
        assert generated.state.dataset.available is True

        model = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
        options = service.execute(
            ConfigureTrainingCommand(
                output_dir=str(tmp_path / "physionet-handoff-training"),
                device="cpu",
                epoch=1,
                batch_size=4,
                learning_rate=0.001,
                save_checkpoints_every=0,
                evaluation_option="val_acc",
            )
        )
        train_capability = service.get_capabilities().get(CommandName.TRAIN)

        assert model.ok, model.message
        assert options.ok, options.message
        assert train_capability.available is True

        trained = service.execute(TrainCommand(confirmed=True, interactive=False))
        history = service.execute(QueryStateCommand(query="training_history"))

        assert trained.ok, trained.message
        assert trained.state.training.run_count == 1
        assert trained.state.training.finished_run_count == 1
        assert history.ok, history.message
        assert history.diagnostics["row_count"] == 1
        train_metrics = history.diagnostics["rows"][0]["metrics"]["train"]
        assert RecordKey.LOSS in train_metrics
        assert RecordKey.ACC in train_metrics
    finally:
        _close_service(service)
