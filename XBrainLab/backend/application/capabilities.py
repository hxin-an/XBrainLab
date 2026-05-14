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
    can_auto_execute: bool = True
    requires_confirmation: bool = False
    decision_boundary: str | None = None
    continue_allowed_after_success: bool = True
    retry_limit: int = 2
    stop_after_success: bool = False
    blocks_downstream_until_confirmed: bool = False

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

    interpretation = state.interpretation
    capabilities[CommandName.SCAN_SOURCE.value] = CommandCapability(
        command_name=CommandName.SCAN_SOURCE.value,
        enabled=True,
        reasons=[],
        can_auto_execute=True,
        decision_boundary="read_only_discovery",
        continue_allowed_after_success=True,
    )
    capabilities[CommandName.PREVIEW_INTERPRETATION.value] = CommandCapability(
        command_name=CommandName.PREVIEW_INTERPRETATION.value,
        enabled=interpretation.has_scan_result,
        reasons=[]
        if interpretation.has_scan_result
        else ["Scan a data source before previewing interpretation."],
        can_auto_execute=True,
        decision_boundary="semantic_preview",
        continue_allowed_after_success=True,
    )
    capabilities[CommandName.VALIDATE_INTERPRETATION.value] = CommandCapability(
        command_name=CommandName.VALIDATE_INTERPRETATION.value,
        enabled=interpretation.has_candidate,
        reasons=[]
        if interpretation.has_candidate
        else ["Preview an interpretation candidate before validation."],
        can_auto_execute=True,
        decision_boundary="semantic_validation",
        continue_allowed_after_success=True,
    )
    apply_reasons: list[str] = []
    if not interpretation.has_validation_decision:
        apply_reasons.append("Validate an interpretation before applying it.")
    if interpretation.validation_decision == "blocked":
        apply_reasons.append("Interpretation is blocked.")
        apply_reasons.extend(interpretation.blocked_reasons)
    apply_reasons.extend(_raw_edit_blockers(state))
    apply_needs_confirmation = (
        interpretation.validation_decision == "needs_confirmation"
    )
    capabilities[CommandName.APPLY_INTERPRETATION.value] = CommandCapability(
        command_name=CommandName.APPLY_INTERPRETATION.value,
        enabled=not apply_reasons,
        reasons=apply_reasons,
        confirmation_required=apply_needs_confirmation,
        can_auto_execute=not apply_needs_confirmation,
        requires_confirmation=apply_needs_confirmation,
        decision_boundary="semantic_apply"
        if apply_needs_confirmation
        else "data_apply",
        continue_allowed_after_success=False,
        retry_limit=0,
        stop_after_success=True,
        blocks_downstream_until_confirmed=apply_needs_confirmation,
    )
    capabilities[CommandName.SAVE_INTERPRETATION_RECIPE.value] = CommandCapability(
        command_name=CommandName.SAVE_INTERPRETATION_RECIPE.value,
        enabled=interpretation.has_applied_interpretation,
        reasons=[]
        if interpretation.has_applied_interpretation
        else ["Apply an interpretation before saving a recipe."],
        can_auto_execute=True,
        decision_boundary="write_recipe",
        continue_allowed_after_success=True,
    )
    capabilities[CommandName.RELOAD_INTERPRETATION_RECIPE.value] = CommandCapability(
        command_name=CommandName.RELOAD_INTERPRETATION_RECIPE.value,
        enabled=True,
        reasons=[],
        can_auto_execute=True,
        decision_boundary="recipe_reload_preview",
        continue_allowed_after_success=True,
    )

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
        attach_reasons + _raw_edit_blockers(state),
    )

    capabilities[CommandName.IMPORT_LABELS.value] = _cap(
        CommandName.IMPORT_LABELS,
        attach_reasons + _raw_edit_blockers(state),
    )

    raw_edit_reasons = _raw_edit_blockers(state)
    capabilities[CommandName.UPDATE_METADATA.value] = _cap(
        CommandName.UPDATE_METADATA,
        _requires_raw(state, "Load raw data before updating metadata.")
        + raw_edit_reasons,
    )
    capabilities[CommandName.APPLY_SMART_PARSE.value] = _cap(
        CommandName.APPLY_SMART_PARSE,
        _requires_raw(state, "Load raw data before applying smart parse.")
        + raw_edit_reasons,
    )
    capabilities[CommandName.REMOVE_FILES.value] = _cap(
        CommandName.REMOVE_FILES,
        _requires_raw(state, "Load raw data before removing files.") + raw_edit_reasons,
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
    if active_dataset.has_epoch_data or active_dataset.has_datasets:
        epoch_reasons.append(
            "Reset the session before recreating epochs for the active dataset."
        )
    capabilities[CommandName.CREATE_EPOCH.value] = _cap(
        CommandName.CREATE_EPOCH,
        epoch_reasons,
    )

    dataset_reasons = []
    if not active_dataset.has_epoch_data:
        dataset_reasons.append("Create epochs before generating datasets.")
    dataset_reasons.extend(_supervised_label_blockers(state))
    if active_training.is_running:
        dataset_reasons.append("Stop training before changing data splitting.")
    if active_dataset.has_datasets or active_training.has_trainer:
        dataset_reasons.append(
            "Reset the session or start a new session before generating a new "
            "dataset from an existing active dataset."
        )
    capabilities[CommandName.GENERATE_DATASET.value] = _cap(
        CommandName.GENERATE_DATASET,
        dataset_reasons,
    )

    clear_dataset_reasons = []
    if active_training.is_running:
        clear_dataset_reasons.append(
            "Stop training before clearing generated datasets.",
        )
    if not active_dataset.has_datasets and not active_training.has_trainer:
        clear_dataset_reasons.append(
            "No generated datasets or training plans to clear.",
        )
    capabilities[CommandName.CLEAR_DATASETS.value] = CommandCapability(
        command_name=CommandName.CLEAR_DATASETS.value,
        enabled=not clear_dataset_reasons,
        reasons=clear_dataset_reasons,
        destructive=True,
        confirmation_required=not clear_dataset_reasons,
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
    if not active_dataset.has_raw_data:
        train_reasons.append("Load raw data before training.")
    if not active_dataset.has_datasets:
        train_reasons.append("Generate datasets before training.")
    train_reasons.extend(_supervised_label_blockers(state))
    if not active_training.has_model:
        train_reasons.append("Select a model before training.")
    if not active_training.has_training_option:
        train_reasons.append("Configure training options before training.")
    capabilities[CommandName.TRAIN.value] = _cap(
        CommandName.TRAIN,
        train_reasons,
        long_running=True,
        can_auto_execute=False,
        requires_confirmation=True,
        decision_boundary="long_running",
        continue_allowed_after_success=False,
        retry_limit=0,
        stop_after_success=True,
    )

    stop_reasons = []
    if not active_training.is_running:
        stop_reasons.append("No training run is active.")
    capabilities[CommandName.STOP_TRAINING.value] = _cap(
        CommandName.STOP_TRAINING,
        stop_reasons,
    )

    clear_history_reasons = []
    if active_training.is_running:
        clear_history_reasons.append("Stop training before clearing history.")
    if not active_training.has_trainer or state.evaluation.total_plans == 0:
        clear_history_reasons.append("No training history is available to clear.")
    capabilities[CommandName.CLEAR_TRAINING_HISTORY.value] = CommandCapability(
        command_name=CommandName.CLEAR_TRAINING_HISTORY.value,
        enabled=not clear_history_reasons,
        reasons=clear_history_reasons,
        destructive=True,
        confirmation_required=not clear_history_reasons,
    )

    evaluate_reasons = []
    if state.evaluation.total_plans == 0:
        evaluate_reasons.append("Create a training plan before evaluating results.")
    capabilities[CommandName.EVALUATE.value] = _cap(
        CommandName.EVALUATE,
        evaluate_reasons,
    )

    visualize_reasons = []
    if (
        not active_dataset.has_epoch_data
        and state.evaluation.finished_runs == 0
        and not state.visualization.saliency_available
    ):
        visualize_reasons.append(
            "Create epochs, complete training, or configure saliency before "
            "opening visualization views."
        )
    capabilities[CommandName.VISUALIZE.value] = _cap(
        CommandName.VISUALIZE,
        visualize_reasons,
    )

    saliency_reasons = []
    if not (
        active_dataset.has_epoch_data
        or active_dataset.has_datasets
        or active_training.has_trainer
        or (active_training.has_model and active_training.has_training_option)
    ):
        saliency_reasons.append(
            "Create epochs, generate datasets, or select a model and training "
            "settings before querying saliency readiness."
        )
    capabilities[CommandName.SALIENCY.value] = _cap(
        CommandName.SALIENCY,
        saliency_reasons,
    )

    montage_reasons = []
    if not active_dataset.has_epoch_data:
        montage_reasons.append("Create epochs before applying a montage.")
    capabilities[CommandName.APPLY_MONTAGE.value] = _cap(
        CommandName.APPLY_MONTAGE,
        montage_reasons,
    )

    capabilities[CommandName.QUERY_STATE.value] = _cap(
        CommandName.QUERY_STATE,
        [],
    )

    reset_preprocess_reasons = []
    if not active_dataset.has_raw_data:
        reset_preprocess_reasons.append("Load raw data before resetting preprocessing.")
    capabilities[CommandName.RESET_PREPROCESS.value] = CommandCapability(
        command_name=CommandName.RESET_PREPROCESS.value,
        enabled=not reset_preprocess_reasons,
        reasons=reset_preprocess_reasons,
        destructive=True,
        confirmation_required=not reset_preprocess_reasons
        and (
            bool(state.preprocessed.operations)
            or active_dataset.has_epoch_data
            or active_dataset.has_datasets
            or active_training.has_trainer
        ),
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
    can_auto_execute: bool = True,
    requires_confirmation: bool = False,
    decision_boundary: str | None = None,
    continue_allowed_after_success: bool = True,
    retry_limit: int = 2,
    stop_after_success: bool = False,
    blocks_downstream_until_confirmed: bool = False,
) -> CommandCapability:
    return CommandCapability(
        command_name=command_name.value,
        enabled=not reasons,
        reasons=reasons,
        long_running=long_running,
        can_auto_execute=can_auto_execute,
        requires_confirmation=requires_confirmation,
        decision_boundary=decision_boundary,
        continue_allowed_after_success=continue_allowed_after_success,
        retry_limit=retry_limit,
        stop_after_success=stop_after_success,
        blocks_downstream_until_confirmed=blocks_downstream_until_confirmed,
    )


def _requires_raw(
    state: ApplicationStateSnapshot,
    message: str,
) -> list[str]:
    return [] if state.active_dataset.has_raw_data else [message]


def _raw_edit_blockers(state: ApplicationStateSnapshot) -> list[str]:
    active_dataset = state.active_dataset
    active_training = state.active_training
    reasons = []
    if active_dataset.has_epoch_data or active_dataset.has_datasets:
        reasons.append(
            "Reset the session before changing raw files, labels, or metadata "
            "after epoching or dataset generation."
        )
    if active_training.has_trainer:
        reasons.append(
            "Reset the session before changing raw files, labels, or metadata "
            "after trainer creation."
        )
    if active_dataset.is_locked:
        reasons.append(
            "Dataset is locked by downstream preprocessing. Reset before editing "
            "raw files, labels, or metadata."
        )
    return reasons


def _supervised_label_blockers(state: ApplicationStateSnapshot) -> list[str]:
    handoff = state.interpretation.epoch_handoff
    if not state.interpretation.has_applied_interpretation or not handoff:
        return []
    if bool(handoff.get("supervised_ready")):
        return []
    blockers = handoff.get("supervised_blockers")
    if isinstance(blockers, list) and blockers:
        return [str(item) for item in blockers if str(item).strip()]
    return ["No class labels are available for supervised workflows."]
