"""Sidebar widget for the preprocessing panel with operations and execution controls."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.dialogs.preprocess import (
    EpochingDialog,
    FilteringDialog,
    NormalizeDialog,
    RereferenceDialog,
    ResampleDialog,
)
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
        layout.addWidget(self.info_panel, stretch=1)

        # Separator
        layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(Stylesheets.SEPARATOR_HORIZONTAL)
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(10)
        layout.addSpacing(10)

        # 2. Operations Group
        ops_group = QGroupBox("OPERATIONS")
        ops_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setContentsMargins(0, 10, 0, 0)

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

        # 3. Execution Group
        exec_group = QGroupBox("EXECUTION")
        exec_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)

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

        # 2. Update Button States & Lock Status
        data_list = self.controller.get_preprocessed_data_list()
        is_epoched = False

        if data_list:
            first_data = data_list[0]
            is_epoched = not first_data.is_raw()

        self._update_button_states(is_epoched)

    def _update_button_states(self, is_epoched):
        """Update button tooltips based on the epoched state.

        Args:
            is_epoched: ``True`` if the data has been epoched and
                preprocessing is locked.
        """
        # Filter
        if is_epoched:
            self.btn_filter.setToolTip(
                "Preprocessing is locked (Data Epoched). Click to see details."
            )
        else:
            self.btn_filter.setToolTip("Apply bandpass/notch filters")

        # Resample
        if is_epoched:
            self.btn_resample.setToolTip(
                "Preprocessing is locked (Data Epoched). Click to see details."
            )
        else:
            self.btn_resample.setToolTip("Change sampling rate")

        # Re-reference
        if is_epoched:
            self.btn_rereference.setToolTip(
                "Preprocessing is locked (Data Epoched). Click to see details."
            )
        else:
            self.btn_rereference.setToolTip("Change reference")

        # Normalize
        if is_epoched:
            self.btn_normalize.setToolTip(
                "Preprocessing is locked (Data Epoched). Click to see details."
            )
        else:
            self.btn_normalize.setToolTip("Apply Z-Score or Min-Max normalization")

        # Epoch Button
        if is_epoched:
            self.btn_epoch.setText("Epoched (Locked)")
            self.btn_epoch.setToolTip(
                "Preprocessing is locked (Data Epoched). Click to see details."
            )
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
        if self.controller.is_epoched():
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
        if not self.controller or not self.controller.has_data():
            QMessageBox.warning(
                self, "Warning", "No data loaded. Please import data first."
            )
            return False
        return True

    def notify_update(self):
        """Notify parent panel to update itself (plots etc)."""
        if self.panel and hasattr(self.panel, "update_panel"):
            self.panel.update_panel()

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
                    self.controller.apply_filter(l_freq, h_freq, notch_freqs)
                    self.notify_update()
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
                try:
                    self.controller.apply_resample(sfreq)
                    self.notify_update()
                    QMessageBox.information(self, "Success", "Resampling applied.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Resample failed: {e}")

    def open_rereference(self):
        """Open the re-reference dialog and apply the new reference."""
        if self.check_lock() or not self.check_data_loaded():
            return

        data_list = self.controller.get_preprocessed_data_list()
        dialog = RereferenceDialog(self, data_list)
        if dialog.exec():
            ref_channels = dialog.get_params()
            if ref_channels:
                try:
                    self.controller.apply_rereference(ref_channels)
                    self.notify_update()
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
                    self.controller.apply_normalization(method)
                    self.notify_update()
                    QMessageBox.information(self, "Success", "Normalization applied.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Normalization failed: {e}")

    def open_epoching(self):
        """Open the epoching dialog and segment the continuous data into epochs."""
        if self.check_lock() or not self.check_data_loaded():
            return

        data_list = self.controller.get_preprocessed_data_list()
        dialog = EpochingDialog(self, data_list)
        if dialog.exec():
            params = dialog.get_params()
            if params:
                baseline, selected_events, tmin, tmax = params
                try:
                    if self.controller.apply_epoching(
                        baseline, selected_events, tmin, tmax
                    ):
                        self.notify_update()
                        # Update main window info if needed (legacy)
                        if self.main_window and hasattr(
                            self.main_window, "update_info_panel"
                        ):
                            self.main_window.update_info_panel()

                        QMessageBox.information(
                            self,
                            "Success",
                            "Epoching applied.\nPreprocessing is now LOCKED.",
                        )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Epoching failed: {e}")

    def reset_preprocess(self):
        """Prompt the user and reset all preprocessing steps to the original data."""
        if not self.check_data_loaded():
            return

        reply = QMessageBox.question(
            self,
            "Confirm Reset",
            "Are you sure you want to reset all preprocessing steps?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.controller.reset_preprocess()
                self.notify_update()
                if self.main_window and hasattr(self.main_window, "update_info_panel"):
                    self.main_window.update_info_panel()
                QMessageBox.information(self, "Success", "Preprocessing reset.")
            except Exception as e:
                logger.error("Reset failed: %s", e)
                QMessageBox.critical(self, "Error", f"Reset failed: {e}")
