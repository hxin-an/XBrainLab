"""Card rendering tests; structured stress values are not tool-admission evidence."""

from __future__ import annotations

import re

import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import QBoxLayout

from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationRisk,
)
from XBrainLab.ui.chat.action_card import AssistantConfirmationCard


def _visible_text(text: str) -> str:
    return text.replace("\u200b", "")


def _show_card(
    card: AssistantConfirmationCard,
    qtbot,
    request: AgentConfirmationRequest,
    *,
    width: int,
) -> None:
    card.setFixedWidth(width)
    card.present(request)
    card.show()
    card.adjustSize()
    qtbot.wait(20)


def _row_by_label(card: AssistantConfirmationCard, label: str):
    return next(
        row for row in card.proposal_rows if _visible_text(row.label.text()) == label
    )


def test_compact_actions_share_a_row_when_their_measured_widths_fit(
    confirmation_card,
    qtbot,
) -> None:
    request = AgentConfirmationRequest.for_action(
        command_name="compute_saliency",
        params={"batch_size": 16},
        action_label="Apply reviewed settings",
        description="Use the reviewed training configuration.",
        destructive=False,
        publication_generation=7,
    )
    confirmation_card.present(request)
    confirmation_card.ensurePolished()
    layout = confirmation_card.layout()
    assert layout is not None
    card_margins = layout.contentsMargins()
    button_margins = confirmation_card.button_layout.contentsMargins()
    measured_width = (
        card_margins.left()
        + card_margins.right()
        + button_margins.left()
        + button_margins.right()
        + confirmation_card.primary_button.sizeHint().width()
        + confirmation_card.secondary_button.sizeHint().width()
        + confirmation_card.button_layout.spacing()
    )

    confirmation_card.setFixedWidth(measured_width)
    confirmation_card.show()
    qtbot.wait(20)

    assert (
        confirmation_card.button_layout.direction() == QBoxLayout.Direction.LeftToRight
    )


@pytest.fixture
def confirmation_card(qtbot) -> AssistantConfirmationCard:
    card = AssistantConfirmationCard()
    qtbot.addWidget(card)
    return card


@pytest.mark.parametrize("width", [320, 420, 760])
def test_action_details_use_human_labels_and_structured_values_at_target_widths(
    confirmation_card,
    qtbot,
    width: int,
) -> None:
    request = AgentConfirmationRequest.for_action(
        command_name="compute_saliency",
        params={
            "evaluation_option": "val_auc",
            "optimizer_settings": {
                "amsgrad": False,
                "beta_1": 0.9,
            },
            "recording_selection_strategy_for_cross_session_validation": (
                "prefer_subject_balanced_recordings"
            ),
            "save_checkpoints_every": 5,
        },
        action_label=(
            "Apply the complete reviewed training configuration and checkpoint policy"
        ),
        description="Use the reviewed settings for the next training run.",
        destructive=False,
        publication_generation=8,
    )

    _show_card(
        confirmation_card,
        qtbot,
        request,
        width=width,
    )

    card = confirmation_card
    assert card.details_title.text() == "Action details"
    assert card.reason_title.text() == "Reason"
    assert card.reason_label.text() == request.description
    assert card.proposal_scroll.horizontalScrollBar().maximum() == 0
    assert card.proposal_scroll.verticalScrollBar().maximum() == 0

    labels = [_visible_text(row.label.text()) for row in card.proposal_rows]
    assert labels == [
        "Model selection",
        "Optimizer settings",
        "Recording selection strategy for cross session validation",
        "Checkpoint interval",
    ]
    assert all("_" not in label for label in labels)

    evaluation = _row_by_label(card, "Model selection")
    assert evaluation.proposed_caption.text() == "Details"
    assert _visible_text(evaluation.proposed_value.text()) == "Validation AUC"

    optimizer = _row_by_label(card, "Optimizer settings")
    optimizer_text = _visible_text(optimizer.proposed_value.text())
    assert optimizer_text == "AMSGrad: No\nBeta 1: 0.9"
    assert not re.search(r"[{}\[\]\"]", optimizer_text)
    assert optimizer.proposed_value.accessibleDescription() == optimizer_text

    for row in card.proposal_rows:
        assert row.width() <= card.proposal_scroll.viewport().width()
        assert row.label.wordWrap()
        for value_label in (row.proposed_value,):
            for segment in re.split(r"[\s\u200b]+", value_label.text()):
                if segment:
                    assert (
                        value_label.fontMetrics().horizontalAdvance(segment)
                        <= value_label.contentsRect().width()
                    )


@pytest.mark.parametrize("width", [320, 420, 760])
def test_large_action_details_delegate_vertical_scroll_and_keep_every_value(
    confirmation_card,
    qtbot,
    width: int,
) -> None:
    params = {
        f"training_parameter_{index:02d}": (
            f"subject_balanced_value_{index:02d}_" + ("W" * 80)
        )
        for index in range(14)
    }
    request = AgentConfirmationRequest.for_action(
        command_name="compute_saliency",
        params=params,
        action_label="Apply reviewed settings",
        description="Review every setting before applying the configuration.",
        destructive=False,
        publication_generation=11,
    )

    _show_card(confirmation_card, qtbot, request, width=width)

    card = confirmation_card
    scroll = card.proposal_scroll
    assert len(card.proposal_rows) == len(params)
    assert scroll.verticalScrollBar().maximum() == 0
    assert scroll.horizontalScrollBar().maximum() == 0
    assert (
        card.proposal_rows[0].proposed_value.accessibleDescription()
        == params["training_parameter_00"]
    )
    assert (
        card.proposal_rows[-1].proposed_value.accessibleDescription()
        == params["training_parameter_13"]
    )
    for row in card.proposal_rows:
        for label in (row.label, row.proposed_value):
            if not label.isVisible() or not label.text():
                continue
            needed = label.fontMetrics().boundingRect(
                QRect(0, 0, max(label.contentsRect().width(), 1), 10_000),
                int(
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignTop
                    | Qt.TextFlag.TextWordWrap
                ),
                label.text(),
            )
            assert needed.height() <= label.contentsRect().height() + 3
    assert card.primary_button.text() == "Compute saliency"
    assert card.secondary_button.text() == "Cancel"

    viewport = scroll.viewport()
    last_row = card.proposal_rows[-1]
    last_top = last_row.mapTo(viewport, QPoint(0, 0)).y()
    assert last_top < viewport.height()
    assert last_top + last_row.height() <= viewport.height() + 2


@pytest.mark.parametrize("width", [320, 420, 760])
def test_confirmation_buttons_use_compact_complete_labels_without_overflow(
    confirmation_card,
    qtbot,
    width: int,
) -> None:
    request = AgentConfirmationRequest.for_action(
        command_name="compute_saliency",
        params={"batch_size": 16},
        action_label=(
            "Apply every reviewed training parameter and checkpoint setting now"
        ),
        description="Use the reviewed training configuration.",
        destructive=False,
        publication_generation=4,
    )

    _show_card(confirmation_card, qtbot, request, width=width)

    card = confirmation_card
    assert card.primary_button.text() == "Compute saliency"
    assert card.secondary_button.text() == "Cancel"
    for button in (card.secondary_button, card.primary_button):
        assert button.accessibleName() == button.text()
        assert (
            button.fontMetrics().horizontalAdvance(button.text()) + 24
            <= button.contentsRect().width()
        )
        assert button.mapTo(card, QPoint(0, 0)).x() >= 0
        assert button.mapTo(card, button.rect().bottomRight()).x() < card.width()


@pytest.mark.parametrize("width", [320, 420, 760])
def test_high_risk_confirmation_stays_explicit_and_emits_the_exact_request(
    confirmation_card,
    qtbot,
    width: int,
) -> None:
    request = AgentConfirmationRequest.for_action(
        command_name="reset_preprocessing",
        params={},
        action_label=("Reset preprocessing while keeping the loaded EEG dataset"),
        description="This restores the current workflow to raw loaded data.",
        destructive=True,
        publication_generation=12,
    )
    decisions: list[tuple[AgentConfirmationRequest, bool]] = []
    confirmation_card.decision_requested.connect(
        lambda pending, approved: decisions.append((pending, approved))
    )

    _show_card(confirmation_card, qtbot, request, width=width)

    card = confirmation_card
    assert card.title_label.text() == "High-risk confirmation"
    assert card.description_label.text() == request.action_label
    assert card.description_label.isVisibleTo(card)
    assert card.reason_title.text() == "Reason"
    assert card.secondary_button.text() == "Cancel"
    assert card.primary_button.text() == "Reset preprocessing"
    assert card.property("destructive") is True

    card.primary_button.click()

    assert decisions == [(request, True)]
    assert card.primary_button.isEnabled() is False
    assert card.secondary_button.isEnabled() is False
    assert card.primary_button.text() == "Working..."
    assert card.primary_button.accessibleName() == "Working..."


@pytest.mark.parametrize("width", [300, 520])
def test_start_training_renders_compact_long_running_confirmation(
    confirmation_card,
    qtbot,
    width: int,
) -> None:
    impact = (
        "Starts a potentially long GPU or CPU job using the configured resources. "
        "You can stop it after it starts."
    )
    request = AgentConfirmationRequest.for_action(
        command_name="start_training",
        params={},
        action_label="Start training",
        description="Run the reviewed training configuration.",
        destructive=False,
        publication_generation=21,
        risk=AgentConfirmationRisk(
            long_running=True,
            decision_boundary="long_running",
            impact_text=impact,
        ),
    )

    _show_card(confirmation_card, qtbot, request, width=width)

    card = confirmation_card
    assert card.title_label.text() == "Start training"
    assert card.description_label.isHidden()
    assert not hasattr(card, "impact_title")
    assert card.impact_label.text() == impact
    assert card.impact_label.isVisibleTo(card)
    assert card.impact_label.wordWrap()
    assert card.property("riskLongRunning") is True
    assert card.property("decisionBoundary") == "long_running"
    assert card.reason_title.isHidden()
    assert card.reason_label.isHidden()
    assert card.details_title.isHidden()
    assert card.proposal_scroll.isHidden()
    assert card.primary_button.text() == "Confirm"
    assert card.secondary_button.text() == "Cancel"
    for widget in (card.impact_label, card.primary_button):
        assert widget.mapTo(card, QPoint(0, 0)).x() >= 0
        assert widget.mapTo(card, widget.rect().bottomRight()).x() < card.width()
