"""Coverage tests for ChatPanel - 59 uncovered lines."""

from __future__ import annotations

import gc
import re
import weakref
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEvent, QMimeData, QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QToolButton,
    QWidget,
)

from XBrainLab.backend.controller.chat_controller import (
    ChatController,
    ChatHistoryReplacement,
    ChatHistoryReplacementKind,
    ChatMessagePresentationKind,
    ChatPanelTarget,
    ChatResponseAction,
    ChatResponseActionKind,
)
from XBrainLab.chat_contract import MAX_CHAT_MESSAGE_CONTENT_LENGTH
from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.ui.chat.message_bubble import MessageBubble
from XBrainLab.ui.chat.presentation import (
    ChatResponseActionSelectionView,
    ChatResponseActionsView,
    ChatResponseActionView,
    ChatResponseActionViewKind,
    ChatResponsePanelTargetView,
    ChatTurnCancelability,
    ChatTurnPresentation,
    ChatTurnPresentationPhase,
    present_assistant_activity,
)


def _assert_inside_panel_on_all_sides(panel: QWidget, widget: QWidget) -> None:
    top_left = widget.mapTo(panel, QPoint(0, 0))
    bottom_right = widget.mapTo(panel, widget.rect().bottomRight())

    assert top_left.x() >= 0
    assert top_left.y() >= 0
    assert bottom_right.x() < panel.width()
    assert bottom_right.y() < panel.height()


@pytest.fixture
def chat_panel(qtbot):
    with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
        from XBrainLab.ui.chat.panel import ChatPanel

        panel = ChatPanel()
        qtbot.addWidget(panel)
        panel.set_runtime_state("ready")
        return panel


class TestChatPanelInit:
    def test_assistant_base_palette_uses_main_gui_theme_tokens(self) -> None:
        from XBrainLab.ui.chat.styles import (
            ASSISTANT_ACCENT,
            ASSISTANT_BACKGROUND,
            ASSISTANT_BORDER,
        )
        from XBrainLab.ui.styles.theme import Theme

        assert ASSISTANT_BACKGROUND == Theme.BACKGROUND_DARK
        assert ASSISTANT_BORDER == Theme.METRICS_TABLE_GRID
        assert ASSISTANT_ACCENT == Theme.BLUE_PRIMARY

    def test_assistant_styles_do_not_define_a_detached_hex_palette(self) -> None:
        style_source = (
            Path(__file__).resolve().parents[4]
            / "XBrainLab"
            / "ui"
            / "chat"
            / "styles.py"
        ).read_text(encoding="utf-8")

        assert re.search(r"#[0-9A-Fa-f]{3,8}", style_source) is None

    def test_ready_cpu_runtime_is_persistently_visible_in_header(
        self,
        chat_panel,
    ) -> None:
        chat_panel.set_runtime_state("ready", execution_device="cpu")

        assert chat_panel.header_status_text == "Local · CPU"

    def test_loading_and_empty_states_are_centered_in_the_main_content(
        self,
        qtbot,
    ) -> None:
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.resize(460, 680)
            panel.set_runtime_state("loading")
            panel.show()
            qtbot.wait(20)

        viewport = panel.scroll_area.viewport()
        assert viewport is not None

        def center_distance(widget: QWidget) -> int:
            widget_top = widget.mapTo(viewport, QPoint(0, 0)).y()
            widget_center = widget_top + (widget.height() // 2)
            return abs(widget_center - (viewport.height() // 2))

        assert center_distance(panel.runtime_state_widget) <= 80

        panel.set_runtime_state("ready")
        qtbot.wait(20)

        assert panel.runtime_state_widget.isHidden()
        assert panel.empty_state_widget.isVisibleTo(panel)
        assert center_distance(panel.empty_state_widget) <= 100

    def test_state_surfaces_are_unframed_and_bounded_in_a_wide_panel(
        self,
        qtbot,
    ) -> None:
        from XBrainLab.ui.chat.styles import (
            RUNTIME_STATE_STYLE,
            TURN_ACTIVITY_STYLE,
        )

        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.resize(760, 680)
            panel.set_runtime_state("loading")
            panel.show()
            qtbot.wait(20)

        assert "background-color: transparent" in RUNTIME_STATE_STYLE
        assert "border: none" in RUNTIME_STATE_STYLE
        assert "background-color: transparent" in TURN_ACTIVITY_STYLE
        assert "border: none" in TURN_ACTIVITY_STYLE
        assert panel.runtime_state_widget.width() <= 540

        panel.set_runtime_state("ready")
        qtbot.wait(20)

        assert panel.empty_state_widget.width() <= 560

    def test_empty_state_suggestions_fill_the_composer_without_auto_sending(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(460, 680)
        chat_panel.show()
        qtbot.wait(10)

        prompts = [
            button
            for button in chat_panel.suggestion_prompt_buttons
            if button.isVisibleTo(chat_panel.empty_state_widget)
        ]

        assert chat_panel.empty_state_title.text() == "Start with your EEG data"
        assert chat_panel.composer_host.parentWidget() is chat_panel.control_panel
        assert len(prompts) == 3
        assert [button.text() for button in prompts] == [
            "Import EEG data",
            "Check supported formats",
            "Explain the import workflow",
        ]
        assert {button.chevron_label.text() for button in prompts} == {
            "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"
        }

        emitted: list[str] = []
        chat_panel.send_message.connect(emitted.append)
        prompts[0].click()

        assert chat_panel.input_field.text() == prompts[0].property("assistantPrompt")
        assert chat_panel.send_btn.isEnabled()
        assert emitted == []

    def test_empty_state_copy_and_prompts_follow_backend_stage(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.set_runtime_state("ready", "")
        chat_panel.set_product_status(
            "Results available",
            "Ready",
            ["evaluate", "visualize"],
        )
        chat_panel.resize(420, 680)
        chat_panel.show()
        qtbot.wait(20)

        assert chat_panel.empty_state_title.text() == "Explore your results"
        assert chat_panel.empty_state_intro.text() == (
            "Ask me to explain metrics, review available analyses, or recommend "
            "what to inspect next."
        )
        assert [button.text() for button in chat_panel.suggestion_prompt_buttons] == [
            "Explain these results",
            "Review available analyses",
            "Suggest the next analysis",
        ]
        assert chat_panel.empty_state_widget.accessibleDescription() == (
            "Current workflow stage: Results available."
        )

    def test_two_line_composer_is_primary_control_and_empty_send_is_disabled(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(460, 680)
        chat_panel.show()
        qtbot.wait(10)

        assert not hasattr(chat_panel, "mode_selector_widget")
        assert not hasattr(chat_panel, "mode_section_label")
        assert 52 <= chat_panel.input_field.height() <= 58
        assert chat_panel.input_field.placeholderText() == (
            "Ask about the current EEG workflow..."
        )
        assert chat_panel.input_field.accessibleName() == "Assistant message"
        assert "EEG workflow" in chat_panel.input_field.accessibleDescription()
        assert chat_panel.send_btn.isEnabled() is False

        chat_panel.input_field.setText("Explain the current settings")
        qtbot.wait(10)
        assert chat_panel.send_btn.isEnabled()

        chat_panel.input_field.clear()
        qtbot.wait(10)
        assert chat_panel.send_btn.isEnabled() is False

    def test_manual_scroll_position_is_preserved_when_assistant_message_arrives(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(320, 520)
        chat_panel.show()
        for index in range(20):
            chat_panel.append_message(
                "assistant",
                f"Message {index}: " + ("long workflow explanation " * 4),
            )
        qtbot.wait(20)

        scroll_bar = chat_panel.scroll_area.verticalScrollBar()
        assert scroll_bar is not None
        assert scroll_bar.maximum() > 0
        scroll_bar.setValue(0)
        qtbot.wait(10)

        chat_panel.append_message(
            "assistant",
            "A new result arrived while the user was reading earlier messages.",
        )
        qtbot.wait(20)

        assert scroll_bar.value() <= 2

    def test_response_actions_are_attached_to_the_message_area(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        controller = ChatController()
        chat_panel.connect_controller(controller)
        chat_panel.resize(420, 680)
        chat_panel.show()
        controller.add_agent_message(
            "The next safe step is to review Training.",
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            presentation_id="attached-action",
            actions=(
                ChatResponseAction(
                    action_id="open-training",
                    label="Open Training",
                    kind=ChatResponseActionKind.OPEN_PANEL,
                    panel=ChatPanelTarget.TRAINING,
                ),
            ),
        )
        qtbot.wait(20)

        assert chat_panel.scroll_area.isAncestorOf(chat_panel.response_actions_widget)
        assert chat_panel.response_actions_widget.isVisibleTo(panel := chat_panel)
        assert panel.response_action_title.text() == "Suggested next step"

    def test_confirmation_card_emits_the_exact_correlated_request(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        request = AgentConfirmationRequest.for_action(
            command_name="configure_training",
            params={"batch_size": 16},
            action_label="Apply training settings",
            description="Reduce GPU memory pressure before training.",
            destructive=False,
            publication_generation=7,
        )
        decisions: list[AgentConfirmationResolution] = []
        chat_panel.confirmation_decision_requested.connect(decisions.append)

        chat_panel.show_confirmation_request(
            request,
            current_values={"Batch size": "32"},
        )
        chat_panel.resize(420, 680)
        chat_panel.show()
        qtbot.wait(20)

        card = chat_panel.confirmation_card_widget
        assert card.isVisibleTo(chat_panel)
        assert card.title_label.text() == "Suggested change"
        assert card.proposal_rows[0].label.text() == "Batch size"
        assert card.proposal_rows[0].current_caption.text() == "Current"
        assert card.proposal_rows[0].current_value.text() == "32"
        assert card.proposal_rows[0].proposed_caption.text() == "Proposed"
        assert card.proposal_rows[0].proposed_value.text() == "16"
        assert card.context_warning.isHidden()

        card.primary_button.click()

        assert len(decisions) == 1
        assert decisions[0].matches(request)
        assert decisions[0].status is AgentConfirmationResolutionStatus.APPROVED
        assert card.isVisibleTo(chat_panel)
        assert card.primary_button.isEnabled() is False
        assert card.secondary_button.isEnabled() is False

    def test_action_confirmation_is_not_presented_as_a_setting_change(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        request = AgentConfirmationRequest.for_action(
            command_name="start_training",
            params={
                "checkpoint_policy": "disabled",
                "output_directory": "./output",
            },
            action_label="Start training",
            description="Start the training process.",
            destructive=False,
            publication_generation=7,
        )

        chat_panel.show_confirmation_request(request)
        chat_panel.resize(420, 680)
        chat_panel.show()
        qtbot.wait(20)

        card = chat_panel.confirmation_card_widget
        assert card.title_label.text() == "Confirmation required"
        assert card.description_label.text() == "Start training"
        assert card.description_label.isVisibleTo(chat_panel)
        assert card.secondary_button.text() == "Cancel"
        assert card.primary_button.text() == "Start training"

    def test_confirmation_card_stacks_actions_without_clipping_in_narrow_panel(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        request = AgentConfirmationRequest.for_action(
            command_name="configure_training",
            params={"batch_size": 16},
            action_label="Apply change",
            description="The current configuration may exceed available VRAM.",
            destructive=False,
            publication_generation=7,
        )
        chat_panel.resize(320, 680)
        chat_panel.show_confirmation_request(
            request,
            current_values={"Batch size": "32"},
        )
        chat_panel.show()
        qtbot.wait(20)

        card = chat_panel.confirmation_card_widget
        assert card.button_layout.direction() == QBoxLayout.Direction.TopToBottom
        for button in (card.secondary_button, card.primary_button):
            text_width = button.fontMetrics().horizontalAdvance(button.text()) + 24
            assert text_width <= button.contentsRect().width()

    def test_confirmation_card_keeps_compact_actions_inline_at_420px(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        request = AgentConfirmationRequest.for_action(
            command_name="configure_training",
            params={"batch_size": 16},
            action_label="Apply reviewed settings",
            description="Use the reviewed training configuration.",
            destructive=False,
            publication_generation=7,
        )
        chat_panel.resize(420, 680)
        chat_panel.show_confirmation_request(
            request,
            current_values={"Batch size": "32"},
        )
        chat_panel.show()
        qtbot.wait(20)

        card = chat_panel.confirmation_card_widget
        assert card.button_layout.direction() == QBoxLayout.Direction.LeftToRight
        for button in (card.secondary_button, card.primary_button):
            required_width = button.fontMetrics().horizontalAdvance(button.text()) + 24
            assert required_width <= button.contentsRect().width()

    def test_confirmation_card_shows_stale_context_warning(self, chat_panel) -> None:
        request = AgentConfirmationRequest.for_action(
            command_name="configure_training",
            params={"output_path": "/tmp/new/output/path"},
            action_label="Apply change",
            description="Use the reviewed output path.",
            destructive=False,
            publication_generation=7,
        )

        chat_panel.show_confirmation_request(
            request,
            current_values={"Output path": "/tmp/old/output/path"},
            current_context_changed=True,
        )

        card = chat_panel.confirmation_card_widget
        assert card.context_warning.isHidden() is False
        assert "workflow changed" in card.context_warning.text().lower()
        assert "AssistantActionContextWarning" in card.context_warning.styleSheet()
        assert "background-color" in card.context_warning.styleSheet()
        assert card.proposal_rows[0].current_value.accessibleDescription() == (
            "/tmp/old/output/path"
        )
        assert card.proposal_rows[0].proposed_value.accessibleDescription() == (
            "/tmp/new/output/path"
        )

    def test_confirmation_card_uses_transcript_as_its_only_vertical_scroll_owner(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        params = {
            f"parameter_{index:02d}": f"{index}-" + ("W" * 160) for index in range(12)
        }
        request = AgentConfirmationRequest.for_action(
            command_name="configure_training",
            params=params,
            action_label="Apply reviewed settings",
            description=(
                "Review every proposed setting before applying this configuration."
            ),
            destructive=False,
            publication_generation=9,
        )
        decisions: list[AgentConfirmationResolution] = []
        chat_panel.confirmation_decision_requested.connect(decisions.append)
        chat_panel.resize(320, 680)
        chat_panel.show_confirmation_request(request)
        chat_panel.show()
        qtbot.wait(30)

        card = chat_panel.confirmation_card_widget
        scrollbar = card.proposal_scroll.verticalScrollBar()
        assert scrollbar.maximum() == 0
        assert card.proposal_scroll.horizontalScrollBar().maximum() == 0
        assert chat_panel.scroll_area.horizontalScrollBar().maximum() == 0
        assert chat_panel.scroll_area.verticalScrollBar().maximum() > 0
        visible_value_labels = [row.proposed_value for row in card.proposal_rows]
        assert visible_value_labels
        for value_label in visible_value_labels:
            value_segments = [
                segment
                for segment in re.split(r"[\s\u200b]+", value_label.text())
                if segment
            ]
            assert (
                max(
                    value_label.fontMetrics().horizontalAdvance(segment)
                    for segment in value_segments
                )
                <= value_label.contentsRect().width()
            )
        copy_target = visible_value_labels[-1]
        copy_target.setSelection(0, len(copy_target.text()))
        copy_target.setFocus()
        qtbot.keyClick(
            copy_target,
            Qt.Key.Key_C,
            modifier=Qt.KeyboardModifier.ControlModifier,
        )
        clipboard = QApplication.clipboard()
        assert clipboard is not None
        assert clipboard.text() == copy_target.accessibleDescription()
        assert "\u200b" not in clipboard.text()

        transcript_scrollbar = chat_panel.scroll_area.verticalScrollBar()
        transcript_scrollbar.setValue(transcript_scrollbar.maximum())
        qtbot.wait(20)
        viewport = chat_panel.scroll_area.viewport()
        for button in (card.secondary_button, card.primary_button):
            origin = button.mapTo(viewport, QPoint(0, 0))
            assert origin.x() >= 0
            assert origin.y() >= 0
            assert origin.x() + button.width() <= viewport.width()
            assert origin.y() + button.height() <= viewport.height()

        card.secondary_button.click()
        assert len(decisions) == 1
        assert decisions[0].matches(request)
        assert decisions[0].status is AgentConfirmationResolutionStatus.CANCELLED

    def test_confirmation_card_replaces_stale_request_and_blocks_double_submit(
        self,
        chat_panel,
    ) -> None:
        first = AgentConfirmationRequest.for_action(
            command_name="configure_training",
            params={"batch_size": 32},
            action_label="Apply training settings",
            description="Use the selected batch size.",
            destructive=False,
            publication_generation=3,
        )
        second = AgentConfirmationRequest.for_action(
            command_name="clear_dataset",
            params={},
            action_label="Clear dataset",
            description=("Remove loaded EEG data and its downstream workspace state."),
            destructive=True,
            publication_generation=3,
        )
        decisions: list[AgentConfirmationResolution] = []
        chat_panel.confirmation_decision_requested.connect(decisions.append)

        chat_panel.show_confirmation_request(first)
        chat_panel.show_confirmation_request(second)
        card = chat_panel.confirmation_card_widget

        assert card.request_id == second.request_id
        assert card.title_label.text() == "High-risk confirmation"
        assert card.secondary_button.text() == "Cancel"
        card.primary_button.click()
        card.primary_button.click()

        assert len(decisions) == 1
        assert decisions[0].matches(second)
        assert decisions[0].status is AgentConfirmationResolutionStatus.APPROVED

        chat_panel.set_confirmation_submitting(second.request_id, False)
        assert card.primary_button.isEnabled()
        assert card.primary_button.text() == "Clear dataset"

    def test_composer_caps_programmatic_oversized_prompt_before_submission(
        self,
        chat_panel,
    ) -> None:
        chat_panel.input_field.setText("x" * 200_000)

        assert len(chat_panel.input_field.text()) == MAX_CHAT_MESSAGE_CONTENT_LENGTH

        chat_panel.input_field.clear()
        clipboard_payload = QMimeData()
        clipboard_payload.setText("x" * 200_000)
        chat_panel.input_field.insertFromMimeData(clipboard_payload)

        assert len(chat_panel.input_field.text()) == MAX_CHAT_MESSAGE_CONTENT_LENGTH

    def test_composer_waits_for_runtime_readiness(self, qtbot):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)

        assert panel.input_field.isEnabled() is False
        assert panel.send_btn.isEnabled() is False
        assert panel.input_field.placeholderText() == "Set up assistant"
        assert panel.input_widget.isHidden() is False
        assert panel.runtime_state_widget.isHidden() is False
        assert panel.runtime_state_title.text() == "Assistant setup required"
        assert panel.setup_btn.isHidden() is False
        assert panel.setup_btn.isEnabled()
        assert panel.retry_runtime_btn.isHidden()
        assert panel.retry_runtime_btn.isEnabled() is False
        assert panel.runtime_progress.isHidden()

        panel.set_runtime_state("loading", "Loading model")
        assert panel.input_field.isEnabled() is False
        assert panel.send_btn.isEnabled() is False
        assert panel.runtime_state_title.text() == "Loading local assistant"
        assert panel.runtime_state_widget.isHidden() is False
        assert panel.workflow_run_status_label.isHidden()
        assert panel.setup_btn.isHidden()
        assert panel.retry_runtime_btn.isHidden()
        assert panel.runtime_progress.isHidden() is False
        assert panel.runtime_progress.minimum() == 0
        assert panel.runtime_progress.maximum() == 0
        assert panel.runtime_progress.isTextVisible() is False

        panel.set_runtime_state("failed", "Model unavailable")
        assert panel.setup_btn.isHidden() is False
        assert panel.setup_btn.isEnabled()
        assert panel.retry_runtime_btn.isHidden() is False
        assert panel.retry_runtime_btn.isEnabled()
        assert panel.runtime_progress.isHidden()
        assert panel.input_widget.isHidden() is False
        assert panel.input_field.isEnabled() is False
        assert panel.send_btn.isEnabled() is False
        assert panel.send_btn.text() == "Send"
        assert panel.send_btn.accessibleName() == "Send request"
        assert panel.send_btn.icon().isNull()
        assert panel.send_btn.toolButtonStyle() == (
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        assert panel.runtime_state_title.text() == "Assistant unavailable"
        assert panel.input_field.placeholderText() == "Assistant unavailable"

        panel.set_runtime_state("loading")
        assert panel.runtime_state_title.text() == "Retrying local assistant"
        assert "retry" in panel.runtime_state_detail.text().lower()
        assert "unavailable" not in panel.runtime_state_detail.text().lower()
        assert "setup required" not in panel.runtime_state_detail.text().lower()
        assert panel.setup_btn.isHidden()
        assert panel.retry_runtime_btn.isHidden()
        assert panel.runtime_progress.isHidden() is False

        panel.set_runtime_state("loading")
        assert panel.runtime_state_title.text() == "Retrying local assistant"

        panel.set_runtime_state("ready")
        assert panel.input_field.isEnabled() is True
        assert panel.send_btn.isEnabled() is False
        assert panel.input_field.placeholderText() == (
            "Ask about the current EEG workflow..."
        )
        assert panel.setup_btn.isHidden()
        assert panel.retry_runtime_btn.isHidden()
        assert panel.runtime_progress.isHidden()
        assert panel.input_widget.isHidden() is False
        assert panel.runtime_state_widget.isHidden()

    def test_cancelled_turn_uses_explicit_typed_presentation(
        self,
        qtbot,
        chat_panel,
    ) -> None:
        chat_panel.resize(320, 620)
        chat_panel.show()
        chat_panel.append_message(
            "assistant",
            "Request cancelled. You can revise it or ask something else.",
            presentation_kind=ChatMessagePresentationKind.CANCELLED,
        )
        qtbot.wait(10)

        bubbles = [
            chat_panel.chat_layout.itemAt(index).widget()
            for index in range(chat_panel.chat_layout.count())
            if isinstance(chat_panel.chat_layout.itemAt(index).widget(), MessageBubble)
        ]

        assert bubbles[-1].get_text() == (
            "Request cancelled. You can revise it or ask something else."
        )
        assert "No further response" not in bubbles[-1].get_text()
        assert bubbles[-1].bubble_frame.width() <= int(
            chat_panel.scroll_area.viewport().width() * 0.84
        )
        assert chat_panel.scroll_area.horizontalScrollBar().maximum() == 0
        assert bubbles[-1].presentation_kind.value == "cancelled"
        assert bubbles[-1].kind_label.text() == "Cancelled"
        assert bubbles[-1].kind_label.isHidden() is False

    @pytest.mark.parametrize(
        "message",
        [
            "Session reset cancelled. Your current workflow is unchanged.",
            "Dataset removal cancelled. Your current workspace is unchanged.",
            "Training history removal cancelled. Your current history is unchanged.",
        ],
    )
    def test_host_owned_confirmation_cancellation_is_visually_distinct(
        self,
        chat_panel,
        message,
    ) -> None:
        chat_panel.append_message(
            "assistant",
            message,
            presentation_kind=ChatMessagePresentationKind.CANCELLED,
        )

        bubble = chat_panel._latest_layout_message_bubble()

        assert bubble is not None
        assert bubble.presentation_kind.value == "cancelled"
        assert bubble.kind_label.text() == "Cancelled"

    def test_ready_to_loading_keeps_runtime_surfaces_mutually_exclusive(
        self,
        qtbot,
    ):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.resize(320, 620)
            panel.show()

        panel.set_runtime_state("ready")
        assert panel.empty_state_widget.isHidden() is False
        assert panel.runtime_state_widget.isHidden()

        panel.set_runtime_state("loading")

        assert panel.empty_state_widget.isHidden()
        assert panel.runtime_state_widget.isHidden() is False

    @pytest.mark.parametrize(
        ("phase", "expected_runtime", "expected_empty"),
        [
            ("idle", True, False),
            ("loading", True, False),
            ("failed", True, False),
            ("ready", False, True),
        ],
    )
    def test_each_runtime_phase_renders_only_its_owned_surface(
        self,
        qtbot,
        phase,
        expected_runtime,
        expected_empty,
    ):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.show()

        panel.set_runtime_state("ready")
        panel.set_runtime_state(phase)

        assert (not panel.runtime_state_widget.isHidden()) is expected_runtime
        assert (not panel.empty_state_widget.isHidden()) is expected_empty

    def test_hidden_panel_runtime_refresh_keeps_empty_state_out_of_transcript(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.append_message("assistant", "The current workflow is ready.")
        assert chat_panel.empty_state_widget.isHidden()

        chat_panel.set_runtime_state("ready")
        chat_panel.show()
        qtbot.wait(10)

        assert chat_panel.chat_content_widget.findChildren(MessageBubble)
        assert chat_panel.empty_state_widget.isHidden()

    def test_hidden_panel_confirmation_clear_keeps_empty_state_out_of_transcript(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.append_message("assistant", "Review the current evaluation results.")
        assert chat_panel.empty_state_widget.isHidden()

        chat_panel.clear_confirmation_request()
        chat_panel.show()
        qtbot.wait(10)

        assert chat_panel.chat_content_widget.findChildren(MessageBubble)
        assert chat_panel.empty_state_widget.isHidden()

    @pytest.mark.parametrize("phase", ["idle", "loading", "failed"])
    def test_non_ready_runtime_rejects_processing_state(self, qtbot, phase):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.set_runtime_state(phase)
            panel.set_processing_state(True)

        assert panel.is_processing is False
        assert panel.send_btn.text() == "Send"
        assert panel.send_btn.accessibleName() == "Send request"
        assert panel.send_btn.icon().isNull()
        assert panel.send_btn.toolButtonStyle() == (
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        assert panel.send_btn.isEnabled() is False
        assert panel.input_field.isEnabled() is False

    def test_idle_and_failed_recovery_action_emits_settings_request(
        self,
        qtbot,
    ):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.show()

        for phase in ("idle", "failed"):
            panel.set_runtime_state(phase)
            with qtbot.waitSignal(panel.open_settings_requested, timeout=1000):
                panel.setup_btn.click()

        panel.set_runtime_state("ready")
        assert panel.setup_btn.isHidden()

    def test_failed_runtime_retry_is_visible_and_emits_dedicated_request(
        self,
        qtbot,
    ):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.show()

        panel.set_runtime_state("idle")
        assert panel.retry_runtime_btn.isHidden()
        assert panel.retry_runtime_btn.isEnabled() is False
        emissions: list[str] = []
        panel.retry_local_assistant_requested.connect(lambda: emissions.append("retry"))
        panel._request_runtime_retry()
        assert emissions == []

        panel.set_runtime_state("failed", "The selected model did not start.")
        assert panel.retry_runtime_btn.text() == "Retry local assistant"
        assert panel.retry_runtime_btn.isVisible()
        assert panel.retry_runtime_btn.isEnabled()
        assert panel.setup_btn.isVisible()

        with qtbot.waitSignal(
            panel.retry_local_assistant_requested,
            timeout=1000,
        ):
            panel.retry_runtime_btn.click()
        assert emissions == ["retry"]

        panel.set_runtime_state("loading")
        assert panel.retry_runtime_btn.isHidden()
        assert panel.retry_runtime_btn.isEnabled() is False

    def test_runtime_actions_have_keyboard_focus_targets(
        self,
        qtbot,
    ):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.set_runtime_state("failed")
            panel.resize(320, 650)
            panel.show()
            qtbot.wait(10)

        for control in (
            panel.retry_runtime_btn,
            panel.setup_btn,
            panel.send_btn,
        ):
            assert control.focusPolicy() == Qt.FocusPolicy.StrongFocus
            assert control.minimumHeight() >= 28

        runtime_right = panel.runtime_state_widget.mapTo(
            panel.chat_content_widget,
            panel.runtime_state_widget.rect().bottomRight(),
        ).x()
        assert panel.width() == 320
        assert runtime_right < panel.chat_content_widget.width()
        horizontal_scroll = panel.scroll_area.horizontalScrollBar()
        assert horizontal_scroll is not None
        assert horizontal_scroll.maximum() == 0
        assert not panel.retry_runtime_btn.geometry().intersects(
            panel.setup_btn.geometry()
        )
        assert panel.setup_btn.geometry().top() > (
            panel.retry_runtime_btn.geometry().bottom()
        )
        for control in (panel.retry_runtime_btn, panel.setup_btn):
            required_width = (
                control.fontMetrics().horizontalAdvance(control.text()) + 24
            )
            assert required_width <= control.contentsRect().width()

    def test_runtime_and_workflow_copy_refit_after_font_metrics_change(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(320, 650)
        chat_panel.set_runtime_state("failed")
        chat_panel.set_processing_state(True)
        chat_panel.set_workflow_status("Waiting for a reviewed decision")
        chat_panel.show()
        qtbot.wait(20)

        enlarged = QFont(chat_panel.font())
        enlarged.setPointSize(max(enlarged.pointSize() + 8, 20))
        for control in (chat_panel.retry_runtime_btn, chat_panel.setup_btn):
            control.setStyleSheet("padding: 4px 12px;")
            control.setFont(enlarged)
        chat_panel.turn_activity_step.setStyleSheet("")
        chat_panel.turn_activity_step.setFont(enlarged)
        chat_panel._reflow_chat_content()
        qtbot.wait(20)

        for control in (chat_panel.retry_runtime_btn, chat_panel.setup_btn):
            required_width = (
                control.fontMetrics().horizontalAdvance(control.text()) + 24
            )
            assert required_width <= control.contentsRect().width()
            if "…" in control.text():
                assert control.toolTip()
        status = chat_panel.turn_activity_step
        required_height = (
            status.fontMetrics()
            .boundingRect(
                QRect(0, 0, max(status.contentsRect().width(), 1), 10_000),
                int(Qt.TextFlag.TextWordWrap),
                status.text(),
            )
            .height()
        )
        assert status.height() >= required_height

    @pytest.mark.parametrize("width", [420, 760, 1280])
    def test_runtime_actions_are_fully_inside_state_surface(
        self,
        qtbot,
        width: int,
    ) -> None:
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.resize(width, 650)
            panel.set_runtime_state("failed")
            panel.show()
            qtbot.wait(20)

        for control in (panel.retry_runtime_btn, panel.setup_btn):
            top_left = control.mapTo(panel.runtime_state_widget, QPoint(0, 0))
            bottom_right = control.mapTo(
                panel.runtime_state_widget,
                control.rect().bottomRight(),
            )
            assert top_left.y() >= 0
            assert bottom_right.y() < panel.runtime_state_widget.height()

    def test_runtime_recovery_actions_stack_without_clipping_at_very_narrow_width(
        self,
        qtbot,
    ):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.resize(280, 620)
            panel.set_runtime_state(
                "failed",
                "The selected local model could not start.",
            )
            panel.show()
            qtbot.wait(20)

        for control in (panel.retry_runtime_btn, panel.setup_btn):
            top_left = control.mapTo(panel, QPoint(0, 0))
            bottom_right = control.mapTo(panel, control.rect().bottomRight())
            assert top_left.x() >= 0
            assert bottom_right.x() < panel.width()
        assert not panel.retry_runtime_btn.geometry().intersects(
            panel.setup_btn.geometry()
        )
        assert panel.setup_btn.geometry().top() > (
            panel.retry_runtime_btn.geometry().bottom()
        )

    def test_runtime_notice_strips_markdown_emphasis(self, qtbot):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.set_runtime_state("failed")
            panel.show_runtime_notice(
                "**Assistant unavailable**: Open Assistant Settings."
            )

        assert panel.runtime_state_detail.text() == "Open Assistant Settings."
        assert "**" not in panel.runtime_state_detail.text()

        panel.set_runtime_state("loading")
        assert panel._notice_owner is None
        assert panel.notice_label.isHidden()
        assert "retry" in panel.runtime_state_title.text().lower()

    def test_creates_panel(self, chat_panel):
        assert isinstance(chat_panel, QWidget)

    def test_connect_controller_restores_history_and_processing_state(
        self,
        chat_panel,
        qtbot,
    ):
        controller = ChatController()
        controller.add_user_message("Review the imported EEG files.")
        controller.add_agent_message("I am checking the current workflow.")
        controller.set_processing(True)

        chat_panel.connect_controller(controller)
        qtbot.wait(10)

        bubbles = [
            chat_panel.chat_layout.itemAt(index).widget()
            for index in range(chat_panel.chat_layout.count())
            if isinstance(chat_panel.chat_layout.itemAt(index).widget(), MessageBubble)
        ]
        assert [bubble.get_text() for bubble in bubbles] == [
            "Review the imported EEG files.",
            "I am checking the current workflow.",
        ]
        assert [bubble.is_user for bubble in bubbles] == [True, False]
        assert chat_panel.is_processing is True
        assert chat_panel.send_btn.text() == "Working"
        assert chat_panel.send_btn.isEnabled() is False
        assert chat_panel.input_field.isEnabled() is False

        controller.add_agent_message("The workflow check is complete.")
        qtbot.wait(10)
        bubbles = [
            chat_panel.chat_layout.itemAt(index).widget()
            for index in range(chat_panel.chat_layout.count())
            if isinstance(chat_panel.chat_layout.itemAt(index).widget(), MessageBubble)
        ]
        assert [bubble.get_text() for bubble in bubbles].count(
            "The workflow check is complete."
        ) == 1

    def test_large_controller_history_rebuild_is_incremental_and_converges(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        controller = ChatController()
        for index in range(96):
            controller.add_user_message(f"Restored message {index}")

        chat_panel.connect_controller(controller)

        synchronous_bubbles = chat_panel.chat_content_widget.findChildren(MessageBubble)
        assert len(synchronous_bubbles) < len(controller.get_typed_history())

        qtbot.waitUntil(
            lambda: len(chat_panel.chat_content_widget.findChildren(MessageBubble))
            == len(controller.get_typed_history()),
            timeout=3_000,
        )
        bubbles = chat_panel.chat_content_widget.findChildren(MessageBubble)
        assert [bubble.get_text() for bubble in bubbles] == [
            record.content for record in controller.get_typed_history()
        ]

    def test_history_rebuild_keeps_live_tail_and_latest_action_state(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        controller = ChatController()
        for index in range(64):
            controller.add_user_message(f"Retained message {index}")
        chat_panel.connect_controller(controller)

        live_record = controller.add_agent_message(
            "Choose the next workflow step.",
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            presentation_id="live-tail-actions",
            actions=(
                ChatResponseAction(
                    action_id="open-live-dataset",
                    label="Open Dataset",
                    kind=ChatResponseActionKind.OPEN_PANEL,
                    panel=ChatPanelTarget.DATASET,
                ),
            ),
        )
        while chat_panel.response_actions_widget.isHidden():
            assert chat_panel._history_rebuild_active is True
            chat_panel._history_rebuild_timer.stop()
            chat_panel._apply_history_rebuild_chunk()
            chat_panel._history_rebuild_timer.stop()

        assert chat_panel._history_rebuild_active is True
        assert chat_panel.response_actions_widget.isHidden() is False

        assert controller.consume_response_actions(live_record.presentation_id) is True
        assert chat_panel.response_actions_widget.isHidden()

        chat_panel._history_rebuild_timer.start(0)

        qtbot.waitUntil(
            lambda: len(chat_panel.chat_content_widget.findChildren(MessageBubble))
            == len(controller.get_typed_history()),
            timeout=3_000,
        )
        bubbles = chat_panel._layout_message_bubbles()
        assert [bubble.property("chatMessageId") for bubble in bubbles] == [
            record.message_id for record in controller.get_typed_history()
        ]
        assert bubbles[-1].get_text() == live_record.content
        assert chat_panel.response_actions_widget.isHidden()

    def test_history_replacement_rebuild_uses_snapshot_without_controller_polling(
        self,
        chat_panel,
        qtbot,
        monkeypatch,
    ) -> None:
        controller = ChatController()
        for index in range(48):
            controller.add_user_message(f"Snapshot message {index}")
        chat_panel.connect_controller(controller)
        qtbot.waitUntil(
            lambda: len(chat_panel._layout_message_bubbles()) == 48,
            timeout=3_000,
        )

        retained = controller.get_typed_history()[12:]
        replacement = ChatHistoryReplacement(
            kind=ChatHistoryReplacementKind.PRUNE,
            records=retained,
        )
        monkeypatch.setattr(
            controller,
            "get_typed_history",
            lambda: pytest.fail("history rebuild polled controller truth"),
        )

        controller.history_replaced.emit(replacement)
        qtbot.waitUntil(
            lambda: [
                bubble.property("chatMessageId")
                for bubble in chat_panel._layout_message_bubbles()
            ]
            == [record.message_id for record in retained],
            timeout=3_000,
        )

    def test_history_replacement_queues_live_add_and_update_in_signal_order(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        controller = ChatController()
        for index in range(48):
            controller.add_user_message(f"Snapshot message {index}")
        chat_panel.connect_controller(controller)
        qtbot.waitUntil(
            lambda: len(chat_panel._layout_message_bubbles()) == 48,
            timeout=3_000,
        )

        retained = controller.get_typed_history()[8:]
        controller.history_replaced.emit(
            ChatHistoryReplacement(
                kind=ChatHistoryReplacementKind.PRUNE,
                records=retained,
            )
        )
        appended = controller.add_agent_message("Live tail after replacement.")
        updated = replace(appended, content="Updated live tail after replacement.")
        controller.message_record_updated.emit(updated)

        expected_ids = [record.message_id for record in retained] + [
            appended.message_id
        ]
        qtbot.waitUntil(
            lambda: [
                bubble.property("chatMessageId")
                for bubble in chat_panel._layout_message_bubbles()
            ]
            == expected_ids,
            timeout=3_000,
        )
        assert chat_panel._layout_message_bubbles()[-1].get_text() == updated.content

    def test_history_replacement_is_incremental_during_prune_teardown(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        controller = ChatController()
        for index in range(96):
            controller.add_user_message(f"Existing message {index}")
        chat_panel.connect_controller(controller)
        qtbot.waitUntil(
            lambda: len(chat_panel._layout_message_bubbles()) == 96,
            timeout=3_000,
        )

        retained = controller.get_typed_history()[-24:]
        controller.history_replaced.emit(
            ChatHistoryReplacement(
                kind=ChatHistoryReplacementKind.PRUNE,
                records=retained,
            )
        )

        # The signal handler must only capture replacement work. Removing the
        # old transcript belongs to bounded event-loop chunks.
        assert chat_panel._history_rebuild_active is True
        assert len(chat_panel._layout_message_bubbles()) > len(retained)

        qtbot.waitUntil(
            lambda: [
                bubble.property("chatMessageId")
                for bubble in chat_panel._layout_message_bubbles()
            ]
            == [record.message_id for record in retained],
            timeout=3_000,
        )

    def test_connected_panel_clear_and_restore_use_typed_replacements(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        controller = ChatController()
        controller.add_user_message("Inspect the imported EEG data.")
        controller.add_agent_message(
            "The import is ready for review.",
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            presentation_id="restore-actions",
            actions=(
                ChatResponseAction(
                    action_id="review-import",
                    label="Review import",
                    kind=ChatResponseActionKind.OPEN_PANEL,
                    panel=ChatPanelTarget.DATASET,
                ),
            ),
        )
        persisted = controller.get_history()
        expected_ids = [record["message_id"] for record in persisted]
        chat_panel.connect_controller(controller)
        qtbot.waitUntil(
            lambda: len(chat_panel._layout_message_bubbles()) == 2,
            timeout=3_000,
        )
        assert chat_panel.response_actions_widget.isVisibleTo(chat_panel)

        controller.clear_conversation()
        qtbot.waitUntil(
            lambda: not chat_panel._layout_message_bubbles(),
            timeout=3_000,
        )
        assert controller.get_typed_history() == ()
        assert controller.get_history() == []
        assert controller.pruned_row_count == 0
        assert chat_panel.response_actions_widget.isHidden()
        assert chat_panel.empty_state_widget.isVisibleTo(chat_panel)

        assert controller.restore_history(persisted) == 2
        qtbot.waitUntil(
            lambda: [
                bubble.property("chatMessageId")
                for bubble in chat_panel._layout_message_bubbles()
            ]
            == expected_ids,
            timeout=3_000,
        )
        assert [
            bubble.get_text() for bubble in chat_panel._layout_message_bubbles()
        ] == [
            "Inspect the imported EEG data.",
            "The import is ready for review.",
        ]
        assert chat_panel.response_actions_widget.isHidden()
        assert not controller.get_typed_history()[-1].has_active_actions

    def test_prune_preserves_retained_reader_anchor(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        controller = ChatController()
        for index in range(80):
            controller.add_agent_message(
                f"Detailed retained transcript message {index}. " * 3
            )
        chat_panel.resize(420, 520)
        chat_panel.show()
        chat_panel.connect_controller(controller)
        qtbot.waitUntil(
            lambda: len(chat_panel._layout_message_bubbles()) == 80
            and chat_panel._history_rebuild_active is False,
            timeout=4_000,
        )
        qtbot.wait(30)

        viewport = chat_panel.scroll_area.viewport()
        scroll_bar = chat_panel.scroll_area.verticalScrollBar()
        target = chat_panel._layout_message_bubbles()[35]
        target_top = target.mapTo(viewport, QPoint(0, 0)).y()
        scroll_bar.setValue(scroll_bar.value() + target_top - 24)
        qtbot.wait(30)
        anchor = chat_panel._capture_reader_anchor()
        assert anchor is not None
        anchor_id, expected_y = anchor
        assert chat_panel._follow_transcript_updates is False

        history = controller.get_typed_history()
        retained = history[10:]
        assert anchor_id in {record.message_id for record in retained}
        controller.history_replaced.emit(
            ChatHistoryReplacement(
                kind=ChatHistoryReplacementKind.PRUNE,
                records=retained,
            )
        )
        qtbot.waitUntil(
            lambda: chat_panel._history_rebuild_active is False,
            timeout=4_000,
        )
        qtbot.wait(80)

        anchored_bubble = chat_panel._message_bubbles_by_id[anchor_id]
        actual_y = anchored_bubble.mapTo(viewport, QPoint(0, 0)).y()
        assert abs(actual_y - expected_y) <= 4
        assert scroll_bar.value() < scroll_bar.maximum()
        assert chat_panel._follow_transcript_updates is False

    def test_connected_replacement_applies_update_then_add_fifo(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        controller = ChatController()
        for index in range(48):
            controller.add_user_message(f"Snapshot message {index}")
        active = controller.add_agent_message("Working on the current step.")
        chat_panel.connect_controller(controller)
        qtbot.waitUntil(
            lambda: len(chat_panel._layout_message_bubbles()) == 49,
            timeout=3_000,
        )

        retained = controller.get_typed_history()[8:]
        controller.history_replaced.emit(
            ChatHistoryReplacement(
                kind=ChatHistoryReplacementKind.PRUNE,
                records=retained,
            )
        )
        for _ in range(20):
            if chat_panel._history_rebuild_phase == "reflow":
                break
            chat_panel._history_rebuild_timer.stop()
            chat_panel._apply_history_rebuild_chunk()
        assert chat_panel._history_rebuild_phase == "reflow"
        updated = replace(active, content="Current step completed.")
        controller.message_record_updated.emit(updated)
        appended = controller.add_agent_message("Ready for the next step.")

        expected_ids = [record.message_id for record in retained] + [
            appended.message_id
        ]
        qtbot.waitUntil(
            lambda: [
                bubble.property("chatMessageId")
                for bubble in chat_panel._layout_message_bubbles()
            ]
            == expected_ids,
            timeout=3_000,
        )
        bubbles = chat_panel._layout_message_bubbles()
        assert bubbles[-2].get_text() == updated.content
        assert bubbles[-1].get_text() == appended.content

    @pytest.mark.parametrize(
        ("kind", "expected_kind", "expected_label"),
        [
            (
                ChatMessagePresentationKind.CLARIFICATION,
                "clarification",
                "Needs input",
            ),
            (
                ChatMessagePresentationKind.ATTENTION,
                "attention",
                "Needs attention",
            ),
            (
                ChatMessagePresentationKind.TOOL_RESULT,
                "tool_result",
                "Completed",
            ),
        ],
    )
    def test_typed_response_has_distinct_visible_semantics(
        self,
        chat_panel,
        qtbot,
        kind,
        expected_kind,
        expected_label,
    ):
        chat_panel.resize(320, 620)
        chat_panel.show()
        controller = ChatController()
        chat_panel.connect_controller(controller)
        controller.add_agent_message(
            "Review the current workflow result.",
            presentation_kind=kind,
        )
        qtbot.wait(10)

        bubble = chat_panel._latest_message_bubble()
        assert bubble is not None
        assert bubble.presentation_kind.value == expected_kind
        assert bubble.kind_label.text() == expected_label
        assert bubble.kind_label.isHidden() is False
        assert bubble.bubble_frame is not None
        assert bubble.bubble_frame.property("assistantMessageKind") == expected_kind

    def test_error_presentation_does_not_depend_on_action_label(
        self,
        chat_panel,
    ) -> None:
        controller = ChatController()
        chat_panel.connect_controller(controller)
        controller.add_agent_message(
            "The assistant could not complete the request. Try again.",
            presentation_kind=ChatMessagePresentationKind.ERROR,
            presentation_id="error-response",
            actions=(
                ChatResponseAction(
                    action_id="continue-action",
                    label="Continue",
                    kind=ChatResponseActionKind.SEND_MESSAGE,
                    prompt="Please retry my previous request.",
                ),
            ),
        )

        bubble = chat_panel._latest_layout_message_bubble()
        assert bubble is not None
        assert bubble.presentation_kind.value == "error"
        assert bubble.kind_label.text() == "Error"
        assert bubble.bubble_frame is not None
        assert bubble.bubble_frame.property("assistantMessageKind") == "error"

    def test_typed_response_actions_fit_narrow_dock_and_clear_on_next_turn(
        self,
        chat_panel,
        qtbot,
    ):
        controller = ChatController()
        chat_panel.connect_controller(controller)
        actions = (
            ChatResponseAction(
                action_id="check-workflow",
                label="Check workflow",
                kind=ChatResponseActionKind.SEND_MESSAGE,
                prompt="Check what is ready now.",
            ),
            ChatResponseAction(
                action_id="open-dataset",
                label="Open Dataset",
                kind=ChatResponseActionKind.OPEN_PANEL,
                panel=ChatPanelTarget.DATASET,
            ),
        )
        chat_panel.resize(320, 620)
        chat_panel.show()
        active_presentation_ids: list[object] = []
        chat_panel.active_response_presentation_changed.connect(
            active_presentation_ids.append
        )

        controller.add_agent_message(
            "Choose a next step.",
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            presentation_id="response-actions",
            actions=actions,
        )
        qtbot.wait(10)

        buttons = chat_panel.response_actions_widget.findChildren(QToolButton)
        assert [button.text() for button in buttons] == [
            "Check workflow",
            "Open Dataset",
        ]
        assert chat_panel.response_actions_widget.isVisible()
        assert all(
            button.width() <= chat_panel.scroll_area.viewport().width()
            for button in buttons
        )
        presentation = chat_panel._response_presentation
        assert isinstance(presentation, ChatResponseActionsView)
        assert all(
            isinstance(action, ChatResponseActionView)
            for action in presentation.actions
        )
        assert presentation.actions[0] is not actions[0]
        assert active_presentation_ids[-1] == "response-actions"
        with pytest.raises(FrozenInstanceError):
            cast(Any, presentation).presentation_id = "changed"

        identity_at_selection: list[object] = []
        chat_panel.response_action_requested.connect(
            lambda _selection: identity_at_selection.append(active_presentation_ids[-1])
        )
        with qtbot.waitSignal(
            chat_panel.response_action_requested,
            timeout=1000,
        ) as emitted:
            buttons[1].click()
        assert emitted.args == [
            ChatResponseActionSelectionView(
                presentation_id="response-actions",
                action=ChatResponseActionView(
                    action_id="open-dataset",
                    label="Open Dataset",
                    kind=ChatResponseActionViewKind.OPEN_PANEL,
                    panel=ChatResponsePanelTargetView.DATASET,
                ),
            )
        ]
        assert identity_at_selection == ["response-actions"]
        assert active_presentation_ids[-1] is None
        assert chat_panel._response_presentation is None
        assert chat_panel.response_actions_widget.isHidden()
        assert controller.get_typed_history()[-1].has_active_actions is True

        controller.add_agent_message(
            "Choose another step.",
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            presentation_id="next-actions",
            actions=(
                replace(actions[0], action_id="check-workflow-next"),
                replace(actions[1], action_id="open-dataset-next"),
            ),
        )
        controller.add_user_message("Next request")
        assert chat_panel.response_actions_widget.isHidden()

    def test_panel_does_not_keep_controller_alive(self, chat_panel, qtbot) -> None:
        controller = ChatController()
        chat_panel.connect_controller(controller)
        controller_ref = weakref.ref(controller)

        del controller
        gc.collect()
        qtbot.wait(1)

        assert controller_ref() is None

    def test_long_response_action_elides_without_widening_narrow_dock(
        self,
        chat_panel,
        qtbot,
    ):
        full_label = "Review the unresolved label alignment details"
        controller = ChatController()
        chat_panel.connect_controller(controller)
        controller.add_agent_message(
            "Choose a next step.",
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            presentation_id="long-action",
            actions=(
                ChatResponseAction(
                    action_id="review-labels",
                    label=full_label,
                    kind=ChatResponseActionKind.SEND_MESSAGE,
                    prompt="Review label alignment.",
                ),
            ),
        )
        chat_panel.resize(320, 620)
        chat_panel.show()
        qtbot.wait(20)

        button = chat_panel.response_actions_widget.findChild(QToolButton)
        viewport = chat_panel.scroll_area.viewport()
        assert button is not None
        assert viewport is not None
        assert button.toolTip() == full_label
        assert button.accessibleName() == full_label
        assert button.text() != full_label
        assert "…" in button.text()
        assert button.text().startswith("Review the unresolved label")
        _assert_inside_panel_on_all_sides(chat_panel, button)
        assert chat_panel.scroll_area.isAncestorOf(chat_panel.response_actions_widget)

    def test_has_input_area(self, chat_panel):
        assert isinstance(chat_panel.input_field, QPlainTextEdit)

    @pytest.mark.parametrize("width", [320, 760, 1280])
    def test_empty_state_copy_and_suggestions_fit_responsive_width(
        self,
        chat_panel,
        qtbot,
        width,
    ) -> None:
        chat_panel.set_product_status(
            "Results available",
            "Ready",
            ["evaluate", "visualize"],
        )
        chat_panel.resize(width, 650)
        chat_panel.set_runtime_state("ready")
        chat_panel.show()
        qtbot.wait(20)

        assert chat_panel.empty_state_title.wordWrap() is True
        title_rect = chat_panel.empty_state_title.fontMetrics().boundingRect(
            chat_panel.empty_state_title.contentsRect(),
            int(Qt.TextFlag.TextWordWrap),
            chat_panel.empty_state_title.text(),
        )
        assert title_rect.height() <= chat_panel.empty_state_title.height() + 2
        for button in chat_panel.suggestion_prompt_buttons:
            for label in (button.title_label, button.subtitle_label):
                text_rect = label.fontMetrics().boundingRect(
                    QRect(0, 0, max(label.contentsRect().width(), 1), 1000),
                    int(Qt.TextFlag.TextWordWrap),
                    label.text(),
                )
                assert text_rect.height() <= label.contentsRect().height() + 2
            button_bottom = button.mapTo(
                chat_panel.suggestion_prompt_widget,
                button.rect().bottomRight(),
            ).y()
            assert button_bottom < chat_panel.suggestion_prompt_widget.height()

        prompt_bottom = chat_panel.suggestion_prompt_widget.mapTo(
            chat_panel.empty_state_widget,
            chat_panel.suggestion_prompt_widget.rect().bottomRight(),
        ).y()
        assert prompt_bottom < chat_panel.empty_state_widget.height()

        if width == 320:
            assert all(
                button.height() <= 68 for button in chat_panel.suggestion_prompt_buttons
            )

    def test_narrow_empty_state_starts_at_the_title_instead_of_the_tail(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(320, 650)
        chat_panel.set_runtime_state("ready")
        chat_panel.show()
        qtbot.wait(30)

        scrollbar = chat_panel.scroll_area.verticalScrollBar()
        assert scrollbar.value() <= 2
        title_top = chat_panel.empty_state_title.mapTo(
            chat_panel.scroll_area.viewport(),
            QPoint(0, 0),
        ).y()
        assert title_top >= 0

    def test_wide_panel_uses_available_width_for_composer(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(760, 650)
        chat_panel.set_runtime_state("ready")
        chat_panel.show()
        qtbot.wait(20)

        assert not hasattr(chat_panel, "mode_selector_widget")
        assert chat_panel.input_widget.width() == 620

    def test_input_placeholder_is_short_for_narrow_panel(self, chat_panel):
        chat_panel.resize(320, 620)
        chat_panel.show()
        placeholder = chat_panel.input_field.placeholderText()
        available_width = chat_panel.input_field.viewport().width() - 4
        required_width = chat_panel.input_field.fontMetrics().horizontalAdvance(
            placeholder
        )

        assert placeholder == "Ask about the current EEG workflow..."
        assert chat_panel.input_field.horizontalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert required_width > 0
        assert available_width > 0
        assert "preprocessing, epoching" not in placeholder

    def test_has_send_button(self, chat_panel):
        assert isinstance(chat_panel.send_btn, QToolButton)

    def test_has_scroll_area(self, chat_panel):
        assert isinstance(chat_panel.scroll_area, QScrollArea)

    def test_not_processing_initially(self, chat_panel):
        assert chat_panel.is_processing is False

    def test_execution_scope_is_inferred_without_a_visible_mode_selector(
        self,
        chat_panel,
    ):
        assert not hasattr(chat_panel, "mode_selector_widget")
        assert not hasattr(chat_panel, "ask_mode_btn")
        assert not hasattr(chat_panel, "workflow_mode_btn")

    def test_composer_uses_one_compact_horizontal_input_surface(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(360, 680)
        chat_panel.show()
        qtbot.wait(20)

        assert chat_panel.send_btn.text() == "Send"
        assert chat_panel.send_btn.accessibleName() == "Send request"
        assert chat_panel.send_btn.width() > chat_panel.send_btn.height()
        assert chat_panel.send_btn.toolButtonStyle() == (
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        assert chat_panel.input_layout.direction() == QBoxLayout.Direction.LeftToRight
        assert chat_panel.composer_actions.parentWidget() is chat_panel.input_widget
        assert chat_panel.send_btn.size() == QSize(84, 34)
        assert chat_panel.input_field.width() > chat_panel.send_btn.width()
        send_top_left = chat_panel.send_btn.mapTo(
            chat_panel.input_widget,
            QPoint(0, 0),
        )
        send_rect = QRect(send_top_left, chat_panel.send_btn.size())
        assert not chat_panel.input_field.geometry().intersects(send_rect)
        assert send_rect.left() > chat_panel.input_field.geometry().right()
        assert abs(send_rect.bottom() - chat_panel.input_field.geometry().bottom()) <= 2

    @pytest.mark.parametrize("width", [320, 420, 760])
    def test_composer_stays_inline_and_compact_at_supported_panel_widths(
        self,
        chat_panel,
        qtbot,
        width,
    ) -> None:
        chat_panel.resize(width, 680)
        chat_panel.show()
        qtbot.wait(20)

        assert chat_panel.input_layout.direction() == QBoxLayout.Direction.LeftToRight
        assert 52 <= chat_panel.input_field.height() <= 58
        assert chat_panel.input_widget.height() <= 72
        assert chat_panel.input_field.viewport().width() >= 172
        send_top_left = chat_panel.send_btn.mapTo(
            chat_panel.input_widget,
            QPoint(0, 0),
        )
        send_rect = QRect(send_top_left, chat_panel.send_btn.size())
        assert not chat_panel.input_field.geometry().intersects(send_rect)
        assert send_rect.left() > chat_panel.input_field.geometry().right()
        assert abs(send_rect.bottom() - chat_panel.input_field.geometry().bottom()) <= 2
        assert chat_panel.input_widget.rect().contains(send_rect)

    def test_suggestions_use_compact_rows_at_normal_dock_width(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(420, 680)
        chat_panel.show()
        qtbot.wait(20)

        assert all(
            button.height() <= 54 for button in chat_panel.suggestion_prompt_buttons
        )

    def test_long_history_runtime_failure_keeps_recovery_actions_visible_at_tail(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(420, 680)
        chat_panel.show()
        for index in range(20):
            chat_panel.append_message(
                "assistant",
                f"Restored message {index}: " + ("workflow context " * 5),
            )
        qtbot.wait(20)

        chat_panel.set_runtime_state(
            "failed",
            "The selected local model could not start.",
        )
        qtbot.wait(30)

        viewport = chat_panel.scroll_area.viewport()
        assert viewport is not None
        runtime_top = chat_panel.runtime_state_widget.mapTo(viewport, QPoint(0, 0)).y()
        runtime_bottom = runtime_top + chat_panel.runtime_state_widget.height()
        assert runtime_top >= 0
        assert runtime_bottom <= viewport.height()
        assert chat_panel.retry_runtime_btn.isVisibleTo(chat_panel)
        assert chat_panel.setup_btn.isVisibleTo(chat_panel)
        assert chat_panel.input_field.isEnabled() is False

    def test_streaming_reflow_follows_tail_only_when_reader_is_at_bottom(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(320, 520)
        chat_panel.show()
        for index in range(10):
            chat_panel.append_message(
                "assistant",
                f"Message {index}: " + ("workflow detail " * 10),
            )
        qtbot.wait(30)
        scroll_bar = chat_panel.scroll_area.verticalScrollBar()
        latest = chat_panel._latest_message_bubble()
        assert latest is not None
        scroll_bar.setValue(scroll_bar.maximum())

        latest.set_text(latest.get_text() + "\n\n" + ("streamed detail " * 40))
        qtbot.wait(40)
        assert scroll_bar.value() >= scroll_bar.maximum() - 2

        scroll_bar.setValue(0)
        latest.set_text(latest.get_text() + "\n\n" + ("more detail " * 40))
        qtbot.wait(40)
        assert scroll_bar.value() <= 2

    def test_progress_status_is_compact_and_visible_while_processing(
        self,
        chat_panel,
    ):
        chat_panel.set_workflow_status("Thinking")
        assert chat_panel.workflow_run_status_label.isHidden()

        chat_panel.set_processing_state(True)
        chat_panel.set_workflow_status("Running: Scan data source")

        assert chat_panel.workflow_run_status_label.text() == (
            "Running: Scan data source"
        )
        assert chat_panel.workflow_run_status_label.isHidden()
        assert chat_panel.turn_activity_widget.isHidden() is False
        assert chat_panel.turn_activity_step.text() == (
            "Current step: Running: Scan data source"
        )
        assert chat_panel.send_btn.text() == "Working"
        assert chat_panel.send_btn.isEnabled() is False

        chat_panel.set_processing_state(False)
        assert chat_panel.workflow_run_status_label.isHidden()

    def test_cancellable_turn_shows_primary_progress_and_enabled_stop(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(320, 620)
        chat_panel.show()
        presentation = ChatTurnPresentation(
            phase=ChatTurnPresentationPhase.WORKING,
            primary_status="Working on your request",
            step="Checking the current EEG workflow",
            scope_summary=(
                "Scope: Continue through Create EEG epochs; stop for decisions."
            ),
            cancelability=ChatTurnCancelability.CANCELLABLE,
            cancelability_text="You can stop before an XBrainLab action starts.",
        )

        chat_panel.set_turn_activity(presentation)
        qtbot.wait(10)

        assert chat_panel.turn_activity_widget.isVisible()
        assert chat_panel.turn_activity_title.text() == "Working on your request"
        assert chat_panel.turn_activity_step.text() == (
            "Current step: Checking the current EEG workflow"
        )
        assert chat_panel.turn_activity_scope.text() == (
            "Scope: Continue through Create EEG epochs; stop for decisions."
        )
        assert chat_panel.turn_activity_scope.isVisible()
        assert chat_panel.turn_activity_cancelability.text() == (
            "You can stop before an XBrainLab action starts."
        )
        assert chat_panel.send_btn.text() == "Stop"
        assert chat_panel.send_btn.accessibleName() == "Stop current request"
        assert chat_panel.send_btn.isEnabled()
        with qtbot.waitSignal(chat_panel.stop_generation, timeout=1000):
            chat_panel.send_btn.click()

    def test_stopping_turn_disables_primary_action_and_keeps_status_visible(
        self,
        chat_panel,
    ) -> None:
        chat_panel.set_turn_activity(
            ChatTurnPresentation(
                phase=ChatTurnPresentationPhase.STOPPING,
                primary_status="Stopping request",
                step="Waiting for the local assistant to stop",
                cancelability=ChatTurnCancelability.STOPPING,
                cancelability_text="No new action will start.",
            )
        )

        assert chat_panel.turn_activity_widget.isHidden() is False
        assert chat_panel.send_btn.text() == "Stopping"
        assert chat_panel.send_btn.accessibleName() == "Stopping current request"
        assert chat_panel.send_btn.isEnabled() is False
        assert "Stop" not in chat_panel.turn_activity_cancelability.text()

    def test_application_command_progress_never_offers_misleading_stop(
        self,
        chat_panel,
    ) -> None:
        chat_panel.set_turn_activity(
            ChatTurnPresentation(
                phase=ChatTurnPresentationPhase.APPLICATION_COMMAND,
                primary_status="XBrainLab action in progress",
                step="Prepare EEG data",
                cancelability=ChatTurnCancelability.NOT_CANCELLABLE,
                cancelability_text=(
                    "This action has already started and cannot be stopped safely."
                ),
            )
        )

        assert chat_panel.turn_activity_widget.isHidden() is False
        assert chat_panel.turn_activity_title.text() == ("XBrainLab action in progress")
        assert chat_panel.turn_activity_step.text() == (
            "Current step: Prepare EEG data"
        )
        assert chat_panel.send_btn.text() == "Working"
        assert chat_panel.send_btn.accessibleName() == "Assistant is working"
        assert chat_panel.send_btn.isEnabled() is False
        assert chat_panel.send_btn.toolTip() == (
            "This XBrainLab action has already started and cannot be stopped safely."
        )

    def test_waiting_for_decision_is_locked_without_claiming_active_work(
        self,
        chat_panel,
    ) -> None:
        presentation = present_assistant_activity(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.WAITING_FOR_DECISION,
                command_name="apply_interpretation",
            )
        )

        chat_panel.set_turn_activity(presentation)

        assert chat_panel.is_processing is True
        assert chat_panel.input_field.isEnabled() is False
        assert chat_panel.send_btn.text() == "Waiting"
        assert chat_panel.send_btn.accessibleName() == "Waiting for your decision"
        assert chat_panel.send_btn.isEnabled() is False
        assert chat_panel.send_btn.toolTip() == (
            "Continue in the open Import EEG Data window."
        )
        assert chat_panel.header_status_text == "Local · Waiting"
        assert chat_panel.turn_activity_step.text() == (
            "Current step: Continue in Import EEG Data"
        )
        assert chat_panel.turn_activity_cancelability.text() == (
            "Continue in the open Import EEG Data window."
        )

    def test_inline_confirmation_waiting_copy_names_the_visible_card(
        self,
        chat_panel,
    ) -> None:
        presentation = present_assistant_activity(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.WAITING_FOR_DECISION,
                command_name="new_session",
            )
        )

        chat_panel.set_turn_activity(presentation)

        assert chat_panel.send_btn.text() == "Waiting"
        assert chat_panel.send_btn.isEnabled() is False
        assert chat_panel.send_btn.toolTip() == (
            "Use the confirmation card to continue or cancel."
        )
        assert chat_panel.turn_activity_cancelability.text() == (
            "Use the confirmation card to continue or cancel."
        )

    def test_workflow_status_fits_in_narrow_dock(
        self,
        chat_panel,
        qtbot,
    ):
        chat_panel.resize(320, 620)
        chat_panel.show()
        chat_panel.set_processing_state(True)
        chat_panel.set_workflow_status("Waiting for decision")
        qtbot.wait(0)

        status = chat_panel.turn_activity_step
        required = status.fontMetrics().boundingRect(
            QRect(0, 0, max(status.width(), 1), 1000),
            int(Qt.TextFlag.TextWordWrap),
            status.text(),
        )
        assert status.isVisible()
        assert status.height() >= required.height()
        assert chat_panel.turn_activity_widget.width() <= (
            chat_panel.scroll_area.viewport().width()
        )

    def test_processing_status_wraps_in_narrow_dock(
        self,
        chat_panel,
        qtbot,
    ):
        status_text = (
            "Checking the selected EEG files and preparing a detailed workflow decision"
        )
        chat_panel.resize(320, 620)
        chat_panel.show()
        chat_panel.set_processing_state(True)
        chat_panel.set_workflow_status(status_text)
        qtbot.wait(20)

        status = chat_panel.turn_activity_step
        required = status.fontMetrics().boundingRect(
            QRect(0, 0, max(status.width(), 1), 1000),
            int(Qt.TextFlag.TextWordWrap),
            status.text(),
        )
        assert chat_panel.turn_activity_widget.isVisible()
        assert status.isVisible()
        assert status.wordWrap()
        assert status.height() >= required.height()

        chat_panel.set_processing_state(False)
        qtbot.wait(0)
        assert chat_panel.turn_activity_widget.isHidden()

    def test_new_turn_does_not_restore_the_previous_turn_status(
        self,
        chat_panel,
    ):
        chat_panel.set_processing_state(True)
        chat_panel.set_workflow_status("Running: Review metadata")
        chat_panel.set_processing_state(False)

        chat_panel.set_processing_state(True)

        assert chat_panel.turn_activity_step.text() == (
            "Current step: Waiting for the current XBrainLab work to finish"
        )
        assert "Review metadata" not in chat_panel.turn_activity_step.text()


class TestChatPanelSendMessage:
    def test_send_empty_ignored(self, chat_panel):
        chat_panel.input_field.clear()
        # Should not emit send_message
        with patch.object(chat_panel, "send_message") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_send()
            mock_sig.emit.assert_not_called()

    def test_send_text(self, chat_panel):
        chat_panel.input_field.setText("hello")
        with patch.object(chat_panel, "send_message") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_send()
            mock_sig.emit.assert_called_once_with("hello")
        assert chat_panel.input_field.text() == "hello"

        chat_panel.accept_composer_submission("hello")

        assert chat_panel.input_field.text() == ""

    def test_rejected_submission_keeps_exact_text_and_focus(self, chat_panel, qtbot):
        chat_panel.show()
        qtbot.wait(10)
        chat_panel.input_field.setText("Review subject 01 labels")

        chat_panel.reject_composer_submission(
            "Review subject 01 labels",
            "The assistant is still processing the previous request.",
        )

        assert chat_panel.input_field.text() == "Review subject 01 labels"
        assert chat_panel.input_field.hasFocus()
        assert chat_panel.notice_label.text() == (
            "The assistant is still processing the previous request."
        )
        assert chat_panel.notice_label.isHidden() is False
        assert chat_panel._notice_timer.isActive() is False

    def test_accepting_stale_submission_does_not_clear_newer_draft(self, chat_panel):
        chat_panel.input_field.setText("A newer draft")

        chat_panel.accept_composer_submission("An older request")

        assert chat_panel.input_field.text() == "A newer draft"

    def test_composer_supports_multiline_request_and_enter_submits(
        self,
        chat_panel,
        qtbot,
    ):
        chat_panel.input_field.setFocus()
        qtbot.keyClicks(chat_panel.input_field, "first line")
        qtbot.keyClick(
            chat_panel.input_field,
            Qt.Key.Key_Return,
            modifier=Qt.KeyboardModifier.ShiftModifier,
        )
        qtbot.keyClicks(chat_panel.input_field, "second line")

        with qtbot.waitSignal(chat_panel.send_message, timeout=1000) as emitted:
            qtbot.keyClick(chat_panel.input_field, Qt.Key.Key_Return)

        assert emitted.args == ["first line\nsecond line"]
        assert chat_panel.input_field.text() == "first line\nsecond line"

        chat_panel.accept_composer_submission("first line\nsecond line")

        assert chat_panel.input_field.text() == ""

    def test_composer_refits_text_entered_before_show(
        self,
        chat_panel,
        qtbot,
    ):
        chat_panel.hide()
        chat_panel.resize(320, 650)
        chat_panel.input_field.setText(
            "Review the workflow.\n"
            "Explain the unresolved labels.\n"
            "Do not change settings."
        )

        chat_panel.show()
        qtbot.wait(0)

        assert chat_panel.input_field.height() > 58
        assert chat_panel.input_field.height() <= 144
        assert chat_panel.input_field.verticalScrollBar().isVisible() is False

    def test_stop_when_processing(self, chat_panel):
        chat_panel.set_turn_activity(
            ChatTurnPresentation(
                phase=ChatTurnPresentationPhase.WORKING,
                primary_status="Working on your request",
                step="Planning the next safe step",
                cancelability=ChatTurnCancelability.CANCELLABLE,
                cancelability_text=("You can stop before an XBrainLab action starts."),
            )
        )
        with patch.object(chat_panel, "stop_generation") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_send()
            mock_sig.emit.assert_called_once()


class TestChatPanelCallbacks:
    def test_append_message_user(self, chat_panel):
        chat_panel.append_message("user", "hi there")
        # Should have added a bubble
        assert chat_panel.chat_layout.count() > 1
        assert chat_panel.empty_state_widget.isHidden()

    def test_append_message_agent(self, chat_panel):
        chat_panel.append_message("assistant", "response")
        bubbles = chat_panel.findChildren(MessageBubble)
        assert bubbles
        assert isinstance(bubbles[-1], QWidget)
        assert chat_panel.empty_state_widget.isHidden()

    def test_resize_keeps_latest_bubble_above_composer(self, chat_panel, qtbot):
        chat_panel.resize(340, 620)
        chat_panel.show()
        qtbot.wait(0)
        messages = [
            ("user", "Hello."),
            (
                "assistant",
                "I can help interpret EEG data and prepare a training-ready dataset.",
            ),
            ("user", "Load my brainwave data."),
            (
                "assistant",
                "Choose a file, folder, BIDS root, or saved recipe before I can scan it.",
            ),
            ("user", "Train it now."),
            (
                "assistant",
                "Training is not ready until data, epochs, a dataset, a model, "
                "and settings are ready.",
            ),
            ("user", "What is ready now?"),
            (
                "assistant",
                "The dataset and training settings are ready; evaluation needs "
                "a completed run.",
            ),
        ]
        for sender, text in messages:
            chat_panel.append_message(sender, text)
        qtbot.wait(0)

        chat_panel.resize(320, 560)
        qtbot.wait(0)

        scrollbar = chat_panel.scroll_area.verticalScrollBar()
        assert scrollbar is not None
        assert scrollbar.value() == scrollbar.maximum()
        bubbles = chat_panel.chat_content_widget.findChildren(MessageBubble)
        assert bubbles
        last_bubble = bubbles[-1]
        viewport = chat_panel.scroll_area.viewport()
        assert viewport is not None
        viewport_bottom_y = last_bubble.mapTo(
            viewport,
            QPoint(0, last_bubble.height()),
        ).y()
        assert viewport_bottom_y <= viewport.height() - 8

        panel_bottom_y = last_bubble.mapTo(
            chat_panel,
            QPoint(0, last_bubble.height()),
        ).y()
        composer_top_y = chat_panel.control_panel.mapTo(chat_panel, QPoint(0, 0)).y()
        assert panel_bottom_y <= composer_top_y - 8

    def test_resize_preserves_the_first_visible_message_for_a_reader(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(760, 650)
        chat_panel.show()
        for index in range(24):
            chat_panel.append_message(
                "assistant",
                f"Message {index}: " + ("workflow explanation " * 6),
            )
        qtbot.wait(30)

        bubbles = chat_panel.chat_content_widget.findChildren(MessageBubble)
        anchor = bubbles[8]
        scroll_bar = chat_panel.scroll_area.verticalScrollBar()
        viewport = chat_panel.scroll_area.viewport()
        assert scroll_bar is not None
        assert viewport is not None
        scroll_bar.setValue(
            max(
                scroll_bar.minimum(),
                anchor.mapTo(chat_panel.chat_content_widget, QPoint(0, 0)).y() - 36,
            )
        )
        qtbot.wait(10)
        captured_anchor = chat_panel._capture_reader_anchor()
        assert captured_anchor is not None
        anchor_id, anchor_y = captured_anchor
        anchor = next(
            bubble
            for bubble in bubbles
            if bubble.property("chatMessageId") == anchor_id
        )
        assert anchor_y < viewport.height()
        assert anchor_y + anchor.height() > 0

        for width in (420, 320, 760):
            chat_panel.resize(width, 650)
            qtbot.wait(40)
            assert abs(anchor.mapTo(viewport, QPoint(0, 0)).y() - anchor_y) <= 4

    def test_typed_record_update_streams_content_into_existing_bubble(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        controller = ChatController()
        chat_panel.connect_controller(controller)
        record = controller.add_agent_message(
            "Result:\n\n```python\nvalue = '" + ("x" * 180) + "'",
        )
        chat_panel.resize(320, 650)
        chat_panel.show()
        qtbot.wait(20)
        bubble = chat_panel._latest_message_bubble()
        assert bubble is not None
        code = bubble.code_blocks[0]
        code.horizontalScrollBar().setValue(code.horizontalScrollBar().maximum())
        old_scroll = code.horizontalScrollBar().value()

        updated = replace(record, content=record.content + "\nprint(value)")
        controller.message_record_updated.emit(updated)
        qtbot.wait(20)

        assert chat_panel._latest_message_bubble() is bubble
        assert bubble.get_text() == updated.content
        assert code.horizontalScrollBar().value() == old_scroll

    def test_messages_added_while_hidden_reflow_to_actual_narrow_viewport(
        self,
        chat_panel,
        qtbot,
    ):
        chat_panel.resize(320, 650)
        chat_panel.hide()
        chat_panel.append_message(
            "user",
            "Inspect this EEG workflow request before changing any data.",
        )
        chat_panel.append_message(
            "assistant",
            "The selected label file contains a "
            "very_long_unbroken_identifier_that_must_wrap_without_clipping.",
        )

        chat_panel.show()
        qtbot.wait(30)

        viewport = chat_panel.scroll_area.viewport()
        bubbles = chat_panel.chat_content_widget.findChildren(MessageBubble)
        assert viewport is not None
        assert len(bubbles) == 2
        for bubble in bubbles:
            assert bubble.bubble_frame is not None
            top_left = bubble.bubble_frame.mapTo(viewport, QPoint(0, 0))
            bottom_right = bubble.bubble_frame.mapTo(
                viewport,
                bubble.bubble_frame.rect().bottomRight(),
            )
            assert top_left.x() >= 0
            assert bottom_right.x() < viewport.width()
            assert bubble.bubble_frame.width() <= int(viewport.width() * 0.84) + 1
        assert chat_panel.input_field.isVisibleTo(chat_panel)
        assert chat_panel.send_btn.isVisibleTo(chat_panel)

    def test_panel_resize_reflows_code_block_without_chat_overflow(
        self,
        chat_panel,
        qtbot,
    ) -> None:
        chat_panel.resize(760, 650)
        chat_panel.show()
        chat_panel.append_message(
            "assistant",
            "Result:\n\n```python\nselected_files = ['"
            + ("subject_session_recording_" * 16)
            + "']\n```",
        )
        qtbot.wait(30)
        bubble = chat_panel._latest_message_bubble()
        assert bubble is not None
        assert len(bubble.code_blocks) == 1
        wide_code_width = bubble.code_blocks[0].width()

        chat_panel.resize(320, 650)
        qtbot.wait(40)

        viewport = chat_panel.scroll_area.viewport()
        assert viewport is not None
        assert bubble.code_blocks[0].width() < wide_code_width
        assert bubble.code_blocks[0].horizontalScrollBar().maximum() > 0
        assert chat_panel.scroll_area.horizontalScrollBar().maximum() == 0
        assert bubble.bubble_frame.width() <= int(viewport.width() * 0.84) + 1

    def test_capture_style_resize_keeps_latest_bubble_above_composer(self, chat_panel):
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        chat_panel.resize(320, 753)
        chat_panel.show()
        app.processEvents()

        messages = [
            ("user", "Hello."),
            (
                "assistant",
                "I can help interpret EEG data and prepare a training-ready dataset.",
            ),
            ("user", "Load my brainwave data."),
            (
                "assistant",
                "Choose a file, folder, BIDS root, or saved recipe before I can scan it.",
            ),
            ("user", "Train it now."),
            (
                "assistant",
                "Training is not ready until data, epochs, a dataset, a model, "
                "and settings are ready.",
            ),
            ("user", "What is ready now?"),
            (
                "assistant",
                "The dataset and training settings are ready; evaluation needs "
                "a completed run.",
            ),
        ]
        for sender, text in messages:
            chat_panel.append_message(sender, text)
            app.processEvents()

        chat_panel.resize(320, 655)
        app.processEvents()

        bubbles = chat_panel.chat_content_widget.findChildren(MessageBubble)
        assert bubbles
        panel_bottom_y = (
            bubbles[-1]
            .mapTo(
                chat_panel,
                QPoint(0, bubbles[-1].height()),
            )
            .y()
        )
        composer_top_y = chat_panel.control_panel.mapTo(chat_panel, QPoint(0, 0)).y()
        assert panel_bottom_y <= composer_top_y - 8

    def test_set_processing_state(self, chat_panel):
        chat_panel.set_processing_state(True)
        assert chat_panel.is_processing is True
        assert chat_panel.send_btn.text() == "Working"
        assert chat_panel.send_btn.isEnabled() is False
        assert chat_panel.input_field.isEnabled() is False
        chat_panel.set_processing_state(False)
        assert chat_panel.is_processing is False
        assert chat_panel.send_btn.text() == "Send"
        assert chat_panel.send_btn.accessibleName() == "Send request"
        assert chat_panel.send_btn.icon().isNull()
        assert chat_panel.send_btn.toolButtonStyle() == (
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        assert chat_panel.input_field.isEnabled() is True

    def test_clear_ui(self, chat_panel):
        chat_panel.append_message("user", "msg1")
        chat_panel.append_message("assistant", "msg2")
        stale_bubbles = chat_panel.chat_content_widget.findChildren(MessageBubble)
        assert stale_bubbles
        chat_panel._clear_ui()
        assert chat_panel._latest_message_bubble() is None
        assert chat_panel.empty_state_widget.isHidden() is False
        assert all(
            bubble.parent() is None or not bubble.isVisible()
            for bubble in stale_bubbles
        )

    def test_clear_ui_discards_stale_reader_anchor(self, chat_panel) -> None:
        chat_panel._reader_anchor = ("stale-message", -24)
        chat_panel._reader_anchor_restore_attempts = 2
        chat_panel._reader_anchor_timer.start(100)

        chat_panel._clear_ui()

        assert chat_panel._reader_anchor is None
        assert chat_panel._reader_anchor_restore_attempts == 0
        assert chat_panel._reader_anchor_timer.isActive() is False

    def test_status_summary_updates_visible_empty_state_and_tooltip(self, chat_panel):
        chat_panel.set_status_summary("Backend: empty", "Train blocked")
        assert chat_panel.empty_state_title.text() == "Start with your EEG data"
        assert chat_panel.empty_state_widget.accessibleDescription() == (
            "No EEG files are open yet."
        )
        assert "Train blocked" in chat_panel.empty_state_widget.toolTip()

    def test_panel_has_no_hidden_second_runtime_or_status_surface(self, chat_panel):
        for legacy_name in (
            "model_btn",
            "feature_btn",
            "mode_btn",
            "status_label",
            "runtime_status_label",
            "workflow_guidance",
        ):
            assert not hasattr(chat_panel, legacy_name)

    def test_product_ui_structure_is_visible(self, chat_panel):
        assert chat_panel.empty_state_title.text() == "Start with your EEG data"
        assert chat_panel.empty_state_intro.text() == (
            "Ask me to find EEG files, explain supported formats, or begin an import."
        )
        assert chat_panel.empty_state_widget.isHidden() is False
        assert chat_panel.empty_state_widget.accessibleDescription() == (
            "No EEG files are open yet."
        )
        assert chat_panel.empty_state_action_button.text() == (
            "Explain the import workflow"
        )
        assert not chat_panel.empty_state_action_button.isHidden()
        assert chat_panel.empty_state_next_label.isHidden()
        assert chat_panel.input_field.isHidden() is False
        assert chat_panel.send_btn.text() == "Send"
        assert chat_panel.send_btn.accessibleName() == "Send request"
        assert chat_panel.send_btn.icon().isNull()
        assert chat_panel.send_btn.toolButtonStyle() == (
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        assert not hasattr(chat_panel, "mode_selector_widget")
        visible_footer_labels = [
            label.text()
            for label in chat_panel.control_panel.findChildren(QLabel)
            if not label.isHidden()
        ]
        assert visible_footer_labels == []

        visible_text = " ".join(
            child.text()
            for child in chat_panel.findChildren(QWidget)
            if isinstance(child, (QLabel, QToolButton))
            and child.isVisible()
            and child.text()
        )
        for hidden_product_detail in [
            "Assistant",
            "Conversation",
            "Step behavior",
            "Single step",
            "Step by step",
            "Continue safely",
            "Local model ready",
            "Backend:",
            "Commands:",
            "load_data",
        ]:
            assert hidden_product_detail not in visible_text

    def test_empty_state_action_uses_its_own_readable_style(self, chat_panel):
        chat_panel.set_product_status(
            stage="Results available",
            model_status="Ready",
            available_commands=["evaluate"],
        )

        assert chat_panel.empty_state_action_button.isEnabled()
        assert "QPushButton#AssistantSuggestionPrompt" in (
            chat_panel.empty_state_action_button.styleSheet()
        )

    def test_loading_blank_space_uses_panel_background_not_black(
        self,
        qtbot,
    ):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)
            panel.resize(320, 650)
            panel.set_runtime_state("loading")
            panel.show()
            qtbot.wait(20)

        pixel = panel.grab().toImage().pixelColor(QPoint(8, 320)).name().lower()
        from XBrainLab.ui.styles.theme import Theme

        assert pixel == Theme.BACKGROUND_DARK

    def test_product_status_updates_visible_empty_state(self, chat_panel):
        chat_panel.set_product_status(
            stage="empty",
            model_status="Setup needed",
            available_commands=["scan_source", "load_data", "attach_labels"],
            tooltip="Setup is incomplete",
            blocked_reason="Generate datasets before training.",
        )

        assert chat_panel.empty_state_widget.accessibleDescription() == (
            "No EEG files are open yet."
        )
        assert chat_panel.empty_state_action_button.text() == (
            "Explain the import workflow"
        )
        assert (
            chat_panel.empty_state_action_button.property("assistantPrompt")
            == "Explain the EEG data import workflow"
        )
        assert not chat_panel.empty_state_action_button.isHidden()
        assert chat_panel.empty_state_next_label.isHidden()
        assert "Setup needed" in chat_panel.empty_state_widget.toolTip()
        visible_text = " ".join(
            label.text()
            for label in chat_panel.findChildren(QLabel)
            if label.isVisible()
        )
        assert "load_data" not in visible_text
        assert "attach_labels" not in visible_text

    def test_product_status_empty_stage_without_scan_capability_uses_safe_prompt(
        self,
        chat_panel,
    ):
        chat_panel.set_product_status(
            stage="No data loaded",
            model_status="Ready",
            available_commands=[],
            tooltip="No EEG data open",
            blocked_reason=None,
        )

        assert chat_panel.empty_state_next_label.text() == (
            "Scan a data source to begin"
        )
        assert not chat_panel.empty_state_next_label.isHidden()
        assert not chat_panel.empty_state_action_button.isHidden()
        assert (
            chat_panel.empty_state_action_button.property("assistantPrompt")
            == "Check the current workflow status"
        )

    def test_product_status_results_stage_uses_results_empty_state(self, chat_panel):
        chat_panel.set_product_status(
            stage="Results available",
            model_status="Ready",
            available_commands=["evaluate", "visualize"],
            tooltip="Training finished",
            blocked_reason=None,
        )

        assert chat_panel.empty_state_title.text() == "Explore your results"
        assert chat_panel.empty_state_intro.text() == (
            "Ask me to explain metrics, review available analyses, or recommend "
            "what to inspect next."
        )
        assert chat_panel.empty_state_widget.accessibleDescription() == (
            "Current workflow stage: Results available."
        )
        assert chat_panel.empty_state_action_button.text() == (
            "Suggest the next analysis"
        )
        assert (
            chat_panel.empty_state_action_button.property("assistantPrompt")
            == "Explain how to choose the next analysis for the current results"
        )
        assert all(
            button.accessibleName() == button.text()
            for button in chat_panel.suggestion_prompt_buttons
        )
        assert not chat_panel.empty_state_action_button.isHidden()
        assert chat_panel.empty_state_next_label.isHidden()

    def test_empty_state_action_sends_stage_aware_request(self, chat_panel, qtbot):
        chat_panel.set_runtime_state("ready")
        chat_panel.set_product_status(
            stage="Results available",
            model_status="Ready",
            available_commands=["evaluate", "visualize"],
        )

        emitted: list[str] = []
        chat_panel.send_message.connect(emitted.append)
        chat_panel.empty_state_action_button.click()

        assert emitted == []
        assert chat_panel.input_field.text() == (
            "Explain how to choose the next analysis for the current results"
        )

    def test_product_status_training_stage_uses_running_empty_state(self, chat_panel):
        chat_panel.set_product_status(
            stage="Training running",
            model_status="Ready",
            available_commands=["stop_training"],
            tooltip="Training is active",
            blocked_reason=None,
        )

        assert chat_panel.empty_state_title.text() == "Training is running"
        assert chat_panel.empty_state_intro.text() == (
            "Ask for progress or stop the current training run."
        )

    def test_low_priority_notice_does_not_enter_transcript(self, chat_panel):
        chat_panel.show_notice("Send a request before using Retry.")
        assert chat_panel.notice_label.isHidden() is False
        assert "Retry" in chat_panel.notice_label.text()
        transcript_widgets = [
            item.widget()
            for index in range(chat_panel.chat_layout.count())
            if (item := chat_panel.chat_layout.itemAt(index)) is not None
        ]
        assert not any(
            isinstance(widget, MessageBubble) for widget in transcript_widgets
        )
        assert chat_panel.response_actions_widget.isHidden()

    def test_runtime_notice_clear_preserves_newer_general_notice(self, chat_panel):
        chat_panel.show_runtime_notice("Assistant unavailable")
        chat_panel.show_notice("Settings saved", timeout_ms=0)

        chat_panel.clear_runtime_notice()

        assert chat_panel.notice_label.text() == "Settings saved"
        assert chat_panel.notice_label.isHidden() is False

    def test_low_priority_notice_expires_without_clearing_newer_notice(
        self,
        chat_panel,
        qtbot,
    ):
        chat_panel.show_notice("First", timeout_ms=10)
        chat_panel.show_notice("Second", timeout_ms=50)
        qtbot.wait(20)

        assert chat_panel.notice_label.text() == "Second"
        assert chat_panel.notice_label.isHidden() is False

        qtbot.wait(50)
        assert chat_panel.notice_label.isHidden()

    @pytest.mark.parametrize("width", [320, 380, 460])
    def test_narrow_dock_composer_controls_fit(self, qtbot, chat_panel, width):
        chat_panel.resize(width, 720)
        chat_panel.show()
        qtbot.wait(10)

        send_top_left = chat_panel.send_btn.mapTo(
            chat_panel.input_widget,
            QPoint(0, 0),
        )
        assert not chat_panel.input_field.geometry().intersects(
            QRect(send_top_left, chat_panel.send_btn.size())
        )
        assert not hasattr(chat_panel, "mode_selector_widget")
        _assert_inside_panel_on_all_sides(chat_panel, chat_panel.input_widget)

    @pytest.mark.parametrize("height", [520, 650])
    def test_long_clarification_keeps_fixed_controls_inside_narrow_panel(
        self,
        qtbot,
        chat_panel,
        height,
    ):
        full_label = (
            "Review "
            "subject_01_session_02_task_motor_run_000000000000000000000000000001 "
            "label alignment before continuing"
        )
        controller = ChatController()
        chat_panel.connect_controller(controller)
        chat_panel.resize(320, height)
        chat_panel.show()
        controller.add_agent_message(
            (
                "The selected EEG source needs one decision before import can continue. "
                "Review "
                "subject_01_session_02_task_motor_run_000000000000000000000000000001 "
                "and confirm which event stream supplies labels. The transcript must "
                "scroll without moving the controls below.\n\n"
                + "\n\n".join(
                    (
                        "Keep the imported data unchanged while this clarification is "
                        "pending. The assistant should preserve the current workflow "
                        "state and leave the decision to the existing Data Import UI."
                    )
                    for _ in range(8)
                )
            ),
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            presentation_id=f"long-clarification-{height}",
            actions=(
                ChatResponseAction(
                    action_id=f"review-labels-{height}",
                    label=full_label,
                    kind=ChatResponseActionKind.SEND_MESSAGE,
                    prompt="Review the unresolved label alignment.",
                ),
            ),
        )
        qtbot.wait(30)

        action = chat_panel.response_actions_widget.findChild(QToolButton)
        assert action is not None
        assert chat_panel.size().width() == 320
        assert chat_panel.size().height() == height
        assert chat_panel.scroll_area.verticalScrollBar().maximum() > 0
        for control in (
            chat_panel.input_field,
            chat_panel.send_btn,
            action,
        ):
            assert control.isVisibleTo(chat_panel)
            _assert_inside_panel_on_all_sides(chat_panel, control)
        assert not hasattr(chat_panel, "mode_selector_widget")
        assert action.toolTip() == full_label
        assert "…" in action.text()
        assert action.text().startswith("Review ")
        assert action.text().endswith("before continuing")
        assert chat_panel.scroll_area.isAncestorOf(chat_panel.response_actions_widget)
        assert (
            chat_panel.response_actions_widget.mapTo(
                chat_panel,
                chat_panel.response_actions_widget.rect().bottomLeft(),
            ).y()
            < chat_panel.control_panel.mapTo(chat_panel, QPoint(0, 0)).y()
        )
        composer_top = chat_panel.input_widget.mapTo(
            chat_panel,
            QPoint(0, 0),
        ).y()
        assert (
            composer_top
            >= chat_panel.control_panel.mapTo(
                chat_panel,
                QPoint(0, 0),
            ).y()
        )
        assert chat_panel.scroll_area.geometry().bottom() < (
            chat_panel.control_panel.geometry().top()
        )

    def test_control_panel_hugs_content_without_large_vertical_gap(
        self,
        qtbot,
        chat_panel,
    ):
        chat_panel.resize(420, 780)
        chat_panel.show()
        qtbot.wait(10)

        assert chat_panel.control_panel.height() <= 230

    def test_sparse_transcript_keeps_consecutive_turns_together(
        self,
        qtbot,
        chat_panel,
    ):
        chat_panel.resize(420, 780)
        chat_panel.show()
        chat_panel.append_message("user", "Hello.")
        chat_panel.append_message(
            "assistant",
            "I can help interpret EEG data and prepare a training-ready dataset.",
        )
        qtbot.wait(20)

        bubbles = [
            chat_panel.chat_layout.itemAt(index).widget()
            for index in range(chat_panel.chat_layout.count())
            if isinstance(
                chat_panel.chat_layout.itemAt(index).widget(),
                MessageBubble,
            )
        ]
        assert len(bubbles) == 2
        first_bottom = bubbles[0].geometry().bottom()
        second_top = bubbles[1].geometry().top()
        assert 0 <= second_top - first_bottom <= 24
        assert bubbles[0].geometry().top() <= 24

    def test_deferred_empty_state_scroll_is_owned_by_panel(
        self,
        qapp,
    ):
        with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            panel.resize(320, 520)
            panel.set_runtime_state("ready")
            panel.show()
            qapp.processEvents()
            panel._scroll_empty_state_to_top()
            panel.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            qapp.processEvents()

    @pytest.mark.parametrize("width", [320, 380, 460])
    def test_user_bubble_keeps_short_word_readable_in_narrow_dock(
        self,
        qtbot,
        chat_panel,
        width,
    ):
        chat_panel.resize(width, 720)
        chat_panel.show()
        chat_panel.append_message("user", "hello")
        qtbot.wait(10)

        bubble = next(
            chat_panel.chat_layout.itemAt(i).widget()
            for i in range(chat_panel.chat_layout.count())
            if hasattr(chat_panel.chat_layout.itemAt(i).widget(), "get_text")
        )
        assert bubble.get_text() == "hello"
        assert 72 <= bubble.bubble_frame.width() <= 110
        assert bubble.text_edit.document().textWidth() >= 48
