"""Backend workflow projection contract shared by UI and assistant hosts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from XBrainLab.backend.application.capabilities import (
    CapabilityPolicy,
    build_capability_policy,
)
from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    EpochStateSnapshot,
    EvaluationStateSnapshot,
    InterpretationStateSnapshot,
    PreprocessedStateSnapshot,
    TrainingStateSnapshot,
)
from XBrainLab.backend.application.workflow_projection import (
    build_workflow_projection,
    decision_fields_for_command,
)
from XBrainLab.backend.supervised_readiness import (
    insufficient_usable_classes_message,
)


def _projection(state: ApplicationStateSnapshot):
    return build_workflow_projection(state, build_capability_policy(state))


def test_projection_owns_data_interpretation_lifecycle_order() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        interpretation=InterpretationStateSnapshot(
            source_path="/datasets/demo",
            has_scan_result=True,
            has_candidate=True,
        ),
    )

    projection = _projection(state)

    assert projection.recommended_command == "validate_interpretation"
    assert projection.decision_fields == ()
    assert "interpretation candidate" in " ".join(projection.evidence).lower()


def test_projection_routes_pending_import_decisions_to_exact_wizard_steps() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        interpretation=InterpretationStateSnapshot(
            source_path="/datasets/demo",
            has_scan_result=True,
            has_candidate=True,
            has_validation_decision=True,
            validation_decision="needs_confirmation",
            pending_confirmation=True,
            action_items=[
                {
                    "issue": "Task metadata is missing.",
                    "impact": "Task grouping is incomplete.",
                    "next_action": "Review task metadata.",
                    "target_step": "Review Metadata",
                    "severity": "needs_confirmation",
                },
                {
                    "issue": "Event roles need review.",
                    "impact": "Training labels are unresolved.",
                    "next_action": "Choose event roles.",
                    "target_step": "Match Labels",
                    "severity": "needs_confirmation",
                },
                {
                    "issue": "No external labels are attached.",
                    "impact": "Supervised training may be limited.",
                    "next_action": "Load labels if needed.",
                    "target_step": "Load Labels",
                    "severity": "warning",
                },
            ],
        ),
    )

    projection = _projection(state)

    assert projection.recommended_command == "apply_interpretation"
    assert projection.decision_fields == ("metadata_review", "label_matching")


def test_projection_falls_back_to_import_review_for_unclassified_confirmation() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        interpretation=InterpretationStateSnapshot(
            source_path="/datasets/demo",
            has_scan_result=True,
            has_candidate=True,
            has_validation_decision=True,
            validation_decision="needs_confirmation",
            pending_confirmation=True,
        ),
    )

    assert _projection(state).decision_fields == ("import_review",)


def test_projection_publishes_epoch_decisions_from_preprocessed_state() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="preprocessed",
        preprocessed=PreprocessedStateSnapshot(available=True, count=3),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
        ),
    )

    projection = _projection(state)

    assert projection.recommended_command == "create_epoch"
    assert projection.decision_fields == ("target_event", "epoch_window")
    assert projection.evidence == ("3 preprocessed item(s) are available.",)


def test_projection_requires_preprocess_settings_before_guided_mutation() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="data_loaded",
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
    )

    projection = _projection(state)

    assert projection.recommended_command == "preprocess"
    assert projection.decision_fields == ("preprocess_settings",)


def test_command_decision_schema_is_available_outside_next_step_projection() -> None:
    state = ApplicationStateSnapshot.empty()

    assert decision_fields_for_command(CommandName.CREATE_EPOCH, state) == (
        "target_event",
        "epoch_window",
    )
    assert decision_fields_for_command("generate_dataset", state) == (
        "split_strategy",
        "training_mode",
    )
    assert decision_fields_for_command("preprocess", state) == ("preprocess_settings",)


def test_projection_chooses_train_only_after_configuration_is_complete() -> None:
    base = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="dataset_ready",
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_datasets=True,
        ),
        training=TrainingStateSnapshot(),
    )

    incomplete = _projection(base)
    configured_state = replace(
        base,
        training=TrainingStateSnapshot(
            has_model=True,
            has_training_option=True,
        ),
        active_training=ActiveTrainingSnapshot(
            has_model=True,
            has_training_option=True,
        ),
    )
    configured = _projection(configured_state)

    assert incomplete.recommended_command == "configure_training"
    assert incomplete.decision_fields == ("model", "training_options")
    assert configured.recommended_command == "train"
    assert configured.decision_fields == ()


def test_ui_agent_manager_does_not_import_llm_workflow_policy() -> None:
    source = Path("XBrainLab/ui/components/agent_manager.py")
    text = source.read_text(encoding="utf-8")

    assert "XBrainLab.llm.agent.decision_context" not in text


def test_projection_does_not_invent_a_command_missing_from_capability_policy() -> None:
    projection = build_workflow_projection(
        ApplicationStateSnapshot.empty(),
        CapabilityPolicy(capabilities={}),
    )

    assert projection.recommended_command is None


def test_trained_projection_skips_a_missing_evaluate_capability() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="trained",
        evaluation=EvaluationStateSnapshot(
            available=True,
            total_plans=1,
            total_runs=1,
            finished_runs=1,
            metrics_available=True,
        ),
    )
    full_policy = build_capability_policy(state)
    partial_policy = CapabilityPolicy(
        capabilities={
            name: capability
            for name, capability in full_policy.capabilities.items()
            if name in {"visualize", "saliency"}
        }
    )

    projection = build_workflow_projection(state, partial_policy)

    assert projection.recommended_command == "visualize"


def test_disabled_dataset_command_is_a_blocker_not_a_recommendation() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="epoch_ready",
        epoch=EpochStateSnapshot(available=True, exists=True, epoch_count=12),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
        ),
        interpretation=InterpretationStateSnapshot(
            has_applied_interpretation=True,
            epoch_handoff={
                "supervised_ready": False,
                "supervised_blockers": ["Resolve label mapping before training."],
            },
        ),
    )

    projection = _projection(state)

    assert projection.recommended_command is None
    assert projection.blocked_command == "generate_dataset"
    assert projection.decision_fields == ()
    assert projection.blocked_reasons == ("Resolve label mapping before training.",)


def _epoch_ready_state_with_missing_import_defaults() -> ApplicationStateSnapshot:
    return replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="epoch_ready",
        epoch=EpochStateSnapshot(
            available=True,
            exists=True,
            epoch_count=6,
            n_channels=4,
            n_times=33,
            event_names=["left", "right"],
            event_ids={"left": 0, "right": 1},
        ),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
        ),
        interpretation=InterpretationStateSnapshot(
            has_applied_interpretation=True,
            class_map={},
            epoch_handoff={
                "supervised_ready": False,
                "supervised_blocker_codes": ["missing_class_labels"],
                "supervised_blockers": [
                    "No class labels are available for supervised epoch defaults."
                ],
                "class_map": {},
                "default_epoch_events": [],
            },
        ),
    )


def test_concrete_multiclass_epoch_contract_supersedes_missing_import_defaults() -> (
    None
):
    state = _epoch_ready_state_with_missing_import_defaults()

    capability = build_capability_policy(state).get(CommandName.GENERATE_DATASET)
    projection = _projection(state)

    assert capability.enabled is True
    assert capability.reasons == []
    assert projection.recommended_command == "generate_dataset"
    assert projection.blocked_command is None
    assert projection.decision_fields == ("split_strategy", "training_mode")


def test_epoch_override_uses_typed_blocker_code_not_display_text() -> None:
    state = _epoch_ready_state_with_missing_import_defaults()
    state = replace(
        state,
        interpretation=replace(
            state.interpretation,
            epoch_handoff={
                **state.interpretation.epoch_handoff,
                "supervised_blockers": ["Import did not provide default class labels."],
            },
        ),
    )

    capability = build_capability_policy(state).get(CommandName.GENERATE_DATASET)

    assert capability.enabled is True
    assert capability.reasons == []


def test_concrete_epoch_also_supersedes_missing_reviewed_class_defaults() -> None:
    state = _epoch_ready_state_with_missing_import_defaults()
    state = replace(
        state,
        interpretation=replace(
            state.interpretation,
            epoch_handoff={
                "supervised_ready": False,
                "supervised_blocker_codes": ["missing_reviewed_target"],
                "supervised_blockers": [
                    "No reviewed class target is available for supervised epoch "
                    "defaults."
                ],
                "class_map": {},
                "default_epoch_events": [],
            },
        ),
    )

    capability = build_capability_policy(state).get(CommandName.GENERATE_DATASET)
    projection = _projection(state)

    assert capability.enabled is True
    assert projection.recommended_command == "generate_dataset"


@pytest.mark.parametrize(
    "blocker_code",
    ["labels_not_applied", "future_policy_blocker"],
)
def test_concrete_epoch_does_not_override_other_typed_blockers(
    blocker_code: str,
) -> None:
    state = _epoch_ready_state_with_missing_import_defaults()
    state = replace(
        state,
        interpretation=replace(
            state.interpretation,
            epoch_handoff={
                **state.interpretation.epoch_handoff,
                "supervised_blocker_codes": [blocker_code],
                # Deliberately reuse old display text: policy must trust the code.
                "supervised_blockers": [
                    "No class labels are available for supervised epoch defaults."
                ],
            },
        ),
    )

    capability = build_capability_policy(state).get(CommandName.GENERATE_DATASET)

    assert capability.enabled is False
    assert capability.reasons == [
        "No class labels are available for supervised epoch defaults."
    ]


def test_legacy_handoff_without_typed_codes_remains_readable_and_fail_closed() -> None:
    state = _epoch_ready_state_with_missing_import_defaults()
    legacy_handoff = dict(state.interpretation.epoch_handoff)
    legacy_handoff.pop("supervised_blocker_codes")
    state = replace(
        state,
        interpretation=replace(
            state.interpretation,
            epoch_handoff=legacy_handoff,
        ),
    )

    capability = build_capability_policy(state).get(CommandName.GENERATE_DATASET)

    assert capability.enabled is False
    assert capability.reasons == [
        "No class labels are available for supervised epoch defaults."
    ]


def test_concrete_epoch_does_not_hide_unresolved_external_label_mapping() -> None:
    state = _epoch_ready_state_with_missing_import_defaults()
    state = replace(
        state,
        interpretation=replace(
            state.interpretation,
            epoch_handoff={
                "supervised_ready": False,
                "supervised_blockers": [
                    "External event values remain unresolved: unknown."
                ],
                "class_map": {},
                "default_epoch_events": [],
            },
        ),
    )

    capability = build_capability_policy(state).get(CommandName.GENERATE_DATASET)
    projection = _projection(state)

    assert capability.enabled is False
    assert capability.reasons == ["External event values remain unresolved: unknown."]
    assert projection.recommended_command is None
    assert projection.blocked_command == "generate_dataset"
    assert projection.blocked_reasons == (
        "External event values remain unresolved: unknown.",
    )


def test_import_default_blockers_remain_before_epoch_creation() -> None:
    state = _epoch_ready_state_with_missing_import_defaults()
    state = replace(
        state,
        pipeline_stage="preprocessed",
        epoch=EpochStateSnapshot(),
        active_dataset=replace(state.active_dataset, has_epoch_data=False),
    )

    capability = build_capability_policy(state).get(CommandName.GENERATE_DATASET)
    projection = _projection(state)

    assert capability.enabled is False
    assert capability.reasons == [
        "Create epochs before generating datasets.",
        "No class labels are available for supervised epoch defaults.",
    ]
    assert projection.recommended_command == "create_epoch"


def test_invalid_epoch_contract_remains_fail_closed_with_exact_reason() -> None:
    base = _epoch_ready_state_with_missing_import_defaults()
    invalid_epochs = (
        (
            replace(base.epoch, epoch_count=0),
            [
                "Create epochs before generating datasets.",
                "No class labels are available for supervised epoch defaults.",
            ],
        ),
        (
            replace(base.epoch, available=False),
            [
                "Create epochs before generating datasets.",
                "No class labels are available for supervised epoch defaults.",
            ],
        ),
        (
            replace(base.epoch, exists=False),
            [
                "Create epochs before generating datasets.",
                "No class labels are available for supervised epoch defaults.",
            ],
        ),
        (
            replace(base.epoch, event_names=[], event_ids=None),
            ["Epoch class label mapping is incomplete or invalid."],
        ),
        (
            replace(base.epoch, event_names=["left"], event_ids={"left": 0}),
            [insufficient_usable_classes_message(["left"])],
        ),
        (
            replace(
                base.epoch,
                event_names=["", "right"],
                event_ids={"": 0, "right": 1},
            ),
            [insufficient_usable_classes_message(["right"])],
        ),
        (
            replace(
                base.epoch,
                event_names=["left", "right"],
                event_ids={"left": 0, "right": 0},
            ),
            ["Epoch class label mapping is incomplete or invalid."],
        ),
        (
            replace(
                base.epoch,
                event_names=["left", "right"],
                event_ids={"left": 0, "other": 1},
            ),
            ["Epoch class label mapping is incomplete or invalid."],
        ),
    )

    for epoch, expected_reasons in invalid_epochs:
        state = replace(base, epoch=epoch)
        capability = build_capability_policy(state).get(CommandName.GENERATE_DATASET)
        projection = _projection(state)

        assert capability.enabled is False
        assert capability.reasons == expected_reasons
        assert projection.recommended_command is None
        assert projection.blocked_command == "generate_dataset"
        assert projection.blocked_reasons == tuple(capability.reasons)


def test_zero_epoch_payload_cannot_generate_dataset_without_import_blocker() -> None:
    base = _epoch_ready_state_with_missing_import_defaults()
    state = replace(
        base,
        epoch=replace(base.epoch, epoch_count=0),
        interpretation=InterpretationStateSnapshot(),
    )

    capability = build_capability_policy(state).get(CommandName.GENERATE_DATASET)
    projection = _projection(state)

    assert capability.enabled is False
    assert capability.reasons == ["Create epochs before generating datasets."]
    assert projection.blocked_command == "generate_dataset"
    assert projection.blocked_reasons == tuple(capability.reasons)
