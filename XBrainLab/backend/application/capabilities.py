"""Command capability policy for the backend application service."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from XBrainLab.backend.model_requirements import minimum_samples_for_model
from XBrainLab.backend.supervised_readiness import (
    MINIMUM_SUPERVISED_CLASS_COUNT,
    has_minimum_usable_classes,
    insufficient_usable_classes_message,
)

from .commands import CommandName
from .epoch_handoff_blockers import (
    EpochHandoffBlockerCode,
    decode_epoch_handoff_blocker_codes,
)
from .state import ApplicationStateSnapshot

RECOVERY_COMMAND_NAMES = frozenset(
    {
        CommandName.STOP_TRAINING.value,
        CommandName.RESET_SESSION.value,
        CommandName.NEW_SESSION.value,
    }
)
UNRELIABLE_STATE_ALLOWED_COMMAND_NAMES = frozenset(
    {CommandName.QUERY_STATE.value, *RECOVERY_COMMAND_NAMES}
)
SALIENCY_TRAINING_ACTIVE_REASON = (
    "Wait for training to finish before configuring saliency."
)
_MISSING_IMPORT_DEFAULT_BLOCKER_CODES = frozenset(
    {
        EpochHandoffBlockerCode.MISSING_CLASS_LABELS,
        EpochHandoffBlockerCode.MISSING_REVIEWED_TARGET,
    }
)


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
    capabilities[CommandName.REVIEW_INTERPRETATION.value] = CommandCapability(
        command_name=CommandName.REVIEW_INTERPRETATION.value,
        enabled=True,
        reasons=[],
        can_auto_execute=True,
        decision_boundary="semantic_review",
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
    if (
        interpretation.has_applied_interpretation
        and not interpretation.pending_confirmation
    ):
        apply_reasons.append("Interpretation has already been applied.")
    apply_needs_confirmation = (
        interpretation.pending_confirmation or active_dataset.has_raw_data
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
    if _has_preprocess_operations(state):
        load_reasons.append(
            "Reset preprocessing before loading new raw data into this session."
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
    if not _has_usable_epoch_payload(state):
        dataset_reasons.append("Create epochs before generating datasets.")
    dataset_reasons.extend(_supervised_label_blockers(state))
    if active_training.is_running:
        dataset_reasons.append("Stop training before changing data splitting.")
    dataset_replacement = (
        active_dataset.has_datasets
        or state.dataset.generator_exists
        or active_training.has_trainer
    )
    dataset_replacement_confirmation = not dataset_reasons and dataset_replacement
    capabilities[CommandName.GENERATE_DATASET.value] = CommandCapability(
        command_name=CommandName.GENERATE_DATASET.value,
        enabled=not dataset_reasons,
        reasons=dataset_reasons,
        destructive=dataset_replacement,
        confirmation_required=dataset_replacement_confirmation,
        requires_confirmation=dataset_replacement_confirmation,
        can_auto_execute=not dataset_replacement_confirmation,
        decision_boundary=(
            "replace_generated_datasets" if dataset_replacement_confirmation else None
        ),
    )

    clear_dataset_reasons = []
    if active_training.is_running:
        clear_dataset_reasons.append(
            "Stop training before clearing generated datasets.",
        )
    if (
        not active_dataset.has_datasets
        and not state.dataset.generator_exists
        and not active_training.has_trainer
    ):
        clear_dataset_reasons.append(
            "No generated datasets or training plans to clear.",
        )
    clear_dataset_confirmation = not clear_dataset_reasons
    capabilities[CommandName.CLEAR_DATASETS.value] = CommandCapability(
        command_name=CommandName.CLEAR_DATASETS.value,
        enabled=not clear_dataset_reasons,
        reasons=clear_dataset_reasons,
        destructive=True,
        confirmation_required=clear_dataset_confirmation,
        requires_confirmation=clear_dataset_confirmation,
        can_auto_execute=not clear_dataset_confirmation,
        decision_boundary="destructive_dataset_cleanup"
        if clear_dataset_confirmation
        else None,
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
    train_reasons.extend(_dataset_split_blockers(state))
    train_reasons.extend(_model_epoch_blockers(state))
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
        can_auto_execute=False,
        continue_allowed_after_success=False,
        retry_limit=0,
        stop_after_success=True,
    )

    clear_history_reasons = []
    if active_training.is_running:
        clear_history_reasons.append("Stop training before clearing history.")
    if not active_training.has_trainer or state.evaluation.total_plans == 0:
        clear_history_reasons.append("No training history is available to clear.")
    clear_history_confirmation = not clear_history_reasons
    capabilities[CommandName.CLEAR_TRAINING_HISTORY.value] = CommandCapability(
        command_name=CommandName.CLEAR_TRAINING_HISTORY.value,
        enabled=not clear_history_reasons,
        reasons=clear_history_reasons,
        destructive=True,
        confirmation_required=clear_history_confirmation,
        requires_confirmation=clear_history_confirmation,
        can_auto_execute=not clear_history_confirmation,
        decision_boundary="destructive_training_history_cleanup"
        if clear_history_confirmation
        else None,
    )

    evaluate_reasons = []
    if state.evaluation.total_plans == 0:
        evaluate_reasons.append("Create a training plan before evaluating results.")
    elif state.evaluation.finished_runs == 0:
        evaluate_reasons.append(
            "Complete at least one training run before evaluating results."
        )
    capabilities[CommandName.EVALUATE.value] = _cap(
        CommandName.EVALUATE,
        evaluate_reasons,
        stop_after_success=True,
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
    if active_training.is_running:
        saliency_reasons.append(SALIENCY_TRAINING_ACTIVE_REASON)
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
    if active_training.is_running:
        reset_preprocess_reasons.append(
            "Stop training before resetting preprocessing.",
        )
    reset_preprocess_confirmation = not reset_preprocess_reasons and (
        bool(state.preprocessed.operations)
        or active_dataset.has_epoch_data
        or active_dataset.has_datasets
        or active_training.has_trainer
    )
    capabilities[CommandName.RESET_PREPROCESS.value] = CommandCapability(
        command_name=CommandName.RESET_PREPROCESS.value,
        enabled=not reset_preprocess_reasons,
        reasons=reset_preprocess_reasons,
        destructive=True,
        confirmation_required=reset_preprocess_confirmation,
        requires_confirmation=reset_preprocess_confirmation,
        can_auto_execute=not reset_preprocess_confirmation,
        decision_boundary="destructive_preprocess_reset"
        if reset_preprocess_confirmation
        else None,
    )

    reset_session_confirmation = has_state
    capabilities[CommandName.RESET_SESSION.value] = CommandCapability(
        command_name=CommandName.RESET_SESSION.value,
        enabled=True,
        reasons=[],
        destructive=True,
        confirmation_required=reset_session_confirmation,
        requires_confirmation=reset_session_confirmation,
        can_auto_execute=not reset_session_confirmation,
        decision_boundary="destructive_session_reset"
        if reset_session_confirmation
        else None,
    )
    new_session_confirmation = has_state
    capabilities[CommandName.NEW_SESSION.value] = CommandCapability(
        command_name=CommandName.NEW_SESSION.value,
        enabled=True,
        reasons=[],
        destructive=True,
        confirmation_required=new_session_confirmation,
        requires_confirmation=new_session_confirmation,
        can_auto_execute=not new_session_confirmation,
        decision_boundary="destructive_new_session"
        if new_session_confirmation
        else None,
    )

    policy = CapabilityPolicy(capabilities)
    if not state.state_reliable:
        return fail_closed_capability_policy(
            policy,
            _unreliable_state_reason(state.read_errors),
        )
    return policy


def fail_closed_capability_policy(
    policy: CapabilityPolicy,
    reason: str,
) -> CapabilityPolicy:
    """Disable uncertain actions while preserving conservative recovery commands."""
    capabilities: dict[str, CommandCapability] = {}
    destructive_recovery = {
        CommandName.RESET_SESSION.value,
        CommandName.NEW_SESSION.value,
    }
    for name, capability in policy.capabilities.items():
        if name in destructive_recovery:
            capabilities[name] = replace(
                capability,
                enabled=True,
                reasons=[],
                destructive=True,
                confirmation_required=True,
                requires_confirmation=True,
                can_auto_execute=False,
                decision_boundary=(
                    capability.decision_boundary or "recovery_confirmation"
                ),
            )
            continue
        if name in UNRELIABLE_STATE_ALLOWED_COMMAND_NAMES:
            capabilities[name] = replace(
                capability,
                enabled=True,
                reasons=[],
            )
            continue
        capabilities[name] = replace(
            capability,
            enabled=False,
            reasons=[reason, *capability.reasons],
            can_auto_execute=False,
        )
    return CapabilityPolicy(capabilities)


def _unreliable_state_reason(read_errors: list[str]) -> str:
    reason = "Backend state could not be verified. Refresh or reset the session."
    if read_errors:
        reason = f"{reason} ({read_errors[0]})"
    return reason


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
        confirmation_required=requires_confirmation,
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
    if _has_preprocess_operations(state):
        reasons.append(
            "Reset preprocessing before changing raw files, labels, or metadata."
        )
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


def _has_preprocess_operations(state: ApplicationStateSnapshot) -> bool:
    return bool(state.preprocessed.operations)


def _dataset_split_blockers(state: ApplicationStateSnapshot) -> list[str]:
    audit = state.dataset.split_summary.get("audit")
    if not isinstance(audit, dict):
        return []
    issues = audit.get("issues")
    if not isinstance(issues, list):
        return []
    reasons: list[str] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("severity", "")).lower() != "error":
            continue
        message = str(issue.get("message", "")).strip()
        if message:
            reasons.append(f"Resolve dataset split audit before training: {message}")
    return reasons


def _model_epoch_blockers(state: ApplicationStateSnapshot) -> list[str]:
    if not (
        state.active_dataset.has_epoch_data
        and state.active_dataset.has_datasets
        and state.active_training.has_model
        and state.active_training.has_training_option
    ):
        return []
    samples = state.epoch.n_times
    sfreq = state.epoch.sfreq
    if samples is None or sfreq is None:
        return []
    requirement = minimum_samples_for_model(
        state.training.model_name,
        sfreq=sfreq,
        model_params=state.training.model_params,
    )
    if requirement is None:
        return []
    if requirement.unsupported_reason:
        return [requirement.unsupported_reason]
    if samples >= requirement.min_samples:
        return []
    duration = float(samples) / float(sfreq)
    return [
        (
            f"{requirement.model_name} needs at least {requirement.min_samples} "
            f"samples ({requirement.min_duration_seconds:.2f}s at {float(sfreq):g}Hz); "
            f"current epoch has {samples} samples ({duration:.2f}s). "
            "Increase the epoch window, lower sampling rate, or choose another model."
        )
    ]


def _supervised_label_blockers(state: ApplicationStateSnapshot) -> list[str]:
    handoff = state.interpretation.epoch_handoff
    normalized_blockers: list[str] = []
    blocker_codes: tuple[EpochHandoffBlockerCode, ...] | None = None
    if state.interpretation.has_applied_interpretation and handoff:
        if bool(handoff.get("supervised_ready")):
            return []
        blockers = handoff.get("supervised_blockers")
        normalized_blockers = (
            [str(item).strip() for item in blockers if str(item).strip()]
            if isinstance(blockers, list)
            else []
        )
        blocker_codes = decode_epoch_handoff_blocker_codes(
            handoff.get("supervised_blocker_codes"),
            expected_count=len(normalized_blockers),
        )
        if normalized_blockers and not _only_missing_import_defaults(blocker_codes):
            return normalized_blockers

    epoch_blockers = _epoch_supervised_class_blockers(state)
    if epoch_blockers:
        return epoch_blockers
    if not state.interpretation.has_applied_interpretation or not handoff:
        return []
    if _has_authoritative_supervised_epoch_contract(
        state
    ) and _only_missing_import_defaults(blocker_codes):
        # An explicit epoch selection replaces absent import defaults. Unknown
        # or unresolved import blockers remain fail-closed below.
        return []
    if normalized_blockers:
        return normalized_blockers
    return ["No class labels are available for supervised workflows."]


def _epoch_supervised_class_blockers(
    state: ApplicationStateSnapshot,
) -> list[str]:
    if not _has_usable_epoch_payload(state):
        return []
    event_ids = state.epoch.event_ids
    if not isinstance(event_ids, dict):
        return ["Epoch class label mapping is incomplete or invalid."]
    labels = [str(label).strip() for label in event_ids if str(label).strip()]
    if not has_minimum_usable_classes(labels):
        return [insufficient_usable_classes_message(labels)]
    if not _has_authoritative_supervised_epoch_contract(state):
        return ["Epoch class label mapping is incomplete or invalid."]
    return []


def _has_usable_epoch_payload(state: ApplicationStateSnapshot) -> bool:
    epoch_count = state.epoch.epoch_count
    return bool(
        state.active_dataset.has_epoch_data
        and state.epoch.available
        and state.epoch.exists
        and isinstance(epoch_count, int)
        and not isinstance(epoch_count, bool)
        and epoch_count > 0
    )


def _has_authoritative_supervised_epoch_contract(
    state: ApplicationStateSnapshot,
) -> bool:
    epoch = state.epoch
    if not _has_usable_epoch_payload(state):
        return False

    event_ids = epoch.event_ids
    if not isinstance(event_ids, dict):
        return False

    labels: list[str] = []
    identifiers: list[int] = []
    for raw_label, raw_identifier in event_ids.items():
        label = str(raw_label).strip()
        if (
            not label
            or not isinstance(raw_identifier, int)
            or isinstance(raw_identifier, bool)
        ):
            return False
        labels.append(label)
        identifiers.append(raw_identifier)

    if (
        len(set(labels)) < MINIMUM_SUPERVISED_CLASS_COUNT
        or len(set(identifiers)) < MINIMUM_SUPERVISED_CLASS_COUNT
    ):
        return False

    event_names = [str(name).strip() for name in epoch.event_names]
    return (
        all(event_names)
        and len(event_names) == len(set(event_names))
        and set(event_names) == set(labels)
    )


def _only_missing_import_defaults(
    blocker_codes: tuple[EpochHandoffBlockerCode, ...] | None,
) -> bool:
    return bool(blocker_codes) and all(
        blocker in _MISSING_IMPORT_DEFAULT_BLOCKER_CODES for blocker in blocker_codes
    )
