"""Sidebar widget for the preprocessing panel with operations and execution controls."""

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import (
    CommandName,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    ResetPreprocessCommand,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    LEGACY_FALLBACK_UNAVAILABLE_MESSAGE,
    LegacyControllerFallbackUnavailableError,
    blocked_reason,
    execute_application_command,
    get_command_capability,
    run_legacy_controller_fallback,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.dialogs.preprocess import (
    EpochingDialog,
    FilteringDialog,
    NormalizeDialog,
    RereferenceDialog,
    ResampleDialog,
)
from XBrainLab.ui.refresh_coordinator import refresh_shared_status
from XBrainLab.ui.styles.stylesheets import Stylesheets


class PreprocessSidebar(QWidget):
    """Sidebar for ``PreprocessPanel`` with operation and execution controls.

    Hosts buttons for filtering, resampling, re-referencing, normalization,
    epoching, and reset.  Gate-checks lock state and data availability
    before delegating to the controller.

    Attributes:
        panel: The parent ``PreprocessPanel`` reference.
        info_panel: ``AggregateInfoPanel`` displaying summary statistics.
        btn_filter: Button to open the filtering dialog.
        btn_resample: Button to open the resample dialog.
        btn_rereference: Button to open the re-reference dialog.
        btn_normalize: Button to open the normalize dialog.
        btn_epoch: Button to open the epoching dialog.
        btn_reset: Button to reset all preprocessing.

    """

    def __init__(self, panel, parent=None):
        """Initialize the preprocessing sidebar.

        Args:
            panel: The parent ``PreprocessPanel``.
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.panel = panel
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.init_ui()

    @property
    def controller(self):
        """PreprocessController: The preprocessing controller from the parent panel."""
        return self.panel.controller

    @property
    def dataset_controller(self):
        """DatasetController: The dataset controller from the parent panel."""
        return self.panel.dataset_controller

    @property
    def main_window(self):
        """QMainWindow: The application main window reference."""
        return self.panel.main_window

    def init_ui(self):
        """Build the sidebar layout with info, operation, and execution groups."""
        self.setFixedWidth(260)
        self.setObjectName("RightPanel")
        self.setStyleSheet(Stylesheets.SIDEBAR_CONTAINER)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)

        # 1. Aggregate Info
        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        layout.addWidget(self.info_panel)

        # Separator
        layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(Stylesheets.SEPARATOR_HORIZONTAL)
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(10)

        # 2. Operations Group
        ops_group = QGroupBox("OPERATIONS")
        ops_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        ops_group.setMinimumHeight(Stylesheets.SIDEBAR_PRIMARY_GROUP_MIN_HEIGHT)
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setContentsMargins(0, 10, 0, 0)
        ops_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_filter = QPushButton("Filtering")
        self.btn_filter.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_filter.clicked.connect(self.open_filtering)

        self.btn_resample = QPushButton("Resample")
        self.btn_resample.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_resample.clicked.connect(self.open_resample)

        self.btn_rereference = QPushButton("Re-reference")
        self.btn_rereference.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_rereference.clicked.connect(self.open_rereference)

        self.btn_normalize = QPushButton("Normalize")
        self.btn_normalize.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_normalize.clicked.connect(self.open_normalize)

        ops_layout.addWidget(self.btn_filter)
        ops_layout.addWidget(self.btn_resample)
        ops_layout.addWidget(self.btn_rereference)
        ops_layout.addWidget(self.btn_normalize)

        layout.addWidget(ops_group)
        layout.addSpacing(Stylesheets.SIDEBAR_GROUP_GAP)

        # 3. Execution Group
        exec_group = QGroupBox("EXECUTION")
        exec_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)
        exec_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_epoch = QPushButton("Epoching")
        self.btn_epoch.setStyleSheet(Stylesheets.BTN_SUCCESS)
        self.btn_epoch.clicked.connect(self.open_epoching)
        exec_layout.addWidget(self.btn_epoch)

        self.btn_reset = QPushButton("Reset All Preprocessing")
        self.btn_reset.setStyleSheet(Stylesheets.BTN_DANGER)
        self.btn_reset.clicked.connect(self.reset_preprocess)
        exec_layout.addWidget(self.btn_reset)

        layout.addWidget(exec_group)

        layout.addStretch()

    # --- Update Logic ---

    def update_sidebar(self):
        """Update info panel and button states."""
        if not self.controller:
            return

        # 1. Update Info Panel
        # Handled by InfoPanelService

        is_epoched = False
        preprocess_capability = get_command_capability(self, CommandName.PREPROCESS)
        epoch_capability = get_command_capability(self, CommandName.CREATE_EPOCH)
        if preprocess_capability is None and epoch_capability is None:
            data_list = self._legacy_preprocessed_data_list_for_render()
            if data_list:
                first_data = data_list[0]
                is_epoched = not first_data.is_raw()

        self._update_button_states(is_epoched)

    def _legacy_preprocessed_data_list_for_render(self) -> list[Any]:
        """Return legacy render data only for mock / legacy UI contexts."""
        try:
            data_list = run_legacy_controller_fallback(
                self,
                self.controller.get_preprocessed_data_list,
            )
        except LegacyControllerFallbackUnavailableError:
            return []
        return list(data_list) if isinstance(data_list, list) else []

    def _preprocessed_data_list_for_epoching(
        self,
        epoch_capability,
    ) -> list[Any] | None:
        return self._preprocessed_data_list_for_dialog(
            epoch_capability,
            "Epoching Blocked",
        )

    def _preprocessed_data_list_for_dialog(
        self,
        command_capability,
        failure_title: str,
    ) -> list[Any] | None:
        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists", include_objects=True),
            refresh=False,
        )
        if result is None:
            if command_capability is None:
                return self._legacy_preprocessed_data_list_for_dialog(failure_title)
            return []
        if result.failed:
            self._show_command_failure(failure_title, result.message)
            return None
        data_list = result.diagnostics.get("preprocessed_data_list")
        return list(data_list) if isinstance(data_list, list) else []

    def _legacy_preprocessed_data_list_for_dialog(
        self,
        failure_title: str,
    ) -> list[Any] | None:
        """Return preprocessed data only for mock / legacy dialog contexts."""
        try:
            data_list = run_legacy_controller_fallback(
                self,
                self.controller.get_preprocessed_data_list,
            )
        except LegacyControllerFallbackUnavailableError:
            QMessageBox.warning(
                self,
                failure_title,
                LEGACY_FALLBACK_UNAVAILABLE_MESSAGE,
            )
            return None
        return list(data_list) if isinstance(data_list, list) else []

    def _update_button_states(self, is_epoched):
        """Update button tooltips based on the epoched state.

        Args:
            is_epoched: ``True`` if the data has been epoched and
                preprocessing is locked.

        """
        preprocess_capability = get_command_capability(self, CommandName.PREPROCESS)
        epoch_capability = get_command_capability(self, CommandName.CREATE_EPOCH)
        preprocess_enabled = (
            preprocess_capability.enabled if preprocess_capability is not None else True
        )
        epoch_enabled = (
            epoch_capability.enabled if epoch_capability is not None else True
        )
        preprocess_reason = blocked_reason(
            preprocess_capability,
            "Preprocessing is not available.",
        )
        epoch_reason = blocked_reason(
            epoch_capability,
            "Epoching is not available.",
        )
        if preprocess_capability is None and is_epoched:
            preprocess_reason = (
                "Preprocessing is locked (Data Epoched). Click to see details."
            )
        if epoch_capability is None and is_epoched:
            epoch_reason = (
                "Preprocessing is locked (Data Epoched). Click to see details."
            )

        for button in (
            self.btn_filter,
            self.btn_resample,
            self.btn_rereference,
            self.btn_normalize,
        ):
            button.setEnabled(preprocess_enabled)
        self.btn_epoch.setEnabled(epoch_enabled)

        # Filter
        if not preprocess_enabled or (preprocess_capability is None and is_epoched):
            self.btn_filter.setToolTip(preprocess_reason)
        else:
            self.btn_filter.setToolTip("Apply bandpass/notch filters")

        # Resample
        if not preprocess_enabled or (preprocess_capability is None and is_epoched):
            self.btn_resample.setToolTip(preprocess_reason)
        else:
            self.btn_resample.setToolTip("Change sampling rate")

        # Re-reference
        if not preprocess_enabled or (preprocess_capability is None and is_epoched):
            self.btn_rereference.setToolTip(preprocess_reason)
        else:
            self.btn_rereference.setToolTip("Change reference")

        # Normalize
        if not preprocess_enabled or (preprocess_capability is None and is_epoched):
            self.btn_normalize.setToolTip(preprocess_reason)
        else:
            self.btn_normalize.setToolTip("Apply Z-Score or Min-Max normalization")

        # Epoch Button
        if not epoch_enabled or (epoch_capability is None and is_epoched):
            self.btn_epoch.setText("Epoched (Locked)" if is_epoched else "Epoching")
            self.btn_epoch.setToolTip(epoch_reason)
        else:
            self.btn_epoch.setText("Epoching")
            self.btn_epoch.setToolTip("Segment data into epochs")

    # --- Action Logic ---

    def check_lock(self):
        """Check if preprocessing is locked due to epoched data.

        Shows a warning dialog if locked.

        Returns:
            bool: ``True`` if the action is blocked, ``False`` otherwise.

        """
        if not self.controller:
            return False
        preprocess_capability = get_command_capability(self, CommandName.PREPROCESS)
        if preprocess_capability is not None and not preprocess_capability.enabled:
            QMessageBox.warning(
                self,
                "Action Blocked",
                blocked_reason(
                    preprocess_capability,
                    "Preprocessing is not available.",
                ),
            )
            return True
        if preprocess_capability is None:
            fallback_ok, is_epoched = self._run_legacy_preprocess_fallback(
                "Action Blocked",
                self.controller.is_epoched,
            )
            if not fallback_ok:
                return True
            if is_epoched:
                QMessageBox.warning(
                    self,
                    "Action Blocked",
                    "Preprocessing is locked because data has been Epoched.\n"
                    "Please 'Reset All Preprocessing' to make changes.",
                )
                return True
        return False

    def check_data_loaded(self):
        """Verify that data is loaded before proceeding.

        Shows a warning dialog if no data is available.

        Returns:
            bool: ``True`` if data is loaded, ``False`` otherwise.

        """
        preprocess_capability = get_command_capability(self, CommandName.PREPROCESS)
        if preprocess_capability is not None and not preprocess_capability.enabled:
            QMessageBox.warning(
                self,
                "Warning",
                blocked_reason(
                    preprocess_capability,
                    "No data loaded. Please import data first.",
                ),
            )
            return False
        if preprocess_capability is None:
            if not self.controller:
                QMessageBox.warning(
                    self,
                    "Warning",
                    "No data loaded. Please import data first.",
                )
                return False
            fallback_ok, has_data = self._run_legacy_preprocess_fallback(
                "Warning",
                self.controller.has_data,
            )
            if not fallback_ok:
                return False
            if not has_data:
                QMessageBox.warning(
                    self,
                    "Warning",
                    "No data loaded. Please import data first.",
                )
                return False
        return True

    def notify_update(self):
        """Notify parent panel to update itself (plots etc)."""
        if self.panel and hasattr(self.panel, "update_panel"):
            self.panel.update_panel()

    def _notify_update_after_legacy_result(self, result) -> None:
        if result is None:
            self.notify_update()

    def _refresh_shared_status_after_legacy_result(self, result) -> None:
        if result is None:
            refresh_shared_status(self)

    def _show_command_failure(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _show_epoch_success(self, result) -> None:
        if result is None:
            QMessageBox.information(
                self,
                "Success",
                "Epoching applied.\nPreprocessing is now LOCKED.",
            )
            return

        message = "Epoching applied. Preprocessing is now locked."
        status_bar_factory = getattr(self.main_window, "statusBar", None)
        if callable(status_bar_factory):
            status_bar = status_bar_factory()
            show_message = getattr(status_bar, "showMessage", None)
            if callable(show_message):
                show_message(message, 5000)
                return

        logger.info(message)

    def _run_legacy_preprocess_fallback(
        self,
        blocked_title: str,
        fallback: Callable[[], Any],
    ) -> tuple[bool, Any]:
        try:
            return True, run_legacy_controller_fallback(self, fallback)
        except LegacyControllerFallbackUnavailableError as exc:
            QMessageBox.warning(self, blocked_title, str(exc))
            return False, None

    def open_filtering(self):
        """Open the filtering dialog and apply bandpass/notch filters."""
        if self.check_lock() or not self.check_data_loaded():
            return

        dialog = FilteringDialog(self)
        if dialog.exec():
            params = dialog.get_params()
            if params:
                l_freq, h_freq, notch_freqs = params
                try:
                    result = None
                    if l_freq is not None and h_freq is not None:
                        result = execute_application_command(
                            self,
                            PreprocessCommand(
                                operation=PreprocessOperation.BANDPASS,
                                low_freq=l_freq,
                                high_freq=h_freq,
                                notch_freq=notch_freqs,
                            ),
                        )
                    elif notch_freqs is not None:
                        result = execute_application_command(
                            self,
                            PreprocessCommand(
                                operation=PreprocessOperation.NOTCH,
                                notch_freq=notch_freqs,
                            ),
                        )
                    if result is None:
                        fallback_ok, _ = self._run_legacy_preprocess_fallback(
                            "Filtering Blocked",
                            lambda: self.controller.apply_filter(
                                l_freq,
                                h_freq,
                                notch_freqs,
                            ),
                        )
                        if not fallback_ok:
                            return
                    elif result.failed:
                        self._show_command_failure("Error", result.message)
                        return
                    self._notify_update_after_legacy_result(result)
                    QMessageBox.information(self, "Success", "Filtering applied.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Filtering failed: {e}")

    def open_resample(self):
        """Open the resample dialog and change the sampling rate."""
        if self.check_lock() or not self.check_data_loaded():
            return

        dialog = ResampleDialog(self)
        if dialog.exec():
            sfreq = dialog.get_params()
            if sfreq:
                rate = int(sfreq)
                try:
                    result = execute_application_command(
                        self,
                        PreprocessCommand(
                            operation=PreprocessOperation.RESAMPLE,
                            rate=rate,
                        ),
                    )
                    if result is None:
                        fallback_ok, _ = self._run_legacy_preprocess_fallback(
                            "Resampling Blocked",
                            lambda: self.controller.apply_resample(rate),
                        )
                        if not fallback_ok:
                            return
                    elif result.failed:
                        self._show_command_failure("Error", result.message)
                        return
                    self._notify_update_after_legacy_result(result)
                    QMessageBox.information(self, "Success", "Resampling applied.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Resample failed: {e}")

    def open_rereference(self):
        """Open the re-reference dialog and apply the new reference."""
        if self.check_lock() or not self.check_data_loaded():
            return

        preprocess_capability = get_command_capability(self, CommandName.PREPROCESS)
        data_list = self._preprocessed_data_list_for_dialog(
            preprocess_capability,
            "Re-reference Blocked",
        )
        if data_list is None:
            return
        dialog = RereferenceDialog(self, data_list)
        if dialog.exec():
            ref_channels = dialog.get_params()
            if ref_channels:
                try:
                    result = execute_application_command(
                        self,
                        PreprocessCommand(
                            operation=PreprocessOperation.REREFERENCE,
                            method=ref_channels
                            if isinstance(ref_channels, str)
                            else None,
                            channels=ref_channels
                            if isinstance(ref_channels, list)
                            else None,
                        ),
                    )
                    if result is None:
                        fallback_ok, _ = self._run_legacy_preprocess_fallback(
                            "Re-reference Blocked",
                            lambda: self.controller.apply_rereference(ref_channels),
                        )
                        if not fallback_ok:
                            return
                    elif result.failed:
                        self._show_command_failure("Error", result.message)
                        return
                    self._notify_update_after_legacy_result(result)
                    QMessageBox.information(self, "Success", "Re-reference applied.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Re-reference failed: {e}")

    def open_normalize(self):
        """Open the normalization dialog and apply the selected method."""
        if self.check_lock() or not self.check_data_loaded():
            return

        dialog = NormalizeDialog(self)
        if dialog.exec():
            method = dialog.get_params()
            if method:
                try:
                    result = execute_application_command(
                        self,
                        PreprocessCommand(
                            operation=PreprocessOperation.NORMALIZE,
                            method=method,
                        ),
                    )
                    if result is None:
                        fallback_ok, _ = self._run_legacy_preprocess_fallback(
                            "Normalization Blocked",
                            lambda: self.controller.apply_normalization(method),
                        )
                        if not fallback_ok:
                            return
                    elif result.failed:
                        self._show_command_failure("Error", result.message)
                        return
                    self._notify_update_after_legacy_result(result)
                    QMessageBox.information(self, "Success", "Normalization applied.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Normalization failed: {e}")

    def open_epoching(self):
        """Open the epoching dialog and segment the continuous data into epochs."""
        epoch_capability = get_command_capability(self, CommandName.CREATE_EPOCH)
        if epoch_capability is not None and not epoch_capability.enabled:
            QMessageBox.warning(
                self,
                "Epoching Blocked",
                blocked_reason(epoch_capability, "Epoching is not available."),
            )
            return

        if epoch_capability is None and (
            self.check_lock() or not self.check_data_loaded()
        ):
            return

        data_list = self._preprocessed_data_list_for_epoching(epoch_capability)
        if data_list is None:
            return
        dialog = EpochingDialog(self, data_list)
        if dialog.exec():
            params = dialog.get_params()
            if params:
                baseline, selected_events, tmin, tmax = params
                try:
                    result = execute_application_command(
                        self,
                        CreateEpochCommand(
                            t_min=tmin,
                            t_max=tmax,
                            baseline=baseline,
                            event_ids=selected_events,
                        ),
                    )
                    applied = True
                    if result is None:
                        fallback_ok, legacy_applied = (
                            self._run_legacy_preprocess_fallback(
                                "Epoching Blocked",
                                lambda: self.controller.apply_epoching(
                                    baseline,
                                    selected_events,
                                    tmin,
                                    tmax,
                                ),
                            )
                        )
                        if not fallback_ok:
                            return
                        applied = bool(legacy_applied)
                    elif result.failed:
                        self._show_command_failure("Error", result.message)
                        return
                    if applied:
                        self._notify_update_after_legacy_result(result)
                        self._refresh_shared_status_after_legacy_result(result)
                        self._show_epoch_success(result)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Epoching failed: {e}")

    def reset_preprocess(self):
        """Prompt the user and reset all preprocessing steps to the original data."""
        reset_capability = get_command_capability(self, CommandName.RESET_PREPROCESS)
        if reset_capability is not None and not reset_capability.enabled:
            QMessageBox.warning(
                self,
                "Reset Blocked",
                blocked_reason(
                    reset_capability,
                    "Load raw data before resetting preprocessing.",
                ),
            )
            return

        if reset_capability is None and not self.check_data_loaded():
            return

        needs_confirmation = reset_capability is None or (
            reset_capability.confirmation_required
            or reset_capability.requires_confirmation
        )
        if needs_confirmation:
            reply = QMessageBox.question(
                self,
                "Confirm Reset",
                "Are you sure you want to reset all preprocessing steps?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            result = execute_application_command(
                self,
                ResetPreprocessCommand(confirmed=True),
            )
            if result is None:
                applied, _ = self._run_legacy_preprocess_fallback(
                    "Reset Blocked",
                    self.controller.reset_preprocess,
                )
                if not applied:
                    return
            elif result.failed:
                self._show_command_failure("Error", result.message)
                return
            self._notify_update_after_legacy_result(result)
            self._refresh_shared_status_after_legacy_result(result)
            QMessageBox.information(self, "Success", "Preprocessing reset.")
        except Exception as e:
            logger.error("Reset failed: %s", e)
            QMessageBox.critical(self, "Error", f"Reset failed: {e}")
