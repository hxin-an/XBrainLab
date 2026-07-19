"""Direct product-language tests for the backend workflow-stage contract."""

from __future__ import annotations

from dataclasses import replace

import pytest

from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.ui.product_language import (
    decision_field_labels,
    tool_action_label,
    workflow_stage_hint,
    workflow_stage_label,
    workflow_stage_text_label,
)


def test_decision_field_labels_hide_backend_identifiers() -> None:
    assert decision_field_labels(("epoch_window", "target_event", "custom_field")) == [
        "epoch window",
        "target events",
        "custom field",
    ]


def test_tool_action_aliases_share_one_product_label_contract() -> None:
    assert tool_action_label("apply_standard_preprocess") == "Preprocess data"
    assert tool_action_label("epoch_data") == "Create epochs"
    assert tool_action_label("create_epochs") == "Create epochs"


@pytest.mark.parametrize(
    ("stage", "expected_label"),
    [
        ("empty", "No data loaded"),
        ("data_loaded", "Ready for preprocessing"),
        ("preprocessed", "Ready for epoching"),
        ("epoch_ready", "Ready to build dataset"),
        ("dataset_ready", "Dataset ready"),
        ("training", "Training running"),
        ("trained", "Results available"),
    ],
)
def test_workflow_stage_labels_follow_backend_stage_contract(
    stage: str,
    expected_label: str,
) -> None:
    state = replace(ApplicationStateSnapshot.empty(), pipeline_stage=stage)

    assert workflow_stage_label(state) == expected_label
    assert workflow_stage_text_label(stage) == expected_label


def test_workflow_stage_label_does_not_rederive_stage_from_detail_flags() -> None:
    empty = ApplicationStateSnapshot.empty()
    contradictory = replace(
        empty,
        pipeline_stage="data_loaded",
        active_dataset=replace(
            empty.active_dataset,
            has_raw_data=True,
            has_preprocessed_data=True,
        ),
    )

    assert workflow_stage_label(contradictory) == "Ready for preprocessing"


@pytest.mark.parametrize(
    ("stage", "expected_hint"),
    [
        ("empty", "No data loaded · Scan data source"),
        ("data_loaded", "Ready for preprocessing · Preprocess data"),
        ("epoch_ready", "Ready to build dataset · Build training dataset"),
        ("training", "Training running"),
        ("trained", "Results available · Review results"),
    ],
)
def test_workflow_stage_hint_uses_backend_contract(
    stage: str,
    expected_hint: str,
) -> None:
    assert workflow_stage_hint(stage) == expected_hint
