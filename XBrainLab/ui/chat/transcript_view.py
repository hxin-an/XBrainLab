"""Qt transcript viewport, bounded history rebuilds and reading position."""

from contextlib import suppress

from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.controller.chat_controller import (
    ChatHistoryReplacement,
    ChatHistoryReplacementKind,
    ChatMessageRecord,
    ChatMessageRole,
)
from XBrainLab.ui.styles.theme import Theme

from .message_bubble import MessageBubble
from .styles import SCROLL_AREA_STYLE

HISTORY_REBUILD_CHUNK_SIZE = 12


class ChatTranscriptView(QScrollArea):
    """Own rendered rows and their Qt work, never canonical history or turn policy.

    The four existing transient surfaces share this viewport's layout. Their
    contents and visibility remain owned by ChatPanel; fitting is requested
    synchronously before the viewport commits geometry.
    """

    surface_fit_requested = pyqtSignal(int)
    content_changed = pyqtSignal()
    history_replacement_started = pyqtSignal(bool)

    def __init__(
        self,
        *,
        runtime_surface: QWidget,
        empty_surface: QWidget,
        confirmation_surface: QWidget,
        activity_surface: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.runtime_state_widget = runtime_surface
        self.empty_state_widget = empty_surface
        self.confirmation_card_widget = confirmation_surface
        self.turn_activity_widget = activity_surface
        self._pending_scroll_to_bottom = False
        self._applying_tail_scroll = False
        self._viewport_reflow_pending = False
        self._reader_anchor: tuple[str, int] | None = None
        self._reader_anchor_restore_attempts = 0
        self._restoring_reader_anchor = False
        self._follow_transcript_updates = True
        self._message_bubbles_by_id: dict[str, MessageBubble] = {}
        self._history_rebuild_active = False
        self._history_rebuild_phase = "idle"
        self._history_rebuild_index = 0
        self._history_rebuild_delta_index = 0
        self._history_rebuild_snapshot: tuple[ChatMessageRecord, ...] = ()
        self._history_rebuild_order: dict[str, int] = {}
        self._history_rebuild_deltas: list[ChatMessageRecord] = []
        self._history_rebuild_remove_ids: tuple[str, ...] = ()
        self._history_rebuild_requires_reorder = False
        self._history_rebuild_reflow_bubbles: tuple[MessageBubble, ...] = ()
        self._history_rebuild_follow_tail = True
        self._deferred_reflow_timer = QTimer(self)
        self._deferred_reflow_timer.setSingleShot(True)
        self._deferred_reflow_timer.timeout.connect(self.refresh_layout)
        self._empty_state_scroll_timer = QTimer(self)
        self._empty_state_scroll_timer.setSingleShot(True)
        self._empty_state_scroll_timer.timeout.connect(self._apply_empty_state_scroll)
        self._tail_scroll_timer = QTimer(self)
        self._tail_scroll_timer.setSingleShot(True)
        self._tail_scroll_timer.timeout.connect(self._apply_pending_scroll_to_bottom)
        self._viewport_reflow_timer = QTimer(self)
        self._viewport_reflow_timer.setSingleShot(True)
        self._viewport_reflow_timer.timeout.connect(self._apply_queued_viewport_reflow)
        self._reader_anchor_timer = QTimer(self)
        self._reader_anchor_timer.setSingleShot(True)
        self._reader_anchor_timer.timeout.connect(self._restore_reader_anchor)
        self._history_rebuild_timer = QTimer(self)
        self._history_rebuild_timer.setSingleShot(True)
        self._history_rebuild_timer.timeout.connect(self._apply_history_rebuild_chunk)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(SCROLL_AREA_STYLE)
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(f"background-color: {Theme.BACKGROUND_DARK};")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(12, 12, 12, 12)
        self.content_layout.setSpacing(12)
        self.content_top_spacer = QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Expanding,
        )
        self.content_bottom_spacer = QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Expanding,
        )
        self.content_layout.addItem(self.content_top_spacer)
        for surface in (
            runtime_surface,
            empty_surface,
            confirmation_surface,
            activity_surface,
        ):
            self.content_layout.addWidget(surface)
            self.content_layout.setAlignment(
                surface,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            )
        self.content_layout.addItem(self.content_bottom_spacer)
        self.setWidget(self.content_widget)
        scroll_bar = self.verticalScrollBar()
        if scroll_bar is not None:
            scroll_bar.rangeChanged.connect(self._on_scroll_range_changed)
            scroll_bar.valueChanged.connect(self._on_scroll_value_changed)

    @property
    def following_tail(self) -> bool:
        """Whether transcript updates currently follow the newest content."""
        return self._follow_transcript_updates

    def _fit_surfaces(self) -> None:
        viewport = self.viewport()
        if viewport is not None and viewport.width() > 0:
            self.surface_fit_requested.emit(viewport.width())

    def replace_history(self, replacement: ChatHistoryReplacement) -> None:
        """Capture one snapshot and reconcile it in bounded Qt event-loop turns."""
        if not isinstance(replacement, ChatHistoryReplacement):
            raise TypeError("Chat history replacements must be typed.")
        snapshot = replacement.records
        preserve_reader = replacement.kind is ChatHistoryReplacementKind.PRUNE
        follow_tail = bool(
            not preserve_reader
            or self._follow_transcript_updates
            or self.is_near_bottom()
        )
        anchor = None if follow_tail else self._capture_reader_anchor()
        retained_ids = {message.message_id for message in snapshot}
        if anchor is not None and anchor[0] not in retained_ids:
            anchor = (snapshot[0].message_id, 0) if snapshot else None

        self._history_rebuild_timer.stop()
        self._reader_anchor_timer.stop()
        self._tail_scroll_timer.stop()
        self._deferred_reflow_timer.stop()
        self._viewport_reflow_timer.stop()
        self._viewport_reflow_pending = False
        self._history_rebuild_active = True
        self._history_rebuild_phase = "remove"
        self._history_rebuild_index = 0
        self._history_rebuild_delta_index = 0
        self._history_rebuild_snapshot = snapshot
        self._history_rebuild_order = {
            message.message_id: index for index, message in enumerate(snapshot)
        }
        self._history_rebuild_deltas.clear()
        current_ids = tuple(
            bubble.property("chatMessageId")
            for bubble in self.message_bubbles()
            if isinstance(bubble.property("chatMessageId"), str)
        )
        current_id_set = set(current_ids)
        self._history_rebuild_remove_ids = tuple(
            message_id for message_id in current_ids if message_id not in retained_ids
        )
        current_retained_order = tuple(
            message_id for message_id in current_ids if message_id in retained_ids
        )
        desired_existing_order = tuple(
            message.message_id
            for message in snapshot
            if message.message_id in current_id_set
        )
        self._history_rebuild_requires_reorder = (
            current_retained_order != desired_existing_order
        )
        self._history_rebuild_reflow_bubbles = ()
        self._history_rebuild_follow_tail = follow_tail
        self._follow_transcript_updates = follow_tail
        self._reader_anchor = anchor
        self._reader_anchor_restore_attempts = 0
        self._pending_scroll_to_bottom = False
        # The host may hide a card and change the scroll range. Capture the
        # reader and mark rebuilding first, then notify synchronously.
        self.history_replacement_started.emit(bool(snapshot))
        if not snapshot and not self._history_rebuild_remove_ids:
            self._history_rebuild_phase = "reflow"
            self._fit_surfaces()
            self._finish_history_rebuild()
            return
        self._history_rebuild_timer.start(0)

    def _apply_history_rebuild_chunk(self) -> None:
        """Apply one bounded remove, upsert, delta, or reflow slice."""
        if not self._history_rebuild_active:
            return

        if self._history_rebuild_phase == "remove":
            remove_ids = self._history_rebuild_remove_ids
            start = min(self._history_rebuild_index, len(remove_ids))
            end = min(start + HISTORY_REBUILD_CHUNK_SIZE, len(remove_ids))
            for message_id in remove_ids[start:end]:
                self._remove_history_bubble(message_id)
            self._history_rebuild_index = end
            self.content_widget.updateGeometry()
            if end < len(remove_ids):
                self._history_rebuild_timer.start(0)
                return
            self._history_rebuild_phase = "upsert"
            self._history_rebuild_index = 0
            self._history_rebuild_timer.start(0)
            return

        if self._history_rebuild_phase == "upsert":
            snapshot = self._history_rebuild_snapshot
            start = min(self._history_rebuild_index, len(snapshot))
            end = min(start + HISTORY_REBUILD_CHUNK_SIZE, len(snapshot))
            for message in snapshot[start:end]:
                bubble = self._message_bubbles_by_id.get(message.message_id)
                if bubble is None:
                    self._insert_message_record_widget(
                        message,
                        settle_layout=False,
                        history_order=self._history_rebuild_order,
                        update_reader_state=False,
                    )
                    continue
                if self._history_rebuild_requires_reorder:
                    self.content_layout.removeWidget(bubble)
                    self.content_layout.insertWidget(
                        self._message_layout_insert_index(
                            message.message_id,
                            self._history_rebuild_order,
                        ),
                        bubble,
                    )
                if bubble.get_text() != message.content:
                    bubble.set_text(message.content)
                if bubble.presentation_kind is not message.presentation_kind:
                    bubble.set_presentation_kind(message.presentation_kind)
            self._history_rebuild_index = end
            self.content_widget.updateGeometry()
            if end < len(snapshot):
                self._history_rebuild_timer.start(0)
                return
            self._history_rebuild_phase = "delta"
            self._history_rebuild_delta_index = 0
            self._history_rebuild_timer.start(0)
            return

        if self._history_rebuild_phase == "delta":
            start = min(
                self._history_rebuild_delta_index,
                len(self._history_rebuild_deltas),
            )
            end = min(
                start + HISTORY_REBUILD_CHUNK_SIZE,
                len(self._history_rebuild_deltas),
            )
            for record in self._history_rebuild_deltas[start:end]:
                if record.message_id not in self._message_bubbles_by_id:
                    self._insert_message_record_widget(
                        record,
                        settle_layout=False,
                        update_reader_state=False,
                    )
            self._history_rebuild_delta_index = end
            if end < len(self._history_rebuild_deltas):
                self._history_rebuild_timer.start(0)
                return
            self._history_rebuild_phase = "reflow"
            self._history_rebuild_index = 0
            self._place_transient_surfaces_after_messages()
            self._history_rebuild_reflow_bubbles = tuple(self.message_bubbles())
            self._fit_surfaces()
            self._history_rebuild_timer.start(0)
            return

        if self._history_rebuild_phase == "reflow":
            bubbles = self._history_rebuild_reflow_bubbles
            viewport = self.viewport()
            if viewport is None or viewport.width() <= 0:
                self._finish_history_rebuild()
                return
            start = min(self._history_rebuild_index, len(bubbles))
            end = min(start + HISTORY_REBUILD_CHUNK_SIZE, len(bubbles))
            for bubble in bubbles[start:end]:
                bubble.adjust_width(viewport.width())
            self._history_rebuild_index = end
            if end < len(bubbles):
                self._history_rebuild_timer.start(0)
                return
            if self._history_rebuild_delta_index < len(self._history_rebuild_deltas):
                self._history_rebuild_phase = "delta"
                self._history_rebuild_timer.start(0)
                return
            self._finish_history_rebuild()

    def _remove_history_bubble(self, message_id: str) -> None:
        """Remove one durable bubble without rebuilding the surrounding UI."""
        bubble = self._message_bubbles_by_id.pop(message_id, None)
        if bubble is None:
            return
        self.content_layout.removeWidget(bubble)
        with suppress(TypeError):
            bubble.layout_changed.disconnect(self._on_message_bubble_layout_changed)
        bubble.hide()
        bubble.setParent(None)
        bubble.deleteLater()

    def _finish_history_rebuild(self) -> None:
        """Publish the final action/scroll state after bounded reconciliation."""
        self._history_rebuild_active = False
        self._history_rebuild_phase = "idle"
        self._history_rebuild_index = 0
        self._history_rebuild_delta_index = 0
        self._history_rebuild_snapshot = ()
        self._history_rebuild_order.clear()
        self._history_rebuild_deltas.clear()
        self._history_rebuild_remove_ids = ()
        self._history_rebuild_requires_reorder = False
        self._history_rebuild_reflow_bubbles = ()
        self.content_changed.emit()
        self._complete_chat_reflow()
        if self._history_rebuild_follow_tail:
            self.follow_tail()
        elif self._reader_anchor is not None:
            self._pending_scroll_to_bottom = False
            self._reader_anchor_timer.start(0)

    def resizeEvent(self, event):  # noqa: N802
        """Re-adjust all bubble widths on window resize.

        Args:
            event: The ``QResizeEvent``.

        """
        scroll_bar = self.verticalScrollBar()
        was_at_bottom = self._follow_transcript_updates or self.is_near_bottom()
        self._reader_anchor = None if was_at_bottom else self._capture_reader_anchor()
        self._reader_anchor_restore_attempts = 0
        super().resizeEvent(event)
        self.refresh_layout()
        if was_at_bottom:
            self.follow_tail()
        elif scroll_bar is not None:
            self._pending_scroll_to_bottom = False
            self._reader_anchor_timer.start(0)

    def showEvent(self, event):  # noqa: N802
        """Reflow content that may have arrived while the dock was hidden."""
        super().showEvent(event)
        self.refresh_layout()
        self._schedule_reflow()

    def refresh_layout(
        self, *, deferred: bool = False, follow_tail: bool | None = None
    ) -> None:
        """Reconcile transient placement and fit the shared viewport geometry."""
        self._place_transient_surfaces_after_messages()
        self._sync_content_alignment()
        if deferred:
            if not self._history_rebuild_active:
                self._schedule_reflow()
            return
        viewport = self.viewport()
        if viewport is None or viewport.width() <= 0:
            return
        self._fit_surfaces()
        for bubble in self.message_bubbles():
            bubble.adjust_width(viewport.width())
        self._complete_chat_reflow()
        if follow_tail is not None:
            self._follow_transcript_updates = follow_tail
            if follow_tail:
                self.follow_tail()

    def _complete_chat_reflow(self) -> None:
        """Commit shared geometry after surfaces and bubbles have been fitted."""
        self._sync_content_alignment()
        self.content_layout.activate()
        self.content_widget.updateGeometry()
        QApplication.sendEvent(self, QEvent(QEvent.Type.LayoutRequest))
        if self._shows_empty_state_only():
            self._scroll_empty_state_to_top()

    def _place_transient_surfaces_after_messages(self) -> None:
        """Keep current transcript activity after the durable messages."""
        for surface in (
            self.runtime_state_widget,
            self.confirmation_card_widget,
            self.turn_activity_widget,
        ):
            self.content_layout.removeWidget(surface)
            self.content_layout.insertWidget(
                self._bottom_spacer_index(),
                surface,
            )
            self.content_layout.setAlignment(
                surface,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            )

    def _bottom_spacer_index(self) -> int:
        """Return the insertion point immediately before the bottom spacer."""
        for index in range(self.content_layout.count()):
            item = self.content_layout.itemAt(index)
            if item is not None and item.spacerItem() is self.content_bottom_spacer:
                return index
        return self.content_layout.count()

    def _sync_content_alignment(self) -> None:
        """Center owned empty/runtime states and top-align real transcripts."""
        homepage_visible = (
            not self.has_messages()
            and self.empty_state_widget.isVisible()
            and not self.runtime_state_widget.isVisible()
            and not self.confirmation_card_widget.isVisible()
            and not self.turn_activity_widget.isVisible()
        )
        centered_surface_visible = (
            not self.has_messages()
            and (
                self.runtime_state_widget.isVisible()
                or self.empty_state_widget.isVisible()
            )
            and not self.confirmation_card_widget.isVisible()
            and not self.turn_activity_widget.isVisible()
        )
        vertical_policy = (
            QSizePolicy.Policy.Expanding
            if centered_surface_visible
            else QSizePolicy.Policy.Minimum
        )
        self.content_top_spacer.changeSize(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            vertical_policy,
        )
        self.content_bottom_spacer.changeSize(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Expanding,
        )
        for index in range(self.content_layout.count()):
            self.content_layout.setStretch(index, 0)
        top_index = next(
            (
                index
                for index in range(self.content_layout.count())
                if (item := self.content_layout.itemAt(index)) is not None
                and item.spacerItem() is self.content_top_spacer
            ),
            -1,
        )
        bottom_index = self._bottom_spacer_index()
        if top_index >= 0:
            self.content_layout.setStretch(
                top_index,
                7 if homepage_visible else (1 if centered_surface_visible else 0),
            )
        if bottom_index < self.content_layout.count():
            self.content_layout.setStretch(
                bottom_index,
                4 if homepage_visible else 1,
            )
        self.content_layout.invalidate()

    def is_near_bottom(self, tolerance: int = 12) -> bool:
        """Return whether transcript updates should continue following the tail."""
        scroll_bar = self.verticalScrollBar()
        return bool(
            scroll_bar is None
            or scroll_bar.maximum() <= 0
            or scroll_bar.value() >= scroll_bar.maximum() - tolerance
        )

    def append_record(
        self,
        message: ChatMessageRecord,
    ) -> None:
        """Create one bubble directly from the typed persistence record."""
        if not isinstance(message, ChatMessageRecord):
            raise TypeError("ChatPanel messages require typed chat records.")
        if self._history_rebuild_active:
            self._history_rebuild_deltas.append(message)
            return
        self._insert_message_record_widget(message)

    def _insert_message_record_widget(
        self,
        record: ChatMessageRecord,
        *,
        settle_layout: bool = True,
        history_order: dict[str, int] | None = None,
        update_reader_state: bool = True,
    ) -> MessageBubble:
        """Insert one unique bubble, optionally deferring transcript-wide layout."""
        existing = self._message_bubbles_by_id.get(record.message_id)
        if existing is not None:
            return existing
        is_user = record.role is ChatMessageRole.USER
        had_transcript = self.has_messages()
        follow_tail = is_user or not had_transcript or self.is_near_bottom()
        if update_reader_state:
            self._follow_transcript_updates = follow_tail
        bubble = MessageBubble(
            record.content,
            is_user,
            presentation_kind=record.presentation_kind,
        )
        bubble.layout_changed.connect(self._on_message_bubble_layout_changed)
        bubble.setProperty("chatMessageId", record.message_id)
        self._message_bubbles_by_id[record.message_id] = bubble

        # M0.4: Initial width adjustment
        viewport = self.viewport()
        if viewport:
            bubble.adjust_width(viewport.width())

        # Insert before the shared transient surfaces.
        self.content_layout.insertWidget(
            self._message_layout_insert_index(record.message_id, history_order),
            bubble,
        )
        if not settle_layout:
            return bubble
        self.content_changed.emit()
        self.refresh_layout()
        self._sync_content_alignment()
        self._schedule_reflow()
        if follow_tail:
            self.follow_tail()
        else:
            self._pending_scroll_to_bottom = False
        return bubble

    def _message_layout_insert_index(
        self,
        message_id: str,
        history_order: dict[str, int] | None,
    ) -> int:
        """Place a rebuilt row before any already-rendered newer live row."""
        if history_order is None:
            return self._bottom_spacer_index()
        desired_order = history_order.get(message_id)
        if desired_order is None:
            return self._bottom_spacer_index()
        for layout_index in range(self.content_layout.count()):
            item = self.content_layout.itemAt(layout_index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, MessageBubble):
                continue
            existing_id = widget.property("chatMessageId")
            existing_order = history_order.get(existing_id)
            if existing_order is not None and existing_order > desired_order:
                return layout_index
        return self._bottom_spacer_index()

    def _on_message_bubble_layout_changed(self) -> None:
        """Settle streamed text geometry without stealing the reader's scroll."""
        self.content_widget.updateGeometry()
        if self._history_rebuild_active:
            return
        self._schedule_reflow()
        if self._follow_transcript_updates or self.is_near_bottom():
            self.follow_tail()
        else:
            self._pending_scroll_to_bottom = False

    def has_messages(self) -> bool:
        """Return transcript truth even while the assistant dock is hidden."""
        return bool(self._message_bubbles_by_id)

    def _shows_empty_state_only(self) -> bool:
        """Return whether the scroll area currently contains only onboarding UI."""
        return bool(
            self.empty_state_widget.isVisible()
            and not self.has_messages()
            and not self.confirmation_card_widget.isVisible()
            and not self.turn_activity_widget.isVisible()
        )

    def _scroll_empty_state_to_top(self) -> None:
        """Keep the onboarding title visible when its suggestions need scrolling."""
        self._pending_scroll_to_bottom = False
        # The empty state is not transcript history. Keep the next real turn
        # tail-following even though onboarding itself starts at the top.
        self._follow_transcript_updates = True

        self._apply_empty_state_scroll()
        self._empty_state_scroll_timer.start(0)

    def _apply_empty_state_scroll(self) -> None:
        """Apply top alignment while the onboarding surface remains current."""
        scroll_bar = self.verticalScrollBar()
        if scroll_bar is not None and self._shows_empty_state_only():
            scroll_bar.setValue(scroll_bar.minimum())

    def follow_tail(self):
        """Scroll the chat area to the bottom."""
        self._follow_transcript_updates = True
        self._pending_scroll_to_bottom = True
        self._apply_pending_scroll_to_bottom()
        self._tail_scroll_timer.start(0)

    def _on_scroll_range_changed(self, _minimum: int, _maximum: int) -> None:
        """Reflow after scrollbar visibility changes, then follow the tail."""
        if self._history_rebuild_active:
            return
        self._queue_viewport_reflow()
        if self._pending_scroll_to_bottom:
            self._apply_pending_scroll_to_bottom()

    def _queue_viewport_reflow(self) -> None:
        """Coalesce scrollbar-driven width changes into one settled reflow."""
        if self._viewport_reflow_pending:
            return
        self._viewport_reflow_pending = True
        self._viewport_reflow_timer.start(0)

    def _apply_queued_viewport_reflow(self) -> None:
        """Apply one scrollbar-driven reflow through an owned timer."""
        self._viewport_reflow_pending = False
        self.refresh_layout()
        if self._shows_empty_state_only():
            self._scroll_empty_state_to_top()
        elif self._follow_transcript_updates or self._pending_scroll_to_bottom:
            self.follow_tail()
        elif self._reader_anchor is not None:
            self._reader_anchor_timer.start(0)

    def _capture_reader_anchor(self) -> tuple[str, int] | None:
        """Remember the first visible durable message and its viewport offset."""
        viewport = self.viewport()
        if viewport is None:
            return None
        for bubble in self.message_bubbles():
            top = bubble.mapTo(viewport, QPoint(0, 0)).y()
            bottom = top + bubble.height()
            message_id = bubble.property("chatMessageId")
            if bottom > 0 and isinstance(message_id, str) and message_id:
                return message_id, top
        return None

    def _restore_reader_anchor(self) -> None:
        """Restore a non-tail reader after width-dependent bubble reflow settles."""
        anchor = self._reader_anchor
        if anchor is None:
            return
        if self._follow_transcript_updates:
            self._reader_anchor = None
            self._reader_anchor_restore_attempts = 0
            return
        message_id, expected_y = anchor
        viewport = self.viewport()
        scroll_bar = self.verticalScrollBar()
        if viewport is None or scroll_bar is None:
            return
        bubble = self._message_bubbles_by_id.get(message_id)
        if bubble is None:
            self._reader_anchor = None
            return
        self.content_layout.activate()
        current_y = bubble.mapTo(viewport, QPoint(0, 0)).y()
        delta = current_y - expected_y
        if delta:
            self._restoring_reader_anchor = True
            try:
                scroll_bar.setValue(scroll_bar.value() + delta)
            finally:
                self._restoring_reader_anchor = False
        self._reader_anchor_restore_attempts += 1
        if self._reader_anchor_restore_attempts < 3:
            self._reader_anchor_timer.start(8)
        else:
            self._reader_anchor = None

    def _schedule_reflow(self) -> None:
        """Coalesce deferred geometry work in a timer owned by this viewport."""
        self._deferred_reflow_timer.start(0)

    def _on_scroll_value_changed(self, _value: int) -> None:
        """Track explicit reading position without fighting internal follow."""
        if (
            self._history_rebuild_active
            or self._applying_tail_scroll
            or self._restoring_reader_anchor
            or self._reader_anchor is not None
        ):
            return
        near_bottom = self.is_near_bottom()
        if not near_bottom:
            self._pending_scroll_to_bottom = False
        self._follow_transcript_updates = near_bottom

    def _apply_pending_scroll_to_bottom(self) -> None:
        """Apply a pending bottom scroll once the scroll range is available."""
        if not self._pending_scroll_to_bottom:
            return
        self.content_widget.adjustSize()
        self.content_widget.updateGeometry()
        scroll_bar = self.verticalScrollBar()
        if not scroll_bar:
            return
        self._applying_tail_scroll = True
        try:
            scroll_bar.setValue(scroll_bar.maximum())
            latest_bubble = self.latest_message_bubble()
            if latest_bubble is not None:
                self.ensureWidgetVisible(latest_bubble, 0, 8)
                scroll_bar.setValue(scroll_bar.maximum())
        finally:
            self._applying_tail_scroll = False
        if scroll_bar.maximum() > 0 and scroll_bar.value() >= scroll_bar.maximum() - 2:
            self._pending_scroll_to_bottom = False
            self._follow_transcript_updates = True

    def latest_message_bubble(self) -> MessageBubble | None:
        for index in range(self.content_layout.count() - 1, -1, -1):
            item = self.content_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, MessageBubble) and widget.isVisible():
                return widget
        return None

    def message_bubbles(self) -> list[MessageBubble]:
        """Return transcript bubbles in their visible layout order."""
        bubbles: list[MessageBubble] = []
        for index in range(self.content_layout.count()):
            item = self.content_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, MessageBubble):
                bubbles.append(widget)
        return bubbles
