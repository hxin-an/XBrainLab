"""Deterministic training-ready fixture shared by UI evidence scripts."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitChoice,
    DatasetSplitContext,
    DatasetSplitPreviewPublication,
    DatasetSplitPreviewRequest,
    DatasetSplitPreviewRow,
)
from XBrainLab.backend.training.record import EvalRecord, RecordKey
from XBrainLab.backend.training.record.artifact_store import (
    TRAINING_RECORD_ARTIFACT_TYPE,
    load_model_state_dict,
    read_json_npz_artifact,
)
from XBrainLab.backend.training.record.train import _decode_training_artifact

if TYPE_CHECKING:
    from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
        DataSplittingPreviewDialog,
    )


def verify_real_training_artifacts(output_root: Path) -> None:
    """Reload one completed evidence run through the product artifact decoders."""
    record_manifests = list(output_root.rglob("record"))
    if len(record_manifests) != 1:
        raise RuntimeError(
            "training persistence did not produce exactly one record manifest"
        )
    artifact_dir = record_manifests[0].parent
    data, arrays = read_json_npz_artifact(
        record_manifests[0], expected_artifact_type=TRAINING_RECORD_ARTIFACT_TYPE
    )
    train, _val, _test, _best, _seed, epoch, *_metadata = _decode_training_artifact(
        data,
        arrays,
        best_record_keys={
            f"best_val_{metric}{suffix}"
            for metric in RecordKey()
            for suffix in ("", "_epoch")
        },
    )
    if epoch < 1 or any(
        len(train[metric]) != epoch
        or not any(value is not None for value in train[metric])
        for metric in (RecordKey.LOSS, RecordKey.ACC)
    ):
        raise RuntimeError("training artifact has no completed epoch metrics")
    checkpoint = artifact_dir / f"Epoch-{epoch}-model"
    if not checkpoint.is_file() or not load_model_state_dict(checkpoint):
        raise RuntimeError("training checkpoint could not be safely reloaded")
    evaluation = EvalRecord.load(str(artifact_dir))
    if (
        evaluation is None
        or len(evaluation.label) == 0
        or len(evaluation.output) != len(evaluation.label)
    ):
        raise RuntimeError("evaluation artifact could not be safely reloaded")


def data_split_capture_context() -> DatasetSplitContext:
    """Small, deterministic context for layout captures, not allocation evidence."""
    return DatasetSplitContext(
        epoch_available=True,
        subject_count=2,
        session_count=1,
        label_count=2,
        trial_count=120,
        subject_choices=(
            DatasetSplitChoice(value="S01", label="S01"),
            DatasetSplitChoice(value="S02", label="S02"),
        ),
        session_choices=(DatasetSplitChoice(value="session", label="session"),),
    )


def data_split_capture_provider(
    request: DatasetSplitPreviewRequest,
) -> DatasetSplitPreviewPublication:
    """Render representative rows consistent with the selected layout mode."""
    fold_count = 5 if request.specification.is_cross_validation else 1
    validation_count = 20 if request.specification.val_splitters else 0
    return DatasetSplitPreviewPublication(
        request=request,
        generation=request.publication_generation,
        rows=tuple(
            DatasetSplitPreviewRow(
                name=(f"Fold_{index}" if fold_count > 1 else "Holdout"),
                train_count=96 - validation_count,
                validation_count=validation_count,
                test_count=24,
            )
            for index in range(fold_count)
        ),
    )


def data_split_capture_dialog(
    *, cross_validation: bool = True
) -> DataSplittingPreviewDialog:
    """Build a settled Step 2 example; the successful caller owns its lifetime."""
    from PyQt6.QtCore import QSize, Qt

    from XBrainLab.backend.dataset import (
        DataSplitter,
        DataSplittingConfig,
        SplitByType,
        TrainingType,
        ValSplitByType,
    )
    from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
        DataSplittingPreviewDialog,
    )

    dialog = DataSplittingPreviewDialog(
        None,
        "Data Splitting Step 2",
        split_context=data_split_capture_context(),
        publication_generation=1,
        config=DataSplittingConfig(
            TrainingType.FULL,
            cross_validation,
            [DataSplitter(ValSplitByType.TRIAL)],
            [DataSplitter(SplitByType.TRIAL)],
        ),
        preview_provider=data_split_capture_provider,
        preview_canceller=lambda _request_id: True,
    )
    try:
        worker = dialog.preview_worker
        if worker is not None:
            worker.join(timeout=2)
            if worker.is_alive():
                raise RuntimeError(  # noqa: TRY301 - close this partially prepared dialog
                    "Data-splitting capture preview did not finish."
                )
        dialog.update_table()
        if dialog.preview_debounce_timer is not None:
            dialog.preview_debounce_timer.stop()
        if dialog.timer is not None:
            dialog.timer.stop()
        if dialog.tree is None:
            raise RuntimeError(  # noqa: TRY301 - close this partially prepared dialog
                "Data-splitting capture tree is unavailable."
            )
        dialog._clear_tree_current_item()
        dialog._resize_tree_to_rows()
        dialog.adjustSize()
        dialog.resize(QSize(980, dialog.sizeHint().height()))
    except BaseException:
        # closeEvent retains the dialog while a worker is still stopping; defer
        # deletion through that existing lifecycle instead of deleting it early.
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.close()
        raise
    return dialog


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
