"""Command objects for the backend application service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from XBrainLab.backend.training_contract import DEFAULT_TRAINING_OUTPUT_DIR

if TYPE_CHECKING:
    from .dataset_split_preview import DatasetSplitPreviewReceipt
    from .evaluation_render import EvaluationSummaryIdentity
    from .saliency_render import SaliencySelectionIdentity


class CommandName(str, Enum):
    """Names understood by :class:`ApplicationService`."""

    SCAN_SOURCE = "scan_source"
    REVIEW_INTERPRETATION = "review_interpretation"
    PREVIEW_INTERPRETATION = "preview_interpretation"
    VALIDATE_INTERPRETATION = "validate_interpretation"
    APPLY_INTERPRETATION = "apply_interpretation"
    SAVE_INTERPRETATION_RECIPE = "save_interpretation_recipe"
    RELOAD_INTERPRETATION_RECIPE = "reload_interpretation_recipe"
    LOAD_DATA = "load_data"
    ATTACH_LABELS = "attach_labels"
    IMPORT_LABELS = "import_labels"
    UPDATE_METADATA = "update_metadata"
    APPLY_SMART_PARSE = "apply_smart_parse"
    REMOVE_FILES = "remove_files"
    PREPROCESS = "preprocess"
    CREATE_EPOCH = "create_epoch"
    CONFIGURE_DATASET_SPLIT = "configure_dataset_split"
    CLEAR_DATASETS = "clear_datasets"
    CONFIGURE_TRAINING = "configure_training"
    TRAIN = "train"
    DISCARD_TRAINING_PREPARATION = "discard_training_preparation"
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
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.LOAD_DATA


@dataclass(frozen=True)
class AttachLabelsCommand:
    """Attach label files to already-loaded raw files."""

    mapping: dict[str, str]
    label_paths: list[str] = field(default_factory=list)
    label_format: str | None = None
    selected_event_names: list[str] | set[str] | None = None
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.ATTACH_LABELS


@dataclass(frozen=True)
class ScanSourceCommand:
    """Scan a source path for EEG files, label carriers, and metadata."""

    source_path: str
    source_hint: str = "auto"
    label_sources: list[str] = field(default_factory=list)
    selected_bids_subjects: list[str] = field(default_factory=list)
    catalog_only: bool = False

    @property
    def name(self) -> CommandName:
        return CommandName.SCAN_SOURCE


@dataclass(frozen=True)
class PreviewInterpretationCommand:
    """Build and preview a candidate data interpretation."""

    scan_id: str | None = None
    choices: dict[str, Any] = field(default_factory=dict)
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.PREVIEW_INTERPRETATION


@dataclass(frozen=True)
class ReviewInterpretationCommand:
    """Scan, preview, and validate a Data Interpretation candidate."""

    source_path: str
    source_hint: str = "auto"
    label_sources: list[str] = field(default_factory=list)
    choices: dict[str, Any] = field(default_factory=dict)
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.REVIEW_INTERPRETATION


@dataclass(frozen=True)
class ValidateInterpretationCommand:
    """Validate an interpretation candidate."""

    candidate_id: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.VALIDATE_INTERPRETATION


@dataclass(frozen=True)
class ApplyInterpretationCommand:
    """Apply a validated interpretation to the active backend session."""

    candidate_id: str | None = None
    confirmed: bool = False
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.APPLY_INTERPRETATION


@dataclass(frozen=True)
class SaveInterpretationRecipeCommand:
    """Save the applied interpretation as a replayable recipe."""

    recipe_path: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.SAVE_INTERPRETATION_RECIPE


@dataclass(frozen=True)
class ReloadInterpretationRecipeCommand:
    """Reload a recipe and re-run scan/preview/validation without applying."""

    recipe_path: str
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.RELOAD_INTERPRETATION_RECIPE


@dataclass(frozen=True)
class LabelImportPlan:
    """Plan for loading label paths and applying them to selected raw data."""

    preview_id: str | None = None
    target_indices: list[int] = field(default_factory=list)
    label_paths: list[str] = field(default_factory=list)
    label_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    mapping: Any = None
    file_mapping: dict[str, str] = field(default_factory=dict)
    mode: str = "batch"
    selected_event_names: list[str] | set[str] | None = None
    force_import: bool = False


@dataclass(frozen=True)
class PreviewLabelImportCommand:
    """Materialize label paths once and publish only a typed UI summary."""

    label_paths: list[str]
    label_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

    @property
    def name(self) -> CommandName:
        # Preview and commit intentionally share one capability and command lock.
        return CommandName.IMPORT_LABELS


@dataclass(frozen=True)
class ImportLabelsCommand:
    """Apply an explicit label import plan to loaded raw data."""

    plan: LabelImportPlan
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

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
    confirmation_receipt: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.CREATE_EPOCH


@dataclass(frozen=True)
class SaveDatasetSplitCommand:
    """Save a validated train/validation/test split specification."""

    test_ratio: float = 0.2
    val_ratio: float = 0.2
    split_strategy: str = "subject"
    training_mode: str = "individual"
    split_config: dict[str, Any] = field(default_factory=dict)
    preview_receipt: DatasetSplitPreviewReceipt | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.CONFIGURE_DATASET_SPLIT


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
    seed: int | None = None
    device: str = "auto"
    optimizer: str = "adam"
    optimizer_params: dict[str, Any] = field(default_factory=dict)
    save_checkpoints_every: int = 0
    output_dir: str = DEFAULT_TRAINING_OUTPUT_DIR
    evaluation_option: str | None = None
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
    confirmed: bool = False
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.TRAIN


@dataclass(frozen=True)
class DiscardTrainingPreparationCommand:
    """Discard one pending resource receipt and speculative split candidate."""

    resource_preflight_token: str | None = None

    @property
    def name(self) -> CommandName:
        return CommandName.DISCARD_TRAINING_PREPARATION


@dataclass(frozen=True)
class StopTrainingCommand:
    """Stop an active training run."""

    wait_timeout: float | None = None

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
    """Read a detached summary of available Evaluation plans and runs."""

    target: str | None = None
    summary_identity: EvaluationSummaryIdentity | None = None

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
    target: SaliencySelectionIdentity | None = None
    resource_preflight_confirmed: bool = False
    resource_preflight_token: str | None = None

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
    ScanSourceCommand
    | ReviewInterpretationCommand
    | PreviewInterpretationCommand
    | ValidateInterpretationCommand
    | ApplyInterpretationCommand
    | SaveInterpretationRecipeCommand
    | ReloadInterpretationRecipeCommand
    | LoadDataCommand
    | AttachLabelsCommand
    | PreviewLabelImportCommand
    | ImportLabelsCommand
    | UpdateMetadataCommand
    | ApplySmartParseCommand
    | RemoveFilesCommand
    | PreprocessCommand
    | CreateEpochCommand
    | SaveDatasetSplitCommand
    | ClearDatasetsCommand
    | ConfigureTrainingCommand
    | TrainCommand
    | DiscardTrainingPreparationCommand
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
