"""Sidebar widget for the preprocessing panel with operations and execution controls."""

from collections.abc import Callable
from typing import Any, cast

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
    PreconditionError,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    ResetPreprocessCommand,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ControllerCompatibilityUnavailableError,
    blocked_reason,
    execute_application_command,
    execute_application_command_async,
    get_application_view_publication,
    get_command_capability,
    get_command_review_context,
    get_epoch_dialog_context,
    has_real_application_context,
    is_stale_publication_result,
    local_result_payload,
    run_controller_compatibility_call,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel, SidebarScrollArea
from XBrainLab.ui.dialogs.preprocess import (
    EpochingDialog,
    FilteringDialog,
    NormalizeDialog,
    RereferenceDialog,
    ResampleDialog,
)
from XBrainLab.ui.interaction_outcome import InteractionOutcome
from XBrainLab.ui.refresh_coordinator import refresh_shared_status
from XBrainLab.ui.status import show_status_message
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

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.scroll_area = SidebarScrollArea(self)
        root_layout.addWidget(self.scroll_area)
        layout = self.scroll_area.content_layout

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
        publication = get_application_view_publication(self)
        if publication is not None:
            active_dataset = getattr(
                getattr(publication, "state", None),
                "active_dataset",
                None,
            )
            is_epoched = bool(getattr(active_dataset, "has_epoch_data", False))
        capabilities = (
            publication.effective_capabilities if publication is not None else None
        )
        preprocess_capability = (
            capabilities.get(CommandName.PREPROCESS)
            if capabilities is not None
            else None
        )
        epoch_capability = (
            capabilities.get(CommandName.CREATE_EPOCH)
            if capabilities is not None
            else None
        )
        if preprocess_capability is None and epoch_capability is None:
            data_list = self._compatibility_preprocessed_data_list_for_render()
            if data_list:
                first_data = data_list[0]
                is_epoched = not first_data.is_raw()

        self._update_button_states(
            is_epoched,
            publication=publication,
        )

    def _compatibility_preprocessed_data_list_for_render(self) -> list[Any]:
        """Return compatibility render data only for mock UI contexts."""
        try:
            data_list = run_controller_compatibility_call(
                self,
                self.controller.get_preprocessed_data_list,
            )
        except ControllerCompatibilityUnavailableError:
            return []
        return list(data_list) if isinstance(data_list, list) else []

    def _preprocessed_data_list_for_epoching(
        self,
        epoch_capability,
        *,
        expected_publication_generation: int | None = None,
    ) -> list[Any] | None:
        return self._preprocessed_data_list_for_dialog(
            epoch_capability,
            "Epoching Blocked",
            expected_publication_generation=expected_publication_generation,
        )

    def _preprocessed_data_list_for_dialog(
        self,
        command_capability,
        failure_title: str,
        *,
        expected_publication_generation: int | None = None,
    ) -> list[Any] | None:
        command_kwargs: dict[str, Any] = {"refresh": False}
        if expected_publication_generation is not None:
            command_kwargs["expected_publication_generation"] = (
                expected_publication_generation
            )
        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists", include_objects=True),
            **command_kwargs,
        )
        if result is None:
            if command_capability is None:
                return self._compatibility_preprocessed_data_list_for_dialog(
                    failure_title,
                )
            QMessageBox.warning(
                self,
                failure_title,
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return None
        if result.failed:
            self._show_command_failure(failure_title, result.message)
            return None
        data_list = local_result_payload(result).get("preprocessed_data_list")
        if not isinstance(data_list, list):
            QMessageBox.warning(
                self,
                failure_title,
                "Preprocessed data is unavailable from the current workflow state.",
            )
            return None
        return list(data_list)

    def _compatibility_preprocessed_data_list_for_dialog(
        self,
        failure_title: str,
    ) -> list[Any] | None:
        """Return preprocessed data only for mock / compatibility dialog contexts."""
        try:
            data_list = run_controller_compatibility_call(
                self,
                self.controller.get_preprocessed_data_list,
            )
        except ControllerCompatibilityUnavailableError:
            QMessageBox.warning(
                self,
                failure_title,
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return None
        return list(data_list) if isinstance(data_list, list) else []

    def _update_button_states(self, is_epoched, *, publication=None):
        """Update button tooltips based on the epoched state.

        Args:
            is_epoched: ``True`` if the data has been epoched and
                preprocessing is locked.

        """
        if publication is None:
            preprocess_capability = get_command_capability(
                self,
                CommandName.PREPROCESS,
            )
            epoch_capability = get_command_capability(
                self,
                CommandName.CREATE_EPOCH,
            )
            reset_capability = get_command_capability(
                self,
                CommandName.RESET_PREPROCESS,
            )
        else:
            capabilities = publication.effective_capabilities
            preprocess_capability = capabilities.get(CommandName.PREPROCESS)
            epoch_capability = capabilities.get(CommandName.CREATE_EPOCH)
            reset_capability = capabilities.get(CommandName.RESET_PREPROCESS)
        preprocess_enabled = (
            preprocess_capability.enabled if preprocess_capability is not None else True
        )
        epoch_enabled = (
            epoch_capability.enabled if epoch_capability is not None else True
        )
        reset_enabled = (
            reset_capability.enabled if reset_capability is not None else True
        )
        preprocess_reason = blocked_reason(
            preprocess_capability,
            "Preprocessing is not available.",
        )
        epoch_reason = blocked_reason(
            epoch_capability,
            "Epoching is not available.",
        )
        reset_reason = blocked_reason(
            reset_capability,
            "Reset preprocessing is not available.",
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
        self.btn_reset.setEnabled(reset_enabled and not is_epoched)
        self.btn_reset.setToolTip(
            "Preprocessing is locked after epoching."
            if is_epoched
            else (
                "Restore the loaded EEG data before preprocessing."
                if reset_enabled
                else reset_reason
            )
        )

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
            fallback_ok, is_epoched = self._run_preprocess_compatibility_call(
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
            fallback_ok, has_data = self._run_preprocess_compatibility_call(
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

    def _notify_update_after_command_result(self, result) -> None:
        if result is None:
            self.notify_update()

    def _refresh_shared_status_after_command_result(self, result) -> None:
        if result is None:
            refresh_shared_status(self)

    def _show_status(self, message: str) -> None:
        if show_status_message(self.panel, message):
            return
        logger.info(message)

    def _show_command_failure(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _show_epoch_success(self, result) -> None:
        message = "Epoching applied. Preprocessing is now locked."
        self._show_status(message)

    def _show_preprocess_success(self, result: Any, message: str) -> None:
        self._notify_update_after_command_result(result)
        self._show_status(message)

    def _handle_epoch_command_success(self, result: Any) -> None:
        self._notify_update_after_command_result(result)
        self._refresh_shared_status_after_command_result(result)
        self._show_epoch_success(result)

    def _run_preprocess_compatibility_call(
        self,
        blocked_title: str,
        fallback: Callable[[], Any],
    ) -> tuple[bool, Any]:
        try:
            return True, run_controller_compatibility_call(self, fallback)
        except ControllerCompatibilityUnavailableError as exc:
            QMessageBox.warning(self, blocked_title, str(exc))
            return False, None

    def _begin_preprocess_review(
        self,
        blocked_title: str,
    ) -> tuple[Any | None, bool]:
        """Capture one authoritative publication before opening an edit dialog."""
        review_context = get_command_review_context(self, CommandName.PREPROCESS)
        if review_context is None:
            return review_context, not (
                self.check_lock() or not self.check_data_loaded()
            )

        capability = getattr(review_context, "capability", None)
        if capability is None:
            QMessageBox.warning(
                self,
                blocked_title,
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return review_context, False
        if not capability.enabled:
            QMessageBox.warning(
                self,
                blocked_title,
                blocked_reason(
                    capability,
                    "Load raw data before applying preprocessing.",
                ),
            )
            return review_context, False
        return review_context, True

    def _execute_preprocess_command(
        self,
        command: PreprocessCommand | CreateEpochCommand,
        *,
        blocked_title: str,
        failure_prefix: str,
        on_success: Callable[[Any], None],
        expected_publication_generation: int | None = None,
        stale_review_title: str | None = None,
    ) -> InteractionOutcome:
        """Run an expensive preprocess command without blocking the UI thread."""

        def _handle_result(result) -> InteractionOutcome:
            if is_stale_publication_result(result):
                QMessageBox.warning(
                    self,
                    stale_review_title or f"Review {blocked_title} Again",
                    result.message,
                )
                return InteractionOutcome.blocked(result.message)
            if result.failed:
                self._show_command_failure("Error", result.message)
                if bool(getattr(result, "recoverable", False)):
                    return InteractionOutcome.blocked(result.message)
                return InteractionOutcome.failed(result.message)
            on_success(result)
            return InteractionOutcome.completed(result.message)

        def _handle_error(error: tuple) -> None:
            message = error[1] if len(error) > 1 else error
            QMessageBox.critical(self, "Error", f"{failure_prefix}: {message}")

        if execute_application_command_async(
            self,
            command,
            on_result=_handle_result,
            on_error=_handle_error,
            busy_target=self.panel,
            expected_publication_generation=expected_publication_generation,
        ):
            return InteractionOutcome.accepted("Preprocessing command was scheduled.")

        if has_real_application_context(self):
            QMessageBox.warning(
                self,
                blocked_title,
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )

        try:
            result = execute_application_command(
                self,
                command,
                expected_publication_generation=expected_publication_generation,
            )
            if result is None:
                QMessageBox.warning(
                    self,
                    blocked_title,
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return InteractionOutcome.blocked(
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
                )
            return _handle_result(result)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"{failure_prefix}: {e}")
            return InteractionOutcome.failed(failure_prefix)

    def open_filtering(self):
        """Open the filtering dialog and apply bandpass/notch filters."""
        review_context, ready = self._begin_preprocess_review("Filtering Blocked")
        if not ready:
            return
        expected_generation = (
            review_context.publication_generation
            if review_context is not None
            else None
        )

        dialog = FilteringDialog(
            self,
            sampling_rate_hz=self._current_sampling_rate_hz(),
        )
        if dialog.exec():
            params = dialog.get_params()
            if params:
                l_freq, h_freq, notch_freqs = params
                command = (
                    PreprocessCommand(
                        operation=PreprocessOperation.BANDPASS,
                        low_freq=l_freq,
                        high_freq=h_freq,
                        notch_freq=notch_freqs,
                    )
                    if l_freq is not None and h_freq is not None
                    else PreprocessCommand(
                        operation=PreprocessOperation.NOTCH,
                        notch_freq=notch_freqs,
                    )
                )
                self._execute_preprocess_command(
                    command,
                    blocked_title="Filtering Blocked",
                    failure_prefix="Filtering failed",
                    on_success=lambda result: self._show_preprocess_success(
                        result,
                        "Filtering applied.",
                    ),
                    expected_publication_generation=expected_generation,
                    stale_review_title="Review Filtering Again",
                )

    def _current_sampling_rate_hz(self) -> float | None:
        """Return the lowest loaded rate so validation is safe for every file."""
        query_candidate = getattr(self.panel, "_query_data_lists_for_render", None)
        if not callable(query_candidate):
            return None
        query = cast(
            Callable[[], tuple[list[Any], list[Any]] | None],
            query_candidate,
        )
        try:
            rendered = query()
        except Exception:
            return None
        if not rendered or not rendered[0]:
            return None
        rates = [
            rate
            for data in rendered[0]
            if (rate := self._sampling_rate_hz(data)) is not None
        ]
        return min(rates) if rates else None

    @staticmethod
    def _sampling_rate_hz(data: Any) -> float | None:
        """Read one signal's rate without loading or mutating its samples."""
        get_sfreq_candidate = getattr(data, "get_sfreq", None)
        if callable(get_sfreq_candidate):
            get_sfreq = cast(Callable[[], Any], get_sfreq_candidate)
            try:
                value = float(get_sfreq())
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
        get_mne_candidate = getattr(data, "get_mne", None)
        if not callable(get_mne_candidate):
            return None
        get_mne = cast(Callable[[], Any], get_mne_candidate)
        try:
            value = float(get_mne().info["sfreq"])
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
        return value if value > 0 else None

    def open_resample(self):
        """Open the resample dialog and change the sampling rate."""
        review_context, ready = self._begin_preprocess_review("Resampling Blocked")
        if not ready:
            return
        expected_generation = (
            review_context.publication_generation
            if review_context is not None
            else None
        )

        dialog = ResampleDialog(self)
        if dialog.exec():
            sfreq = dialog.get_params()
            if sfreq:
                rate = int(sfreq)
                self._execute_preprocess_command(
                    PreprocessCommand(
                        operation=PreprocessOperation.RESAMPLE,
                        rate=rate,
                    ),
                    blocked_title="Resampling Blocked",
                    failure_prefix="Resample failed",
                    on_success=lambda result: self._show_preprocess_success(
                        result,
                        "Resampling applied.",
                    ),
                    expected_publication_generation=expected_generation,
                    stale_review_title="Review Resampling Again",
                )

    def open_rereference(self):
        """Open the re-reference dialog and apply the new reference."""
        review_context, ready = self._begin_preprocess_review(
            "Re-reference Blocked",
        )
        if not ready:
            return
        expected_generation = (
            review_context.publication_generation
            if review_context is not None
            else None
        )

        preprocess_capability = (
            review_context.capability
            if review_context is not None
            else get_command_capability(self, CommandName.PREPROCESS)
        )
        data_list = self._preprocessed_data_list_for_dialog(
            preprocess_capability,
            "Re-reference Blocked",
            expected_publication_generation=expected_generation,
        )
        if data_list is None:
            return
        dialog = RereferenceDialog(self, data_list)
        if dialog.exec():
            ref_channels = dialog.get_params()
            if ref_channels:
                self._execute_preprocess_command(
                    PreprocessCommand(
                        operation=PreprocessOperation.REREFERENCE,
                        method=ref_channels if isinstance(ref_channels, str) else None,
                        channels=ref_channels
                        if isinstance(ref_channels, list)
                        else None,
                    ),
                    blocked_title="Re-reference Blocked",
                    failure_prefix="Re-reference failed",
                    on_success=lambda result: self._show_preprocess_success(
                        result,
                        "Re-reference applied.",
                    ),
                    expected_publication_generation=expected_generation,
                    stale_review_title="Review Re-reference Again",
                )

    def open_normalize(self):
        """Open the normalization dialog and apply the selected method."""
        review_context, ready = self._begin_preprocess_review(
            "Normalization Blocked",
        )
        if not ready:
            return
        expected_generation = (
            review_context.publication_generation
            if review_context is not None
            else None
        )

        dialog = NormalizeDialog(self)
        if dialog.exec():
            method = dialog.get_params()
            if method:
                self._execute_preprocess_command(
                    PreprocessCommand(
                        operation=PreprocessOperation.NORMALIZE,
                        method=method,
                    ),
                    blocked_title="Normalization Blocked",
                    failure_prefix="Normalization failed",
                    on_success=lambda result: self._show_preprocess_success(
                        result,
                        result.message,
                    ),
                    expected_publication_generation=expected_generation,
                    stale_review_title="Review Normalization Again",
                )

    def open_epoching(
        self,
        *,
        suggested_values: dict[str, str] | None = None,
    ) -> InteractionOutcome:
        """Open the epoching dialog and segment the continuous data into epochs."""
        dialog_context = get_epoch_dialog_context(self)
        try:
            dialog_context.require_usable()
        except PreconditionError as exc:
            message = str(exc)
            QMessageBox.warning(self, "Epoching Blocked", message)
            return InteractionOutcome.blocked(message)

        epoch_capability = dialog_context.capability
        if epoch_capability is None:
            message = dialog_context.unavailable_reason or (
                "Epoching is unavailable because workflow state could not be verified."
            )
            QMessageBox.warning(self, "Epoching Blocked", message)
            return InteractionOutcome.blocked(message)
        if not epoch_capability.enabled:
            message = blocked_reason(
                epoch_capability,
                "Epoching is not available.",
            )
            QMessageBox.warning(
                self,
                "Epoching Blocked",
                message,
            )
            return InteractionOutcome.blocked(message)

        data_list = self._preprocessed_data_list_for_epoching(
            epoch_capability,
            expected_publication_generation=dialog_context.publication_generation,
        )
        if data_list is None:
            return InteractionOutcome.blocked(
                "Preprocessed data is unavailable for epoching."
            )
        epoch_handoff = dialog_context.epoch_handoff
        if epoch_handoff is None:
            message = "Epoching context is unavailable."
            QMessageBox.warning(self, "Epoching Blocked", message)
            return InteractionOutcome.blocked(message)
        dialog_kwargs: dict[str, Any] = {}
        if epoch_handoff:
            dialog_kwargs["epoch_handoff"] = dict(epoch_handoff)
        if suggested_values:
            dialog_kwargs["assistant_suggestions"] = dict(suggested_values)
        dialog = EpochingDialog(self, data_list, **dialog_kwargs)
        if not dialog.exec():
            return InteractionOutcome.cancelled("Epoching was cancelled.")
        params = dialog.get_params()
        if not params:
            return InteractionOutcome.accepted(
                "The epoching dialog was accepted without an applicable change."
            )
        baseline, selected_events, tmin, tmax = params
        return self._execute_preprocess_command(
            CreateEpochCommand(
                t_min=tmin,
                t_max=tmax,
                baseline=baseline,
                event_ids=selected_events,
                confirmation_receipt=dialog.get_confirmation_receipt(),
            ),
            blocked_title="Epoching Blocked",
            failure_prefix="Epoching failed",
            on_success=self._handle_epoch_command_success,
            expected_publication_generation=(dialog_context.publication_generation),
            stale_review_title="Review Epoching Again",
        )

    def reset_preprocess(self):
        """Prompt the user and reset all preprocessing steps to the original data."""
        publication = get_application_view_publication(self)
        reset_capability = (
            publication.effective_capabilities.get(CommandName.RESET_PREPROCESS)
            if publication is not None
            else get_command_capability(self, CommandName.RESET_PREPROCESS)
        )
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
                expected_publication_generation=(
                    publication.generation if publication is not None else None
                ),
            )
            if result is None:
                QMessageBox.warning(
                    self,
                    "Reset Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif is_stale_publication_result(result):
                QMessageBox.warning(
                    self,
                    "Review Reset Preprocessing Again",
                    result.message,
                )
                return
            elif result.failed:
                self._show_command_failure("Error", result.message)
                return
            self._notify_update_after_command_result(result)
            self._refresh_shared_status_after_command_result(result)
            self._show_status("Preprocessing reset")
        except Exception as e:
            logger.error("Reset failed: %s", e)
            QMessageBox.critical(self, "Error", f"Reset failed: {e}")
