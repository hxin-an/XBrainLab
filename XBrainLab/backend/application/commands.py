"""Command objects for the backend application service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommandName(str, Enum):
    """Names understood by :class:`ApplicationService`."""

    LOAD_DATA = "load_data"
    ATTACH_LABELS = "attach_labels"
    PREPROCESS = "preprocess"
    CREATE_EPOCH = "create_epoch"
    GENERATE_DATASET = "generate_dataset"
    CONFIGURE_TRAINING = "configure_training"
    TRAIN = "train"
    STOP_TRAINING = "stop_training"
    EVALUATE = "evaluate"
    VISUALIZE = "visualize"
    SALIENCY = "saliency"
    RESET_SESSION = "reset_session"
    NEW_SESSION = "new_session"


class PreprocessOperation(str, Enum):
    """Supported preprocessing operations."""

    BANDPASS = "bandpass"
    NOTCH = "notch"
    RESAMPLE = "resample"
    NORMALIZE = "normalize"
    REREFERENCE = "rereference"
    SELECT_CHANNELS = "select_channels"
    CHANNEL_SELECTION = "channel_selection"
    SET_MONTAGE = "set_montage"
    STANDARD = "standard"


@dataclass(frozen=True)
class LoadDataCommand:
    """Load raw EEG files into the active study."""

    paths: list[str]
    allow_append: bool = True

    @property
    def name(self) -> CommandName:
        return CommandName.LOAD_DATA


@dataclass(frozen=True)
class AttachLabelsCommand:
    """Attach label files to already-loaded raw files."""

    mapping: dict[str, str]
    label_format: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.ATTACH_LABELS


@dataclass(frozen=True)
class PreprocessCommand:
    """Apply a preprocessing operation to the active study."""

    operation: PreprocessOperation | str
    low_freq: float | None = None
    high_freq: float | None = None
    notch_freq: float | None = None
    rate: int | None = None
    method: str | None = None
    channels: list[str] | None = None
    montage_name: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.PREPROCESS


@dataclass(frozen=True)
class CreateEpochCommand:
    """Create epochs from preprocessed data."""

    t_min: float
    t_max: float
    baseline: list[float] | tuple[float | None, float | None] | None = None
    event_ids: list[str] | dict[str, int] | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.CREATE_EPOCH


@dataclass(frozen=True)
class GenerateDatasetCommand:
    """Generate train/validation/test datasets from epoch data."""

    test_ratio: float = 0.2
    val_ratio: float = 0.2
    split_strategy: str = "subject"
    training_mode: str = "individual"

    @property
    def name(self) -> CommandName:
        return CommandName.GENERATE_DATASET


@dataclass(frozen=True)
class ConfigureTrainingCommand:
    """Configure model and training hyperparameters."""

    epoch: int | None = None
    batch_size: int | None = None
    learning_rate: float | None = None
    repeat: int = 1
    device: str = "auto"
    optimizer: str = "adam"
    save_checkpoints_every: int = 0
    output_dir: str = "./output"
    model_name: str | None = None
    model_params: dict[str, Any] = field(default_factory=dict)
    pretrained_weight_path: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.CONFIGURE_TRAINING


@dataclass(frozen=True)
class TrainCommand:
    """Start model training."""

    append: bool = True
    interactive: bool = True

    @property
    def name(self) -> CommandName:
        return CommandName.TRAIN


@dataclass(frozen=True)
class StopTrainingCommand:
    """Stop an active training run."""

    @property
    def name(self) -> CommandName:
        return CommandName.STOP_TRAINING


@dataclass(frozen=True)
class EvaluateCommand:
    """Reserved evaluation query command.

    The command object is part of the contract so callers can receive a stable
    failure instead of a router error while the service query API is still being
    designed.
    """

    target: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.EVALUATE


@dataclass(frozen=True)
class VisualizeCommand:
    """Reserved visualization query command."""

    view: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.VISUALIZE


@dataclass(frozen=True)
class SaliencyCommand:
    """Reserved saliency command."""

    method: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.SALIENCY


@dataclass(frozen=True)
class ResetSessionCommand:
    """Clear loaded data and downstream state."""

    confirmed: bool = False

    @property
    def name(self) -> CommandName:
        return CommandName.RESET_SESSION


@dataclass(frozen=True)
class NewSessionCommand:
    """Reserved new-session command.

    Creating a separate session requires an owner above the backend service, so
    this command remains disabled until that lifecycle exists.
    """

    confirmed: bool = False

    @property
    def name(self) -> CommandName:
        return CommandName.NEW_SESSION


Command = (
    LoadDataCommand
    | AttachLabelsCommand
    | PreprocessCommand
    | CreateEpochCommand
    | GenerateDatasetCommand
    | ConfigureTrainingCommand
    | TrainCommand
    | StopTrainingCommand
    | EvaluateCommand
    | VisualizeCommand
    | SaliencyCommand
    | ResetSessionCommand
    | NewSessionCommand
)


def command_name(command: Command | Any) -> CommandName:
    """Return the routing name for a command-like object."""
    name = getattr(command, "name", None)
    if isinstance(name, CommandName):
        return name
    if isinstance(name, str):
        return CommandName(name)
    raise TypeError(f"Unsupported command object: {command!r}")
