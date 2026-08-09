"""Transient action cards shown inside the assistant message area."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent, QKeyEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest
from XBrainLab.product_language import tool_action_label

from .styles import (
    ACTION_CARD_CONTEXT_WARNING_STYLE,
    ACTION_CARD_DESTRUCTIVE_BUTTON_STYLE,
    ACTION_CARD_FRAME_STYLE,
    ACTION_CARD_LABEL_STYLE,
    ACTION_CARD_PRIMARY_BUTTON_STYLE,
    ACTION_CARD_PROPOSAL_ROW_STYLE,
    ACTION_CARD_SECONDARY_BUTTON_STYLE,
    ACTION_CARD_TEXT_STYLE,
    ACTION_CARD_TITLE_STYLE,
)

_SOFT_WRAP_MARK = "\u200b"
_MAX_UNBROKEN_DISPLAY_CHARS = 12
_SETTING_CHANGE_COMMANDS = frozenset({"configure_training", "set_model"})
_PARAMETER_LABELS = {
    "batch size": "Batch size",
    "checkpoint policy": "Checkpoint saving",
    "device": "Compute device",
    "epoch": "Training epochs",
    "evaluation option": "Model selection",
    "learning rate": "Learning rate",
    "model": "Model",
    "model name": "Model",
    "optimizer": "Optimizer",
    "output dir": "Output folder",
    "output directory": "Output folder",
    "repeat": "Training runs",
    "save checkpoints every": "Checkpoint interval",
}
_DISPLAY_ACRONYMS = {
    "amsgrad": "AMSGrad",
    "auc": "AUC",
    "cpu": "CPU",
    "eeg": "EEG",
    "gpu": "GPU",
    "id": "ID",
    "url": "URL",
}
_DISPLAY_VALUES = {
    "adam": "Adam",
    "adamw": "AdamW",
    "cpu": "CPU",
    "cuda": "CUDA",
    "false": "No",
    "last_epoch": "Last training epoch",
    "none": "Not set",
    "null": "Not set",
    "sgd": "SGD",
    "true": "Yes",
    "val_acc": "Validation accuracy",
    "val_auc": "Validation AUC",
    "val_loss": "Validation loss",
}


def _setting_change_action_labels(
    request: AgentConfirmationRequest,
) -> tuple[str, str]:
    """Match setting-change actions to the number of proposed values."""
    if len(request.parameter_rows) == 1:
        return "Apply change", "Keep current value"
    return "Apply changes", "Keep current"


def _add_soft_wrap_opportunities(text: str) -> str:
    """Let Qt wrap long paths, hashes, and identifiers without changing meaning."""

    def wrap_token(match: re.Match[str]) -> str:
        token = match.group(0)
        return _SOFT_WRAP_MARK.join(
            token[index : index + _MAX_UNBROKEN_DISPLAY_CHARS]
            for index in range(0, len(token), _MAX_UNBROKEN_DISPLAY_CHARS)
        )

    return re.sub(
        rf"[^\s{_SOFT_WRAP_MARK}]{{{_MAX_UNBROKEN_DISPLAY_CHARS + 1},}}",
        wrap_token,
        text,
    )


def _normalized_words(text: str) -> list[str]:
    normalized = re.sub(r"[_\-.]+", " ", str(text or "").strip())
    return [word for word in normalized.split() if word]


def _humanize_parameter_label(label: str) -> str:
    """Return deterministic first-layer copy for one parameter identifier."""
    words = _normalized_words(label)
    key = " ".join(words).casefold()
    if key in _PARAMETER_LABELS:
        return _PARAMETER_LABELS[key]
    if not words:
        return "Setting"
    rendered = [
        _DISPLAY_ACRONYMS.get(word.casefold(), word.casefold()) for word in words
    ]
    if rendered[0] not in _DISPLAY_ACRONYMS.values():
        rendered[0] = rendered[0].capitalize()
    return " ".join(rendered)


def _humanize_scalar(value: object) -> str:
    if value is None:
        return "Not set"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if not isinstance(value, str):
        return str(value)
    stripped = value.strip()
    known = _DISPLAY_VALUES.get(stripped.casefold())
    if known is not None:
        return known
    if re.fullmatch(r"[a-z][a-z0-9_]*", stripped) and "_" in stripped:
        return _humanize_parameter_label(stripped)
    return value


def _format_structured_value(value: object) -> str:
    if isinstance(value, Mapping):
        if not value:
            return "No values"
        lines: list[str] = []
        for key in sorted(value, key=lambda item: str(item)):
            label = _humanize_parameter_label(str(key))
            rendered = _format_structured_value(value[key])
            if "\n" in rendered:
                indented = "\n".join(f"  {line}" for line in rendered.splitlines())
                lines.append(f"{label}:\n{indented}")
            else:
                lines.append(f"{label}: {rendered}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "No values"
        rendered_items = [_format_structured_value(item) for item in value]
        if all("\n" not in item for item in rendered_items):
            return ", ".join(rendered_items)
        return "\n".join("- " + item.replace("\n", "\n  ") for item in rendered_items)
    return _humanize_scalar(value)


def _format_display_value(raw_value: str) -> str:
    """Present structured values without exposing raw JSON punctuation."""
    stripped = raw_value.strip()
    if stripped.startswith(("{", "[")):
        try:
            decoded = json.loads(stripped)
        except ValueError:
            pass
        else:
            return _format_structured_value(decoded)
    return _humanize_scalar(raw_value)


class _SoftWrappingValueLabel(QLabel):
    """Wrap long tokens visually while copying the exact original value."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._raw_text = ""

    def set_wrapped_text(self, text: str) -> None:
        self._raw_text = text
        self.setText(_add_soft_wrap_opportunities(text))
        self.setAccessibleDescription(text)

    def fit_height_to_current_width(self) -> None:
        """Recompute wrapped text height after the proposal viewport settles."""
        if not self.isVisible() or not self.text():
            self.setMinimumHeight(0)
            return
        available_width = max(self.contentsRect().width(), 1)
        needed = self.fontMetrics().boundingRect(
            QRect(0, 0, available_width, 10_000),
            int(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap
            ),
            self.text(),
        )
        self.setMinimumHeight(max(needed.height(), self.fontMetrics().height()))

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802
        if event is None:
            super().keyPressEvent(event)
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:  # noqa: N802
        if event is None:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        if copy_action is None:
            return
        copy_action.setEnabled(bool(self.selectedText()))
        copy_action.triggered.connect(self._copy_selection)
        menu.exec(event.globalPos())

    def _copy_selection(self) -> None:
        selected = self.selectedText()
        if not selected:
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(selected.replace(_SOFT_WRAP_MARK, "").replace("\u2029", "\n"))


class _ProposalRow(QFrame):
    """One readable current-to-proposed setting comparison."""

    def __init__(
        self,
        label: str,
        current: str | None,
        proposed: str,
        setting_change: bool,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AssistantProposalRow")
        self.setStyleSheet(ACTION_CARD_PROPOSAL_ROW_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self.label = _SoftWrappingValueLabel(self)
        self.label.setObjectName("AssistantProposalLabel")
        self.label.set_wrapped_text(label)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        values = QWidget(self)
        values.setStyleSheet("background: transparent; border: none;")
        values_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, values)
        values_layout.setContentsMargins(0, 0, 0, 0)
        values_layout.setSpacing(5)

        current_group = QWidget(values)
        current_group.setStyleSheet("background: transparent; border: none;")
        current_layout = QVBoxLayout(current_group)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.setSpacing(1)
        self.current_caption = QLabel("Current", current_group)
        self.current_caption.setObjectName("AssistantProposalCaption")
        current_layout.addWidget(self.current_caption)
        self.current_value = _SoftWrappingValueLabel(current_group)
        self.current_value.setObjectName("AssistantProposalCurrent")
        current_display = _format_display_value(current) if current is not None else ""
        self.current_value.set_wrapped_text(current_display)
        self.current_value.setWordWrap(True)
        self.current_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        current_layout.addWidget(self.current_value)
        proposed_display = _format_display_value(proposed)
        current_visible = current is not None and current_display != proposed_display
        current_group.setVisible(current_visible)
        self.current_caption.setVisible(current_visible)
        self.current_value.setVisible(current_visible)
        values_layout.addWidget(current_group, 1)

        proposed_group = QWidget(values)
        proposed_group.setStyleSheet("background: transparent; border: none;")
        proposed_layout = QVBoxLayout(proposed_group)
        proposed_layout.setContentsMargins(0, 0, 0, 0)
        proposed_layout.setSpacing(1)
        self.proposed_caption = QLabel(
            "Proposed" if setting_change else "Details",
            proposed_group,
        )
        self.proposed_caption.setObjectName("AssistantProposalCaption")
        proposed_layout.addWidget(self.proposed_caption)
        self.proposed_value = _SoftWrappingValueLabel(proposed_group)
        self.proposed_value.setObjectName("AssistantProposalValue")
        self.proposed_value.set_wrapped_text(proposed_display)
        self.proposed_value.setWordWrap(True)
        self.proposed_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        proposed_layout.addWidget(self.proposed_value)
        values_layout.addWidget(proposed_group, 1)
        layout.addWidget(values)


class AssistantConfirmationCard(QFrame):
    """Present one exact correlated assistant action for user approval."""

    decision_requested = pyqtSignal(object, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._request: AgentConfirmationRequest | None = None
        self.setObjectName("AssistantConfirmationCard")
        self.setStyleSheet(ACTION_CARD_FRAME_STYLE)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.title_label = QLabel("Confirmation required")
        self.title_label.setObjectName("AssistantActionCardTitle")
        self.title_label.setStyleSheet(ACTION_CARD_TITLE_STYLE)
        layout.addWidget(self.title_label)

        self.description_label = QLabel("")
        self.description_label.setObjectName("AssistantActionCardDescription")
        self.description_label.setStyleSheet(ACTION_CARD_TEXT_STYLE)
        self.description_label.setWordWrap(True)
        self.description_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        layout.addWidget(self.description_label)

        self.context_warning = QLabel("")
        self.context_warning.setObjectName("AssistantActionContextWarning")
        self.context_warning.setStyleSheet(ACTION_CARD_CONTEXT_WARNING_STYLE)
        self.context_warning.setWordWrap(True)
        self.context_warning.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.context_warning.setVisible(False)
        layout.addWidget(self.context_warning)

        self.proposal_rows_widget = QWidget(self)
        self.proposal_rows_widget.setObjectName("AssistantProposalRows")
        self.proposal_rows_widget.setStyleSheet(
            "background: transparent; border: none;"
        )
        self.proposal_rows_layout = QVBoxLayout(self.proposal_rows_widget)
        self.proposal_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.proposal_rows_layout.setSpacing(6)
        self.proposal_rows: list[_ProposalRow] = []

        self.details_title = QLabel("Proposed settings")
        self.details_title.setObjectName("AssistantActionCardLabel")
        self.details_title.setStyleSheet(ACTION_CARD_LABEL_STYLE)
        layout.addWidget(self.details_title)

        self.proposal_scroll = QScrollArea(self)
        self.proposal_scroll.setObjectName("AssistantProposalScroll")
        self.proposal_scroll.setWidgetResizable(True)
        self.proposal_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.proposal_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.proposal_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.proposal_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.proposal_scroll.setStyleSheet("background: transparent; border: none;")
        self.proposal_scroll.setWidget(self.proposal_rows_widget)
        proposal_viewport = self.proposal_scroll.viewport()
        if proposal_viewport is not None:
            proposal_viewport.installEventFilter(self)
        self._proposal_reflow_timer = QTimer(self)
        self._proposal_reflow_timer.setSingleShot(True)
        self._proposal_reflow_timer.timeout.connect(
            self._update_proposal_viewport_height
        )
        layout.addWidget(self.proposal_scroll)

        self.reason_title = QLabel("Reason")
        self.reason_title.setObjectName("AssistantActionCardLabel")
        self.reason_title.setStyleSheet(ACTION_CARD_LABEL_STYLE)
        layout.addWidget(self.reason_title)

        self.reason_label = QLabel("")
        self.reason_label.setObjectName("AssistantActionCardReason")
        self.reason_label.setStyleSheet(ACTION_CARD_TEXT_STYLE)
        self.reason_label.setWordWrap(True)
        self.reason_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        layout.addWidget(self.reason_label)

        button_row = QWidget(self)
        button_row.setObjectName("AssistantActionCardButtons")
        button_row.setStyleSheet("background: transparent; border: none;")
        button_layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight,
            button_row,
        )
        self.button_layout = button_layout
        button_layout.setContentsMargins(0, 2, 0, 0)
        button_layout.setSpacing(8)

        self.secondary_button = QPushButton("Keep current value")
        self.secondary_button.setObjectName("AssistantActionCardSecondary")
        self.secondary_button.setStyleSheet(ACTION_CARD_SECONDARY_BUTTON_STYLE)
        self.secondary_button.setMinimumHeight(34)
        self.secondary_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.secondary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.secondary_button.clicked.connect(
            lambda _checked=False: self._resolve(False)
        )
        button_layout.addWidget(self.secondary_button)

        self.primary_button = QPushButton("Apply change")
        self.primary_button.setObjectName("AssistantActionCardPrimary")
        self.primary_button.setStyleSheet(ACTION_CARD_PRIMARY_BUTTON_STYLE)
        self.primary_button.setMinimumHeight(34)
        self.primary_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.primary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_button.clicked.connect(lambda _checked=False: self._resolve(True))
        button_layout.addWidget(self.primary_button)
        layout.addWidget(button_row)
        self.details_title.setVisible(False)
        self.proposal_scroll.setVisible(False)
        self.setVisible(False)

    @property
    def request_id(self) -> str | None:
        """Return the id of the request currently leased to this card."""
        return self._request.request_id if self._request is not None else None

    @property
    def command_name(self) -> str | None:
        """Return the command identity currently leased to this card."""
        return self._request.command_name if self._request is not None else None

    def present(
        self,
        request: AgentConfirmationRequest,
        *,
        current_values: Mapping[str, str] | None = None,
        current_context_changed: bool = False,
    ) -> None:
        """Render a request without changing or reconstructing its parameters."""
        if not isinstance(request, AgentConfirmationRequest):
            raise TypeError("Assistant confirmation cards require a typed request.")
        self._request = request
        self.setProperty("destructive", request.destructive)
        setting_change = request.command_name in _SETTING_CHANGE_COMMANDS
        self.title_label.setText(
            "High-risk confirmation"
            if request.destructive
            else ("Suggested change" if setting_change else "Confirmation required")
        )
        self.description_label.setText(request.action_label)
        self.description_label.setVisible(not setting_change)
        self.reason_label.setText(request.description)
        self.context_warning.setText(
            "The workflow changed after this suggestion. XBrainLab will validate "
            "the action again before applying it."
            if current_context_changed
            else ""
        )
        self.context_warning.setVisible(current_context_changed)
        self._render_proposal_rows(
            request,
            current_values=current_values,
            setting_change=setting_change,
        )

        if setting_change:
            primary_label, secondary_label = _setting_change_action_labels(request)
        else:
            primary_label = tool_action_label(request.command_name)
            secondary_label = "Cancel"
        self.primary_button.setText(primary_label)
        self.primary_button.setAccessibleName(primary_label)
        self.primary_button.setAccessibleDescription(request.action_label)
        self.primary_button.setToolTip(
            request.action_label if request.action_label != primary_label else ""
        )
        self.primary_button.setStyleSheet(
            ACTION_CARD_DESTRUCTIVE_BUTTON_STYLE
            if request.destructive
            else ACTION_CARD_PRIMARY_BUTTON_STYLE
        )
        self.secondary_button.setText(secondary_label)
        self.secondary_button.setAccessibleName(secondary_label)
        self.set_submitting(False)
        self._update_button_layout_direction()
        self.setVisible(True)
        self._proposal_reflow_timer.start(0)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def _render_proposal_rows(
        self,
        request: AgentConfirmationRequest,
        *,
        current_values: Mapping[str, str] | None,
        setting_change: bool,
    ) -> None:
        """Render a human-facing projection without changing the typed request."""
        while self.proposal_rows:
            row = self.proposal_rows.pop()
            self.proposal_rows_layout.removeWidget(row)
            row.deleteLater()
        current = {
            _humanize_parameter_label(str(key)).casefold(): str(value)
            for key, value in (current_values or {}).items()
        }
        for raw_label, proposed in request.parameter_rows:
            label = _humanize_parameter_label(raw_label)
            row = _ProposalRow(
                label,
                current.get(label.casefold()),
                proposed,
                setting_change,
                self.proposal_rows_widget,
            )
            self.proposal_rows.append(row)
            self.proposal_rows_layout.addWidget(row)
        has_rows = bool(self.proposal_rows)
        self.details_title.setText(
            "Proposed settings" if setting_change else "Action details"
        )
        self.details_title.setVisible(has_rows)
        self.proposal_rows_widget.setVisible(has_rows)
        self.proposal_scroll.setVisible(has_rows)
        self._update_proposal_viewport_height()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Stack actions when both labels cannot remain readable."""
        super().resizeEvent(event)
        self._update_proposal_viewport_height()
        self._proposal_reflow_timer.start(0)
        self._update_button_layout_direction()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """Reflow rows from the real scroll viewport, not its pre-show default."""
        proposal_scroll = getattr(self, "proposal_scroll", None)
        if (
            proposal_scroll is not None
            and watched is proposal_scroll.viewport()
            and event is not None
            and event.type() is QEvent.Type.Resize
        ):
            self._proposal_reflow_timer.start(0)
        return super().eventFilter(watched, event)

    def _update_proposal_viewport_height(self) -> None:
        """Give proposal rows their natural height; the transcript owns scrolling."""
        if not self.proposal_rows:
            return
        card_layout = self.layout()
        margins = card_layout.contentsMargins() if card_layout is not None else None
        horizontal_margins = (
            margins.left() + margins.right() if margins is not None else 0
        )
        viewport = self.proposal_scroll.viewport()
        viewport_width = viewport.width() if viewport is not None else 0
        row_width = max(
            viewport_width
            if viewport_width > 0
            else self.width()
            - horizontal_margins
            - (2 * self.proposal_scroll.frameWidth()),
            80,
        )
        self.proposal_rows_widget.setFixedWidth(row_width)
        row_heights: list[int] = []
        for row in self.proposal_rows:
            row.setFixedWidth(row_width)
            row_layout = row.layout()
            if row_layout is not None:
                row_layout.activate()
            for label in (row.label, row.current_value, row.proposed_value):
                label.setMinimumHeight(0)
            if row_layout is not None:
                row_layout.activate()
            for label in (row.label, row.current_value, row.proposed_value):
                label.fit_height_to_current_width()
            if row_layout is not None:
                row_layout.activate()
            row.adjustSize()
            row_heights.append(max(row.sizeHint().height(), row.height(), 56))
        rows_height = sum(row_heights)
        spacing_height = self.proposal_rows_layout.spacing() * max(
            len(self.proposal_rows) - 1,
            0,
        )
        frame_height = self.proposal_scroll.frameWidth() * 2
        content_height = rows_height + spacing_height
        self.proposal_rows_widget.setFixedHeight(content_height)
        self.proposal_scroll.setFixedHeight(content_height + frame_height)

    def _update_button_layout_direction(self) -> None:
        """Choose the action layout from rendered labels, not a viewport guess."""
        self.ensurePolished()
        self.primary_button.ensurePolished()
        self.secondary_button.ensurePolished()
        card_layout = self.layout()
        card_margins = (
            card_layout.contentsMargins() if card_layout is not None else None
        )
        button_margins = self.button_layout.contentsMargins()
        horizontal_padding = (
            ((card_margins.left() + card_margins.right()) if card_margins else 0)
            + button_margins.left()
            + button_margins.right()
        )
        available_width = max(self.width() - horizontal_padding, 1)
        required_horizontal_width = (
            self.primary_button.sizeHint().width()
            + self.secondary_button.sizeHint().width()
            + self.button_layout.spacing()
        )
        self.button_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if available_width < required_horizontal_width
            else QBoxLayout.Direction.LeftToRight
        )

    def set_submitting(self, submitting: bool) -> None:
        """Prevent duplicate decisions while the runtime accepts the response."""
        self.primary_button.setEnabled(not submitting)
        self.secondary_button.setEnabled(not submitting)
        if submitting:
            setting_change = (
                self._request is not None
                and self._request.command_name in _SETTING_CHANGE_COMMANDS
            )
            label = "Applying..." if setting_change else "Working..."
            self.primary_button.setText(label)
            self.primary_button.setAccessibleName(label)
        elif self._request is not None:
            setting_change = self._request.command_name in _SETTING_CHANGE_COMMANDS
            label = (
                _setting_change_action_labels(self._request)[0]
                if setting_change
                else tool_action_label(self._request.command_name)
            )
            self.primary_button.setText(label)
            self.primary_button.setAccessibleName(label)
        self._update_button_layout_direction()

    def clear(self) -> None:
        """Release the UI lease without creating any backend resolution."""
        self._request = None
        self.setVisible(False)

    def _resolve(self, approved: bool) -> None:
        request = self._request
        if request is None or not self.primary_button.isEnabled():
            return
        self.set_submitting(True)
        self.decision_requested.emit(request, approved)
