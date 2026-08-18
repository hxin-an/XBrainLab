"""Direct product-language tests for the backend workflow-stage contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.ui.product_language import (
    command_label,
    decision_field_labels,
    tool_action_label,
    workflow_stage_hint,
    workflow_stage_label,
    workflow_stage_text_label,
)


def test_decision_field_labels_hide_backend_identifiers() -> None:
    assert decision_field_labels(("epoch_window", "target_event", "custom_field")) == [
        "EEG epoch window",
        "target events",
        "custom field",
    ]


def test_tool_action_aliases_share_one_product_label_contract() -> None:
    assert tool_action_label("apply_standard_preprocess") == "Preprocess data"
    assert command_label("create_epoch") == "Create EEG epochs"
    assert tool_action_label("create_epoch") == "Create EEG epochs"
    assert tool_action_label("epoch_data") == "Create EEG epochs"
    assert tool_action_label("create_epochs") == "Create EEG epochs"


def test_eeg_epoch_product_copy_does_not_regress_to_ambiguous_epoch_language() -> None:
    root = Path(__file__).resolve().parents[3]
    product_sources = (
        root / "XBrainLab/backend/application/capabilities.py",
        root / "XBrainLab/backend/application/dataset_split_preview.py",
        root / "XBrainLab/backend/application/data_interpretation_choice_schema.py",
        root / "XBrainLab/backend/application/data_interpretation_label_carriers.py",
        root / "XBrainLab/backend/application/data_interpretation_placement.py",
        root / "XBrainLab/backend/application/data_interpretation_review.py",
        root / "XBrainLab/backend/application/data_interpretation_state.py",
        root / "XBrainLab/backend/application/pipeline_stage.py",
        root / "XBrainLab/backend/application/preprocess_service.py",
        root / "XBrainLab/backend/application/resource_guard.py",
        root / "XBrainLab/backend/training/record/eval.py",
        root / "XBrainLab/backend/training/record/train.py",
        root / "XBrainLab/llm/agent/controller.py",
        root / "XBrainLab/llm/pipeline_state.py",
        root / "XBrainLab/llm/tools/definitions/preprocess_def.py",
        root / "XBrainLab/llm/tools/mock/preprocess_mock.py",
        root / "XBrainLab/llm/tools/mock/training_mock.py",
        root / "XBrainLab/ui/dialogs/dataset/data_splitting_preview_dialog.py",
        root / "XBrainLab/ui/panels/dataset/panel.py",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in product_sources)

    assert "Create epochs" not in combined
    assert "creating epochs" not in combined
    assert "Created epochs" not in combined
    assert "Open Epoch Settings" not in combined
    assert "Ready for epoching" not in combined
    assert "after epoching" not in combined
    assert "before epoch setup" not in combined
    assert "supervised epoch" not in combined
    assert "; epoch windows will" not in combined
    assert "downstream epoch setup" not in combined
    assert "for epoch setup" not in combined
    assert "Epoched data" not in combined
    assert "Training configured (Epochs:" not in combined
    assert "Last Epoch Statistics" not in combined
    assert "(Epoch " not in combined
    assert 'set_xlabel("Epochs")' not in combined
    assert '"Total Epochs:' not in combined
    assert 'setHeaderLabels(["Dataset", "Train"' not in combined


@pytest.mark.parametrize(
    ("relative_path", "forbidden", "required"),
    [
        (
            "XBrainLab/ui/chat/action_card.py",
            '"epoch": "Epochs"',
            '"epoch": "Training epochs"',
        ),
        (
            "XBrainLab/ui/chat/action_card.py",
            '"last_epoch": "Last epoch"',
            '"last_epoch": "Last training epoch"',
        ),
        (
            "XBrainLab/backend/application/preprocess_service.py",
            '"Epoch target is not in the reviewed import labels: "',
            '"EEG epoch target is not in the reviewed import labels: "',
        ),
        (
            "XBrainLab/backend/application/training_service.py",
            '"epoch, batch_size, and learning_rate are required."',
            '"Training epochs, batch size, and learning rate are required."',
        ),
        (
            "XBrainLab/backend/application/saliency_render.py",
            '"Epoch data is no longer available"',
            '"EEG epoch data is no longer available"',
        ),
    ],
)
def test_user_visible_epoch_copy_names_the_domain(
    relative_path: str,
    forbidden: str,
    required: str,
) -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / relative_path).read_text(encoding="utf-8")

    assert forbidden not in source
    assert required in source


@pytest.mark.parametrize(
    ("stage", "expected_label"),
    [
        ("empty", "No data loaded"),
        (
            "data_loaded",
            "EEG data loaded · Ready for preprocessing or epoching",
        ),
        ("preprocessed", "Ready for EEG epoching"),
        ("epoch_ready", "Ready to configure split"),
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

    assert workflow_stage_label(contradictory) == (
        "EEG data loaded · Ready for preprocessing or epoching"
    )


@pytest.mark.parametrize(
    ("stage", "expected_hint"),
    [
        ("empty", "No data loaded · Scan data source"),
        (
            "data_loaded",
            "EEG data loaded · Ready for preprocessing or epoching",
        ),
        ("epoch_ready", "Ready to configure split · Configure data splitting"),
        ("training", "Training running"),
        ("trained", "Results available · Review results"),
    ],
)
def test_workflow_stage_hint_uses_backend_contract(
    stage: str,
    expected_hint: str,
) -> None:
    assert workflow_stage_hint(stage) == expected_hint
