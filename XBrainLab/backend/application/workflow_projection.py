"""Backend-owned projection of the next workflow action and required decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capabilities import CapabilityPolicy
from .commands import CommandName
from .pipeline_stage import (
    PipelineStage,
    pipeline_stage_contract,
    pipeline_stage_from_snapshot,
)
from .state import ApplicationStateSnapshot


@dataclass(frozen=True)
class WorkflowProjection:
    """Deterministic workflow facts shared by product hosts.

    UI routing and prompt wording remain host responsibilities. This value only
    describes backend workflow truth derived from one state/capability generation.
    """

    recommended_command: str | None
    blocked_command: str | None = None
    decision_fields: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    execution_controls: tuple[str, ...] = ()


def build_workflow_projection(
    state: ApplicationStateSnapshot,
    capabilities: CapabilityPolicy,
) -> WorkflowProjection:
    """Project one atomic state/capability generation into its next action."""
    if state.active_training.is_running:
        return WorkflowProjection(
            recommended_command=None,
            evidence=("Training is currently running.",),
            execution_controls=(CommandName.STOP_TRAINING.value,),
        )

    recommended, blocked = _command_selection(state, capabilities)
    if recommended is None:
        blocked_reasons = _top_blocked_reasons(capabilities)
        if blocked is not None:
            blocked_reasons = tuple(capabilities.get(blocked).reasons)
        return WorkflowProjection(
            recommended_command=None,
            blocked_command=blocked,
            decision_fields=_blocked_decision_fields(blocked, state),
            blocked_reasons=blocked_reasons,
        )

    capability = capabilities.get(recommended)
    return WorkflowProjection(
        recommended_command=recommended,
        decision_fields=decision_fields_for_command(recommended, state),
        evidence=_evidence(recommended, state),
        blocked_reasons=tuple(capability.reasons),
    )


def _command_selection(
    state: ApplicationStateSnapshot,
    capabilities: CapabilityPolicy,
) -> tuple[str | None, str | None]:
    stage = pipeline_stage_from_snapshot(state)
    interpretation_step = _interpretation_next_step(state)
    if interpretation_step is not None:
        candidates = [interpretation_step]
    elif stage is PipelineStage.TRAINED:
        candidates = [
            CommandName.EVALUATE.value,
            CommandName.VISUALIZE.value,
            CommandName.SALIENCY.value,
        ]
    elif stage is PipelineStage.DATASET_READY:
        candidates = [
            CommandName.TRAIN.value
            if state.training.has_model and state.training.has_training_option
            else CommandName.CONFIGURE_TRAINING.value
        ]
    else:
        next_command = (
            pipeline_stage_contract(stage).next_command if stage is not None else None
        )
        candidates = [next_command] if next_command is not None else []

    first_blocked_candidate: str | None = None
    for command_name in candidates:
        try:
            capability = capabilities.get(command_name)
        except KeyError:
            continue
        if capability.enabled:
            return command_name, None
        if first_blocked_candidate is None:
            first_blocked_candidate = command_name
    return None, first_blocked_candidate


def _interpretation_next_step(state: ApplicationStateSnapshot) -> str | None:
    interpretation = state.interpretation
    if interpretation.has_applied_interpretation:
        return None
    if interpretation.has_validation_decision:
        return CommandName.APPLY_INTERPRETATION.value
    if interpretation.has_candidate:
        return CommandName.VALIDATE_INTERPRETATION.value
    if interpretation.has_scan_result:
        return CommandName.PREVIEW_INTERPRETATION.value
    if interpretation.source_path and not state.active_dataset.has_raw_data:
        return CommandName.SCAN_SOURCE.value
    return None


def decision_fields_for_command(
    command_name: str | CommandName,
    state: ApplicationStateSnapshot,
) -> tuple[str, ...]:
    """Return backend-owned user decisions required by one command.

    This contract is intentionally independent from the currently recommended
    command so UI and assistant admission can route any enabled explicit
    request through the same decision schema.
    """
    normalized = (
        command_name.value
        if isinstance(command_name, CommandName)
        else str(command_name or "").strip()
    )
    if normalized == CommandName.SCAN_SOURCE.value:
        return () if state.interpretation.source_path else ("source_path",)
    if normalized == CommandName.PREPROCESS.value:
        return ("preprocess_settings",)
    if normalized == CommandName.APPLY_INTERPRETATION.value:
        return _interpretation_apply_decision_fields(state)
    if normalized == CommandName.CREATE_EPOCH.value:
        return ("target_event", "epoch_window")
    if normalized == CommandName.GENERATE_DATASET.value:
        return ("split_strategy", "training_mode")
    if normalized == CommandName.CONFIGURE_TRAINING.value:
        missing: list[str] = []
        if not state.training.has_model:
            missing.append("model")
        if not state.training.has_training_option:
            missing.append("training_options")
        return tuple(missing or ["training_options"])
    return ()


_INTERPRETATION_STEP_DECISION_FIELD: dict[str, str] = {
    "Choose EEG Data": "eeg_source",
    "Load Labels": "label_source",
    "Review Metadata": "metadata_review",
    "Match Labels": "label_matching",
    "Review and Import": "import_review",
}


def _interpretation_apply_decision_fields(
    state: ApplicationStateSnapshot,
) -> tuple[str, ...]:
    interpretation = state.interpretation
    if (
        not interpretation.pending_confirmation
        and interpretation.validation_decision != "blocked"
    ):
        return ()

    fields: list[str] = []
    for item in interpretation.action_items:
        severity = str(item.get("severity") or "").strip().lower()
        if severity not in {"blocked", "needs_confirmation"}:
            continue
        target_step = str(item.get("target_step") or "").strip()
        field = _INTERPRETATION_STEP_DECISION_FIELD.get(
            target_step,
            "import_review",
        )
        if field not in fields:
            fields.append(field)
    return tuple(fields or ["import_review"])


def _blocked_decision_fields(
    command_name: str | None,
    state: ApplicationStateSnapshot,
) -> tuple[str, ...]:
    """Expose only decisions that can resolve the projected blocker."""
    if command_name == CommandName.APPLY_INTERPRETATION.value:
        return _interpretation_apply_decision_fields(state)
    return ()


def _evidence(
    command_name: str,
    state: ApplicationStateSnapshot,
) -> tuple[str, ...]:
    interpretation = state.interpretation
    if command_name == CommandName.SCAN_SOURCE.value:
        if interpretation.source_path:
            return (f"Data source is selected: {interpretation.source_path}.",)
        return ("No raw EEG data is loaded in the active session.",)
    if command_name == CommandName.PREVIEW_INTERPRETATION.value:
        return (
            "A data source scan is ready for import preview.",
            _interpretation_reference(interpretation),
        )
    if command_name == CommandName.VALIDATE_INTERPRETATION.value:
        return (
            "An import interpretation candidate is ready for validation.",
            _interpretation_reference(interpretation),
        )
    if command_name == CommandName.APPLY_INTERPRETATION.value:
        return (
            "Import validation decision: "
            f"{interpretation.validation_decision or 'ready'}.",
            _interpretation_reference(interpretation),
        )
    if command_name == CommandName.PREPROCESS.value:
        return (f"{state.raw.count} raw EEG file(s) are loaded.",)
    if command_name == CommandName.CREATE_EPOCH.value:
        return (f"{state.preprocessed.count} preprocessed item(s) are available.",)
    if command_name == CommandName.GENERATE_DATASET.value:
        return ("Epoch data is available.",)
    if command_name == CommandName.CONFIGURE_TRAINING.value:
        return ("A generated dataset is available.",)
    if command_name == CommandName.TRAIN.value:
        return ("Dataset, model, and training options are configured.",)
    if state.active_dataset.has_datasets:
        return ("A generated dataset is available.",)
    return ()


def _interpretation_reference(interpretation: Any) -> str:
    for attr in (
        "latest_candidate_id",
        "latest_preview_id",
        "latest_scan_id",
        "source_path",
    ):
        value = getattr(interpretation, attr, None)
        if value:
            return f"Import reference: {value}."
    return "Import reference is available in ApplicationService state."


def _top_blocked_reasons(capabilities: CapabilityPolicy) -> tuple[str, ...]:
    for command_name in (
        CommandName.TRAIN.value,
        CommandName.GENERATE_DATASET.value,
        CommandName.CREATE_EPOCH.value,
        CommandName.PREPROCESS.value,
    ):
        try:
            capability = capabilities.get(command_name)
        except KeyError:
            continue
        reasons = tuple(capability.reasons[:2])
        if reasons:
            return reasons
    return ()
