"""Command objects for the backend application service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommandName(str, Enum):
    """Names understood by :class:`ApplicationService`."""

    LOAD_DATA = "load_data"
    ATTACH_LABELS = "attach_labels"
    IMPORT_LABELS = "import_labels"
    UPDATE_METADATA = "update_metadata"
    APPLY_SMART_PARSE = "apply_smart_parse"
    REMOVE_FILES = "remove_files"
    PREPROCESS = "preprocess"
    CREATE_EPOCH = "create_epoch"
    GENERATE_DATASET = "generate_dataset"
    CLEAR_DATASETS = "clear_datasets"
    CONFIGURE_TRAINING = "configure_training"
    TRAIN = "train"
    STOP_TRAINING = "stop_training"
    CLEAR_TRAINING_HISTORY = "clear_training_history"
    EVALUATE = "evaluate"
    VISUALIZE = "visualize"
    SALIENCY = "saliency"
    APPLY_MONTAGE = "apply_montage"
    QUERY_STATE = "query_state"
    RESET_PREPROCESS = "reset_preprocess"
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
class LabelImportPlan:
    """Plan for applying labels already collected by a UI import dialog."""

    target_indices: list[int] = field(default_factory=list)
    label_map: dict[str, Any] = field(default_factory=dict)
    mapping: Any = None
    file_mapping: dict[str, str] = field(default_factory=dict)
    mode: str = "batch"
    selected_event_names: list[str] | set[str] | None = None
    force_import: bool = False


@dataclass(frozen=True)
class ImportLabelsCommand:
    """Apply an explicit label import plan to loaded raw data."""

    plan: LabelImportPlan

    @property
    def name(self) -> CommandName:
        return CommandName.IMPORT_LABELS


@dataclass(frozen=True)
class MetadataUpdate:
    """Metadata edit for one loaded file."""

    index: int
    subject: str | None = None
    session: str | None = None


@dataclass(frozen=True)
class UpdateMetadataCommand:
    """Update subject/session metadata for one or more loaded files."""

    index: int | None = None
    subject: str | None = None
    session: str | None = None
    updates: list[MetadataUpdate] = field(default_factory=list)

    @property
    def name(self) -> CommandName:
        return CommandName.UPDATE_METADATA


@dataclass(frozen=True)
class ApplySmartParseCommand:
    """Apply filename parser results to loaded-file metadata."""

    results: dict[str, tuple[str, str] | list[str] | Any]

    @property
    def name(self) -> CommandName:
        return CommandName.APPLY_SMART_PARSE


@dataclass(frozen=True)
class RemoveFilesCommand:
    """Remove loaded raw files by row/index."""

    indices: list[int]

    @property
    def name(self) -> CommandName:
        return CommandName.REMOVE_FILES


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
    generator: Any | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.GENERATE_DATASET


@dataclass(frozen=True)
class ClearDatasetsCommand:
    """Clear generated datasets and any training plan tied to them."""

    confirmed: bool = False

    @property
    def name(self) -> CommandName:
        return CommandName.CLEAR_DATASETS


@dataclass(frozen=True)
class ConfigureTrainingCommand:
    """Configure model and training hyperparameters."""

    epoch: int | None = None
    batch_size: int | None = None
    learning_rate: float | None = None
    repeat: int = 1
    device: str = "auto"
    optimizer: str = "adam"
    optimizer_params: dict[str, Any] = field(default_factory=dict)
    save_checkpoints_every: int = 0
    output_dir: str = "./output"
    evaluation_option: str | None = None
    model_name: str | None = None
    model_params: dict[str, Any] = field(default_factory=dict)
    pretrained_weight_path: str | None = None
    training_option: Any | None = None

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
class ClearTrainingHistoryCommand:
    """Clear training plan/run history while preserving current configuration."""

    confirmed: bool = False

    @property
    def name(self) -> CommandName:
        return CommandName.CLEAR_TRAINING_HISTORY


@dataclass(frozen=True)
class EvaluateCommand:
    """Read evaluation metrics and run summaries from the active backend."""

    target: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.EVALUATE


@dataclass(frozen=True)
class VisualizeCommand:
    """Read visualization readiness and available view summaries."""

    view: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.VISUALIZE


@dataclass(frozen=True)
class SaliencyCommand:
    """Configure or query saliency readiness."""

    method: str | None = None
    params: dict[str, Any] | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.SALIENCY


@dataclass(frozen=True)
class ApplyMontageCommand:
    """Apply confirmed channel montage positions to epoch data."""

    channels: list[str]
    positions: list[tuple[float, float, float]]
    montage_name: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.APPLY_MONTAGE


@dataclass(frozen=True)
class QueryStateCommand:
    """Read-only typed query through the application service."""

    query: str = "state"
    params: dict[str, Any] = field(default_factory=dict)
    include_objects: bool = False

    @property
    def name(self) -> CommandName:
        return CommandName.QUERY_STATE


@dataclass(frozen=True)
class ResetPreprocessCommand:
    """Reset preprocessing to loaded raw data and remove downstream artifacts."""

    confirmed: bool = False

    @property
    def name(self) -> CommandName:
        return CommandName.RESET_PREPROCESS


@dataclass(frozen=True)
class ResetSessionCommand:
    """Clear loaded data and downstream state."""

    confirmed: bool = False

    @property
    def name(self) -> CommandName:
        return CommandName.RESET_SESSION


@dataclass(frozen=True)
class NewSessionCommand:
    """Start a new single-backend session by clearing current state."""

    confirmed: bool = False

    @property
    def name(self) -> CommandName:
        return CommandName.NEW_SESSION


Command = (
    LoadDataCommand
    | AttachLabelsCommand
    | ImportLabelsCommand
    | UpdateMetadataCommand
    | ApplySmartParseCommand
    | RemoveFilesCommand
    | PreprocessCommand
    | CreateEpochCommand
    | GenerateDatasetCommand
    | ClearDatasetsCommand
    | ConfigureTrainingCommand
    | TrainCommand
    | StopTrainingCommand
    | ClearTrainingHistoryCommand
    | EvaluateCommand
    | VisualizeCommand
    | SaliencyCommand
    | ApplyMontageCommand
    | QueryStateCommand
    | ResetPreprocessCommand
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
