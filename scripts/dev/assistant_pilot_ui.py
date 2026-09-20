"""Case-scoped research observation/driver for the normal Qt Assistant host.

Attach inside the controller factory BEFORE returning it to the runtime: the
host's same-thread dialog slot can enter a nested modal loop before later slots.
No oracle is accepted. A ready dialog is cancelled, never filled or submitted.
"""

from __future__ import annotations

import copy
import math
from contextlib import suppress
from functools import partial
from pathlib import Path
from time import perf_counter_ns

from PyQt6.QtCore import (
    QBuffer,
    QIODevice,
    QObject,
    QPoint,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest
from XBrainLab.llm.agent.response_presentation import AssistantPanelNavigationRequest
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffSurfaceKind,
    workflow_ui_handoff_route_for,
)
from XBrainLab.ui.chat.action_card import AssistantConfirmationCard
from XBrainLab.ui.components.modal_presentation import ModalAlertDialog
from XBrainLab.ui.panel_navigation import (
    PANEL_DATASET,
    PANEL_EVALUATION,
    PANEL_PREPROCESS,
    PANEL_TRAINING,
    PANEL_VISUALIZATION,
    VISUALIZATION_TAB_3D_PLOT,
    VISUALIZATION_TAB_SALIENCY_MAP,
    VISUALIZATION_TAB_SPECTROGRAM,
    VISUALIZATION_TAB_TOPOGRAPHIC_MAP,
)

# Concrete classes opened by WorkflowUiHandoffHost, not titles or model answers.
_DIALOGS = {
    "data_import_dialog": (
        "dataset.eeg_source_chooser_dialog",
        "EegSourceChooserDialog",
    ),
    "data_import_review_dialog": (
        "dataset.data_interpretation_preview_dialog",
        "DataInterpretationPreviewDialog",
    ),
    "channel_selection_dialog": (
        "dataset.channel_selection_dialog",
        "ChannelSelectionDialog",
    ),
    "epoch_settings_dialog": ("preprocess.epoching_dialog", "EpochingDialog"),
    "dataset_split_dialog": ("dataset.data_splitting_dialog", "DataSplittingDialog"),
    "montage_settings_dialog": (
        "visualization.montage_picker_dialog",
        "PickMontageDialog",
    ),
}
_PANELS = {
    "dataset": PANEL_DATASET,
    "preprocess": PANEL_PREPROCESS,
    "training": PANEL_TRAINING,
    "evaluation": PANEL_EVALUATION,
    "visualization": PANEL_VISUALIZATION,
}
_VIEWS = {
    "saliency_map": VISUALIZATION_TAB_SALIENCY_MAP,
    "spectrogram": VISUALIZATION_TAB_SPECTROGRAM,
    "topographic_map": VISUALIZATION_TAB_TOPOGRAPHIC_MAP,
    "3d_plot": VISUALIZATION_TAB_3D_PLOT,
}


def _known_product_notice(dialog: QDialog, item: dict) -> bool:
    """Recognize only the product-owned acknowledgement tied to 3D routing."""
    payload = item.get("payload")
    return bool(
        item.get("kind") == "navigation"
        and isinstance(payload, AssistantPanelNavigationRequest)
        and payload.target.value == "visualization"
        and payload.view_mode == "3d_plot"
        and type(dialog) is ModalAlertDialog
        and not dialog.is_confirmation
        and dialog.windowTitle() == "VRAM Warning"
    )


def _reachable(widget: QWidget) -> bool:
    if not widget.isVisible() or not widget.isEnabled():
        return False
    # visibleRegion excludes opaque children, so a fully occupied plot/container
    # can legitimately have no own paint region. Check ancestor viewport clipping.
    visible = QRect(widget.mapToGlobal(QPoint()), widget.size())
    current = widget
    while not current.isWindow() and current.parentWidget() is not None:
        current = current.parentWidget()
        visible = visible.intersected(
            QRect(current.mapToGlobal(QPoint()), current.size())
        )
    screen = widget.screen()
    return bool(
        screen is not None and not visible.intersected(screen.geometry()).isEmpty()
    )


class PilotUiDriver(QObject):
    """Observe actual surfaces; UI actions are separate from model decisions.

    The caller guarantees an isolated synthetic Study, sets allow_confirmation
    explicitly, attaches before host wiring, and closes this object per case.
    Screenshots are Qt widget captures, not a claim of native desktop acceptance.
    """

    _queued = pyqtSignal(object)

    def __init__(
        self,
        window,
        manager,
        output_dir: Path,
        *,
        allow_confirmation: bool = False,
        readiness_timeout_seconds: float = 15.0,
    ):
        super().__init__(window)
        if manager.main_window is not window:
            raise ValueError("Driver requires the matching real host")
        if (
            type(allow_confirmation) is not bool
            or type(readiness_timeout_seconds) not in {int, float}
            or not math.isfinite(readiness_timeout_seconds)
            or not 0 < readiness_timeout_seconds <= 120
        ):
            raise ValueError("Invalid UI observation budget/authorization")
        self.window, self.manager = window, manager
        self.output_dir = Path(output_dir).absolute()
        self.output_dir.mkdir()
        self._allow_confirmation = allow_confirmation
        self._timeout_ns = int(readiness_timeout_seconds * 1e9)
        self._events: list[dict] = []
        self._issues: list[str] = []
        self._pending: list[dict] = []
        self._connections: list[tuple] = []
        self._closed = False
        self._queued.connect(self._receive, Qt.ConnectionType.QueuedConnection)
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._poll_safely)

    def attach(self, controller) -> None:
        """Call in controller_factory before normal AgentManager wiring."""
        if self._connections or self._closed:
            raise ValueError("UI driver already used")
        for signal_name, kind in (
            ("workflow_ui_handoff_requested", "handoff"),
            ("confirmation_requested", "confirmation"),
            ("panel_navigation_requested", "navigation"),
        ):
            signal = getattr(controller, signal_name)
            callback = partial(self._capture, kind)
            signal.connect(callback, Qt.ConnectionType.DirectConnection)
            self._connections.append((signal, callback))
        self._timer.start()

    def _capture(self, kind: str, payload) -> None:
        # No QWidget access here; safe even if a future controller emits off-thread.
        self._queued.emit((kind, payload, perf_counter_ns()))

    def _receive(self, captured) -> None:
        if self._closed:
            return
        kind, payload, observed_ns = captured
        expected = {
            "handoff": WorkflowUiHandoffRequest,
            "confirmation": AgentConfirmationRequest,
            "navigation": AssistantPanelNavigationRequest,
        }[kind]
        if not isinstance(payload, expected):
            self._issue("untyped_ui_request")
            return
        if len(self._pending) >= 16 or len(self._events) >= 256:
            self._issue("ui_observation_limit")
            return
        item = {"kind": kind, "payload": payload, "observed_ns": observed_ns}
        self._pending.append(item)
        self._record("request_observed", item, signal_observed_ns=observed_ns)
        self._poll_safely()

    def _identity(self, item) -> dict:
        payload = item["payload"]
        if item["kind"] == "navigation":
            return {
                "route": "panel_navigation",
                "request_id": None,
                "target": payload.target.value,
                "view_mode": payload.view_mode,
                "correlation": None
                if payload.correlation is None
                else {
                    "turn_id": payload.correlation.turn_id,
                    "generation": payload.correlation.generation,
                },
            }
        route = (
            workflow_ui_handoff_route_for(payload.command)
            if item["kind"] == "handoff"
            else None
        )
        return {
            "request_id": payload.request_id,
            "command": payload.command_name,
            "route": route.route_identity.value if route else "confirmation_card",
        }

    def _record(self, kind: str, item: dict | None = None, **details) -> None:
        if len(self._events) >= 256:
            self._issue("ui_observation_limit")
            return
        self._events.append(
            {
                "kind": kind,
                "monotonic_ns": perf_counter_ns(),
                **(self._identity(item) if item else {}),
                **details,
            }
        )

    def _issue(self, issue: str) -> None:
        if issue not in self._issues and len(self._issues) < 32:
            self._issues.append(issue)

    def _screenshot(self, widget: QWidget) -> str:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not widget.grab().save(buffer, "PNG"):
            raise RuntimeError("Widget capture failed")
        path = self.output_dir / f"surface-{len(self._events):03d}.png"
        with path.open("xb") as output:
            output.write(bytes(buffer.data()))
        return str(path)

    def _poll_safely(self) -> None:
        if self._closed:
            return
        try:
            self._poll()
        except Exception as exc:
            self._issue("ui_observer_error")
            self._record("observer_error", exception_type=type(exc).__name__)
            self._pending.clear()
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, QDialog) and self._owns(dialog):
                dialog.reject()

    def _owns(self, widget: QWidget) -> bool:
        # QWidget.isAncestorOf deliberately stops at child-window boundaries.
        # QObject ownership still correlates this modal with this exact host.
        current = widget
        while current is not None:
            if current is self.window:
                return True
            current = current.parent()
        return False

    def _poll(self) -> None:
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QDialog) and self._owns(dialog) and _reachable(dialog):
            notice_item = next(
                (
                    entry
                    for entry in self._pending
                    if _known_product_notice(dialog, entry)
                ),
                None,
            )
            if notice_item is not None:
                self._record(
                    "product_notice",
                    notice_item,
                    widget_class=type(dialog).__name__,
                    ready_observed_ns=perf_counter_ns(),
                    screenshot=self._screenshot(dialog),
                )
                self._record(
                    "driver_action",
                    notice_item,
                    action="dismiss_product_notice",
                )
                dialog.reject()
                return
            item = next(
                (entry for entry in self._pending if entry["kind"] == "handoff"), None
            )
            active = self.manager._workflow_ui_handoff_host.active_request
            matched = False
            if item is not None and active == item["payload"]:
                request = item["payload"]
                route = workflow_ui_handoff_route_for(request.command)
                expected = _DIALOGS.get(route.route_identity.value) if route else None
                if route and route.route_identity.value == "training_settings_dialog":
                    model = (
                        "model" in request.decision_fields
                        or "model" in request.suggestions
                    )
                    expected = (
                        ("training.model_selection_dialog", "ModelSelectionDialog")
                        if model
                        else (
                            "training.training_setting_dialog",
                            "TrainingSettingDialog",
                        )
                    )
                matched = bool(
                    expected
                    and type(dialog).__module__ == f"XBrainLab.ui.dialogs.{expected[0]}"
                    and type(dialog).__name__ == expected[1]
                )
            kind = "dialog_ready" if matched else "unexpected_dialog"
            self._record(
                kind,
                item,
                widget_class=type(dialog).__name__,
                ready_observed_ns=perf_counter_ns(),
                screenshot=self._screenshot(dialog),
            )
            if not matched:
                self._issue("unexpected_dialog")
            if item is not None:
                self._pending.remove(item)
            self._record("driver_action", item, action="reject_dialog")
            dialog.reject()
            return
        for item in tuple(self._pending):
            if perf_counter_ns() - item["observed_ns"] >= self._timeout_ns:
                self._issue("readiness_timeout")
                self._record(
                    "readiness_timeout", item, screenshot=self._screenshot(self.window)
                )
                self._pending.remove(item)
                continue
            payload = item["payload"]
            if item["kind"] == "confirmation":
                cards = [
                    card
                    for card in self.window.findChildren(AssistantConfirmationCard)
                    if card.request_id == payload.request_id
                    and card.command_name == payload.command_name
                    and _reachable(card.primary_button)
                ]
                if len(cards) != 1:
                    continue
                card = cards[0]
                self._record(
                    "confirmation_ready",
                    item,
                    ready_observed_ns=perf_counter_ns(),
                    screenshot=self._screenshot(card),
                )
                self._pending.remove(item)
                if self._allow_confirmation:
                    self._record(
                        "driver_action", item, action="click_confirmation_primary"
                    )
                    card.primary_button.click()
                else:
                    self._issue("confirmation_not_authorized")
            elif item["kind"] == "navigation":
                self._observe_panel(item, payload.target.value, payload.view_mode)
            else:
                route = workflow_ui_handoff_route_for(payload.command)
                if route is None:
                    self._issue("unsupported_ui_route")
                    self._pending.remove(item)
                elif route.surface_kind is not WorkflowUiHandoffSurfaceKind.DIALOG:
                    self._observe_panel(item, route.target_panel.value, None)

    def _observe_panel(self, item: dict, target: str, view_mode: str | None) -> None:
        index = _PANELS.get(target)
        if index is None or self.window.stack.currentIndex() != index:
            return
        panel = self.window.stack.currentWidget()
        if not _reachable(panel):
            return
        publication = self.manager.application_service.get_view_publication()
        if (
            not publication.usable
            or not self.window._panel_rendered_application_revision(
                index, publication.revision
            )
        ):
            return
        details = {
            "projection_ready": True,
            "render_ready": None,
            "publication_generation": publication.generation,
            "publication_revision": publication.revision,
        }
        if target == "visualization":
            tabs = getattr(panel, "tabs", None)
            if tabs is None or (
                view_mode and tabs.currentIndex() != _VIEWS.get(view_mode)
            ):
                return
            view = tabs.currentWidget()
            if not _reachable(view):
                return
            status = view.property("renderStatus")
            if status in {"failed", "cancelled"}:
                self._issue("visualization_render_failed")
                self._record(
                    "render_failed",
                    item,
                    render_status=status,
                    screenshot=self._screenshot(panel),
                )
                self._pending.remove(item)
                return
            if (
                status != "completed"
                or view.property("publicationGeneration") != publication.generation
            ):
                return
            details.update(
                render_ready=True,
                render_status=status,
                operation_id=view.property("operationId"),
                run_id=view.property("runId"),
                tab_index=tabs.currentIndex(),
            )
        self._record(
            "panel_ready",
            item,
            **details,
            ready_observed_ns=perf_counter_ns(),
            screenshot=self._screenshot(panel),
        )
        self._pending.remove(item)

    def snapshot(self) -> dict:
        return {
            "schema": "xbrainlab.assistant_pilot_ui.v1",
            "events": copy.deepcopy(self._events),
            "issues": list(self._issues),
            "pending_count": len(self._pending),
            "screenshot_kind": "qt_widget_capture",
        }

    def close(self) -> None:
        self._closed = True
        self._timer.stop()
        for signal, callback in self._connections:
            with suppress(TypeError, RuntimeError):
                signal.disconnect(callback)
        self._connections.clear()
