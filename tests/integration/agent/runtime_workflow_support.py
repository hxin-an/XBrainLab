"""Small real-command fixture for Assistant training and navigation regressions."""

from scripts.dev.chatpanel_training_fixture import write_training_ready_raw_fif
from scripts.dev.training_evidence_fixture import prepare_training_dataset_ready_state
from XBrainLab.backend.application import (
    ApplyMontageCommand,
    ConfigureTrainingCommand,
    TrainCommand,
    get_application_service,
)


def start_cpu_training(study, tmp_path, *, epochs=1):
    """Start an owned CPU job; the test must await or cancel the returned operation."""
    source = write_training_ready_raw_fif(tmp_path / "training_raw.fif")
    prepared = prepare_training_dataset_ready_state(study, source, tmp_path / "output")
    assert prepared["ok"], prepared["commands"]
    service = get_application_service(study)
    for command in (
        ConfigureTrainingCommand(
            model_name="EEGNet",
            epoch=epochs,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
            seed=43,
            output_dir=str(tmp_path / "output"),
        ),
        ApplyMontageCommand(
            channels=["C3", "C4", "Cz", "Pz"],
            positions=[
                (-0.06, 0.0, 0.04),
                (0.06, 0.0, 0.04),
                (0.0, 0.04, 0.08),
                (0.0, -0.08, 0.02),
            ],
            montage_name="synthetic-4ch",
        ),
    ):
        result = service.execute(command)
        assert result.ok, result.message
    command = TrainCommand(confirmed=True, interactive=True)
    operation = service.begin_owned_operation(command)
    result = service.execute(command, operation_id=operation.operation_id)
    assert result.ok, result.message
    return operation.operation_id
