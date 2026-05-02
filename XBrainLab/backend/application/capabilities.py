"""Command capability policy for the backend application service."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .commands import CommandName
from .state import ApplicationStateSnapshot


@dataclass(frozen=True)
class CommandCapability:
    """Whether a command can currently be executed and why."""

    command_name: str
    enabled: bool
    reasons: list[str] = field(default_factory=list)
    long_running: bool = False
    destructive: bool = False
    confirmation_required: bool = False

    @property
    def command(self) -> str:
        return self.command_name

    @property
    def available(self) -> bool:
        return self.enabled

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityPolicy:
    """Collection of capabilities keyed by command name."""

    capabilities: dict[str, CommandCapability]

    def get(self, command_name: CommandName | str) -> CommandCapability:
        key = (
            command_name.value
            if isinstance(command_name, CommandName)
            else command_name
        )
        return self.capabilities[key]

    def to_dict(self) -> dict[str, Any]:
        return {
            name: capability.to_dict() for name, capability in self.capabilities.items()
        }


def build_capability_policy(state: ApplicationStateSnapshot) -> CapabilityPolicy:
    """Build command capabilities from an application state snapshot."""
    active_dataset = state.active_dataset
    active_training = state.active_training
    has_state = (
        active_dataset.has_raw_data
        or active_dataset.has_preprocessed_data
        or active_dataset.has_epoch_data
        or active_dataset.has_datasets
        or active_training.has_model
        or active_training.has_training_option
        or active_training.has_trainer
    )

    capabilities: dict[str, CommandCapability] = {}

    load_reasons = []
    if (
        active_dataset.has_epoch_data
        or active_dataset.has_datasets
        or active_training.has_trainer
    ):
        load_reasons.append(
            "Reset the session before loading new raw data after epoching, "
            "dataset generation, or trainer creation."
        )
    capabilities[CommandName.LOAD_DATA.value] = _cap(
        CommandName.LOAD_DATA,
        load_reasons,
    )

    attach_reasons = []
    if not active_dataset.has_raw_data:
        attach_reasons.append("Load raw data before attaching labels.")
    capabilities[CommandName.ATTACH_LABELS.value] = _cap(
        CommandName.ATTACH_LABELS,
        attach_reasons,
    )

    preprocess_reasons = []
    if not active_dataset.has_raw_data:
        preprocess_reasons.append("Load raw data before preprocessing.")
    if active_dataset.has_epoch_data or active_dataset.has_datasets:
        preprocess_reasons.append(
            "Reset the session before changing preprocessing after epoching "
            "or dataset generation."
        )
    capabilities[CommandName.PREPROCESS.value] = _cap(
        CommandName.PREPROCESS,
        preprocess_reasons,
    )

    epoch_reasons = []
    if not active_dataset.has_preprocessed_data:
        epoch_reasons.append("Preprocess data before creating epochs.")
    capabilities[CommandName.CREATE_EPOCH.value] = _cap(
        CommandName.CREATE_EPOCH,
        epoch_reasons,
    )

    dataset_reasons = []
    if not active_dataset.has_epoch_data:
        dataset_reasons.append("Create epochs before generating datasets.")
    capabilities[CommandName.GENERATE_DATASET.value] = _cap(
        CommandName.GENERATE_DATASET,
        dataset_reasons,
    )

    configure_reasons = []
    if active_training.is_running:
        configure_reasons.append(
            "Stop training before changing training configuration."
        )
    capabilities[CommandName.CONFIGURE_TRAINING.value] = _cap(
        CommandName.CONFIGURE_TRAINING,
        configure_reasons,
    )

    train_reasons = []
    if active_training.is_running:
        train_reasons.append("Training is already running.")
    if not active_dataset.has_datasets:
        train_reasons.append("Generate datasets before training.")
    if not active_training.has_model:
        train_reasons.append("Select a model before training.")
    if not active_training.has_training_option:
        train_reasons.append("Configure training options before training.")
    capabilities[CommandName.TRAIN.value] = _cap(
        CommandName.TRAIN,
        train_reasons,
        long_running=True,
    )

    stop_reasons = []
    if not active_training.is_running:
        stop_reasons.append("No training run is active.")
    capabilities[CommandName.STOP_TRAINING.value] = _cap(
        CommandName.STOP_TRAINING,
        stop_reasons,
    )

    capabilities[CommandName.EVALUATE.value] = _cap(
        CommandName.EVALUATE,
        [],
    )
    capabilities[CommandName.VISUALIZE.value] = _cap(
        CommandName.VISUALIZE,
        [],
    )

    capabilities[CommandName.SALIENCY.value] = _cap(
        CommandName.SALIENCY,
        [],
    )

    capabilities[CommandName.RESET_SESSION.value] = CommandCapability(
        command_name=CommandName.RESET_SESSION.value,
        enabled=True,
        reasons=[],
        destructive=True,
        confirmation_required=has_state,
    )
    capabilities[CommandName.NEW_SESSION.value] = CommandCapability(
        command_name=CommandName.NEW_SESSION.value,
        enabled=True,
        reasons=[],
        destructive=True,
        confirmation_required=has_state,
    )

    return CapabilityPolicy(capabilities)


def _cap(
    command_name: CommandName,
    reasons: list[str],
    long_running: bool = False,
) -> CommandCapability:
    return CommandCapability(
        command_name=command_name.value,
        enabled=not reasons,
        reasons=reasons,
        long_running=long_running,
    )
