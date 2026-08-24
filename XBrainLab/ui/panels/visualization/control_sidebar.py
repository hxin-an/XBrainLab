"""Sidebar widget for the visualization panel with configuration controls."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import (
    ApplyMontageCommand,
    CommandName,
    QueryStateCommand,
    SaliencyCommand,
    SaliencyCrossFoldIdentity,
    SaliencyRunIdentity,
)
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ControllerCompatibilityUnavailableError,
    blocked_reason,
    execute_application_command,
    get_command_capability,
    get_command_review_context,
    has_real_application_context,
    is_stale_publication_result,
    run_controller_compatibility_call,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel, SidebarScrollArea
from XBrainLab.ui.components.modal_presentation import show_warning
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.dialogs.visualization import (
    PickMontageDialog,
    SaliencySettingDialog,
)
from XBrainLab.ui.interaction_outcome import InteractionOutcome
from XBrainLab.ui.montage_positions import normalize_montage_positions
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme


class ControlSidebar(QWidget):
    """Sidebar for Visualization Panel configuration."""

    def __init__(self, panel, parent=None):
        """Initialize the control sidebar.

        Args:
            panel: The parent ``VisualizationPanel``.
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.panel = panel
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.init_ui()

    @property
    def controller(self):
        """VisualizationController: The controller from the parent panel."""
        return self.panel.controller

    @property
    def main_window(self):
        """QMainWindow: The application main window reference."""
        return self.panel.main_window

    def _show_status(self, message: str) -> None:
        show_status_message(self.panel, message)

    def init_ui(self):
        """Build the sidebar layout with info, configuration, and operation groups."""
        self.setFixedWidth(260)
        self.setObjectName("RightPanel")
        self.setStyleSheet(Stylesheets.SIDEBAR_CONTAINER)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.scroll_area = SidebarScrollArea(self)
        root_layout.addWidget(self.scroll_area)
        layout = self.scroll_area.content_layout

        # 1. Data Summary
        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        layout.addWidget(self.info_panel)

        layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(Stylesheets.SEPARATOR_HORIZONTAL)
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(10)

        # Group 1: Configuration
        config_group = QGroupBox("CONFIGURATION")
        config_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        config_group.setMinimumHeight(Stylesheets.SIDEBAR_PRIMARY_GROUP_MIN_HEIGHT)
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(0, 10, 0, 0)
        config_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_montage = QPushButton("Set Montage")
        self.btn_montage.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_montage.clicked.connect(self.set_montage)
        config_layout.addWidget(self.btn_montage)

        self.btn_saliency = QPushButton("Saliency Settings")
        self.btn_saliency.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_saliency.clicked.connect(self.set_saliency)
        config_layout.addWidget(self.btn_saliency)

        self.btn_reset_view = QPushButton("Reset view")
        self.btn_reset_view.setObjectName("VisualizationResetView")
        self.btn_reset_view.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_reset_view.clicked.connect(self._reset_active_view)
        self.btn_reset_view.hide()
        config_layout.addWidget(self.btn_reset_view)

        self.three_d_controls_group = QGroupBox("3D PLOT")
        self.three_d_controls_group.setObjectName("Visualization3DControls")
        self.three_d_controls_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        three_d_layout = QVBoxLayout(self.three_d_controls_group)
        three_d_layout.setContentsMargins(0, 10, 0, 0)
        three_d_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_3d_electrodes = QPushButton("Electrodes")
        self.btn_3d_electrodes.setObjectName("Visualization3DElectrodesToggle")
        self.btn_3d_electrodes.setCheckable(True)
        self.btn_3d_electrodes.setChecked(True)
        self.btn_3d_electrodes.setStyleSheet(self._three_d_toggle_style())
        self.btn_3d_electrodes.toggled.connect(self._toggle_3d_electrodes)
        three_d_layout.addWidget(self.btn_3d_electrodes)

        self.btn_3d_head_surface = QPushButton("Head surface")
        self.btn_3d_head_surface.setObjectName("Visualization3DHeadSurfaceToggle")
        self.btn_3d_head_surface.setCheckable(True)
        self.btn_3d_head_surface.setChecked(True)
        self.btn_3d_head_surface.setStyleSheet(self._three_d_toggle_style())
        self.btn_3d_head_surface.toggled.connect(self._toggle_3d_head_surface)
        three_d_layout.addWidget(self.btn_3d_head_surface)

        self.three_d_controls_group.hide()

        layout.addWidget(config_group)
        layout.addSpacing(Stylesheets.SIDEBAR_GROUP_GAP)
        layout.addWidget(self.three_d_controls_group)
        layout.addSpacing(Stylesheets.SIDEBAR_GROUP_GAP)
        layout.addStretch()

    def update_info(self):
        """Refresh the aggregate info panel (delegated to InfoPanelService)."""
        if not self.info_panel:
            return

        # Handled by InfoPanelService

    @staticmethod
    def _three_d_toggle_style() -> str:
        """Return the selected-state styling for 3D scene toggles."""
        return (
            Stylesheets.SIDEBAR_BTN + "\nQPushButton:checked {"
            f" background-color: {Theme.TABLE_SELECTION};"
            f" color: {Theme.TEXT_PRIMARY};"
            f" border: 1px solid {Theme.ACCENT_PRIMARY};"
            "}"
        )

    def refresh_view_controls(self) -> None:
        """Show only the controls that apply to the currently visible view."""
        tabs = getattr(self.panel, "tabs", None)
        current_view = tabs.currentWidget() if tabs is not None else None
        three_d_view = getattr(self.panel, "tab_3d", None)
        is_three_d = current_view is three_d_view
        scene_ready = bool(getattr(three_d_view, "scene_ready", False))
        detail_active = bool(
            not is_three_d
            and getattr(self.panel, "saliency_combo", None) is not None
            and self.panel.saliency_combo.currentData() is not None
        )

        self.btn_reset_view.setVisible(detail_active or (is_three_d and scene_ready))
        self.three_d_controls_group.setVisible(is_three_d and scene_ready)
        if is_three_d and scene_ready:
            self._toggle_3d_electrodes(self.btn_3d_electrodes.isChecked())
            self._toggle_3d_head_surface(self.btn_3d_head_surface.isChecked())

    def _reset_active_view(self) -> None:
        """Reset the current detail canvas or the ready 3D camera."""
        current_view = self.panel.tabs.currentWidget()
        if current_view is getattr(self.panel, "tab_3d", None):
            reset_camera = getattr(current_view, "_reset_camera", None)
            if callable(reset_camera):
                reset_camera()
            return
        reset_view = getattr(current_view, "reset_view", None)
        if callable(reset_view):
            reset_view()

    def _toggle_3d_electrodes(self, checked: bool) -> None:
        three_d_view = getattr(self.panel, "tab_3d", None)
        toggle = getattr(three_d_view, "_toggle_electrodes", None)
        if callable(toggle):
            toggle(checked)

    def _toggle_3d_head_surface(self, checked: bool) -> None:
        toggle = getattr(getattr(self.panel, "tab_3d", None), "_toggle_head", None)
        if callable(toggle):
            toggle(checked)

    # --- Actions ---

    def set_montage(
        self,
        _checked: bool = False,
        *,
        default_montage: str | None = None,
        warning: str = "",
    ) -> InteractionOutcome:
        """Open the montage picker and return its observed product outcome."""
        review_context = get_command_review_context(
            self,
            CommandName.APPLY_MONTAGE,
        )
        if review_context is None and has_real_application_context(self):
            message = CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            show_warning(self, "Montage blocked", message)
            return InteractionOutcome.blocked(message)
        capability = (
            getattr(review_context, "capability", None)
            if review_context is not None
            else get_command_capability(self, CommandName.APPLY_MONTAGE)
        )
        if review_context is not None and capability is None:
            message = CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            show_warning(self, "Montage blocked", message)
            return InteractionOutcome.blocked(message)
        if capability is not None and not capability.enabled:
            message = blocked_reason(
                capability,
                "Create EEG epochs before applying a montage.",
            )
            show_warning(self, "Montage blocked", message)
            return InteractionOutcome.blocked(message)

        if capability is None:
            has_epoch_data = self._compatibility_has_epoch_data_for_montage()
            if has_epoch_data is None:
                self._show_compatibility_fallback_warning("Montage blocked")
                return InteractionOutcome.blocked(
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
                )
            if not has_epoch_data:
                message = "No EEG epochs are available."
                show_warning(self, "Warning", message)
                return InteractionOutcome.blocked(message)

        reviewed_generation = (
            review_context.publication_generation
            if review_context is not None
            else None
        )
        channel_query = execute_application_command(
            self,
            QueryStateCommand(query="state"),
            refresh=False,
            expected_publication_generation=reviewed_generation,
        )
        if channel_query is not None and channel_query.failed:
            title = (
                "Review Montage Again"
                if is_stale_publication_result(channel_query)
                else "Montage blocked"
                if channel_query.recoverable
                else "Montage failed"
            )
            show_warning(
                self,
                title,
                channel_query.message,
            )
            if channel_query.recoverable:
                return InteractionOutcome.blocked(channel_query.message)
            return InteractionOutcome.failed(channel_query.message)

        try:
            channels = self._montage_channel_names(channel_query)
        except ControllerCompatibilityUnavailableError:
            self._show_compatibility_fallback_warning("Montage blocked")
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
        if not channels:
            message = "No EEG epoch channel names are available for montage setup."
            show_warning(self, "Montage blocked", message)
            return InteractionOutcome.blocked(message)

        normalized_warning = " ".join(str(warning or "").split())
        if normalized_warning:
            self._show_status(normalized_warning)
        dialog_kwargs = {"default_montage": default_montage} if default_montage else {}
        dialog = PickMontageDialog(self, channels, **dialog_kwargs)
        if not dialog.exec():
            return InteractionOutcome.cancelled("Montage setup was cancelled.")

        selected_channels, positions = dialog.get_result()
        if selected_channels is None or positions is None:
            message = "No valid montage configuration was selected."
            show_warning(self, "Montage blocked", message)
            return InteractionOutcome.blocked(message)
        try:
            normalized_positions = normalize_montage_positions(
                selected_channels,
                positions,
            )
        except Exception:
            message = present_unexpected_error(
                self,
                UnexpectedErrorContext.MONTAGE_SETUP,
            )
            return InteractionOutcome.failed(message)

        result = execute_application_command(
            self,
            ApplyMontageCommand(
                channels=list(selected_channels),
                positions=normalized_positions,
            ),
            expected_publication_generation=reviewed_generation,
        )
        if result is None:
            self._show_compatibility_fallback_warning("Montage blocked")
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
        if result.failed:
            title = (
                "Review Montage Again"
                if is_stale_publication_result(result)
                else "Montage blocked"
                if result.recoverable
                else "Montage failed"
            )
            show_warning(
                self,
                title,
                result.message,
            )
            if result.recoverable:
                return InteractionOutcome.blocked(result.message)
            return InteractionOutcome.failed(result.message)

        self._show_status("Montage set")
        return InteractionOutcome.completed("Montage set.")

    def _montage_channel_names(self, query_result) -> list[str]:
        if query_result is None:
            return self._compatibility_montage_channel_names()
        diagnostics = getattr(query_result, "diagnostics", {}) or {}
        state = diagnostics.get("state")
        epoch = state.get("epoch") if isinstance(state, dict) else {}
        names = epoch.get("channel_names") if isinstance(epoch, dict) else None
        if not isinstance(names, list):
            return []
        return [str(name) for name in names]

    def _compatibility_has_epoch_data_for_montage(self) -> bool | None:
        """Return epoch availability only for mock / compatibility UI contexts."""
        try:
            return bool(
                run_controller_compatibility_call(
                    self,
                    self.controller.has_epoch_data,
                ),
            )
        except ControllerCompatibilityUnavailableError:
            return None

    def _compatibility_montage_channel_names(self) -> list[str]:
        """Return montage channel names only for mock / compatibility UI contexts."""
        return run_controller_compatibility_call(
            self,
            self.controller.get_channel_names,
        )

    def set_saliency(self) -> InteractionOutcome:
        """Stage saliency settings without starting computation."""
        review_context = get_command_review_context(
            self,
            CommandName.SALIENCY,
        )
        if review_context is None and has_real_application_context(self):
            message = CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            show_warning(self, "Saliency blocked", message)
            return InteractionOutcome.blocked(message)
        capability = (
            getattr(review_context, "capability", None)
            if review_context is not None
            else get_command_capability(self, CommandName.SALIENCY)
        )
        if review_context is not None and capability is None:
            message = CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            show_warning(self, "Saliency blocked", message)
            return InteractionOutcome.blocked(message)
        if capability is not None and not capability.enabled:
            message = blocked_reason(
                capability,
                "Saliency analysis is not ready yet.",
            )
            show_warning(
                self,
                "Saliency blocked",
                message,
            )
            return InteractionOutcome.blocked(message)

        reviewed_generation = (
            review_context.publication_generation
            if review_context is not None
            else None
        )
        query_result = execute_application_command(
            self,
            SaliencyCommand(),
            refresh=False,
            expected_publication_generation=reviewed_generation,
        )
        if query_result is not None and query_result.failed:
            title = (
                "Review Saliency Settings Again"
                if is_stale_publication_result(query_result)
                else "Saliency blocked"
                if query_result.recoverable
                else "Saliency failed"
            )
            show_warning(
                self,
                title,
                query_result.message,
            )
            if bool(getattr(query_result, "recoverable", False)):
                return InteractionOutcome.blocked(query_result.message)
            return InteractionOutcome.failed(query_result.message)
        configuration_block_reason = self._saliency_configuration_block_reason(
            query_result,
        )
        if configuration_block_reason is not None:
            show_warning(self, "Saliency blocked", configuration_block_reason)
            return InteractionOutcome.blocked(configuration_block_reason)
        try:
            dialog_params = self._saliency_dialog_params(query_result)
        except ControllerCompatibilityUnavailableError:
            self._show_compatibility_fallback_warning("Saliency blocked")
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )

        reviewed_target: (
            tuple[
                int,
                SaliencyRunIdentity | SaliencyCrossFoldIdentity,
                str,
            ]
            | None
        ) = None
        target_reader = getattr(self.panel, "saliency_settings_target", None)
        if reviewed_generation is not None:
            candidate_target = target_reader() if callable(target_reader) else None
            if (
                not isinstance(candidate_target, tuple)
                or len(candidate_target) != 3
                or candidate_target[0] != reviewed_generation
                or not isinstance(
                    candidate_target[1],
                    (SaliencyRunIdentity, SaliencyCrossFoldIdentity),
                )
                or not isinstance(candidate_target[2], str)
            ):
                message = (
                    "Visualization results or the selected run changed. "
                    "Refresh Visualization, then review Saliency Settings again."
                )
                show_warning(
                    self,
                    "Review Saliency Settings Again",
                    message,
                )
                return InteractionOutcome.blocked(message)
            reviewed_target = candidate_target

        win = SaliencySettingDialog(
            self,
            dialog_params,
        )
        if not win.exec():
            return InteractionOutcome.cancelled("Saliency settings were cancelled.")
        params = win.get_result()
        if not params:
            return InteractionOutcome.accepted(
                "The saliency dialog was accepted without an applicable change."
            )
        stage_params = getattr(self.panel, "stage_saliency_params", None)
        if not callable(stage_params):
            self._show_compatibility_fallback_warning("Saliency blocked")
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
        if reviewed_target is None:
            staged = stage_params(dict(params))
        else:
            target_generation, run_identity, model_name = reviewed_target
            staged = stage_params(
                dict(params),
                publication_generation=target_generation,
                run_identity=run_identity,
                model_name=model_name,
            )
        if staged is False:
            message = (
                "Visualization results or the selected run changed while settings "
                "were open. Review Saliency Settings again."
            )
            show_warning(
                self,
                "Review Saliency Settings Again",
                message,
            )
            return InteractionOutcome.blocked(message)
        self._show_status("Saliency settings ready")
        return InteractionOutcome.accepted(
            "Saliency settings are ready for an explicit compute action."
        )

    def _saliency_dialog_params(self, query_result) -> dict | None:
        if query_result is None:
            return self._compatibility_saliency_dialog_params()
        diagnostics = getattr(query_result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "saliency_summary":
            return None
        params = diagnostics.get("params")
        return params if isinstance(params, dict) else None

    @staticmethod
    def _saliency_configuration_block_reason(query_result) -> str | None:
        if query_result is None:
            return None
        diagnostics = getattr(query_result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "saliency_summary":
            return None
        if diagnostics.get("configure_available", True) is not False:
            return None
        reasons = diagnostics.get("configure_reasons")
        if isinstance(reasons, list):
            for reason in reasons:
                text = str(reason).strip()
                if text:
                    return text
        return "Select a model and training settings before configuring saliency."

    def _compatibility_saliency_dialog_params(self) -> dict | None:
        """Return saliency params only for mock / compatibility UI contexts."""
        return run_controller_compatibility_call(
            self,
            self.controller.get_saliency_params,
        )

    def _show_compatibility_fallback_warning(self, title: str) -> None:
        show_warning(self, title, CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE)
