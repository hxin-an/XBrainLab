"""Real backend workflow tests for the ApplicationService command layer."""

from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from typing import Any

import mne
import numpy as np
import pytest
from scipy.io import savemat

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ApplyMontageCommand,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    DatasetGenerationMode,
    DatasetSplitContextRequest,
    ErrorType,
    EvaluateCommand,
    GenerateDatasetCommand,
    ImportRecipe,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
    ReviewInterpretationCommand,
    SaliencyCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
    data_interpretation_bids,
    data_interpretation_label_carriers,
    data_interpretation_metadata,
    resource_guard,
)
from XBrainLab.backend.application import data_interpretation_service as service_module
from XBrainLab.backend.load_data import label_loader
from XBrainLab.backend.training import Trainer

EXPECTED_SYNTHETIC_SPLIT_25_25_SUMMARY = {
    "count": 1,
    "train_count": 7,
    "val_count": 2,
    "test_count": 3,
    "audit": {"ok": True, "dataset_count": 1, "issues": []},
}

EXPECTED_SYNTHETIC_SPLIT_20_20_SUMMARY = {
    "count": 1,
    "train_count": 8,
    "val_count": 2,
    "test_count": 2,
    "audit": {"ok": True, "dataset_count": 1, "issues": []},
}


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


def _write_synthetic_raw_fif(tmp_path):
    sfreq = 128
    n_channels = 4
    duration = 26
    ch_names = [f"EEG{i}" for i in range(n_channels)]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    data = np.random.default_rng(42).normal(
        size=(n_channels, sfreq * duration),
    )
    raw = mne.io.RawArray(data, info)
    # Keep the generic workflow fixture non-overlapping for its 1.3 s epoch
    # window. Temporal-overlap behavior has a dedicated leakage integration test.
    events = np.array(
        [
            [second * sfreq, 0, 1 if index % 2 == 0 else 2]
            for index, second in enumerate(range(1, 25, 2))
        ],
    )
    annotations = mne.annotations_from_events(
        events,
        sfreq=sfreq,
        event_desc={1: "left", 2: "right"},
    )
    raw.set_annotations(annotations)

    path = tmp_path / "synthetic_raw.fif"
    raw.save(path, overwrite=True)
    return path


def _write_bids_eeg_motor_imagery_fixture(tmp_path):
    bids_root = tmp_path / "bids_mi"
    eeg_dir = bids_root / "sub-01" / "ses-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text(
        '{"Name":"Synthetic BIDS EEG motor imagery","BIDSVersion":"1.10.0"}',
        encoding="utf-8",
    )
    (bids_root / "participants.tsv").write_text(
        "participant_id\tsex\tage\nsub-01\tF\t21\n",
        encoding="utf-8",
    )

    sfreq = 128
    info = mne.create_info(
        ch_names=["C3", "C4", "Cz", "Pz"],
        sfreq=sfreq,
        ch_types="eeg",
    )
    data = np.random.default_rng(314).normal(size=(4, sfreq * 6))
    raw = mne.io.RawArray(data, info)
    eeg_path = eeg_dir / "sub-01_ses-01_task-mi_run-1_eeg.fif"
    raw.save(eeg_path, overwrite=True)

    events_path = eeg_dir / "sub-01_ses-01_task-mi_run-1_events.tsv"
    events_path.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        "0.50\t0.40\tleft\t769\n"
        "1.20\t0.40\tright\t770\n"
        "1.90\t0.40\tleft\t769\n"
        "2.60\t0.40\tright\t770\n"
        "3.30\t0.40\tleft\t769\n"
        "4.00\t0.40\tright\t770\n",
        encoding="utf-8",
    )
    events_path.with_suffix(".json").write_text(
        '{"trial_type":{"LongName":"Motor imagery class",'
        '"Levels":{"left":"Left hand","right":"Right hand"}},'
        '"value":{"Description":"Original event code"}}',
        encoding="utf-8",
    )
    channels_path = eeg_dir / "sub-01_ses-01_task-mi_run-1_channels.tsv"
    channels_path.write_text(
        "name\ttype\tunits\tstatus\n"
        "C3\tEEG\tuV\tgood\n"
        "C4\tEEG\tuV\tgood\n"
        "Cz\tEEG\tuV\tgood\n"
        "Pz\tEEG\tuV\tbad\n",
        encoding="utf-8",
    )
    return bids_root, eeg_path, events_path, channels_path


def _write_resource_preflight_bids_fixture(tmp_path):
    bids_root = tmp_path / "resource_bids"
    eeg_dir = bids_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text(
        '{"Name":"Resource preflight","BIDSVersion":"1.10.0"}',
        encoding="utf-8",
    )
    participants = bids_root / "participants.tsv"
    participants.write_text("participant_id\nsub-01\n", encoding="utf-8")
    eeg_path = eeg_dir / "sub-01_task-mi_eeg.fif"
    events_path = eeg_dir / "sub-01_task-mi_events.tsv"
    channels = eeg_dir / "sub-01_task-mi_channels.tsv"
    eeg_path.write_bytes(b"header only")
    events_path.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    channels.write_text("name\tstatus\nC3\tgood\n", encoding="utf-8")
    return bids_root, eeg_path, events_path, participants, channels


def test_public_scan_is_shallow_at_one_byte_and_preview_materializes_after_admission(
    tmp_path,
    monkeypatch,
):
    bids_root, _eeg_path, events_path, _participants, _channels = (
        _write_resource_preflight_bids_fixture(tmp_path)
    )
    external_mat = tmp_path / "external-labels.mat"
    savemat(external_mat, {"classlabel": np.array([1, 2])})
    service = ApplicationService()
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 1)
    tsv_reads = []
    event_reads = []
    loadmat_calls = 0
    real_read_tsv = data_interpretation_metadata._read_tsv_rows
    real_read_events = data_interpretation_bids._read_events_rows
    real_loadmat = data_interpretation_label_carriers.loadmat

    def _observed_read_tsv(path):
        tsv_reads.append(path)
        return real_read_tsv(path)

    def _observed_read_events(path):
        event_reads.append(path)
        return real_read_events(path)

    def _observed_loadmat(*args, **kwargs):
        nonlocal loadmat_calls
        loadmat_calls += 1
        return real_loadmat(*args, **kwargs)

    monkeypatch.setattr(
        data_interpretation_metadata, "_read_tsv_rows", _observed_read_tsv
    )
    monkeypatch.setattr(
        data_interpretation_bids, "_read_events_rows", _observed_read_events
    )
    monkeypatch.setattr(
        data_interpretation_label_carriers, "loadmat", _observed_loadmat
    )

    scan_result = service.execute(
        ScanSourceCommand(
            source_path=str(bids_root),
            source_hint="bids",
            label_sources=[str(external_mat)],
        ),
    )

    assert scan_result.ok is True
    shallow = scan_result.diagnostics["scan_result"]
    assert shallow["bids"]["metadata_materialized"] is False
    assert shallow["bids"]["participants"] == []
    assert shallow["bids"]["events_files"] == [str(events_path.resolve())]
    assert str(external_mat.resolve()) in shallow["label_carriers"]
    assert scan_result.state.interpretation.has_scan_result is True
    assert scan_result.state.interpretation.has_preview is False
    assert tsv_reads == []
    assert event_reads == []
    assert loadmat_calls == 0

    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 1_000_000_000)
    preview_result = service.execute(
        PreviewInterpretationCommand(
            choices={"excluded_label_carriers": [str(external_mat.resolve())]},
        ),
    )

    assert preview_result.ok is True
    assert (
        preview_result.diagnostics["preview"]["bids"]["metadata_materialized"] is True
    )
    assert preview_result.diagnostics["preview"]["bids"]["participant_count"] == 1
    assert tsv_reads
    assert event_reads
    assert loadmat_calls == 0


@pytest.mark.parametrize("workflow", ["preview", "review"])
def test_bids_description_payload_is_parsed_only_after_resource_admission(
    tmp_path,
    monkeypatch,
    workflow,
):
    bids_root, _eeg_path, _events_path, _participants, _channels = (
        _write_resource_preflight_bids_fixture(tmp_path)
    )
    description = (bids_root / "dataset_description.json").resolve()
    service = ApplicationService()
    ordering = []
    real_path_open = Path.open
    real_json_loads = data_interpretation_metadata.json.loads
    real_preflight = service_module.check_import_resource_preflight

    class _ObservedReader:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, *args):
            return self._handle.__exit__(*args)

        def read(self, *args, **kwargs):
            ordering.append("description:read")
            return self._handle.read(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._handle, name)

    def _observed_open(path: Path, *args, **kwargs):
        handle = real_path_open(path, *args, **kwargs)
        mode = str(args[0] if args else kwargs.get("mode", "r"))
        if path.resolve() == description and "r" in mode:
            ordering.append("description:open")
            return _ObservedReader(handle)
        return handle

    def _observed_loads(payload, *args, **kwargs):
        payload_text = (
            payload.decode("utf-8", errors="ignore")
            if isinstance(payload, bytes)
            else str(payload)
        )
        if "Resource preflight" in payload_text:
            ordering.append("description:json.loads")
        return real_json_loads(payload, *args, **kwargs)

    def _observed_preflight(paths):
        ordering.append("resource:admission")
        return real_preflight(paths)

    monkeypatch.setattr(Path, "open", _observed_open)
    monkeypatch.setattr(data_interpretation_metadata.json, "loads", _observed_loads)
    monkeypatch.setattr(
        service_module, "check_import_resource_preflight", _observed_preflight
    )
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 1_000_000_000)

    if workflow == "preview":
        scan_result = service.execute(
            ScanSourceCommand(source_path=str(bids_root), source_hint="bids"),
        )
        assert scan_result.ok is True
        assert ordering[0] == "resource:admission"
        assert "description:open" in ordering[1:]
        assert "description:read" in ordering[1:]
        assert "description:json.loads" not in ordering
        ordering.clear()
        result = service.execute(PreviewInterpretationCommand())
    else:
        result = service.execute(
            ReviewInterpretationCommand(
                source_path=str(bids_root),
                source_hint="bids",
            ),
        )

    assert result.ok is True
    cache_reused = bool(
        result.diagnostics["resource_preflight"].get("admission_cache_reused")
    )
    if workflow == "preview":
        assert cache_reused is True
        assert "resource:admission" not in ordering
    else:
        assert cache_reused is False
        assert ordering[0] == "resource:admission"
    assert ordering.count("description:json.loads") == 1
    assert "description:open" in ordering
    assert "description:read" in ordering
    assert ordering.index("description:json.loads") > ordering.index("description:read")


@pytest.mark.parametrize("suffix", [".mat", ".csv"])
def test_application_service_resource_block_precedes_real_label_loader_and_mutation(
    tmp_path,
    monkeypatch,
    suffix,
):
    eeg_path = _write_synthetic_raw_fif(tmp_path)
    label_path = tmp_path / f"synthetic_raw{suffix}"
    if suffix == ".mat":
        savemat(label_path, {"classlabel": np.tile(np.array([1, 2]), 6)})
    else:
        label_path.write_text(
            "onset,classlabel\n0.5,left\n1.5,right\n",
            encoding="utf-8",
        )
    service = ApplicationService()
    monkeypatch.setattr(
        resource_guard,
        "available_ram_bytes",
        lambda: 1_000_000_000,
    )
    initial_load = service.execute(LoadDataCommand(paths=[str(eeg_path)]))
    assert initial_load.ok is True
    raw_before = initial_load.state.raw
    dataset_before = initial_load.state.dataset

    choices = {}
    if suffix == ".mat":
        choices = {
            "selected_eeg_files": [str(eeg_path)],
            "label_carrier_choices": {
                str(label_path): {
                    "label_field": "classlabel",
                    "target_event_codes": ["left", "right"],
                    "placement_method": "eeg_event",
                    "time_model": "trial_order",
                    "granularity": "trial",
                    "value_decisions": _class_value_decisions(
                        {"1": "left", "2": "right"}
                    ),
                }
            },
        }
    review = service.execute(
        ReviewInterpretationCommand(
            source_path=str(eeg_path),
            label_sources=[str(label_path)],
            choices=choices,
        ),
    )

    assert review.ok is True
    assert review.state.raw == raw_before
    assert review.state.dataset == dataset_before
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 1_000_000)
    loadmat_calls = 0
    read_csv_calls = 0
    real_loadmat = data_interpretation_label_carriers.loadmat
    real_read_csv = label_loader.pd.read_csv

    def _observed_loadmat(*args, **kwargs):
        nonlocal loadmat_calls
        loadmat_calls += 1
        return real_loadmat(*args, **kwargs)

    def _observed_read_csv(*args, **kwargs):
        nonlocal read_csv_calls
        read_csv_calls += 1
        return real_read_csv(*args, **kwargs)

    monkeypatch.setattr(
        data_interpretation_label_carriers, "loadmat", _observed_loadmat
    )
    monkeypatch.setattr(label_loader.pd, "read_csv", _observed_read_csv)

    result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert result.failed is True
    assert result.diagnostics["resource_preflight"]["risk_level"] == "blocking"
    assert loadmat_calls == 0
    assert read_csv_calls == 0
    assert result.state.raw == raw_before
    assert result.state.dataset == dataset_before
    assert result.state.interpretation.has_scan_result is True
    assert result.state.interpretation.has_applied_interpretation is False


@pytest.mark.parametrize(
    ("command_kind", "large_metadata_kind"),
    [("review", "participants"), ("reload", "channels")],
)
def test_application_service_bids_scan_metadata_is_admitted_in_source_order(
    tmp_path,
    monkeypatch,
    command_kind,
    large_metadata_kind,
):
    bids_root, eeg_path, events_path, participants, channels = (
        _write_resource_preflight_bids_fixture(tmp_path)
    )
    large_path = participants if large_metadata_kind == "participants" else channels
    with large_path.open("ab") as handle:
        handle.truncate(2_000_000)
    service = ApplicationService()
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 100_000_000)
    read_paths = []
    real_read_tsv = data_interpretation_metadata._read_tsv_rows

    def _observed_read_tsv(path):
        read_paths.append(path)
        return real_read_tsv(path)

    monkeypatch.setattr(
        data_interpretation_metadata, "_read_tsv_rows", _observed_read_tsv
    )
    if command_kind == "review":
        command = ReviewInterpretationCommand(
            source_path=str(bids_root),
            source_hint="bids",
        )
    else:
        recipe_path = tmp_path / "resource-recipe.json"
        ImportRecipe(
            recipe_id="resource-recipe",
            interpretation_id="interpretation-1",
            source_path=str(bids_root),
            source_kind="bids",
            selected_eeg_files=[str(eeg_path)],
            label_carriers=[str(events_path)],
        ).write_json(str(recipe_path))
        command = ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))

    result = service.execute(command)

    assert result.failed is True
    assert result.diagnostics["resource_preflight"]["risk_level"] == "blocking"
    assert str(large_path.resolve()) in {
        item["path"] for item in result.diagnostics["resource_preflight"]["files"]
    }
    assert read_paths == []
    assert result.state.raw.loaded is False
    assert result.state.raw.count == 0
    assert result.state.dataset.available is False
    assert result.state.dataset.count == 0
    assert result.state.interpretation.has_scan_result is False


def test_application_service_load_epoch_dataset_workflow(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    load_result = service.execute(LoadDataCommand(paths=[str(fif_path)]))

    assert load_result.ok is True
    assert load_result.diagnostics["success_count"] == 1
    assert load_result.changed_state.raw_changed is True
    assert load_result.changed_state.preprocessed_changed is True
    assert load_result.state.raw.loaded is True
    assert load_result.state.preprocessed.available is True
    assert service.get_capabilities().get(CommandName.CREATE_EPOCH).available is True

    preprocess_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
    )
    assert preprocess_result.ok is True
    assert preprocess_result.changed_state.preprocessed_changed is True

    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=1.3,
            event_ids=["left", "right"],
        ),
    )

    assert epoch_result.ok is True
    assert epoch_result.changed_state.epoch_changed is True
    assert epoch_result.state.epoch.available is True
    assert epoch_result.state.epoch.epoch_count == 12
    assert epoch_result.state.dataset.available is False
    policy_after_epoch = service.get_capabilities()
    assert policy_after_epoch.get(CommandName.LOAD_DATA).available is False
    assert policy_after_epoch.get(CommandName.CREATE_EPOCH).available is False
    assert (
        "Reset the session"
        in policy_after_epoch.get(
            CommandName.CREATE_EPOCH,
        ).reasons[0]
    )
    assert (
        policy_after_epoch.get(CommandName.RESET_SESSION).confirmation_required is True
    )

    dataset_result = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
    )

    assert dataset_result.ok is True
    assert dataset_result.changed_state.datasets_changed is True
    assert dataset_result.state.dataset.available is True
    assert (
        dataset_result.state.dataset.count
        == EXPECTED_SYNTHETIC_SPLIT_25_25_SUMMARY["count"]
    )
    assert dataset_result.state.dataset.split_summary == (
        EXPECTED_SYNTHETIC_SPLIT_25_25_SUMMARY
    )
    assert service.get_capabilities().get(CommandName.TRAIN).available is False

    model_result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
    assert model_result.ok is True
    assert model_result.changed_state.training_changed is True
    assert model_result.state.training.has_model is True
    assert service.get_capabilities().get(CommandName.TRAIN).available is False

    training_result = service.execute(
        ConfigureTrainingCommand(
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            output_dir=str(tmp_path / "training-output"),
        ),
    )
    assert training_result.ok is True
    assert training_result.state.training.has_training_option is True
    assert service.get_capabilities().get(CommandName.TRAIN).available is True

    evaluate_result = service.execute(EvaluateCommand())
    visualize_result = service.execute(VisualizeCommand())
    saliency_result = service.execute(SaliencyCommand())
    query_result = service.execute(QueryStateCommand(query="data_summary"))

    assert evaluate_result.failed is True
    assert visualize_result.ok is True
    assert visualize_result.diagnostics["payload_type"] == "visualization_summary"
    assert saliency_result.ok is True
    assert saliency_result.diagnostics["payload_type"] == "saliency_summary"
    assert query_result.ok is True
    assert query_result.diagnostics["count"] == 1
    prior_error = query_result.state.last_error
    assert evaluate_result.state.last_error is None
    assert evaluate_result.changed_state.error_changed is False
    assert prior_error is None

    reset_preprocess_without_confirmation = service.execute(ResetPreprocessCommand())
    assert reset_preprocess_without_confirmation.failed is True
    assert reset_preprocess_without_confirmation.error_type is (
        ErrorType.CONFIRMATION_REQUIRED
    )
    assert reset_preprocess_without_confirmation.state.last_error == prior_error

    reset_without_confirmation = service.execute(ResetSessionCommand())
    assert reset_without_confirmation.failed is True
    assert reset_without_confirmation.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert reset_without_confirmation.state.last_error == prior_error

    reset_result = service.execute(ResetSessionCommand(confirmed=True))
    assert reset_result.ok is True
    assert reset_result.state.raw.loaded is False
    assert reset_result.state.preprocessed.available is False
    assert reset_result.state.epoch.available is False
    assert reset_result.state.dataset.available is False
    assert reset_result.state.training.has_model is False
    assert reset_result.state.training.has_training_option is False
    assert reset_result.state.training.has_trainer is False
    assert reset_result.state.last_error is None
    assert reset_result.changed_state.error_changed is False
    assert service.get_capabilities().get(CommandName.LOAD_DATA).available is True


def test_explicit_multiclass_epoch_unlocks_dataset_after_label_free_import(
    tmp_path,
) -> None:
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    assert service.execute(ScanSourceCommand(source_path=str(fif_path))).ok is True
    assert service.execute(PreviewInterpretationCommand()).ok is True
    assert service.execute(ValidateInterpretationCommand()).ok is True
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.state.interpretation.class_map == {}
    assert apply_result.state.interpretation.epoch_handoff["supervised_ready"] is False
    assert apply_result.state.interpretation.epoch_handoff["supervised_blockers"] == [
        "No class labels are available for supervised EEG epoch defaults."
    ]
    assert apply_result.state.interpretation.epoch_handoff[
        "supervised_blocker_codes"
    ] == ["missing_class_labels"]
    recipe_result = service.execute(
        SaveInterpretationRecipeCommand(
            recipe_path=str(tmp_path / "load-only-recipe.json"),
        ),
    )
    assert recipe_result.ok is True
    assert apply_result.state.raw.loaded is True
    assert {
        "epoch",
        "epoch_handoff",
        "epoch_settings",
        "epoch_window",
        "baseline",
    }.isdisjoint(recipe_result.diagnostics["recipe"])
    blocked_before_epoch = service.get_capabilities().get(CommandName.GENERATE_DATASET)
    assert blocked_before_epoch.enabled is False
    assert (
        "Create EEG epochs before building the training dataset."
        in blocked_before_epoch.reasons
    )

    preprocess_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
    )
    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=1.3,
            event_ids=["left", "right"],
        ),
    )

    assert preprocess_result.ok is True
    assert epoch_result.ok is True
    assert epoch_result.state.pipeline_stage == "epoch_ready"
    assert epoch_result.state.epoch.epoch_count == 12
    assert epoch_result.state.epoch.event_names == ["left", "right"]
    assert epoch_result.state.epoch.event_ids == {"left": 0, "right": 1}
    dataset_capability = service.get_capabilities().get(CommandName.GENERATE_DATASET)
    assert dataset_capability.enabled is True
    assert dataset_capability.reasons == []

    dataset_result = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
    )

    assert dataset_result.ok is True
    assert dataset_result.state.dataset.available is True


def test_montage_reorders_real_epoch_channels_before_dataset_and_locks_afterward(
    tmp_path,
):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    assert service.execute(LoadDataCommand(paths=[str(fif_path)])).ok is True
    assert (
        service.execute(
            CreateEpochCommand(
                t_min=0.0,
                t_max=1.3,
                event_ids=["left", "right"],
            )
        ).ok
        is True
    )
    split_context = service.get_dataset_split_context(
        DatasetSplitContextRequest(
            publication_generation=service.get_view_publication().generation,
        ),
    )
    assert split_context.context.epoch_available is True
    assert split_context.context.trial_count == 12

    montage_result = service.execute(
        ApplyMontageCommand(
            channels=["EEG2", "EEG0"],
            positions=[(0.0, 0.1, 0.2), (0.3, 0.4, 0.5)],
            montage_name="integration-order",
        )
    )

    assert montage_result.ok is True
    assert montage_result.state.epoch.channel_names == ["EEG2", "EEG0"]
    assert montage_result.state.visualization.montage_positions == [
        [0.0, 0.1, 0.2],
        [0.3, 0.4, 0.5],
    ]
    generated = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        )
    )
    assert generated.ok is True
    blocked = service.execute(
        ApplyMontageCommand(
            channels=["EEG0", "EEG2"],
            positions=[(0.3, 0.4, 0.5), (0.0, 0.1, 0.2)],
            montage_name="too-late",
        )
    )

    assert blocked.failed is True
    assert "before generating datasets" in blocked.message
    assert blocked.state.epoch.channel_names == ["EEG2", "EEG0"]
    assert blocked.state.visualization.montage_positions == [
        [0.0, 0.1, 0.2],
        [0.3, 0.4, 0.5],
    ]
    assert blocked.state.dataset == generated.state.dataset


def test_application_service_accepts_dialog_generator_split_and_updates_readiness(
    tmp_path,
):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    assert service.execute(LoadDataCommand(paths=[str(fif_path)])).ok is True
    assert (
        service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z-score",
            ),
        ).ok
        is True
    )
    assert (
        service.execute(
            CreateEpochCommand(
                t_min=0.0,
                t_max=1.3,
                event_ids=["left", "right"],
            ),
        ).ok
        is True
    )

    dialog_like_config = {
        "train_type": "Full Data",
        "is_cross_validation": False,
        "val_splitters": [
            {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"},
        ],
        "test_splitters": [
            {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"},
        ],
    }
    context_result = service.get_dataset_split_context(
        DatasetSplitContextRequest(
            publication_generation=service.get_view_publication().generation,
        ),
    )

    assert context_result.context.epoch_available is True
    assert context_result.context.trial_count == 12
    dataset_result = service.execute(
        GenerateDatasetCommand(split_config=dialog_like_config),
    )

    assert dataset_result.ok is True
    assert dataset_result.diagnostics["split_audit"]["ok"] is True
    assert dataset_result.state.dataset.available is True
    assert (
        dataset_result.state.dataset.count
        == EXPECTED_SYNTHETIC_SPLIT_20_20_SUMMARY["count"]
    )
    assert dataset_result.state.dataset.split_summary == (
        EXPECTED_SYNTHETIC_SPLIT_20_20_SUMMARY
    )

    assert service.execute(ConfigureTrainingCommand(model_name="EEGNet")).ok is True
    assert (
        service.execute(
            ConfigureTrainingCommand(
                epoch=1,
                batch_size=2,
                learning_rate=0.001,
                output_dir=str(tmp_path / "training-output"),
            ),
        ).ok
        is True
    )
    assert service.get_capabilities().get(CommandName.TRAIN).available is True


def test_dataset_replacement_rolls_back_real_split_then_can_commit(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    assert service.execute(LoadDataCommand(paths=[str(fif_path)])).ok is True
    assert service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
    ).ok
    assert service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=1.3,
            event_ids=["left", "right"],
        ),
    ).ok
    initial = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
    )
    assert initial.ok is True
    assert service.execute(
        ConfigureTrainingCommand(
            model_name="EEGNet",
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            output_dir=str(tmp_path / "replacement-training-output"),
        )
    ).ok
    before_replacement = service.get_state()
    old_summary = before_replacement.dataset.split_summary

    invalid_replacement = service.execute(
        GenerateDatasetCommand(
            split_config={
                "train_type": "Full Data",
                "is_cross_validation": False,
                "val_splitters": [],
                "test_splitters": [],
            },
            replacement_mode=DatasetGenerationMode.REPLACE_EXISTING,
            confirmed=True,
        ),
    )

    assert invalid_replacement.failed is True
    assert invalid_replacement.diagnostics["rolled_back"] is True
    assert invalid_replacement.state.dataset == before_replacement.dataset
    assert invalid_replacement.state.training == before_replacement.training
    assert invalid_replacement.state.active_dataset == (
        before_replacement.active_dataset
    )
    assert invalid_replacement.state.active_training == (
        before_replacement.active_training
    )
    assert invalid_replacement.state.dataset.split_summary == old_summary

    committed_replacement = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.2,
            val_ratio=0.2,
            split_strategy="trial",
            training_mode="individual",
            replacement_mode=DatasetGenerationMode.REPLACE_EXISTING,
            confirmed=True,
        ),
    )

    assert committed_replacement.ok is True
    assert committed_replacement.diagnostics["replaced_existing"] is True
    assert committed_replacement.state.dataset.split_summary == (
        EXPECTED_SYNTHETIC_SPLIT_20_20_SUMMARY
    )
    assert committed_replacement.state.dataset.generator_exists is True
    assert committed_replacement.state.training.has_trainer is False


def test_dataset_replacement_fences_plan_generation_across_real_publication(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    assert service.execute(LoadDataCommand(paths=[str(fif_path)])).ok
    assert service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
    ).ok
    assert service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=1.3,
            event_ids=["left", "right"],
        ),
    ).ok
    assert service.execute(
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
    ).ok
    assert service.execute(ConfigureTrainingCommand(model_name="EEGNet")).ok
    assert service.execute(
        ConfigureTrainingCommand(
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            output_dir=str(tmp_path / "atomic-replacement-output"),
        ),
    ).ok

    manager = service.study.training_manager
    trainer = Trainer([])
    manager.trainer = trainer
    original_set_datasets = service.study.data_manager.set_datasets
    original_clean = trainer.clean
    publication_visible = Event()
    release_publication = Event()
    clean_started = Event()
    release_clean = Event()
    publication_owned: list[bool] = []
    published_datasets: list[Any] = []

    def block_after_publication(
        datasets: list[Any],
        force_update: bool = False,
    ) -> None:
        original_set_datasets(datasets, force_update=force_update)
        published_datasets[:] = datasets
        publication_owned.append(manager._training_operation_owner is not None)
        publication_visible.set()
        assert release_publication.wait(timeout=2.0)

    def hold_trainer_cleanup(*, force_update: bool = False) -> None:
        clean_started.set()
        assert release_clean.wait(timeout=2.0)
        original_clean(force_update=force_update)

    monkeypatch.setattr(
        service.study.data_manager,
        "set_datasets",
        block_after_publication,
    )
    monkeypatch.setattr(trainer, "clean", hold_trainer_cleanup)
    command_results: list[Any] = []
    command_errors: list[BaseException] = []
    contender_errors: list[BaseException] = []
    contender_started = Event()

    def replace_datasets() -> None:
        try:
            command_results.append(
                service.execute(
                    GenerateDatasetCommand(
                        test_ratio=0.2,
                        val_ratio=0.2,
                        split_strategy="trial",
                        training_mode="individual",
                        replacement_mode=(DatasetGenerationMode.REPLACE_EXISTING),
                        confirmed=True,
                    ),
                ),
            )
        except BaseException as exc:
            command_errors.append(exc)

    def generate_competing_plan() -> None:
        contender_started.set()
        try:
            manager.generate_plan(
                list(published_datasets),
                append=True,
            )
        except BaseException as exc:
            contender_errors.append(exc)

    replacement = Thread(target=replace_datasets, daemon=True)
    contender = Thread(target=generate_competing_plan, daemon=True)
    replacement.start()
    try:
        assert publication_visible.wait(timeout=2.0)
        contender.start()
        assert contender_started.wait(timeout=1.0)
        contender.join(timeout=0.05)
        assert contender.is_alive()
    finally:
        release_publication.set()
        try:
            assert clean_started.wait(timeout=2.0)
            contender.join(timeout=1.0)
        finally:
            release_clean.set()

    replacement.join(timeout=2.0)
    contender.join(timeout=2.0)

    assert not replacement.is_alive()
    assert not contender.is_alive()
    assert command_errors == []
    assert len(command_results) == 1
    assert command_results[0].ok is True
    assert publication_owned == [True]
    assert len(contender_errors) == 1
    assert isinstance(contender_errors[0], RuntimeError)
    assert "Another training lifecycle operation" in str(contender_errors[0])
    assert manager.trainer is None


def test_data_interpretation_to_dataset_workflow_is_non_mocked(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    recipe_path = tmp_path / "synthetic_import_recipe.json"

    scan_result = service.execute(ScanSourceCommand(source_path=str(fif_path)))
    recipe_choices = {
        "metadata_overrides": {
            fif_path.name: {
                "subject": "S01",
                "task": "motor-imagery",
            }
        },
        "internal_event_selection": {
            "label_event_codes": ["left", "right"],
            "class_map": {"left": "left", "right": "right"},
        },
        "label_carrier": "embedded_events",
        "event_roles": {"internal_events": "class cue"},
        "class_map": {"1": "left", "2": "right"},
    }
    preview_result = service.execute(
        PreviewInterpretationCommand(choices=recipe_choices),
    )
    validation_result = service.execute(ValidateInterpretationCommand())

    assert scan_result.ok is True
    assert scan_result.diagnostics["payload_type"] == "scan_result"
    assert preview_result.ok is True
    assert preview_result.diagnostics["payload_type"] == "interpretation_preview"
    assert validation_result.ok is True
    assert validation_result.state.interpretation.validation_decision == (
        "needs_confirmation"
    )

    apply_without_confirmation = service.execute(ApplyInterpretationCommand())
    assert apply_without_confirmation.failed is True
    assert apply_without_confirmation.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert apply_without_confirmation.state.last_error is None

    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    save_recipe_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert apply_result.ok is True
    assert apply_result.changed_state.raw_changed is True
    assert apply_result.changed_state.interpretation_changed is True
    assert apply_result.state.raw.loaded is True
    assert apply_result.state.interpretation.has_applied_interpretation is True
    assert save_recipe_result.ok is True
    assert save_recipe_result.state.interpretation.has_recipe is True
    assert recipe_path.exists()

    reload_service = ApplicationService()
    reload_result = reload_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert reload_result.ok is True
    assert reload_result.diagnostics["payload_type"] == "recipe_reload_preview"
    assert reload_result.state.raw.loaded is False
    assert reload_result.state.interpretation.has_preview is True
    assert reload_result.state.interpretation.has_validation_decision is True
    reloaded_candidate = reload_result.diagnostics["candidate"]
    reload_preview = reload_result.diagnostics["preview"]
    assert (
        reloaded_candidate["choices"]["metadata_overrides"]
        == (recipe_choices["metadata_overrides"])
    )
    assert reload_preview["recipe_reload_summary"]["reapplied_choice_types"] == [
        "selected EEG files",
        "metadata overrides",
        "event roles",
        "class map",
    ]
    assert {
        "item": "EEG files",
        "status": "Matched",
        "detail": "Saved recipe still matches 1 saved file(s).",
    } in reload_preview["recipe_reload_summary"]["diff_rows"]
    assert reloaded_candidate["event_roles"]["internal_events"] == "class cue"
    assert reloaded_candidate["class_map"] == {"1": "left", "2": "right"}
    assert "choices:metadata_overrides" in reloaded_candidate["recipe_trace"]
    assert "choices:event_roles" in reloaded_candidate["recipe_trace"]
    assert "choices:class_map" in reloaded_candidate["recipe_trace"]

    reload_apply_without_confirmation = reload_service.execute(
        ApplyInterpretationCommand(),
    )
    reload_apply_result = reload_service.execute(
        ApplyInterpretationCommand(confirmed=True),
    )

    assert reload_apply_without_confirmation.failed is True
    assert reload_apply_without_confirmation.error_type is (
        ErrorType.CONFIRMATION_REQUIRED
    )
    assert reload_apply_without_confirmation.state.last_error is None
    assert reload_apply_result.ok is True
    assert reload_apply_result.state.raw.loaded is True
    assert reload_apply_result.state.raw.files == [fif_path.name]
    assert reload_apply_result.diagnostics["applied_interpretation"][
        "loaded_files"
    ] == [str(fif_path)]

    preprocess_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
    )
    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.25,
            event_ids=["left", "right"],
        ),
    )
    dataset_result = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
    )

    assert preprocess_result.ok is True
    assert epoch_result.ok is True
    assert epoch_result.state.epoch.epoch_count == 12
    assert dataset_result.ok is True
    assert dataset_result.diagnostics["split_audit"]["ok"] is True
    assert dataset_result.state.dataset.available is True
    assert (
        dataset_result.state.dataset.count
        == EXPECTED_SYNTHETIC_SPLIT_25_25_SUMMARY["count"]
    )
    assert dataset_result.state.dataset.split_summary == (
        EXPECTED_SYNTHETIC_SPLIT_25_25_SUMMARY
    )


def test_product_smoke_bids_import_apply_create_epoch(tmp_path):
    service = ApplicationService()
    bids_root, eeg_path, events_path, channels_path = (
        _write_bids_eeg_motor_imagery_fixture(tmp_path)
    )
    recipe_path = tmp_path / "bids-import-recipe.json"

    scan_result = service.execute(
        ScanSourceCommand(source_path=str(bids_root), source_hint="bids"),
    )
    preview_result = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _class_value_decisions(
                            {"left": "Left hand", "right": "Right hand"}
                        ),
                    }
                },
            },
        ),
    )
    validation_result = service.execute(ValidateInterpretationCommand())

    assert scan_result.ok is True
    assert scan_result.state.interpretation.bids["is_bids"] is True
    assert scan_result.state.interpretation.bids["scan_location"] == str(
        bids_root.resolve()
    )
    assert scan_result.state.interpretation.label_carriers == [
        str(events_path.resolve())
    ]
    assert scan_result.state.interpretation.bids["channels_files"] == [
        str(channels_path.resolve())
    ]
    assert preview_result.ok is True
    preview = preview_result.diagnostics["preview"]
    assert preview["bids"]["selected_scope"]["eeg_files"] == [str(eeg_path.resolve())]
    assert preview["metadata_preview"][0]["subject"]["value"] == "01"
    assert preview["metadata_preview"][0]["session"]["value"] == "01"
    assert preview["metadata_preview"][0]["task"]["value"] == "mi"
    assert preview["metadata_preview"][0]["run"]["value"] == "1"
    assert preview["class_map"] == {"left": "Left hand", "right": "Right hand"}
    assert validation_result.ok is True

    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    recipe_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert apply_result.ok is True
    handoff = apply_result.state.interpretation.epoch_handoff
    assert handoff["label_source"] == "bids_events"
    assert handoff["default_epoch_events"] == ["Left hand", "Right hand"]
    assert handoff["bids"]["selected_scope"]["events_files"] == [
        str(events_path.resolve())
    ]
    assert recipe_result.ok is True
    assert recipe_result.diagnostics["recipe"]["bids"]["root"] == str(
        bids_root.resolve()
    )
    reload_service = ApplicationService()
    reload_result = reload_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    assert reload_result.ok is True
    assert reload_result.diagnostics["candidate"]["bids"]["selected_scope"][
        "events_files"
    ] == [str(events_path.resolve())]
    assert reload_result.diagnostics["candidate"]["class_map"] == {
        "left": "Left hand",
        "right": "Right hand",
    }
    assert reload_result.diagnostics["recipe"]["bids"]["root"] == str(
        bids_root.resolve()
    )

    preprocess_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
    )
    epoch_result = service.execute(CreateEpochCommand(t_min=-0.1, t_max=0.3))

    assert preprocess_result.ok is True
    assert epoch_result.ok is True
    assert epoch_result.state.epoch.available is True
    assert epoch_result.state.epoch.epoch_count == 6
    assert set(epoch_result.state.epoch.event_ids) == {"Left hand", "Right hand"}


def test_reload_recipe_blocks_missing_saved_eeg_file(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    recipe_path = tmp_path / "missing-file-recipe.json"
    missing_path = tmp_path / "missing_raw.fif"
    ImportRecipe(
        recipe_id="recipe-missing",
        interpretation_id="interpretation-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(fif_path), str(missing_path)],
    ).write_json(str(recipe_path))

    reload_result = service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert reload_result.ok is True
    decision = reload_result.diagnostics["validation_decision"]
    assert decision["decision"] == "blocked"
    assert "missing_raw.fif" in decision["blocked_reasons"][0]
    assert reload_result.state.interpretation.validation_decision == "blocked"


def test_reload_recipe_blocks_missing_saved_label_carrier(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    recipe_path = tmp_path / "missing-label-carrier-recipe.json"
    missing_events = tmp_path / "missing_events.tsv"
    ImportRecipe(
        recipe_id="recipe-missing-label",
        interpretation_id="interpretation-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(fif_path)],
        label_carriers=[str(missing_events)],
    ).write_json(str(recipe_path))

    reload_result = service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert reload_result.ok is True
    decision = reload_result.diagnostics["validation_decision"]
    assert decision["decision"] == "blocked"
    assert "missing_events.tsv" in decision["blocked_reasons"][0]
    assert "label/event carrier" in decision["blocked_reasons"][0]
    assert reload_result.state.interpretation.validation_decision == "blocked"


def test_reload_recipe_accepts_explicit_label_carrier_remap(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    old_events = tmp_path / "old_events.tsv"
    new_events = tmp_path / "renamed_events.tsv"
    new_events.write_text("onset\tduration\ttrial_type\n1\t0\tleft\n", encoding="utf-8")
    recipe_path = tmp_path / "remap-label-carrier-recipe.json"
    ImportRecipe(
        recipe_id="recipe-remap-label",
        interpretation_id="interpretation-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(fif_path)],
        label_carriers=[str(old_events)],
        label_carrier_plan=[
            {
                "path": str(old_events),
                "selected_label_field": "trial_type",
                "selected_anchor": "onset",
                "time_model": "seconds",
                "granularity": "trial",
                "role": "class cue labels",
            }
        ],
    ).write_json(str(recipe_path))

    reload_result = service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    scan = reload_result.diagnostics["scan_result"]
    candidate = reload_result.diagnostics["candidate"]
    choices = dict(candidate["choices"])
    choices["label_carrier_remap"] = {
        str(old_events): str(new_events),
    }
    choices["label_carrier_choices"][str(old_events)]["value_decisions"] = (
        _class_value_decisions({"left": "left"})
    )

    preview_result = service.execute(
        PreviewInterpretationCommand(
            scan_id=scan["scan_id"],
            choices=choices,
        ),
    )
    validation_result = service.execute(ValidateInterpretationCommand())

    assert reload_result.diagnostics["validation_decision"]["decision"] == "blocked"
    assert preview_result.ok is True
    assert validation_result.ok is True
    assert validation_result.diagnostics["validation_decision"]["decision"] == (
        "needs_confirmation"
    )
    remapped = preview_result.diagnostics["candidate"]["label_carrier_plan"][0]
    assert remapped["path"] == str(new_events)
    assert remapped["selected_label_field"] == "trial_type"
    assert (
        "choices:label_carrier_remap"
        in preview_result.diagnostics["candidate"]["recipe_trace"]
    )


def test_reload_recipe_accepts_explicit_eeg_file_remap(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)
    old_fif = tmp_path / "old_raw.fif"
    recipe_path = tmp_path / "remap-eeg-file-recipe.json"
    ImportRecipe(
        recipe_id="recipe-remap-eeg",
        interpretation_id="interpretation-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(old_fif)],
    ).write_json(str(recipe_path))

    reload_result = service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    scan = reload_result.diagnostics["scan_result"]
    candidate = reload_result.diagnostics["candidate"]
    choices = dict(candidate["choices"])
    choices["eeg_file_remap"] = {
        str(old_fif): str(fif_path),
    }

    preview_result = service.execute(
        PreviewInterpretationCommand(
            scan_id=scan["scan_id"],
            choices=choices,
        ),
    )
    validation_result = service.execute(ValidateInterpretationCommand())

    assert reload_result.diagnostics["validation_decision"]["decision"] == "blocked"
    assert preview_result.ok is True
    assert validation_result.ok is True
    assert validation_result.diagnostics["validation_decision"]["decision"] in {
        "safe",
        "needs_confirmation",
    }
    remapped = preview_result.diagnostics["candidate"]
    assert remapped["selected_eeg_files"] == [str(fif_path)]
    assert "choices:eeg_file_remap" in remapped["recipe_trace"]


def test_application_service_failed_command_sets_and_clears_last_error(tmp_path):
    service = ApplicationService()
    fif_path = _write_synthetic_raw_fif(tmp_path)

    load_result = service.execute(LoadDataCommand(paths=[str(fif_path)]))
    assert load_result.ok is True
    assert load_result.state.last_error is None

    premature_dataset = service.execute(GenerateDatasetCommand())
    assert premature_dataset.failed is True
    assert premature_dataset.state.last_error is not None
    assert premature_dataset.state.raw.loaded is True
    assert premature_dataset.state.epoch.available is False
    assert premature_dataset.state.dataset.available is False
    assert premature_dataset.changed_state.error_changed is True
    assert premature_dataset.changed_state.datasets_changed is False

    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0.0,
            t_max=0.25,
            event_ids=["left", "right"],
        ),
    )

    assert epoch_result.ok is True
    assert epoch_result.state.epoch.available is True
    assert epoch_result.state.last_error is None
    assert epoch_result.changed_state.error_changed is True
