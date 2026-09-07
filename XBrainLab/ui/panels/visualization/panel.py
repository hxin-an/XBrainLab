"""Visualization panel: saliency maps, topomaps, spectrograms, and 3-D views."""

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, cast

import numpy as np
from PyQt6.QtCore import QEvent, QSignalBlocker, Qt, QThread
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import (
    ErrorType,
    SaliencyCommand,
    SaliencyCrossFoldIdentity,
    SaliencyPlanIdentity,
    SaliencyRenderPublication,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
    VisualizeCommand,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.resource_preflight import (
    ResourcePreflightContractError,
    ResourcePreflightView,
)
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.backend.application.saliency_policy import (
    is_recommended_saliency_method,
    recommended_saliency_params_for_method,
    saliency_command_params_from_configured,
    selected_saliency_methods_from_params,
)
from XBrainLab.backend.application.saliency_render import (
    SaliencyRenderView,
)
from XBrainLab.backend.application.state import (
    EpochStateSnapshot,
    EvaluationStateSnapshot,
    SaliencyClassCoverageSnapshot,
    SaliencyMethodCoverageSnapshot,
    SaliencyRunCoverageSnapshot,
    VisualizationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
)
from XBrainLab.backend.saliency_methods import all_saliency_methods
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable, ObserverDeliveryStatus
from XBrainLab.backend.visualization.saliency_semantics import (
    NONNEGATIVE_SALIENCY_METHODS,
)
from XBrainLab.ui.application_capabilities import (
    VisualizationActionPort,
    VisualizationPublicationPort,
    VisualizationQueryPort,
    application_ui_runtime,
    begin_saliency_render_operation,
    cancel_application_operation,
    enter_saliency_render_commit_operation,
    execute_application_command,
    execute_application_command_async,
    fail_application_operation,
    finish_saliency_render_operation,
    get_application_operation,
    is_stale_publication_result,
    prepare_saliency_render_variants_operation,
)
from XBrainLab.ui.application_publication_renderer import (
    ApplicationPublicationRenderLedger,
)
from XBrainLab.ui.components.modal_presentation import (
    AlertSeverity,
    ask_confirmation,
    show_alert,
)
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.core.worker import PythonThreadWorker
from XBrainLab.ui.interaction_outcome import (
    InteractionContinuationLease,
    InteractionOutcome,
    reserve_interaction_continuation,
)
from XBrainLab.ui.owned_operation_presenter import OwnedOperationPresenter
from XBrainLab.ui.product_language import fold_display_label, run_display_label
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

from .control_sidebar import ControlSidebar
from .saliency_views.map_view import SaliencyMapWidget
from .saliency_views.plot_3d_view import Saliency3DPlotWidget
from .saliency_views.spectrogram_view import SaliencySpectrogramWidget
from .saliency_views.topomap_view import SaliencyTopographicMapWidget

if TYPE_CHECKING:
    from XBrainLab.ui.application_capabilities import ApplicationUiRuntime

_SALIENCY_PUBLICATION_UNAVAILABLE_MESSAGE = (
    "Saliency coverage is unavailable because application state could not be verified."
)
_SALIENCY_SELECTION_COVERAGE_UNAVAILABLE_MESSAGE = (
    "Saliency coverage is unavailable for the selected result."
)
_SALIENCY_COMPUTE_START_FAILED_MESSAGE = "Saliency compute could not start. Try again."
_SALIENCY_COMPUTE_INVALID_RESULT_MESSAGE = (
    "Saliency compute returned an invalid result. Try again."
)
_SALIENCY_COMPUTE_FAILED_MESSAGE = (
    "Saliency could not be computed. Adjust the settings and try again."
)
_SALIENCY_RESOURCE_DIALOG_TITLE = "Saliency Resource Check"
_SALIENCY_RESOURCE_CONFIRMATION_INVALID_MESSAGE = (
    "The saliency resource check could not be confirmed safely. "
    "Run the resource check again before continuing."
)
_SALIENCY_RESOURCE_RECEIPT_REJECTED_MESSAGE = (
    "The saliency resource confirmation is no longer valid for this request. "
    "Run the resource check again before continuing."
)
_SALIENCY_RESOURCE_CONFIRMATION_CANCELLED_MESSAGE = (
    "Saliency resource confirmation was cancelled."
)
_SALIENCY_SETTINGS_REVIEW_TITLE = "Review Saliency Settings Again"
_SALIENCY_RESULTS_CHANGED_DETAIL = (
    "Visualization results changed. Open Settings and review the saliency "
    "configuration again."
)
_VISUALIZATION_LOAD_FAILED_MESSAGE = (
    "Visualization could not be loaded. Refresh Visualization and try again."
)
_NO_COMPUTED_METHODS = "No results"


def explanation_provenance_text(
    tab_index: int,
    *,
    dataset_label: str = "",
    plan_label: str = "",
    run_label: str = "",
) -> str:
    """Return compact result identity plus grouping and aggregation provenance."""
    aggregation = {
        0: "True class · Mean over EEG epochs",
        1: "True class · Mean magnitude over EEG epochs and channels",
        2: "True class · Mean over EEG epochs and time",
        3: "True class · Mean over EEG epochs",
    }.get(tab_index, "True class · Mean over EEG epochs")
    identity = [
        value.strip()
        for value in (dataset_label, plan_label, run_label)
        if value.strip()
    ]
    return " · ".join((*identity, aggregation))


@dataclass(frozen=True, slots=True)
class _SaliencySettingsTarget:
    """Immutable result identity reviewed by the saliency settings dialog."""

    publication_generation: int
    run_identity: SaliencyRunIdentity | SaliencyCrossFoldIdentity
    model_name: str


@dataclass(frozen=True, slots=True)
class _SaliencyCrossFoldChoice:
    """One backend-admitted cross-fold option rendered by the UI."""

    identity: SaliencyCrossFoldIdentity
    display_name: str
    run_label: str
    methods: tuple[str, ...]
    source_split: str
    classes: tuple[SaliencyClassCoverageSnapshot, ...]


@dataclass(frozen=True, slots=True)
class _SaliencyCrossFoldGroup:
    """Selector identity for one admitted cohort of folds."""

    plan_indexes: tuple[int, ...]
    display_name: str


_SaliencyPlanSelection = SaliencyPlanIdentity | _SaliencyCrossFoldGroup
_SaliencyRunSelection = SaliencyRunIdentity | SaliencyCrossFoldIdentity


@dataclass(frozen=True, slots=True)
class _VisualizationPublicationSignature:
    """Application fields that can change Visualization's rendered state."""

    usable: bool
    state_reliable: bool
    training_liveness_reliable: bool
    pipeline_stage: str
    trainer_identity: str | None
    training_boundary_stable: bool
    raw_loaded: bool
    raw_files: tuple[str, ...]
    raw_channels: tuple[str, ...]
    preprocessed_available: bool
    preprocessed_files: tuple[str, ...]
    preprocessed_channels: tuple[str, ...]
    epoch_state: EpochStateSnapshot
    training_has_model: bool
    training_model_name: str | None
    training_has_trainer: bool
    training_is_running: bool
    training_plan_count: int
    training_run_count: int
    training_finished_run_count: int
    training_terminal_outcome: TrainingTerminalOutcome
    training_missing_requirements: tuple[str, ...]
    evaluation_state: EvaluationStateSnapshot
    visualization_state: VisualizationStateSnapshot


@dataclass(frozen=True, slots=True)
class _SaliencyRenderTask:
    """One exact saliency publication requested outside the GUI thread."""

    request: SaliencyRenderRequest
    needs_normalized_variant: bool
    operation_id: str = field(default="", compare=False)


class VisualizationPanel(BasePanel):
    """Panel for visualizing data and model explanations with unified controls.
    Manages multiple view tabs (Map, Topomap, Spectrogram, 3D) and coordinates updates.
    """

    def __init__(
        self,
        parent=None,
        *,
        query_port: VisualizationQueryPort | None = None,
        publication_port: VisualizationPublicationPort | None = None,
        action_port: VisualizationActionPort | None = None,
    ):
        """Initialize the visualization panel.

        Args:
            parent: Parent widget (typically the main window).
            query_port: Typed application publication/render query port.
            publication_port: Typed application publication subscription port.
            action_port: Typed Visualization command port.

        """
        self._runs_by_plan: dict[
            _SaliencyPlanSelection,
            tuple[tuple[_SaliencyRunSelection, str], ...],
        ] = {}
        self._cross_fold_choice_by_identity: dict[
            SaliencyCrossFoldIdentity,
            _SaliencyCrossFoldChoice,
        ] = {}
        self._known_evaluation_cross_fold_identities: set[SaliencyCrossFoldIdentity] = (
            set()
        )
        self.last_application_query: CommandResult | None = None
        self.last_saliency_query: CommandResult | None = None
        self._last_active_saliency_view: QWidget | None = None
        self._application_view_publication: ApplicationViewPublication | None = None
        self._saliency_render_cache_request: SaliencyRenderRequest | None = None
        self._saliency_render_cache: dict[bool, SaliencyRenderPublication] = {}
        self._last_application_revision = 0
        self._last_visualization_publication_signature: (
            _VisualizationPublicationSignature | None
        ) = None
        self._application_summary_dirty = True
        self._application_summary_request_sequence = 0
        self._active_application_summary_request: tuple[int, int] | None = None
        self._saliency_summary_dirty = True
        self._saliency_compute_in_progress = False
        self._saliency_command_busy = False
        self._saliency_busy_control_states: list[tuple[QWidget, bool]] = []
        self._saliency_compute_attempted: set[tuple[object, ...]] = set()
        self._pending_saliency_params: dict[str, object] | None = None
        self._pending_saliency_target: _SaliencySettingsTarget | None = None
        self._pending_saliency_method: str | None = None
        self._saliency_settings_review_required = False
        self._saliency_settings_review_detail = ""
        self._active_saliency_operation_id: str | None = None
        self._active_saliency_minimum_generation: int | None = None
        self._active_saliency_generation: int | None = None
        self._saliency_interaction_continuation: InteractionContinuationLease | None = (
            None
        )
        self._current_saliency_coverage: dict[
            str,
            SaliencyMethodCoverageSnapshot,
        ] = {}
        self._saliency_action_requires_recompute = False
        self._native_render_shutdown_requested = False
        self._native_render_resources_finalized = False
        self._saliency_render_worker: PythonThreadWorker | None = None
        self._saliency_render_active_task: _SaliencyRenderTask | None = None
        self._saliency_render_pending_task: _SaliencyRenderTask | None = None
        self._saliency_render_result_seen = False
        self._native_render_bindings: dict[
            QWidget,
            tuple[
                int,
                int,
                str,
                SaliencyRenderPublication,
                tuple[object, ...],
            ],
        ] = {}

        super().__init__(parent=parent, controller=None)

        self._application_render_ledger = ApplicationPublicationRenderLedger(
            panel_name="Visualization",
            render_publication=self._render_application_publication,
            commit_publication=self._record_application_publication,
            parent=self,
        )
        self._application_refresh_timer = self._application_render_ledger.timer
        runtime = application_ui_runtime(self)
        self._query_port = query_port if query_port is not None else runtime
        self._publication_port = (
            publication_port if publication_port is not None else runtime
        )
        self._action_port = action_port if action_port is not None else runtime
        self._subscribe_to_application_publications()
        self.init_ui()

    def _subscribe_to_application_publications(self) -> None:
        """Subscribe once to Visualization's sole state-changing refresh truth."""
        publication_port = self._publication_port
        if publication_port is None:
            return
        self._create_bridge(
            cast(Observable, publication_port),
            APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
            self._on_application_view_publication_changed,
        )

    def _on_application_view_publication_changed(
        self,
        publication: object,
    ) -> bool:
        """Queue at most one render for each relevant monotonic revision."""
        if not self._valid_application_publication(publication):
            logger.error("Ignored malformed Visualization application publication.")
            return False
        typed_publication = cast(ApplicationViewPublication, publication)
        if typed_publication.revision <= self._last_application_revision:
            return True
        signature = self._visualization_publication_signature(typed_publication)
        accepted = self._accept_application_publication(typed_publication)
        explicit_status = typed_publication.state.visualization.post_training_saliency
        if (
            accepted
            and self._saliency_compute_in_progress
            and self._active_saliency_operation_id is not None
            and explicit_status.phase
            in {
                PostTrainingSaliencyPhase.PENDING,
                PostTrainingSaliencyPhase.RUNNING,
            }
            and self._saliency_status_matches_active_operation(explicit_status)
        ):
            # The click receipt and OwnedOperationPresenter already own this
            # visible busy state.  Commit backend progress revisions without
            # rebuilding every saliency view; the generation-bound terminal
            # publication below still performs the result render.
            self._show_saliency_action_bar(self._saliency_compute_method_name())
            return self._application_render_ledger.record_rendered(typed_publication)
        if signature == self._last_visualization_publication_signature:
            return self._application_render_ledger.record_rendered(typed_publication)
        self._mark_application_summaries_dirty()
        return self._application_render_ledger.queue(typed_publication)

    def _render_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> bool | ObserverDeliveryStatus:
        self._accept_application_publication(publication)
        self.update_panel()
        return (
            ObserverDeliveryStatus.DEFERRED
            if self._application_summary_dirty and self.last_application_query is None
            else True
        )

    def init_ui(self):
        """Build the panel layout with control bar, tabbed plots, and sidebar."""
        # Main Layout: Horizontal (Left: Content, Right: Controls)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Column: Visualization Content ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(10)

        # 1. Unified Control Bar
        self.ctrl_bar = QGroupBox("VISUALIZATION CONTROLS")
        self.ctrl_layout = QGridLayout(self.ctrl_bar)
        self.ctrl_layout.setContentsMargins(10, 15, 10, 10)
        self.ctrl_layout.setHorizontalSpacing(8)
        self.ctrl_layout.setVerticalSpacing(6)

        # Fold Selector
        self.plan_label = QLabel("Fold:")
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a fold")
        self.plan_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.plan_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.plan_combo.currentTextChanged.connect(self.on_plan_changed)

        # Run Selector
        self.run_label = QLabel("Run:")
        self.run_combo = QComboBox()
        self.run_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.run_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.run_combo.currentTextChanged.connect(self.on_update)

        # Method Selector
        self.method_label = QLabel("Method:")
        self.method_combo = QComboBox()
        self.method_combo.addItem(_NO_COMPUTED_METHODS)
        self.method_combo.setEnabled(False)
        self.method_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.method_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.method_combo.currentTextChanged.connect(self._on_method_changed)

        # Absolute Checkbox
        self.abs_check = QCheckBox("Absolute")
        self.abs_check.setToolTip("Use absolute saliency values")
        self.abs_check.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        absolute_policy = self.abs_check.sizePolicy()
        absolute_policy.setRetainSizeWhenHidden(True)
        self.abs_check.setSizePolicy(absolute_policy)
        self.abs_check.stateChanged.connect(self.on_update)

        self.normalize_check = QCheckBox("Normalize")
        self.normalize_check.setToolTip(
            "Scale all displayed classes together without changing saved saliency."
        )
        self.normalize_check.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        self.normalize_check.stateChanged.connect(self.on_update)

        # One selector owns the user-visible saliency scope.  The two hidden
        # widgets below remain only as an internal compatibility projection for
        # renderers that receive ``display_mode`` plus an exact class key.
        self.saliency_combo = QComboBox()
        self.saliency_combo.addItem("All classes", None)
        self.saliency_combo.setMinimumWidth(180)
        self.saliency_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.saliency_combo.currentIndexChanged.connect(self._on_saliency_combo_changed)
        self.saliency_view_mode = QComboBox()
        self.saliency_view_mode.addItem("All classes", "all")
        self.saliency_view_mode.addItem("Single class", "single")
        self.saliency_class_combo = QComboBox()
        self.saliency_view_label = QLabel("Saliency:")
        self._controls_layout_mode: str | None = None
        self._apply_visualization_control_layout("narrow")
        left_layout.addWidget(self.ctrl_bar)

        # 2. Saliency compute entry point
        self.saliency_action_bar = self._build_saliency_action_bar()
        self.saliency_action_bar.setVisible(False)
        left_layout.addWidget(self.saliency_action_bar)

        # 3. Explanation canvas
        self._explanation_context_text = ""

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setObjectName("SaliencyViewTabs")
        self.tabs.setStyleSheet(Stylesheets.TAB_WIDGET_CLEAN)
        # Signal connected at the end of init_ui to avoid early triggering

        # Get trainers for initialization (empty initially)

        # Tab 1: Saliency Map
        self.tab_map = SaliencyMapWidget(self)
        self.tab_map.class_selected.connect(self._open_saliency_class_detail)
        self.tab_map.setObjectName("SaliencyMapRenderStatus")
        self.tab_map.setProperty("renderStatus", "idle")
        self.tab_map.setProperty("operationId", "")
        map_commit_guard = getattr(self.tab_map, "set_render_commit_guard", None)
        if callable(map_commit_guard):
            map_commit_guard(
                lambda generation, publication_generation: (
                    self._admit_native_render_commit(
                        self.tab_map,
                        generation,
                        publication_generation,
                    )
                )
            )
        map_terminal = getattr(self.tab_map, "render_terminal", None)
        if map_terminal is not None:
            map_terminal.connect(
                lambda generation, publication_generation, phase: (
                    self._on_native_render_terminal(
                        self.tab_map,
                        generation,
                        publication_generation,
                        phase,
                    )
                )
            )
        self.tabs.addTab(self.tab_map, "Saliency Map")

        # Tab 2: Spectrogram (Swapped order)
        self.tab_spectro = SaliencySpectrogramWidget(self)
        self.tab_spectro.setObjectName("SpectrogramRenderStatus")
        self.tab_spectro.setProperty("renderStatus", "idle")
        self.tab_spectro.setProperty("operationId", "")
        spectro_commit_guard = getattr(
            self.tab_spectro,
            "set_render_commit_guard",
            None,
        )
        if callable(spectro_commit_guard):
            spectro_commit_guard(
                lambda generation, publication_generation: (
                    self._admit_native_render_commit(
                        self.tab_spectro,
                        generation,
                        publication_generation,
                    )
                )
            )
        spectro_terminal = getattr(self.tab_spectro, "render_terminal", None)
        if spectro_terminal is not None:
            spectro_terminal.connect(
                lambda generation, publication_generation, phase: (
                    self._on_native_render_terminal(
                        self.tab_spectro,
                        generation,
                        publication_generation,
                        phase,
                    )
                )
            )
        self.tabs.addTab(self.tab_spectro, "Spectrogram")

        # Tab 3: Topographic Map
        self.tab_topo = SaliencyTopographicMapWidget(self)
        self.tabs.addTab(self.tab_topo, "Topographic Map")

        # Tab 4: 3D Plot
        self.tab_3d = Saliency3DPlotWidget(self)
        self.tabs.addTab(self.tab_3d, "3D Plot")
        self._last_active_saliency_view = self.tab_map

        left_layout.addWidget(self.tabs, stretch=1)
        main_layout.addWidget(left_widget, stretch=1)

        # --- Right Side: Sidebar ---
        self.sidebar = ControlSidebar(self, self)
        main_layout.addWidget(self.sidebar, stretch=0)

        # Connect tab signal now that everything is initialized
        self.tabs.currentChanged.connect(self.on_tab_changed)
        scene_controls_changed = getattr(self.tab_3d, "scene_controls_changed", None)
        if scene_controls_changed is not None:
            scene_controls_changed.connect(self._refresh_sidebar_view_controls)
        self._refresh_explanation_context()
        self._refresh_absolute_control()

        # Keep startup light; populate data-backed controls when the panel is opened.
        self._clear_plan_controls()

    def _build_saliency_action_bar(self) -> QFrame:
        """Build the explicit saliency compute prompt shown for metric-only runs."""
        frame = QFrame()
        frame.setObjectName("SaliencyActionBar")
        frame.setStyleSheet(
            f"""
            QFrame#SaliencyActionBar {{
                background-color: {Theme.BACKGROUND_MID};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 6px;
            }}
            QLabel#SaliencyActionTitle {{
                background-color: transparent;
                color: {Theme.TEXT_PRIMARY};
                font-weight: bold;
            }}
            QLabel#SaliencyActionDetail {{
                background-color: transparent;
                color: {Theme.TEXT_SECONDARY};
            }}
            """
        )

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        self.saliency_action_title = QLabel("Saliency not computed yet")
        self.saliency_action_title.setObjectName("SaliencyActionTitle")
        self.saliency_action_detail = QLabel(
            "Recommended profile computes Gradient + Gradient * Input."
        )
        self.saliency_action_detail.setObjectName("SaliencyActionDetail")
        self.saliency_action_detail.setWordWrap(True)
        text_layout.addWidget(self.saliency_action_title)
        text_layout.addWidget(self.saliency_action_detail)

        self.compute_saliency_btn = QPushButton("Compute Saliency")
        self.compute_saliency_btn.setObjectName("ComputeSaliencyButton")
        self.compute_saliency_btn.setProperty("operationId", "")
        self.compute_saliency_btn.setProperty("operationPhase", "idle")
        self.compute_saliency_btn.setMinimumWidth(140)
        self.compute_saliency_btn.setStyleSheet(
            Stylesheets.BTN_PRIMARY
            + f"""
            QPushButton:disabled {{
                background-color: {Theme.BTN_DISABLED_BG};
                color: {Theme.BTN_DISABLED_TEXT};
            }}
            """
        )
        self.compute_saliency_btn.clicked.connect(
            self._compute_saliency_from_action_bar
        )

        self.cancel_saliency_btn = QPushButton("Cancel")
        self.cancel_saliency_btn.setObjectName("OwnedOperationCancelButton")
        self.cancel_saliency_btn.setMinimumWidth(86)
        self.cancel_saliency_btn.setToolTip("Cancel the active saliency computation")
        self.cancel_saliency_btn.setStyleSheet(Stylesheets.BTN_WARNING)

        self._saliency_operation_presenter = OwnedOperationPresenter(
            self,
            cancel_button=self.cancel_saliency_btn,
            snapshot_getter=lambda operation_id: get_application_operation(
                self,
                operation_id,
                runtime=cast("ApplicationUiRuntime", self._action_port),
            ),
            canceller=self._cancel_owned_saliency_operation,
        )
        self._saliency_operation_presenter.terminal.connect(
            self._on_saliency_operation_terminal
        )

        self.saliency_settings_btn = QPushButton("Settings")
        self.saliency_settings_btn.setMinimumWidth(86)
        self.saliency_settings_btn.setStyleSheet(Stylesheets.BTN_GHOST)
        self.saliency_settings_btn.clicked.connect(self._open_saliency_settings)

        layout.addLayout(text_layout, stretch=1)
        layout.addWidget(self.cancel_saliency_btn)
        layout.addWidget(self.saliency_settings_btn)
        layout.addWidget(self.compute_saliency_btn)
        return frame

    def set_busy(self, busy: bool) -> None:
        """Fence saliency target mutations without disabling visible Cancel."""
        self._saliency_command_busy = bool(busy)
        self._sync_saliency_busy_controls()

    def _sync_saliency_busy_controls(self) -> None:
        """Keep the reviewed target stable for the complete owned operation."""
        if not hasattr(self, "plan_combo"):
            return
        active = self._saliency_command_busy or self._saliency_compute_in_progress
        self.setCursor(
            Qt.CursorShape.WaitCursor if active else Qt.CursorShape.ArrowCursor
        )
        controls: list[QWidget] = [
            self.plan_combo,
            self.run_combo,
            self.method_combo,
            self.abs_check,
            self.normalize_check,
            self.saliency_settings_btn,
        ]
        control = getattr(getattr(self, "sidebar", None), "btn_saliency", None)
        if isinstance(control, QWidget):
            controls.append(control)
        if active:
            if not self._saliency_busy_control_states:
                self._saliency_busy_control_states = [
                    (control, control.isEnabled()) for control in controls
                ]
            for control in controls:
                control.setEnabled(False)
            return

        control_states = self._saliency_busy_control_states
        self._saliency_busy_control_states = []
        for control, was_enabled in control_states:
            control.setEnabled(was_enabled)

    def resizeEvent(self, event):  # noqa: N802
        """Switch visualization controls between compact and full-width layouts."""
        super().resizeEvent(event)
        self._refresh_control_layout_for_width()

    def _refresh_control_layout_for_width(self) -> None:
        if not hasattr(self, "ctrl_bar"):
            return
        available_width = max(self.ctrl_bar.width(), self.width() - 340)
        if available_width >= 760:
            layout_mode = "wide"
        elif available_width >= 700:
            layout_mode = "medium"
        else:
            layout_mode = "narrow"
        self._apply_visualization_control_layout(layout_mode)

    def _apply_visualization_control_layout(self, layout_mode: str) -> None:
        if getattr(self, "_controls_layout_mode", None) == layout_mode:
            return

        self._controls_layout_mode = layout_mode
        for column in range(12):
            self.ctrl_layout.setColumnStretch(column, 0)

        controls = (
            self.plan_label,
            self.plan_combo,
            self.run_label,
            self.run_combo,
            self.saliency_view_label,
            self.saliency_combo,
            self.method_label,
            self.method_combo,
            self.normalize_check,
            self.abs_check,
        )
        for control in controls:
            self.ctrl_layout.removeWidget(control)

        if layout_mode == "wide":
            self.plan_combo.setMinimumWidth(150)
            self.plan_combo.setMaximumWidth(210)
            self.run_combo.setMinimumWidth(105)
            self.run_combo.setMaximumWidth(145)
            self.method_combo.setMinimumWidth(150)
            self.method_combo.setMaximumWidth(190)
            self.ctrl_layout.addWidget(self.plan_label, 0, 0)
            self.ctrl_layout.addWidget(self.plan_combo, 0, 1)
            self.ctrl_layout.addWidget(self.run_label, 0, 2)
            self.ctrl_layout.addWidget(self.run_combo, 0, 3)
            self.ctrl_layout.addWidget(self.saliency_view_label, 0, 4)
            self.ctrl_layout.addWidget(self.saliency_combo, 0, 5)
            self.ctrl_layout.addWidget(self.method_label, 0, 6)
            self.ctrl_layout.addWidget(self.method_combo, 0, 7)
            self.ctrl_layout.setColumnStretch(11, 1)
            self._position_transform_controls(layout_mode)
            return

        if layout_mode == "medium":
            self.plan_combo.setMinimumWidth(150)
            self.plan_combo.setMaximumWidth(210)
            self.run_combo.setMinimumWidth(105)
            self.run_combo.setMaximumWidth(145)
            self.method_combo.setMinimumWidth(150)
            self.method_combo.setMaximumWidth(190)
            self.saliency_combo.setMinimumWidth(160)
            self.ctrl_layout.addWidget(self.plan_label, 0, 0)
            self.ctrl_layout.addWidget(self.plan_combo, 0, 1)
            self.ctrl_layout.addWidget(self.run_label, 0, 2)
            self.ctrl_layout.addWidget(self.run_combo, 0, 3)
            self.ctrl_layout.addWidget(self.saliency_view_label, 0, 4)
            self.ctrl_layout.addWidget(self.saliency_combo, 0, 5)
            self.ctrl_layout.addWidget(self.method_label, 1, 0)
            self.ctrl_layout.addWidget(self.method_combo, 1, 1)
            self.ctrl_layout.setColumnStretch(7, 1)
            self._position_transform_controls(layout_mode)
            return

        self.plan_combo.setMinimumWidth(115)
        self.plan_combo.setMaximumWidth(150)
        self.run_combo.setMinimumWidth(90)
        self.run_combo.setMaximumWidth(120)
        self.method_combo.setMinimumWidth(100)
        self.method_combo.setMaximumWidth(135)
        self.saliency_combo.setMinimumWidth(135)
        self.ctrl_layout.addWidget(self.plan_label, 0, 0)
        self.ctrl_layout.addWidget(self.plan_combo, 0, 1)
        self.ctrl_layout.addWidget(self.run_label, 0, 2)
        self.ctrl_layout.addWidget(self.run_combo, 0, 3)
        self.ctrl_layout.addWidget(self.saliency_view_label, 1, 0)
        self.ctrl_layout.addWidget(self.saliency_combo, 1, 1)
        self.ctrl_layout.addWidget(self.method_label, 2, 0)
        self.ctrl_layout.addWidget(self.method_combo, 2, 1)
        self.ctrl_layout.setColumnStretch(5, 1)
        self._position_transform_controls(layout_mode)

    def _position_transform_controls(self, layout_mode: str) -> None:
        """Place compact transforms without reserving hidden-control holes."""
        self.ctrl_layout.removeWidget(self.abs_check)
        self.ctrl_layout.removeWidget(self.normalize_check)

        spectrogram_active = hasattr(
            self, "tabs"
        ) and self.tabs.currentWidget() is getattr(self, "tab_spectro", None)
        show_absolute = not spectrogram_active
        self.abs_check.setVisible(show_absolute)
        self.normalize_check.setVisible(True)

        if layout_mode == "wide":
            row = 0
            normalize_column = 9
            absolute_column = 10
        elif layout_mode == "medium":
            row = 1
            normalize_column = 2
            absolute_column = 3
        else:
            row = 2
            normalize_column = 2
            absolute_column = 3

        self.ctrl_layout.addWidget(self.normalize_check, row, normalize_column)
        if show_absolute:
            self.ctrl_layout.addWidget(self.abs_check, row, absolute_column)

    def _cross_fold_choices_from_query(
        self,
    ) -> tuple[_SaliencyCrossFoldChoice, ...]:
        """Parse backend-admitted summary identities without inferring cohorts."""
        payload = self._visualization_query_payload()
        if payload is None:
            return ()
        evaluation_choices = payload.get("evaluation_cross_fold_choices", [])
        saliency_choices = payload.get("saliency_cross_fold_choices", [])
        if not isinstance(evaluation_choices, list) or not isinstance(
            saliency_choices, list
        ):
            return ()
        # Evaluation admits a Fold Set before saliency exists.  A verified
        # saliency entry with the same exact identity replaces that read-only
        # placeholder once it can be rendered.
        raw_choices = [*evaluation_choices, *saliency_choices]
        choices: list[_SaliencyCrossFoldChoice] = []
        for raw_choice in raw_choices:
            if not isinstance(raw_choice, dict):
                continue
            raw_identity = raw_choice.get("identity")
            raw_members = (
                raw_identity.get("members") if isinstance(raw_identity, dict) else None
            )
            raw_methods = raw_choice.get("methods", [])
            raw_classes = raw_choice.get("classes", [])
            if (
                not isinstance(raw_members, list)
                or not isinstance(raw_methods, list)
                or not isinstance(raw_classes, list)
            ):
                continue
            try:
                members = tuple(
                    SaliencyRunIdentity(
                        plan=SaliencyPlanIdentity(
                            plan_index=int(member["plan_index"]),
                        ),
                        run_index=int(member["run_index"]),
                    )
                    for member in raw_members
                    if isinstance(member, dict)
                )
                identity = SaliencyCrossFoldIdentity(members=members)
                methods = tuple(
                    str(method)
                    for method in raw_methods
                    if str(method) in all_saliency_methods
                )
                classes = tuple(
                    SaliencyClassCoverageSnapshot(
                        class_index=int(item["class_index"]),
                        display_name=str(item["display_name"]),
                        event_code=item.get("event_code"),
                        store_key=item.get("store_key"),
                        available=True,
                    )
                    for item in raw_classes
                    if isinstance(item, dict)
                )
            except (KeyError, TypeError, ValueError):
                continue
            choices.append(
                _SaliencyCrossFoldChoice(
                    identity=identity,
                    display_name=str(raw_choice.get("display_name") or "All Folds"),
                    run_label=str(
                        raw_choice.get("run_label") or f"Run {identity.run_index + 1}"
                    ).replace(" (Summary)", ""),
                    methods=methods,
                    source_split=str(raw_choice.get("source_split") or "unknown"),
                    classes=classes,
                )
            )
        by_identity = {choice.identity: choice for choice in choices}
        return tuple(by_identity.values())

    def _evaluation_cross_fold_identities_from_query(
        self,
        choices: tuple[_SaliencyCrossFoldChoice, ...],
    ) -> set[SaliencyCrossFoldIdentity]:
        """Return only backend-admitted Fold Sets, never inferred exact folds."""
        payload = self._visualization_query_payload()
        raw_choices = (
            payload.get("evaluation_cross_fold_choices", []) if payload else []
        )
        if not isinstance(raw_choices, list):
            return set()
        raw_members: set[tuple[tuple[int, int], ...]] = set()
        for raw in raw_choices:
            identity = raw.get("identity") if isinstance(raw, dict) else None
            members = identity.get("members") if isinstance(identity, dict) else None
            if not isinstance(members, list):
                continue
            try:
                raw_members.add(
                    tuple(
                        (int(member["plan_index"]), int(member["run_index"]))
                        for member in members
                        if isinstance(member, dict)
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return {
            choice.identity
            for choice in choices
            if tuple(
                (member.plan.plan_index, member.run_index)
                for member in choice.identity.members
            )
            in raw_members
        }

    def refresh_combos(self):
        """Refresh plan/run identities from one immutable view publication."""
        if self._application_summary_dirty or self.last_application_query is None:
            self._refresh_application_query(view="summary")
        if self._application_summary_dirty:
            # Keep the current Fold Set while a newer published summary is
            # queued. Rebuilding from an unpaired P1/P2 boundary would reset
            # the selection before the ledger delivers the coherent retry.
            return

        if self._application_query_blocks_display(self.last_application_query):
            self._clear_plan_controls()
            return

        previous_plan = self.plan_combo.currentData()
        previous_plan_text = self.plan_combo.currentText()
        previous_run = self.run_combo.currentData()
        previous_run_text = self.run_combo.currentText()
        publication = self._application_view_publication
        coverage = (
            publication.state.visualization.saliency_coverage
            if publication is not None and publication.usable
            else ()
        )
        grouped_runs: dict[
            _SaliencyPlanSelection,
            list[tuple[_SaliencyRunSelection, str]],
        ] = {}
        plan_labels: dict[_SaliencyPlanSelection, str] = {}
        for run_coverage in coverage:
            plan_identity = SaliencyPlanIdentity(run_coverage.plan_index)
            run_identity = SaliencyRunIdentity(
                plan=plan_identity,
                run_index=run_coverage.run_index,
            )
            run_label = run_display_label(run_coverage.run_index)
            grouped_runs.setdefault(plan_identity, []).append((run_identity, run_label))
            plan_labels.setdefault(
                plan_identity,
                fold_display_label(run_coverage.plan_index, run_coverage.plan_name),
            )

        cross_fold_choices = self._cross_fold_choices_from_query()
        self._cross_fold_choice_by_identity = {
            choice.identity: choice for choice in cross_fold_choices
        }
        cross_fold_groups: dict[
            tuple[int, ...],
            tuple[_SaliencyCrossFoldGroup, list[tuple[_SaliencyRunSelection, str]]],
        ] = {}
        for choice in cross_fold_choices:
            indexes = tuple(
                member.plan.plan_index for member in choice.identity.members
            )
            if indexes not in cross_fold_groups:
                group = _SaliencyCrossFoldGroup(indexes, choice.display_name)
                cross_fold_groups[indexes] = (group, [])
            group, runs = cross_fold_groups[indexes]
            runs.append((choice.identity, choice.run_label))
            plan_labels[group] = choice.display_name
        grouped_runs.update(dict(cross_fold_groups.values()))

        self.plan_combo.blockSignals(True)
        self.run_combo.blockSignals(True)
        self.plan_combo.clear()
        self.plan_combo.addItem("Select a fold")
        self.run_combo.clear()
        self._runs_by_plan = {
            identity: tuple(sorted(runs, key=lambda item: item[0].run_index))
            for identity, runs in grouped_runs.items()
        }

        if not self._runs_by_plan:
            self.plan_combo.blockSignals(False)
            self.run_combo.blockSignals(False)
            self.on_update()
            return

        plan_order = sorted(
            self._runs_by_plan,
            key=lambda identity: (
                1 if isinstance(identity, _SaliencyCrossFoldGroup) else 0,
                identity.plan_indexes[0]
                if isinstance(identity, _SaliencyCrossFoldGroup)
                else identity.plan_index,
            ),
        )
        for plan_identity in plan_order:
            self.plan_combo.addItem(plan_labels[plan_identity], plan_identity)

        evaluation_identities = self._evaluation_cross_fold_identities_from_query(
            cross_fold_choices,
        )
        new_evaluation_identities = (
            evaluation_identities - self._known_evaluation_cross_fold_identities
        )
        self._known_evaluation_cross_fold_identities = evaluation_identities

        # A newly admitted training round must not leave the user looking at a
        # previous round's completed saliency. Prefer its aggregate Fold Set;
        # if it is not cross-validation, select its first exact fold instead.
        if self.plan_combo.count() > 1:
            selected_index = 1
            if new_evaluation_identities:
                newest = max(
                    new_evaluation_identities,
                    key=lambda identity: max(
                        member.plan.plan_index for member in identity.members
                    ),
                )
                for i in range(1, self.plan_combo.count()):
                    candidate = self.plan_combo.itemData(i)
                    if isinstance(candidate, _SaliencyCrossFoldGroup) and tuple(
                        candidate.plan_indexes
                    ) == tuple(member.plan.plan_index for member in newest.members):
                        selected_index = i
                        break
            else:
                for i in range(1, self.plan_combo.count()):
                    if self.plan_combo.itemData(i) == previous_plan:
                        selected_index = i
                        break
                    if (
                        previous_plan_text
                        and self.plan_combo.itemText(i) == previous_plan_text
                    ):
                        selected_index = i
                        break
            self.plan_combo.setCurrentIndex(selected_index)
            self.plan_combo.blockSignals(False)
            self.run_combo.blockSignals(False)
            # Explicitly call on_plan_changed to ensure run_combo is populated
            self.on_plan_changed(
                self.plan_combo.currentText(),
                preferred_run=previous_run,
                preferred_run_text=previous_run_text,
            )
        else:
            self.plan_combo.blockSignals(False)
            self.run_combo.blockSignals(False)

    def on_plan_changed(self, text, preferred_run=None, preferred_run_text=""):
        """Update Run combo when Plan changes."""
        del text
        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        plan_identity = self.plan_combo.currentData()
        if isinstance(
            plan_identity,
            (SaliencyPlanIdentity, _SaliencyCrossFoldGroup),
        ):
            for run_identity, run_label in self._runs_by_plan.get(plan_identity, ()):
                self.run_combo.addItem(run_label, run_identity)

        if self.run_combo.count() > 0:
            selected_index = 0
            for i in range(self.run_combo.count()):
                if self.run_combo.itemData(i) == preferred_run:
                    selected_index = i
                    break
                if (
                    preferred_run_text
                    and self.run_combo.itemText(i) == preferred_run_text
                ):
                    selected_index = i
                    break
            self.run_combo.setCurrentIndex(selected_index)
            self.run_combo.blockSignals(False)
            self._refresh_selection_actions()
            self.on_update()
        else:
            self.run_combo.blockSignals(False)
            self._refresh_selection_actions()
            self.on_update()  # Trigger update to clear if empty

    def _refresh_selection_actions(self) -> None:
        """Keep Saliency settings bound to the exact selected result identity."""
        selection = self.run_combo.currentData()
        cross_fold = isinstance(selection, SaliencyCrossFoldIdentity)
        selectable = isinstance(
            selection,
            (SaliencyRunIdentity, SaliencyCrossFoldIdentity),
        )
        if hasattr(self, "sidebar") and hasattr(self.sidebar, "btn_saliency"):
            self.sidebar.btn_saliency.setEnabled(selectable)
            self.sidebar.btn_saliency.setToolTip(
                "Configure one method profile for every Fold in this set."
                if cross_fold
                else "Configure saliency methods and parameters."
            )

    def on_tab_changed(self, index):
        """Handle tab switch."""
        del index
        current_widget = self.tabs.currentWidget()
        previous_widget = self._last_active_saliency_view
        if previous_widget is not current_widget:
            cancelled = self._cancel_native_render_binding(previous_widget)
            if cancelled:
                invalidate = getattr(
                    previous_widget,
                    "invalidate_render_publication",
                    None,
                )
                if callable(invalidate):
                    invalidate()
        self._last_active_saliency_view = current_widget
        self._refresh_explanation_context()
        self._refresh_absolute_control()
        self._refresh_sidebar_view_controls()
        self.on_update()

    def begin_native_render_shutdown(self) -> None:
        """Cooperatively cancel every saliency view before application close."""
        if (
            self._native_render_shutdown_requested
            or self._native_render_resources_finalized
        ):
            return
        self._native_render_shutdown_requested = True
        operation_id = self._active_saliency_operation_id
        if operation_id is not None:
            cancel_application_operation(
                self,
                operation_id,
                runtime=cast("ApplicationUiRuntime", self._action_port),
            )
        self._saliency_render_pending_task = None
        active_task = self._saliency_render_active_task
        if active_task is not None and active_task.operation_id:
            cancel_application_operation(
                self,
                active_task.operation_id,
                runtime=cast("ApplicationUiRuntime", self._query_port),
            )
        for widget in tuple(self._native_render_bindings):
            self._cancel_native_render_binding(widget)
        for view in self._saliency_views():
            begin_shutdown = getattr(view, "begin_render_shutdown", None)
            if callable(begin_shutdown):
                begin_shutdown()

    def native_render_work_idle(self) -> bool:
        """Return true after every saliency worker reaches terminal cleanup."""
        if self._saliency_render_worker is not None:
            return False
        for view in self._saliency_views():
            is_idle = getattr(view, "native_render_work_idle", None)
            if callable(is_idle) and not bool(is_idle()):
                return False
        return True

    def native_render_resources_finalized(self) -> bool:
        """Return true only after every child reports terminal native cleanup."""
        if not self._native_render_resources_finalized:
            return False
        for view in self._saliency_views():
            is_finalized = getattr(
                view,
                "native_render_resources_finalized",
                None,
            )
            if not callable(is_finalized) or not bool(is_finalized()):
                return False
        return True

    def cancel_native_render_shutdown(self) -> None:
        """Resume the active tab from the retained application publication."""
        if self._native_render_resources_finalized:
            return
        resume_active_render = self._native_render_shutdown_requested
        self._native_render_shutdown_requested = False
        for view in self._saliency_views():
            cancel_shutdown = getattr(view, "cancel_render_shutdown", None)
            if callable(cancel_shutdown):
                cancel_shutdown()
        publication = self._application_view_publication
        current_widget = self.tabs.currentWidget()
        if (
            resume_active_render
            and publication is not None
            and publication.usable
            and current_widget in self._saliency_views()
        ):
            self.on_update()

    def finalize_native_render_resources(self) -> bool:
        """Finalize every saliency native widget once without waiting."""
        if self._native_render_resources_finalized:
            return True
        if QThread.currentThread() is not self.thread():
            logger.error(
                "Visualization native resources must be finalized on the GUI thread."
            )
            return False
        finalized = True
        for view in self._saliency_views():
            finalize = getattr(view, "finalize_native_render_resources", None)
            if callable(finalize) and not bool(finalize()):
                finalized = False
        self._native_render_resources_finalized = finalized
        return finalized

    def _saliency_views(self) -> tuple[QWidget, ...]:
        return tuple(
            view
            for name in ("tab_map", "tab_spectro", "tab_topo", "tab_3d")
            if isinstance((view := getattr(self, name, None)), QWidget)
        )

    def _on_method_changed(self, _method: str) -> None:
        self._refresh_absolute_control()
        self.on_update()

    def _refresh_absolute_control(self) -> None:
        """Hide or disable an irrelevant transform while preserving its choice."""
        if not hasattr(self, "abs_check") or not hasattr(self, "tabs"):
            return
        self._refresh_control_layout_for_width()
        self._position_transform_controls(self._controls_layout_mode or "narrow")
        method = self.method_combo.currentText()
        if self.tabs.currentIndex() == 1:
            self.abs_check.setEnabled(False)
            self.abs_check.setToolTip(
                "Spectrograms display attribution magnitude by definition."
            )
            return
        if method in NONNEGATIVE_SALIENCY_METHODS:
            self.abs_check.setEnabled(False)
            self.abs_check.setToolTip(f"{method} is non-negative by definition.")
            return
        self.abs_check.setEnabled(True)
        self.abs_check.setToolTip("Display absolute attribution values.")

    def _refresh_explanation_context(self) -> None:
        """Explain the selected result identity and scientific aggregation."""
        if not hasattr(self, "tabs"):
            return
        self._explanation_context_text = explanation_provenance_text(
            self.tabs.currentIndex(),
            dataset_label=self._selected_dataset_label(),
            plan_label=self._selected_plan_label(),
            run_label=self._selected_run_label(),
        )
        self.tabs.setToolTip(self._explanation_context_text)

    def _selected_dataset_label(self) -> str:
        """Return the dataset identity bound to the selected finished result."""
        coverage = self._selected_run_coverage()
        return coverage.plan_name.strip() if coverage is not None else ""

    def _selected_plan_label(self) -> str:
        publication = self._application_view_publication
        if publication is None or not publication.usable:
            return ""
        return (
            self.plan_combo.currentText()
            if isinstance(
                self.plan_combo.currentData(),
                (SaliencyPlanIdentity, _SaliencyCrossFoldGroup),
            )
            else ""
        )

    def _selected_run_label(self) -> str:
        publication = self._application_view_publication
        if publication is None or not publication.usable:
            return ""
        return (
            self.run_combo.currentText()
            if isinstance(
                self.run_combo.currentData(),
                (SaliencyRunIdentity, SaliencyCrossFoldIdentity),
            )
            else ""
        )

    def on_update(self):
        """Gather settings and call update_plot on current tab."""
        current_widget = self.tabs.currentWidget()
        if current_widget is None:
            return
        self._hide_saliency_action_bar()
        if self._application_summary_dirty or self.last_application_query is None:
            self._refresh_application_query(
                view=self.tabs.tabText(self.tabs.currentIndex())
            )
        if self._application_summary_dirty:
            return
        self._refresh_explanation_context()

        if self._application_query_blocks_display(self.last_application_query):
            self._sync_method_options({})
            message = self._application_query_message()
            if self._application_query_is_readiness_block(self.last_application_query):
                self._show_widget_message(current_widget, message)
            else:
                self._show_widget_error(current_widget, message)
            publication = self._application_view_publication
            if publication is not None and self._saliency_compute_awaits_current_render(
                publication.generation
            ):
                self._release_saliency_compute_after_render()
            return

        blocked_view_message = self._selected_view_blocked_message()
        if blocked_view_message:
            method_coverage = self._published_coverage_for_selection()
            if method_coverage is None:
                self._sync_method_options({})
            else:
                method_name = self._sync_method_options(method_coverage)
                selected_coverage = method_coverage.get(
                    method_name,
                    SaliencyMethodCoverageSnapshot(method=method_name),
                )
                self._sync_saliency_class_controls(selected_coverage)
                if hasattr(self, "tab_3d"):
                    self.tab_3d.select_class_key(
                        self.saliency_class_combo.currentData()
                    )
            self._show_widget_message(current_widget, blocked_view_message)
            publication = self._application_view_publication
            if publication is not None and self._saliency_compute_awaits_current_render(
                publication.generation
            ):
                self._release_saliency_compute_after_render()
            return

        automatic_status = self._post_training_saliency_status()

        plan_identity = self.plan_combo.currentData()
        run_identity = self.run_combo.currentData()
        absolute = self.abs_check.isChecked() and current_widget is not self.tab_spectro
        normalize = self.normalize_check.isChecked()

        single_selection = isinstance(
            plan_identity,
            SaliencyPlanIdentity,
        ) and isinstance(run_identity, SaliencyRunIdentity)
        cross_fold_selection = isinstance(
            plan_identity,
            _SaliencyCrossFoldGroup,
        ) and isinstance(run_identity, SaliencyCrossFoldIdentity)
        if not single_selection and not cross_fold_selection:
            self._sync_method_options({})
            setup_message = self._setup_only_message()
            if setup_message:
                self._show_widget_message(current_widget, setup_message)
                return
            # Clear or show placeholder
            self._show_widget_message(
                current_widget,
                "Select a fold and run to continue.",
            )
            return

        publication = self._application_view_publication
        if publication is None:
            self._sync_method_options({})
            self._publish_saliency_view_state(
                current_widget,
                coverage=None,
                automatic_status=automatic_status,
            )
            self._show_widget_message(
                current_widget,
                _SALIENCY_PUBLICATION_UNAVAILABLE_MESSAGE,
            )
            return

        method_coverage = self._published_coverage_for_selection()
        if method_coverage is None:
            self._sync_method_options({})
            self._publish_saliency_view_state(
                current_widget,
                coverage=None,
                automatic_status=automatic_status,
            )
            self._show_widget_message(
                current_widget,
                _SALIENCY_SELECTION_COVERAGE_UNAVAILABLE_MESSAGE,
            )
            return
        method_name = self._sync_method_options(method_coverage)
        selected_coverage = method_coverage.get(
            method_name,
            SaliencyMethodCoverageSnapshot(method=method_name),
        )
        self._sync_saliency_class_controls(selected_coverage)
        if hasattr(self, "tab_3d"):
            self.tab_3d.select_class_key(self.saliency_class_combo.currentData())
        self._publish_saliency_view_state(
            current_widget,
            coverage=selected_coverage,
            automatic_status=automatic_status,
        )
        if not selected_coverage.available:
            if self._should_surface_automatic_status(
                automatic_status,
                method_name,
            ):
                self._show_post_training_saliency_state(
                    current_widget,
                    method_name,
                    selected_coverage,
                    automatic_status,
                )
                return
            self._show_saliency_action_bar(method_name, selected_coverage)
            self._show_widget_message(
                current_widget,
                (
                    self._incomplete_saliency_message(selected_coverage)
                    if self._coverage_requires_recompute(selected_coverage)
                    else f"{method_name} saliency has not been computed for this run. "
                    "Use Compute Saliency to continue."
                ),
            )
            return
        if self.tabs.currentIndex() != 3 and not selected_coverage.complete:
            if self._should_surface_automatic_status(
                automatic_status,
                method_name,
            ):
                self._show_post_training_saliency_state(
                    current_widget,
                    method_name,
                    selected_coverage,
                    automatic_status,
                )
                return
            self._show_saliency_action_bar(method_name, selected_coverage)
            self._show_widget_message(
                current_widget,
                self._incomplete_saliency_message(selected_coverage),
            )
            return

        request = SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=run_identity,
            method=method_name,
            normalize=normalize,
            view=self._saliency_render_view(current_widget),
        )
        # Spectrogram normalization is a display-linear transform. Keep its
        # source publication raw so toggling Normalize can reuse one STFT.
        publication_request = (
            replace(request, normalize=False)
            if current_widget is self.tab_spectro
            else request
        )
        display_key = (
            bool(absolute),
            bool(normalize),
            str(self.saliency_view_mode.currentData() or "all"),
            self.saliency_class_combo.currentData(),
        )
        set_detail_interactions = getattr(
            current_widget,
            "set_detail_interactions_enabled",
            None,
        )
        if callable(set_detail_interactions):
            set_detail_interactions(display_key[2] == "single")
        active_binding = self._native_render_bindings.get(current_widget)
        if (
            active_binding is not None
            and active_binding[3].request == publication_request
            and active_binding[4] == display_key
        ):
            return
        if active_binding is not None and not self._cancel_native_render_binding(
            current_widget
        ):
            return
        if not self._saliency_render_is_cached(publication_request):
            task = _SaliencyRenderTask(
                request=publication_request,
                needs_normalized_variant=publication_request.normalize,
            )
            self._request_saliency_render(task)
            self._show_widget_message(
                current_widget,
                (
                    "Preparing the All Folds saliency summary..."
                    if cross_fold_selection
                    else "Loading saliency visualization..."
                ),
            )
            return
        try:
            render_publication = self._saliency_render_publication(publication_request)
        except PreconditionError as exc:
            logger.warning(
                "Saliency render publication became unavailable: %s",
                exc,
            )
            self._application_summary_dirty = True
            self._clear_application_view_publication(
                invalidate_render_publications=True,
            )
            self._show_widget_message(
                current_widget,
                "Visualization results changed. Refresh Visualization and try again.",
            )
            return
        except Exception:
            logger.error("Saliency render publication failed", exc_info=True)
            self._show_widget_error(
                current_widget,
                "Saliency render data could not be published. Try again.",
            )
            return
        if not isinstance(render_publication, SaliencyRenderPublication):
            self._application_summary_dirty = True
            self._clear_application_view_publication(
                invalidate_render_publications=True,
            )
            self._show_widget_message(
                current_widget,
                "Visualization results changed. Refresh Visualization and try again.",
            )
            return
        typed_render_publication = cast(
            SaliencyRenderPublication,
            render_publication,
        )
        if (
            typed_render_publication.request != publication_request
            or typed_render_publication.generation != publication.generation
            or typed_render_publication.data.method != method_name
            or typed_render_publication.data.normalized != publication_request.normalize
        ):
            self._application_summary_dirty = True
            self._clear_application_view_publication(
                invalidate_render_publications=True,
            )
            self._show_widget_message(
                current_widget,
                "Visualization results changed. Refresh Visualization and try again.",
            )
            return
        self._clear_saliency_render_cache()
        if current_widget is self.tab_spectro:
            self.tab_spectro.update_plot(
                typed_render_publication,
                absolute,
                display_normalized=normalize,
                selected_label_key=self.saliency_class_combo.currentData(),
                display_mode=str(self.saliency_view_mode.currentData() or "all"),
            )
            self._publish_saliency_render_identity(
                self.tab_spectro,
                typed_render_publication,
            )
            self._bind_native_render_terminal(
                self.tab_spectro,
                typed_render_publication,
                display_key=display_key,
            )
        elif current_widget in {self.tab_map, self.tab_topo}:
            if current_widget is self.tab_map:
                target_widget = self.tab_map
            else:
                target_widget = self.tab_topo
            target_widget.update_plot(
                typed_render_publication,
                absolute,
                selected_label_key=self.saliency_class_combo.currentData(),
                display_mode=str(self.saliency_view_mode.currentData() or "all"),
            )
            self._publish_saliency_render_identity(
                current_widget,
                typed_render_publication,
            )
            self._bind_native_render_terminal(
                current_widget,
                typed_render_publication,
                display_key=display_key,
            )
        elif current_widget is self.tab_3d:
            self.tab_3d.update_plot(typed_render_publication, absolute)
            self._publish_saliency_render_identity(
                self.tab_3d,
                typed_render_publication,
            )
            self._bind_native_render_terminal(
                self.tab_3d,
                typed_render_publication,
                display_key=display_key,
            )

    def _sync_saliency_class_controls(
        self,
        coverage: SaliencyMethodCoverageSnapshot,
    ) -> None:
        """Project one visible scope selector using backend class keys."""
        previous = self.saliency_combo.currentData()
        with (
            QSignalBlocker(self.saliency_class_combo),
            QSignalBlocker(self.saliency_combo),
        ):
            self.saliency_class_combo.clear()
            self.saliency_combo.clear()
            self.saliency_combo.addItem("All classes", None)
            for item in coverage.classes:
                if item.available:
                    self.saliency_class_combo.addItem(item.display_name, item.store_key)
                    self.saliency_combo.addItem(item.display_name, item.store_key)
            if self.saliency_class_combo.count() > 0:
                index = self.saliency_class_combo.findData(previous)
                self.saliency_class_combo.setCurrentIndex(max(index, 0))
            selected = self.saliency_combo.findData(previous)
            if (
                selected <= 0
                and hasattr(self, "tabs")
                and self.tabs.currentWidget() is getattr(self, "tab_3d", None)
            ):
                selected = next(
                    (
                        index
                        for index in range(1, self.saliency_combo.count())
                        if self.saliency_combo.itemData(index) is not None
                    ),
                    selected,
                )
            self.saliency_combo.setCurrentIndex(max(selected, 0))
        class_key = self.saliency_combo.currentData()
        with QSignalBlocker(self.saliency_view_mode):
            self.saliency_view_mode.setCurrentIndex(
                self.saliency_view_mode.findData(
                    "all" if class_key is None else "single"
                )
            )
        self._refresh_sidebar_view_controls()

    def _on_saliency_combo_changed(self, _index: int) -> None:
        """Project the selected scope once; renderers never own a second selector."""
        class_key = self.saliency_combo.currentData()
        with (
            QSignalBlocker(self.saliency_view_mode),
            QSignalBlocker(self.saliency_class_combo),
        ):
            self.saliency_view_mode.setCurrentIndex(
                self.saliency_view_mode.findData(
                    "all" if class_key is None else "single"
                )
            )
            if class_key is not None:
                index = self.saliency_class_combo.findData(class_key)
                if index >= 0:
                    self.saliency_class_combo.setCurrentIndex(index)
        self._refresh_sidebar_view_controls()
        self.on_update()

    def _open_saliency_class_detail(self, class_key: object) -> None:
        """Turn an overview tile activation into an exact-key detailed view."""
        index = self.saliency_combo.findData(class_key)
        if index < 0:
            return
        self.saliency_combo.setCurrentIndex(index)

    def _refresh_sidebar_view_controls(self) -> None:
        """Synchronize contextual view actions after selection or scene changes."""
        if hasattr(self, "sidebar"):
            self.sidebar.refresh_view_controls()

    def _saliency_render_publication(
        self,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication | None:
        """Return a publication prepared by the background render worker."""
        raw_request = replace(request, normalize=False)
        if self._saliency_render_cache_request != raw_request:
            return None

        raw_publication = self._saliency_render_cache.get(False)
        if not isinstance(raw_publication, SaliencyRenderPublication):
            return None

        if not request.normalize:
            return raw_publication
        normalized_publication = self._saliency_render_cache.get(True)
        return (
            normalized_publication
            if isinstance(normalized_publication, SaliencyRenderPublication)
            else None
        )

    def _saliency_render_is_cached(self, request: SaliencyRenderRequest) -> bool:
        raw_request = replace(request, normalize=False)
        if self._saliency_render_cache_request != raw_request:
            return False
        return False in self._saliency_render_cache and (
            not request.normalize or True in self._saliency_render_cache
        )

    def _request_saliency_render(self, task: _SaliencyRenderTask) -> None:
        if self._native_render_shutdown_requested:
            return
        worker = self._saliency_render_worker
        # Ownership lasts until the queued ``finished`` callback runs.  The
        # Python thread may already have exited while Qt still has result and
        # finished signals queued, so replacing it based on ``is_alive`` would
        # lose the terminal callback and can publish stale work.
        if worker is not None:
            if task == self._saliency_render_active_task:
                self._saliency_render_pending_task = (
                    task if self._saliency_render_result_seen else None
                )
            else:
                self._saliency_render_pending_task = task
            return
        runtime = self._query_port
        if runtime is None:
            self._set_saliency_render_status(self.tabs.currentWidget(), "failed")
            self._show_widget_error(
                self.tabs.currentWidget(),
                _VISUALIZATION_LOAD_FAILED_MESSAGE,
            )
            return
        operation = begin_saliency_render_operation(
            self,
            replace(task.request, normalize=False),
            runtime=cast("ApplicationUiRuntime", runtime),
        )
        if operation is None:
            self._set_saliency_render_status(self.tabs.currentWidget(), "failed")
            return
        task = replace(task, operation_id=operation.operation_id)
        self._saliency_render_active_task = task
        self._set_saliency_render_status(
            self.tabs.currentWidget(),
            "running",
            operation_id=task.operation_id,
        )
        self._saliency_operation_presenter.bind(
            task.operation_id,
            stage="Queued saliency render",
        )
        self._saliency_render_pending_task = None
        self._saliency_render_result_seen = False
        worker = PythonThreadWorker(
            self._load_saliency_render,
            runtime,
            task,
            name="xbrainlab-saliency-publication",
        )
        self._saliency_render_worker = worker
        worker.signals.result.connect(
            lambda result, owned_worker=worker: self._on_saliency_render_ready(
                owned_worker,
                result,
            )
        )
        worker.signals.error.connect(
            lambda error, owned_worker=worker: self._on_saliency_render_error(
                owned_worker,
                error,
            )
        )
        worker.signals.finished.connect(
            lambda owned_worker=worker: self._on_saliency_render_finished(owned_worker)
        )
        try:
            worker.start()
        except Exception:
            logger.error("Saliency render worker could not start.", exc_info=True)
            failure_message = "Saliency render worker could not start."
            try:
                terminalized = self._finish_render_operation(
                    task.operation_id,
                    "failed",
                    failure_message,
                )
            except Exception:
                logger.error(
                    "Saliency render startup failure could not publish terminal state.",
                    exc_info=True,
                )
                terminalized = False
            if not terminalized:
                fail_application_operation(
                    self,
                    task.operation_id,
                    message=failure_message,
                    runtime=cast("ApplicationUiRuntime", runtime),
                )
            self._saliency_render_worker = None
            self._saliency_render_active_task = None
            self._saliency_render_result_seen = False
            self._saliency_operation_presenter.refresh()
            self._set_saliency_render_status(
                self.tabs.currentWidget(),
                "failed",
                operation_id=task.operation_id,
            )
            self._show_widget_error(
                self.tabs.currentWidget(),
                _VISUALIZATION_LOAD_FAILED_MESSAGE,
            )

    @staticmethod
    def _load_saliency_render(
        runtime,
        task: _SaliencyRenderTask,
    ):
        raw_request = replace(task.request, normalize=False)
        try:
            variants = prepare_saliency_render_variants_operation(
                None,
                task.operation_id,
                raw_request,
                include_normalized=task.needs_normalized_variant,
                runtime=runtime,
            )
        except PreconditionError as error:
            if error.diagnostics.get("saliency_render_stale") is not True:
                raise
            return task, error, None
        if variants is None:
            raise RuntimeError("Saliency render publication is unavailable")
        raw_publication, normalized_publication = variants
        if not isinstance(raw_publication, SaliencyRenderPublication):
            raise RuntimeError("Saliency render publication is unavailable")
        verified_raw_publication = cast(
            SaliencyRenderPublication,
            raw_publication,
        )
        return task, verified_raw_publication, normalized_publication

    @staticmethod
    def _saliency_tasks_share_lineage(
        first: _SaliencyRenderTask,
        second: _SaliencyRenderTask,
    ) -> bool:
        return replace(first.request, normalize=False) == replace(
            second.request,
            normalize=False,
        )

    def _current_saliency_render_task(self) -> _SaliencyRenderTask | None:
        publication = self._application_view_publication
        run = self.run_combo.currentData()
        if (
            publication is None
            or not publication.usable
            or not isinstance(run, (SaliencyRunIdentity, SaliencyCrossFoldIdentity))
        ):
            return None
        normalize = self.normalize_check.isChecked()
        request = SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=run,
            method=self.method_combo.currentText(),
            normalize=(
                False if self.tabs.currentWidget() is self.tab_spectro else normalize
            ),
            view=self._saliency_render_view(self.tabs.currentWidget()),
        )
        return _SaliencyRenderTask(
            request=request,
            needs_normalized_variant=request.normalize,
        )

    def _saliency_render_view(self, widget: QWidget | None) -> SaliencyRenderView:
        if widget is self.tab_topo:
            return "topographic_map"
        if widget is self.tab_3d:
            return "three_dimensional"
        return "channel_time"

    def _on_saliency_render_ready(
        self,
        worker: PythonThreadWorker,
        result: object,
    ) -> None:
        if self._saliency_render_worker is not worker:
            return
        active_task = self._saliency_render_active_task
        if self._native_render_shutdown_requested:
            if active_task is not None and active_task.operation_id:
                self._finish_render_operation(
                    active_task.operation_id,
                    "cancelled",
                )
            return
        self._saliency_render_result_seen = True
        if (
            isinstance(result, tuple)
            and len(result) == 3
            and isinstance(result[0], _SaliencyRenderTask)
            and result[0] == active_task
            and isinstance(result[1], PreconditionError)
            and result[1].diagnostics.get("saliency_render_stale") is True
        ):
            self._on_saliency_render_error(worker, (type(result[1]), result[1], ""))
            return
        if (
            not isinstance(result, tuple)
            or len(result) != 3
            or not isinstance(result[0], _SaliencyRenderTask)
            or not isinstance(result[1], SaliencyRenderPublication)
        ):
            if active_task is not None and active_task.operation_id:
                self._finish_render_operation(
                    active_task.operation_id,
                    "failed",
                    "Saliency render worker returned an invalid result.",
                )
            self._show_widget_error(
                self.tabs.currentWidget(),
                _VISUALIZATION_LOAD_FAILED_MESSAGE,
            )
            return
        task, raw_publication, normalized_publication = result
        raw_request = replace(task.request, normalize=False)
        normalized_matches = (
            not task.needs_normalized_variant
            or self._render_publication_matches_request(
                normalized_publication,
                replace(raw_request, normalize=True),
            )
        )
        if (
            not self._render_publication_matches_request(
                raw_publication,
                raw_request,
            )
            or not normalized_matches
        ):
            self._finish_render_operation(
                task.operation_id,
                "failed",
                "Saliency render publication identity changed.",
            )
            self._application_summary_dirty = True
            self._clear_application_view_publication(
                invalidate_render_publications=True,
            )
            self._show_widget_message(
                self.tabs.currentWidget(),
                "Visualization results changed. Refresh Visualization and try again.",
            )
            return
        current_task = self._current_saliency_render_task()
        if current_task is None or not self._saliency_tasks_share_lineage(
            task,
            current_task,
        ):
            self._finish_render_operation(task.operation_id, "cancelled")
            return
        self._clear_saliency_render_cache()
        self._saliency_render_cache_request = raw_publication.request
        self._saliency_render_cache[False] = raw_publication
        if isinstance(normalized_publication, SaliencyRenderPublication):
            self._saliency_render_cache[True] = normalized_publication
        # The active result is now accepted into the exact-lineage cache. A
        # synchronous ``on_update`` may request the same task while the worker's
        # queued ``finished`` signal still owns cleanup; that is not a discarded
        # result and must not schedule a duplicate backend publication.
        self._saliency_render_result_seen = False
        self.on_update()

    def _on_saliency_render_error(
        self,
        worker: PythonThreadWorker,
        error: tuple,
    ) -> None:
        if self._saliency_render_worker is not worker:
            return
        self._saliency_render_result_seen = True
        task = self._saliency_render_active_task
        if self._native_render_shutdown_requested:
            if task is not None and task.operation_id:
                self._finish_render_operation(task.operation_id, "cancelled")
            return
        current = self._current_saliency_render_task()
        if task is None:
            return
        if current is None or not self._saliency_tasks_share_lineage(task, current):
            self._finish_render_operation(task.operation_id, "cancelled")
            return
        detail = error[1] if len(error) > 1 else error
        if (
            isinstance(detail, PreconditionError)
            and detail.diagnostics.get("saliency_render_stale") is True
        ):
            self._finish_render_operation(task.operation_id, "cancelled")
            self._set_saliency_render_status(self.tabs.currentWidget(), "cancelled")
            self._show_widget_message(
                self.tabs.currentWidget(),
                "Visualization results changed. Refresh Visualization and try again.",
            )
        else:
            logger.error("Saliency render publication failed: %s", detail)
            self._finish_render_operation(task.operation_id, "failed", str(detail))
            self._set_saliency_render_status(self.tabs.currentWidget(), "failed")
            self._show_widget_error(
                self.tabs.currentWidget(),
                _VISUALIZATION_LOAD_FAILED_MESSAGE,
            )
        if self._saliency_compute_awaits_current_render(
            task.request.publication_generation
        ):
            self._release_saliency_compute_after_render()
            self._hide_saliency_action_bar()

    def _on_saliency_render_finished(self, worker: PythonThreadWorker) -> None:
        if self._saliency_render_worker is not worker:
            return
        active_task = self._saliency_render_active_task
        self._saliency_render_worker = None
        self._saliency_render_active_task = None
        self._saliency_render_result_seen = False
        pending = self._saliency_render_pending_task
        self._saliency_render_pending_task = None
        if (
            active_task is not None
            and active_task.operation_id
            and not any(
                binding[2] == active_task.operation_id
                for binding in self._native_render_bindings.values()
            )
        ):
            self._finish_render_operation(
                active_task.operation_id,
                "cancelled",
            )
        if pending is not None and not self._native_render_shutdown_requested:
            self._request_saliency_render(pending)

    @staticmethod
    def _render_publication_matches_request(
        publication: object,
        request: SaliencyRenderRequest,
    ) -> bool:
        if not isinstance(publication, SaliencyRenderPublication):
            return False
        typed_publication = cast(SaliencyRenderPublication, publication)
        return (
            typed_publication.request == request
            and typed_publication.generation == request.publication_generation
            and typed_publication.data.method == request.method
            and typed_publication.data.normalized == request.normalize
        )

    def _clear_saliency_render_cache(self) -> None:
        """Release at most two display variants for the previous selection."""
        self._saliency_render_cache_request = None
        self._saliency_render_cache.clear()

    @staticmethod
    def _publish_saliency_view_state(
        current_widget,
        *,
        coverage: SaliencyMethodCoverageSnapshot | None,
        automatic_status: PostTrainingSaliencyStatus,
    ) -> None:
        """Inject immutable Application publication data into the active view."""
        set_coverage = getattr(current_widget, "set_saliency_coverage", None)
        if callable(set_coverage):
            set_coverage(coverage)
        set_automatic_status = getattr(
            current_widget,
            "set_post_training_saliency_status",
            None,
        )
        if callable(set_automatic_status):
            set_automatic_status(automatic_status)

    def compute_saliency(self) -> InteractionOutcome:
        """Start Compute Saliency using the current reviewed panel selection."""
        return self._compute_saliency_from_action_bar()

    def _compute_saliency_from_action_bar(self) -> InteractionOutcome:
        """Compute saliency for the current run using a product-friendly default."""
        if self._training_is_running():
            return InteractionOutcome.blocked(
                "Saliency can be computed after training finishes."
            )
        if self._saliency_compute_in_progress:
            return InteractionOutcome.blocked(
                "Saliency computation is already running."
            )
        current_widget = self.tabs.currentWidget() if hasattr(self, "tabs") else None
        if self._saliency_settings_review_required:
            self._require_saliency_settings_review(
                self._saliency_settings_review_detail
                or _SALIENCY_RESULTS_CHANGED_DETAIL,
                current_widget=current_widget,
            )
            return InteractionOutcome.blocked(_SALIENCY_SETTINGS_REVIEW_TITLE)

        current_target = self._current_saliency_settings_target()
        if current_target is None:
            self._require_saliency_settings_review(
                _SALIENCY_RESULTS_CHANGED_DETAIL,
                current_widget=current_widget,
            )
            return InteractionOutcome.blocked(_SALIENCY_SETTINGS_REVIEW_TITLE)
        if self._pending_saliency_params is not None and (
            self._pending_saliency_target is None
            or self._pending_saliency_target.publication_generation
            != current_target.publication_generation
        ):
            self._require_saliency_settings_review(
                _SALIENCY_RESULTS_CHANGED_DETAIL,
                current_widget=current_widget,
            )
            return InteractionOutcome.blocked(_SALIENCY_SETTINGS_REVIEW_TITLE)

        method_name = self._saliency_compute_method_name()
        params = self._effective_saliency_params(method_name)
        methods = params.get("methods")
        methods_key = tuple(methods) if isinstance(methods, (list, tuple, set)) else ()
        started = self._start_saliency_compute(
            params=params,
            method_name=method_name,
            current_widget=current_widget,
            attempt_key=(
                "manual",
                current_target.publication_generation,
                method_name,
                methods_key,
            ),
            expected_publication_generation=current_target.publication_generation,
        )
        if not started:
            self._set_saliency_action_busy(False)
            if not self._saliency_settings_review_required:
                show_status_message(self, _SALIENCY_COMPUTE_START_FAILED_MESSAGE)
                return InteractionOutcome.failed(_SALIENCY_COMPUTE_START_FAILED_MESSAGE)
            return InteractionOutcome.blocked(_SALIENCY_SETTINGS_REVIEW_TITLE)
        return InteractionOutcome.accepted("Saliency computation started.")

    def _open_saliency_settings(self) -> None:
        sidebar = getattr(self, "sidebar", None)
        set_saliency = getattr(sidebar, "set_saliency", None)
        if callable(set_saliency):
            set_saliency()

    def saliency_settings_target(
        self,
    ) -> (
        tuple[
            int,
            SaliencyRunIdentity | SaliencyCrossFoldIdentity,
            str,
        ]
        | None
    ):
        """Return the immutable publication/run/model identity visible to Settings."""
        target = self._current_saliency_settings_target()
        if target is None:
            return None
        return (
            target.publication_generation,
            target.run_identity,
            target.model_name,
        )

    def stage_saliency_params(
        self,
        params: dict[str, object],
        *,
        publication_generation: int | None = None,
        run_identity: SaliencyRunIdentity | SaliencyCrossFoldIdentity | None = None,
        model_name: str | None = None,
    ) -> bool:
        """Keep dialog choices local and bind them to the reviewed result."""
        if not isinstance(params, dict) or not params:
            raise ValueError("Saliency settings must be a non-empty dictionary.")
        provided_target = (
            publication_generation is not None
            or run_identity is not None
            or model_name is not None
        )
        if provided_target and (
            publication_generation is None
            or not isinstance(
                run_identity,
                (SaliencyRunIdentity, SaliencyCrossFoldIdentity),
            )
            or model_name is None
        ):
            raise ValueError(
                "Saliency settings require publication, run, and model identity."
            )
        current_target = self._current_saliency_settings_target()
        reviewed_target = (
            _SaliencySettingsTarget(
                publication_generation=publication_generation,
                run_identity=run_identity,
                model_name=str(model_name),
            )
            if provided_target
            and publication_generation is not None
            and isinstance(
                run_identity,
                (SaliencyRunIdentity, SaliencyCrossFoldIdentity),
            )
            and model_name is not None
            else current_target
        )
        if (
            current_target is None
            or reviewed_target is None
            or reviewed_target.publication_generation
            != current_target.publication_generation
        ):
            self._require_saliency_settings_review(
                _SALIENCY_RESULTS_CHANGED_DETAIL,
                current_widget=(
                    self.tabs.currentWidget() if hasattr(self, "tabs") else None
                ),
            )
            return False
        self._pending_saliency_params = dict(params)
        self._pending_saliency_target = reviewed_target
        self._saliency_settings_review_required = False
        self._saliency_settings_review_detail = ""
        self._saliency_compute_attempted.clear()
        selected_methods = selected_saliency_methods_from_params(params)
        selected_method = next(
            (method for method in all_saliency_methods if method in selected_methods),
            (
                self.method_combo.currentText()
                if self.method_combo.currentText() in all_saliency_methods
                else "Gradient"
            ),
        )
        self._pending_saliency_method = selected_method
        self._show_saliency_action_bar(
            selected_method,
            self._current_saliency_coverage.get(selected_method),
        )
        return True

    @staticmethod
    def _coverage_requires_recompute(
        coverage: SaliencyMethodCoverageSnapshot,
    ) -> bool:
        """Keep invalid stored output distinct from a never-computed method."""
        return (coverage.available and not coverage.complete) or any(
            item.store_key is not None and item.reason is not None
            for item in coverage.classes
        )

    def _show_saliency_action_bar(
        self,
        method_name: str | None = None,
        coverage: SaliencyMethodCoverageSnapshot | None = None,
    ) -> None:
        if not hasattr(self, "saliency_action_bar"):
            return
        method_name = method_name or "Gradient"
        if self._training_is_running():
            self._saliency_action_requires_recompute = False
            self.saliency_action_title.setText("Training in progress")
            self.saliency_action_detail.setText(
                "Saliency can be computed after training finishes."
            )
            self._set_saliency_action_busy(False)
            self.saliency_action_bar.setVisible(True)
            return
        if self._saliency_settings_review_required:
            self._saliency_action_requires_recompute = False
            self.saliency_action_title.setText(_SALIENCY_SETTINGS_REVIEW_TITLE)
            self.saliency_action_detail.setText(
                self._saliency_settings_review_detail
                or _SALIENCY_RESULTS_CHANGED_DETAIL
            )
            self._set_saliency_action_busy(False)
            self.saliency_action_bar.setVisible(True)
            return
        self._saliency_action_requires_recompute = bool(
            self._pending_saliency_params is not None
            or (coverage is not None and self._coverage_requires_recompute(coverage))
        )
        if self._saliency_compute_in_progress:
            self.saliency_action_title.setText("Computing saliency")
            status = self._post_training_saliency_status()
            methods = (
                status.methods
                if self._saliency_status_matches_active_operation(status)
                else selected_saliency_methods_from_params(
                    self._effective_saliency_params(method_name)
                )
            )
            detail = (
                "Computing "
                + ", ".join(
                    method for method in all_saliency_methods if method in methods
                )
                + " in the background."
            )
        elif self._pending_saliency_params is not None:
            self.saliency_action_title.setText("Saliency settings ready")
            detail = "Use Recompute Saliency to apply the selected settings."
        elif self._saliency_action_requires_recompute and coverage is not None:
            self.saliency_action_title.setText("Saliency is incomplete")
            detail = self._incomplete_saliency_message(coverage)
        elif is_recommended_saliency_method(method_name):
            self.saliency_action_title.setText("Saliency not computed yet")
            detail = "Use Compute Saliency to prepare Gradient + Gradient * Input."
        else:
            self.saliency_action_title.setText("Advanced saliency not computed")
            detail = f"{method_name} uses default noise settings. Adjust in Settings."
        self.saliency_action_detail.setText(detail)
        params = self._effective_saliency_params(method_name)
        self.compute_saliency_btn.setProperty("saliencyMethod", method_name)
        self.compute_saliency_btn.setProperty("saliencyParameters", params)
        self.compute_saliency_btn.setProperty(
            "saliencyNormalize",
            bool(
                self.normalize_check.isChecked()
                if hasattr(self, "normalize_check")
                else False
            ),
        )
        self._set_saliency_action_busy(self._saliency_compute_in_progress)
        self.saliency_action_bar.setVisible(True)

    def _hide_saliency_action_bar(self) -> None:
        if not hasattr(self, "saliency_action_bar"):
            return
        if (
            self._saliency_compute_in_progress
            or self._pending_saliency_params is not None
        ):
            return
        self.saliency_action_bar.setVisible(False)
        self._saliency_action_requires_recompute = False
        self._set_saliency_action_busy(False)

    def _set_saliency_action_busy(self, busy: bool) -> None:
        if not hasattr(self, "compute_saliency_btn"):
            return
        training_is_running = self._training_is_running()
        self.compute_saliency_btn.setVisible(not training_is_running)
        self.compute_saliency_btn.setEnabled(not busy and not training_is_running)
        self.compute_saliency_btn.setText(
            "Computing..."
            if busy
            else "Recompute Saliency"
            if self._saliency_action_requires_recompute
            else "Compute Saliency"
        )
        self._sync_saliency_busy_controls()

    def _training_is_running(self) -> bool:
        """Read training liveness only from the accepted Application publication."""
        publication = self._application_view_publication
        if publication is None or not publication.usable:
            return False
        state = publication.state
        return bool(state.training.is_running or state.active_training.is_running)

    def update_info(self):
        """Update the Sidebar Info Panel and refresh combos."""
        if self._saliency_summary_dirty or self.last_saliency_query is None:
            publication = self._application_view_publication
            action_port = self._action_port
            self.last_saliency_query = (
                execute_application_command(
                    self,
                    SaliencyCommand(),
                    refresh=False,
                    expected_publication_generation=(
                        publication.generation if publication is not None else None
                    ),
                    runtime=cast("ApplicationUiRuntime", action_port),
                )
                if action_port is not None and publication is not None
                else None
            )
            if self.last_saliency_query is not None:
                self._refresh_application_publication()
            self._saliency_summary_dirty = False

        if hasattr(self, "sidebar"):
            self.sidebar.update_info()

        # Refresh combos as new training might have finished
        self.refresh_combos()

    def update_panel(self):
        """Refresh Visualization and commit a direct render only after success."""
        self._update_panel_content()
        if self._application_render_ledger.render_in_progress or (
            self._application_summary_dirty and self.last_application_query is None
        ):
            return
        publication = self._application_view_publication
        if publication is not None:
            self._application_render_ledger.record_rendered(publication)

    def _update_panel_content(self):
        """Called when switching to this panel."""
        if self._application_view_publication is None:
            self._refresh_application_publication()
        self.update_info()
        if self._application_summary_dirty and self.last_application_query is None:
            return
        # Explicitly trigger update to ensure plot is shown even if signals were
        # suppressed
        self.on_update()

    def mark_refresh_dirty(self) -> None:
        """Invalidate cached ApplicationService visualization summaries."""
        self._mark_application_summaries_dirty(invalidate_render_publications=True)

    def _mark_application_summaries_dirty(
        self,
        *,
        invalidate_render_publications: bool = False,
    ) -> None:
        """Invalidate derived summaries without replacing publication truth."""
        if invalidate_render_publications:
            self._invalidate_view_render_publications()
        self._application_summary_dirty = True
        self._saliency_summary_dirty = True
        self._saliency_compute_attempted.clear()

    def cleanup(self) -> None:
        """Cancel queued renders and release the publication subscription."""
        self._active_application_summary_request = None
        self.begin_native_render_shutdown()
        self._clear_saliency_render_cache()
        self._application_render_ledger.cleanup()
        super().cleanup()

    def event(self, event):
        """Finalize child native widgets before deferred panel destruction."""
        if event.type() is QEvent.Type.DeferredDelete:
            self.finalize_native_render_resources()
        return super().event(event)

    def closeEvent(self, event):  # noqa: N802
        """Finalize child native widgets through the shared idempotent path."""
        self.cleanup()
        self.finalize_native_render_resources()
        super().closeEvent(event)

    def _start_saliency_compute(
        self,
        *,
        params: dict[str, object],
        method_name: str,
        current_widget,
        attempt_key: tuple[object, ...],
        expected_publication_generation: int | None = None,
    ) -> bool:
        """Run configured saliency computation in the ApplicationService worker."""
        if expected_publication_generation is not None:
            current_target = self._current_saliency_settings_target()
            if (
                current_target is None
                or expected_publication_generation
                != current_target.publication_generation
            ):
                self._require_saliency_settings_review(
                    _SALIENCY_RESULTS_CHANGED_DETAIL,
                    current_widget=current_widget,
                    attempt_key=attempt_key,
                )
                return False
        if self._saliency_compute_in_progress:
            if current_widget is not None:
                self._show_widget_message(current_widget, "Computing saliency...")
            return True

        if attempt_key in self._saliency_compute_attempted:
            return False

        self._saliency_compute_attempted.add(attempt_key)
        self._saliency_compute_in_progress = True
        current_status = self._post_training_saliency_status()
        self._active_saliency_minimum_generation = current_status.generation + 1
        self._active_saliency_generation = None
        self._show_saliency_action_bar(method_name)
        self._set_saliency_action_busy(True)
        if current_widget is not None:
            self._show_widget_message(current_widget, "Computing saliency...")
        show_status_message(self, "Computing saliency...")

        return self._dispatch_saliency_compute_command(
            params=params,
            method_name=method_name,
            current_widget=current_widget,
            attempt_key=attempt_key,
            expected_publication_generation=expected_publication_generation,
        )

    def _dispatch_saliency_compute_command(
        self,
        *,
        params: dict[str, object],
        method_name: str,
        current_widget,
        attempt_key: tuple[object, ...],
        expected_publication_generation: int | None,
        resource_preflight_confirmed: bool = False,
        resource_preflight_token: str | None = None,
        resource_confirmation_replayed: bool = False,
    ) -> bool:
        """Dispatch one initial or backend-receipt-authorized saliency command."""
        operation_id: str | None = None

        def bind_operation(started_id: str) -> None:
            nonlocal operation_id
            operation_id = started_id
            self._bind_saliency_operation(started_id)

        def handle_result(result: CommandResult) -> InteractionOutcome | None:
            if (
                operation_id is not None
                and operation_id != self._active_saliency_operation_id
            ):
                return None
            return self._on_lazy_saliency_configured(
                result,
                attempt_key=attempt_key,
                current_widget=current_widget,
                params=params,
                method_name=method_name,
                expected_publication_generation=expected_publication_generation,
                resource_confirmation_replayed=resource_confirmation_replayed,
            )

        def handle_error(error: tuple) -> None:
            if (
                operation_id is not None
                and operation_id != self._active_saliency_operation_id
            ):
                return
            self._on_lazy_saliency_error(
                error,
                attempt_key=attempt_key,
                current_widget=current_widget,
            )

        try:
            started = execute_application_command_async(
                self,
                SaliencyCommand(
                    method=method_name,
                    params=dict(params),
                    resource_preflight_confirmed=resource_preflight_confirmed,
                    resource_preflight_token=resource_preflight_token,
                ),
                on_result=handle_result,
                on_error=handle_error,
                refresh=False,
                busy_target=self,
                runtime=cast("ApplicationUiRuntime", self._action_port),
                expected_publication_generation=expected_publication_generation,
                on_operation_started=bind_operation,
            )
        except Exception:
            logger.exception("Could not set up the saliency compute worker")
            self._finish_saliency_compute_failure(
                message=_SALIENCY_COMPUTE_START_FAILED_MESSAGE,
                attempt_key=attempt_key,
                current_widget=current_widget,
            )
            return False
        if not started:
            self._finish_saliency_compute_failure(
                message=_SALIENCY_COMPUTE_START_FAILED_MESSAGE,
                attempt_key=attempt_key,
                current_widget=current_widget,
            )
            return False
        return True

    def _bind_saliency_operation(self, operation_id: str) -> None:
        """Retain backend ownership for explicit cancel/close control."""
        if self._active_saliency_minimum_generation is None:
            current_status = self._post_training_saliency_status()
            self._active_saliency_minimum_generation = current_status.generation + 1
        self._active_saliency_operation_id = operation_id
        self.compute_saliency_btn.setProperty("operationId", operation_id)
        self.compute_saliency_btn.setProperty("operationPhase", "pending")
        self._saliency_operation_presenter.bind(
            operation_id,
            stage="Computing saliency",
        )
        self._set_saliency_render_status(
            self.tab_map,
            "computing",
            operation_id=operation_id,
        )
        self._set_saliency_render_status(
            self.tab_spectro,
            "computing",
            operation_id=operation_id,
        )

    def _on_saliency_operation_terminal(
        self,
        operation_id: str,
        phase: str,
    ) -> None:
        if phase not in {"cancelled", "failed"}:
            return
        if operation_id != self._active_saliency_operation_id:
            return
        self.compute_saliency_btn.setProperty("operationPhase", phase)
        for widget in (self.tab_map, self.tab_spectro):
            if str(widget.property("operationId") or "") == operation_id:
                self._set_saliency_render_status(widget, phase)
        self._settle_saliency_interaction(
            InteractionOutcome.cancelled("Saliency computation was cancelled.")
            if phase == "cancelled"
            else InteractionOutcome.failed(_SALIENCY_COMPUTE_FAILED_MESSAGE)
        )

    def _set_saliency_render_status(
        self,
        widget: QWidget | None,
        status: str,
        *,
        operation_id: str | None = None,
    ) -> None:
        """Expose lifecycle truth on the two required visible result views."""
        if widget is None or widget not in {self.tab_map, self.tab_spectro}:
            return
        if operation_id is not None:
            widget.setProperty("operationId", operation_id)
        publication = self._application_view_publication
        widget.setProperty(
            "publicationGeneration",
            publication.generation if publication is not None else None,
        )
        run_identity = self.run_combo.currentData()
        if isinstance(run_identity, SaliencyRunIdentity):
            plan_index = run_identity.plan.plan_index
            widget.setProperty("fold", plan_index)
            widget.setProperty(
                "runId",
                f"plan-{plan_index}:run-{run_identity.run_index}",
            )
        widget.setProperty("renderStatus", status)
        widget.setProperty("indeterminate", status in {"computing", "running"})
        widget.repaint()

    def _publish_saliency_render_identity(
        self,
        widget: QWidget,
        publication: SaliencyRenderPublication,
    ) -> None:
        """Publish only the immutable identity rendered by the visible view."""
        widget.setProperty("evaluationSplit", publication.data.source_split)
        widget.setProperty(
            "classLabels",
            [str(name) for _key, name in publication.data.class_map],
        )
        widget.setProperty(
            "classMapping",
            [
                {
                    "class_index": index,
                    "event_code": str(event_code),
                    "class_name": str(class_name),
                }
                for index, (event_code, class_name) in enumerate(
                    publication.data.class_map
                )
            ],
        )
        widget.setProperty(
            "eventLabels",
            [str(name) for name in publication.data.event_ids],
        )
        widget.setProperty("trainingGeneration", publication.training_generation)
        # SaliencyRenderPublisher accepts the DTO only across a stable captured
        # training boundary; expose that product truth beside the generation.
        widget.setProperty("trainingBoundaryStable", True)
        widget.setProperty(
            "splitSpecificationFingerprint",
            publication.split_specification_fingerprint or "",
        )
        widget.setProperty("splitEpochRevision", publication.split_epoch_revision or 0)
        producer_payloads = [
            identity.to_payload() for identity in publication.data.producer_identities
        ]
        widget.setProperty("producerIdentities", producer_payloads)
        widget.setProperty(
            "producerFingerprints",
            [str(payload["fingerprint"]) for payload in producer_payloads],
        )
        values = tuple(
            np.asarray(array) for array in publication.data.saliency_by_class.values()
        )
        sample_count = sum(int(array.size) for array in values)
        finite_count = sum(int(np.isfinite(array).sum()) for array in values)
        widget.setProperty(
            "saliencyNumericSummary",
            {
                "count": sample_count,
                "finite_count": finite_count,
                "nonfinite_count": sample_count - finite_count,
                "minimum": min(float(np.min(array)) for array in values),
                "maximum": max(float(np.max(array)) for array in values),
            },
        )

    def _bind_native_render_terminal(
        self,
        widget: QWidget,
        publication: SaliencyRenderPublication,
        *,
        display_key: tuple[object, ...],
    ) -> None:
        operation_id = str(publication.operation_id or "").strip()
        generation = getattr(widget, "active_render_generation", None)
        publication_generation = getattr(
            widget,
            "active_render_publication_generation",
            None,
        )
        if (
            not operation_id
            or not isinstance(generation, int)
            or publication_generation != publication.generation
        ):
            if operation_id:
                self._finish_render_operation(
                    operation_id,
                    "failed",
                    "Native saliency render was not scheduled.",
                )
            self._set_saliency_render_status(widget, "failed")
            return
        self._native_render_bindings[widget] = (
            generation,
            publication.generation,
            operation_id,
            publication,
            display_key,
        )
        self._set_saliency_render_status(
            widget,
            "running",
            operation_id=operation_id,
        )

    def _admit_native_render_commit(
        self,
        widget: QWidget,
        generation: int,
        publication_generation: int,
    ) -> bool:
        """Admit only the exact visible native request before canvas mutation."""
        binding = self._native_render_bindings.get(widget)
        if binding is None or binding[:2] != (generation, publication_generation):
            return False
        return enter_saliency_render_commit_operation(
            self,
            binding[2],
            runtime=cast("ApplicationUiRuntime", self._query_port),
        )

    def _on_native_render_terminal(
        self,
        widget: QWidget,
        generation: int,
        publication_generation: int,
        phase: str,
    ) -> None:
        binding = self._native_render_bindings.get(widget)
        if binding is None or binding[:2] != (generation, publication_generation):
            return
        self._native_render_bindings.pop(widget, None)
        operation_id = binding[2]
        self._finish_render_operation(operation_id, phase)
        self._set_saliency_render_status(
            widget,
            phase,
            operation_id=operation_id,
        )
        if not self._saliency_compute_awaits_current_render(publication_generation):
            return
        self._release_saliency_compute_after_render()
        self._hide_saliency_action_bar()
        if phase == "completed":
            show_status_message(self, "Saliency ready")
        elif phase == "cancelled":
            show_status_message(self, "Saliency rendering cancelled.")
        else:
            show_status_message(self, _VISUALIZATION_LOAD_FAILED_MESSAGE)

    def _cancel_native_render_binding(self, widget: QWidget | None) -> bool:
        if widget is None:
            return True
        binding = self._native_render_bindings.get(widget)
        if binding is None:
            return True
        operation_id = binding[2]
        return self._cancel_owned_saliency_operation(operation_id)

    def _cancel_owned_saliency_operation(self, operation_id: str) -> bool:
        """Cancel registry ownership and the matching native worker together."""
        accepted = cancel_application_operation(
            self,
            operation_id,
            runtime=cast("ApplicationUiRuntime", self._action_port),
        )
        if not accepted:
            return False
        for widget, binding in tuple(self._native_render_bindings.items()):
            if binding[2] != operation_id:
                continue
            self._native_render_bindings.pop(widget, None)
            invalidate = getattr(widget, "invalidate_render_publication", None)
            if callable(invalidate):
                invalidate()
            self._finish_render_operation(operation_id, "cancelled")
            self._set_saliency_render_status(
                widget,
                "cancelled",
                operation_id=operation_id,
            )
            break
        return True

    def _finish_render_operation(
        self,
        operation_id: str,
        phase: str,
        message: str = "",
    ) -> bool:
        normalized_operation_id = str(operation_id or "").strip()
        if not normalized_operation_id:
            return False
        return finish_saliency_render_operation(
            self,
            normalized_operation_id,
            phase,
            message=message,
            runtime=cast("ApplicationUiRuntime", self._query_port),
        )

    def _on_lazy_saliency_configured(
        self,
        result: object,
        *,
        attempt_key: tuple[object, ...] | None = None,
        current_widget=None,
        params: dict[str, object] | None = None,
        method_name: str | None = None,
        expected_publication_generation: int | None = None,
        resource_confirmation_replayed: bool = False,
    ) -> InteractionOutcome:
        if not isinstance(result, CommandResult):
            self._finish_saliency_compute_failure(
                message=_SALIENCY_COMPUTE_INVALID_RESULT_MESSAGE,
                attempt_key=attempt_key,
                current_widget=current_widget,
            )
            return InteractionOutcome.failed(_SALIENCY_COMPUTE_INVALID_RESULT_MESSAGE)

        if result.ok and result.diagnostics.get("action") == "schedule":
            if self._active_saliency_operation_id is None:
                # A very small job can publish its terminal generation before
                # the queued command receipt reaches Qt. The terminal
                # publication already owns the render handoff; never
                # resurrect a stale compute operation from the older receipt.
                return InteractionOutcome.completed(result.message)
            schedule = result.diagnostics.get("post_training_saliency_schedule")
            status = schedule.get("status") if isinstance(schedule, dict) else None
            generation = status.get("generation") if isinstance(status, dict) else None
            minimum_generation = self._active_saliency_minimum_generation
            if (
                isinstance(generation, bool)
                or not isinstance(generation, int)
                or minimum_generation is None
                or generation < minimum_generation
            ):
                self._finish_saliency_compute_failure(
                    message=_SALIENCY_COMPUTE_INVALID_RESULT_MESSAGE,
                    attempt_key=attempt_key,
                    current_widget=current_widget,
                )
                return InteractionOutcome.failed(
                    _SALIENCY_COMPUTE_INVALID_RESULT_MESSAGE
                )
            self._active_saliency_generation = generation
            self._saliency_interaction_continuation = reserve_interaction_continuation()
            self.compute_saliency_btn.setProperty("operationPhase", "running")
            self._set_saliency_action_busy(True)
            show_status_message(self, "Computing saliency...")
            return InteractionOutcome.accepted(result.message)

        if result.failed:
            logger.error(
                "Saliency compute command failed: %s",
                result.error_message or result.message,
            )
            if is_stale_publication_result(result):
                self._require_saliency_settings_review(
                    _SALIENCY_RESULTS_CHANGED_DETAIL,
                    current_widget=current_widget,
                    attempt_key=attempt_key,
                )
                return InteractionOutcome.blocked(_SALIENCY_SETTINGS_REVIEW_TITLE)
            resource_preflight = self._saliency_resource_preflight_from_result(result)
            if (
                resource_preflight is not None
                and resource_preflight.risk_level == "blocking"
            ):
                message = resource_preflight.message or result.message
                self._finish_saliency_compute_failure(
                    message=message,
                    attempt_key=attempt_key,
                    current_widget=current_widget,
                )
                show_alert(
                    self,
                    severity=AlertSeverity.CRITICAL,
                    title=_SALIENCY_RESOURCE_DIALOG_TITLE,
                    message=message,
                )
                return InteractionOutcome.blocked(message)
            if result.error_type is ErrorType.CONFIRMATION_REQUIRED:
                return self._handle_saliency_resource_confirmation(
                    result,
                    resource_preflight=resource_preflight,
                    params=params,
                    method_name=method_name,
                    expected_publication_generation=(expected_publication_generation),
                    resource_confirmation_replayed=(resource_confirmation_replayed),
                    attempt_key=attempt_key,
                    current_widget=current_widget,
                )
            message = _SALIENCY_COMPUTE_FAILED_MESSAGE
            self._finish_saliency_compute_failure(
                message=message,
                attempt_key=attempt_key,
                current_widget=current_widget,
            )
            return InteractionOutcome.failed(message)
        self._saliency_compute_in_progress = False
        self._clear_active_saliency_operation()
        self._set_saliency_action_busy(False)
        self._settle_applied_saliency_settings()
        show_status_message(self, "Saliency ready")
        self._application_summary_dirty = True
        self._saliency_summary_dirty = True
        return InteractionOutcome.completed(result.message)

    @staticmethod
    def _saliency_resource_preflight_from_result(
        result: CommandResult,
    ) -> ResourcePreflightView | None:
        """Parse only the backend-owned resource-preflight wire contract."""
        try:
            return ResourcePreflightView.from_diagnostics(result.diagnostics)
        except ResourcePreflightContractError:
            logger.warning("Rejected malformed saliency resource-preflight result.")
            return None

    def _handle_saliency_resource_confirmation(
        self,
        result: CommandResult,
        *,
        resource_preflight: ResourcePreflightView | None,
        params: dict[str, object] | None,
        method_name: str | None,
        expected_publication_generation: int | None,
        resource_confirmation_replayed: bool,
        attempt_key: tuple[object, ...] | None,
        current_widget,
    ) -> InteractionOutcome:
        """Ask once, then replay only the exact backend-issued saliency receipt."""
        if resource_confirmation_replayed:
            self._finish_saliency_compute_failure(
                message=_SALIENCY_RESOURCE_RECEIPT_REJECTED_MESSAGE,
                attempt_key=attempt_key,
                current_widget=current_widget,
            )
            return InteractionOutcome.failed(
                _SALIENCY_RESOURCE_RECEIPT_REJECTED_MESSAGE
            )

        def invalid_outcome() -> InteractionOutcome:
            self._finish_saliency_compute_failure(
                message=_SALIENCY_RESOURCE_CONFIRMATION_INVALID_MESSAGE,
                attempt_key=attempt_key,
                current_widget=current_widget,
            )
            return InteractionOutcome.failed(
                _SALIENCY_RESOURCE_CONFIRMATION_INVALID_MESSAGE
            )

        if resource_preflight is None:
            return invalid_outcome()
        challenge = resource_preflight.challenge
        if (
            resource_preflight.risk_level not in {"warning", "unknown"}
            or not resource_preflight.requires_confirmation
            or challenge is None
            or challenge.command_name != "saliency"
            or not isinstance(params, dict)
            or not params
            or not isinstance(method_name, str)
            or not method_name.strip()
        ):
            return invalid_outcome()

        message = resource_preflight.message or result.message
        reply = ask_confirmation(
            self,
            severity=AlertSeverity.WARNING,
            title=_SALIENCY_RESOURCE_DIALOG_TITLE,
            message=f"{message}\n\nContinue computing saliency?",
            confirm_text="Continue",
            cancel_text="Cancel",
        )
        if not reply:
            self._finish_saliency_compute_cancelled(
                attempt_key=attempt_key,
                current_widget=current_widget,
            )
            return InteractionOutcome.cancelled(
                _SALIENCY_RESOURCE_CONFIRMATION_CANCELLED_MESSAGE
            )

        if attempt_key is None:
            self._finish_saliency_compute_failure(
                message=_SALIENCY_RESOURCE_CONFIRMATION_INVALID_MESSAGE,
                attempt_key=None,
                current_widget=current_widget,
            )
            return InteractionOutcome.failed(
                _SALIENCY_RESOURCE_CONFIRMATION_INVALID_MESSAGE
            )
        started = self._dispatch_saliency_compute_command(
            params=params,
            method_name=method_name,
            current_widget=current_widget,
            attempt_key=attempt_key,
            expected_publication_generation=expected_publication_generation,
            resource_preflight_confirmed=True,
            resource_preflight_token=challenge.challenge_id,
            resource_confirmation_replayed=True,
        )
        if not started:
            return InteractionOutcome.failed(_SALIENCY_COMPUTE_START_FAILED_MESSAGE)
        return InteractionOutcome.accepted(message)

    def _on_lazy_saliency_error(
        self,
        error: tuple,
        *,
        attempt_key: tuple[object, ...] | None = None,
        current_widget=None,
    ) -> None:
        diagnostic = error[1] if len(error) > 1 else error
        formatted_traceback = error[2] if len(error) > 2 else ""
        logger.error(
            "Saliency compute worker failed: %s\n%s",
            diagnostic,
            formatted_traceback,
        )
        self._finish_saliency_compute_failure(
            message=_SALIENCY_COMPUTE_FAILED_MESSAGE,
            attempt_key=attempt_key,
            current_widget=current_widget,
        )

    def _finish_saliency_compute_failure(
        self,
        *,
        message: str,
        attempt_key: tuple[object, ...] | None,
        current_widget,
    ) -> None:
        """Restore a retryable, visibly failed saliency action."""
        if hasattr(self, "compute_saliency_btn"):
            self.compute_saliency_btn.setProperty("operationPhase", "failed")
        self._saliency_compute_in_progress = False
        self._clear_active_saliency_operation()
        if attempt_key is None:
            self._saliency_compute_attempted.clear()
        else:
            self._saliency_compute_attempted.discard(attempt_key)
        self._saliency_summary_dirty = True
        if hasattr(self, "saliency_action_bar"):
            self.saliency_action_title.setText("Saliency compute failed")
            self.saliency_action_detail.setText(message)
            self.saliency_action_bar.setVisible(True)
        self._set_saliency_action_busy(False)
        if current_widget is not None:
            self._show_widget_error(current_widget, message)
        show_status_message(self, message)

    def _finish_saliency_compute_cancelled(
        self,
        *,
        attempt_key: tuple[object, ...] | None,
        current_widget,
    ) -> None:
        """Restore the retryable action without presenting cancellation as failure."""
        if hasattr(self, "compute_saliency_btn"):
            self.compute_saliency_btn.setProperty("operationPhase", "cancelled")
        self._saliency_compute_in_progress = False
        self._clear_active_saliency_operation()
        if attempt_key is None:
            self._saliency_compute_attempted.clear()
        else:
            self._saliency_compute_attempted.discard(attempt_key)
        if hasattr(self, "saliency_action_bar"):
            self.saliency_action_title.setText("Saliency compute cancelled")
            self.saliency_action_detail.setText(
                _SALIENCY_RESOURCE_CONFIRMATION_CANCELLED_MESSAGE
            )
            self.saliency_action_bar.setVisible(True)
        self._set_saliency_action_busy(False)
        if current_widget is not None:
            self._show_widget_message(
                current_widget,
                _SALIENCY_RESOURCE_CONFIRMATION_CANCELLED_MESSAGE,
            )
        show_status_message(
            self,
            _SALIENCY_RESOURCE_CONFIRMATION_CANCELLED_MESSAGE,
        )

    def _current_saliency_settings_target(
        self,
    ) -> _SaliencySettingsTarget | None:
        """Return the selected result identity from one accepted publication."""
        publication = self._application_view_publication
        run_identity = self.run_combo.currentData()
        if (
            publication is None
            or not publication.usable
            or not isinstance(
                run_identity,
                (SaliencyRunIdentity, SaliencyCrossFoldIdentity),
            )
        ):
            return None
        members = (
            run_identity.members
            if isinstance(run_identity, SaliencyCrossFoldIdentity)
            else (run_identity,)
        )
        if isinstance(run_identity, SaliencyCrossFoldIdentity) and (
            run_identity not in self._known_evaluation_cross_fold_identities
        ):
            return None
        run_coverages = tuple(
            self._run_coverage_for_identity(member) for member in members
        )
        if any(coverage is None for coverage in run_coverages):
            return None
        model_names = sorted(
            {
                str(coverage.model_name).strip()
                for coverage in run_coverages
                if coverage is not None and str(coverage.model_name or "").strip()
            }
        )
        model_name = (
            model_names[0]
            if len(model_names) == 1
            else " + ".join(model_names)
            if model_names
            else publication.state.training.model_name or ""
        )
        return _SaliencySettingsTarget(
            publication_generation=publication.generation,
            run_identity=run_identity,
            model_name=str(model_name),
        )

    def _settle_applied_saliency_settings(self) -> None:
        """Release settings after their matching compute succeeds."""
        self._pending_saliency_params = None
        self._pending_saliency_target = None
        self._pending_saliency_method = None
        self._saliency_settings_review_required = False
        self._saliency_settings_review_detail = ""

    def _require_saliency_settings_review(
        self,
        detail: str,
        *,
        current_widget=None,
        attempt_key: tuple[object, ...] | None = None,
    ) -> None:
        """Discard stale settings and expose one actionable recovery state."""
        self._saliency_compute_in_progress = False
        self._clear_active_saliency_operation()
        self._pending_saliency_params = None
        self._pending_saliency_target = None
        self._pending_saliency_method = None
        self._saliency_settings_review_required = True
        self._saliency_settings_review_detail = detail
        self._saliency_summary_dirty = True
        if attempt_key is None:
            self._saliency_compute_attempted.clear()
        else:
            self._saliency_compute_attempted.discard(attempt_key)
        self._show_saliency_action_bar()
        if current_widget is not None:
            self._show_widget_message(
                current_widget,
                _SALIENCY_SETTINGS_REVIEW_TITLE,
            )
        show_status_message(self, _SALIENCY_SETTINGS_REVIEW_TITLE)

    def _published_coverage_for_selection(
        self,
    ) -> dict[str, SaliencyMethodCoverageSnapshot] | None:
        """Read selected-run coverage only from the Application publication."""
        selection = self.run_combo.currentData()
        if isinstance(selection, SaliencyCrossFoldIdentity):
            choice = self._cross_fold_choice_by_identity.get(selection)
            if choice is None:
                return None
            return {
                method: SaliencyMethodCoverageSnapshot(
                    method=method,
                    available=True,
                    complete=True,
                    classes=list(choice.classes),
                )
                for method in choice.methods
            }
        run_coverage = self._selected_run_coverage()
        if run_coverage is None:
            return None
        return {item.method: item for item in run_coverage.methods}

    def _selected_run_coverage(self) -> SaliencyRunCoverageSnapshot | None:
        """Return selected result coverage from the accepted publication only."""
        run_identity = self.run_combo.currentData()
        if not isinstance(run_identity, SaliencyRunIdentity):
            return None
        return self._run_coverage_for_identity(run_identity)

    def _run_coverage_for_identity(
        self,
        run_identity: SaliencyRunIdentity,
    ) -> SaliencyRunCoverageSnapshot | None:
        """Return one exact run coverage from the accepted publication."""
        publication = self._application_view_publication
        if publication is None or not publication.usable:
            return None
        for run_coverage in publication.state.visualization.saliency_coverage:
            if (
                run_coverage.plan_index == run_identity.plan.plan_index
                and run_coverage.run_index == run_identity.run_index
            ):
                return run_coverage
        return None

    def _post_training_saliency_status(self) -> PostTrainingSaliencyStatus:
        """Return only the lifecycle in the committed Application publication."""
        publication = self._application_view_publication
        if publication is None or not publication.usable:
            return PostTrainingSaliencyStatus.idle()
        status = getattr(
            publication.state.visualization,
            "post_training_saliency",
            None,
        )
        if isinstance(status, PostTrainingSaliencyStatus):
            return status
        return PostTrainingSaliencyStatus.idle()

    def _show_post_training_saliency_state(
        self,
        current_widget,
        method_name: str,
        coverage: SaliencyMethodCoverageSnapshot,
        status: PostTrainingSaliencyStatus,
    ) -> None:
        """Explain missing output without contradicting a background job."""
        phase = status.phase
        active = phase in {
            PostTrainingSaliencyPhase.PENDING,
            PostTrainingSaliencyPhase.RUNNING,
        }
        targeted = method_name in status.methods
        methods_text = ", ".join(status.methods) or "the configured methods"
        if phase is PostTrainingSaliencyPhase.PENDING:
            title = "Saliency is queued"
            detail = (
                f"{method_name} saliency is waiting to start in the background."
                if targeted
                else (
                    f"Saliency for {methods_text} is waiting to start. "
                    f"{method_name} is not part of this job; wait before computing it."
                )
            )
        elif phase is PostTrainingSaliencyPhase.RUNNING:
            title = "Computing saliency"
            detail = (
                f"{method_name} saliency is being computed in the background."
                if targeted
                else (
                    f"Saliency for {methods_text} is being computed. "
                    f"{method_name} is not part of this job; wait before computing it."
                )
            )
        elif phase is PostTrainingSaliencyPhase.FAILED:
            title = "Saliency computation failed"
            detail = self._terminal_saliency_detail(
                "Saliency computation failed to complete.",
                method_name,
                coverage,
            )
        elif phase is PostTrainingSaliencyPhase.CANCELLED:
            title = "Saliency computation was cancelled"
            detail = self._terminal_saliency_detail(
                "Saliency computation was cancelled.",
                method_name,
                coverage,
            )
        else:
            title = "Saliency output is incomplete"
            detail = self._terminal_saliency_detail(
                "Saliency computation finished, but no complete renderable output "
                "was published.",
                method_name,
                coverage,
            )

        self._saliency_action_requires_recompute = not active
        self.saliency_action_title.setText(title)
        self.saliency_action_detail.setText(detail)
        self.saliency_action_bar.setVisible(True)
        self.compute_saliency_btn.setEnabled(not active)
        self.compute_saliency_btn.setText(
            "Computing..." if active else "Recompute Saliency"
        )
        self._show_widget_message(current_widget, detail)

    @staticmethod
    def _should_surface_automatic_status(
        status: PostTrainingSaliencyStatus,
        method_name: str,
    ) -> bool:
        if status.phase in {
            PostTrainingSaliencyPhase.PENDING,
            PostTrainingSaliencyPhase.RUNNING,
        }:
            return True
        return (
            status.phase
            in {
                PostTrainingSaliencyPhase.FAILED,
                PostTrainingSaliencyPhase.CANCELLED,
            }
            and method_name in status.methods
        )

    @staticmethod
    def _terminal_saliency_detail(
        lifecycle_message: str,
        method_name: str,
        coverage: SaliencyMethodCoverageSnapshot,
    ) -> str:
        missing = [item.display_name for item in coverage.classes if not item.available]
        if coverage.available and missing:
            scope = f"Missing {method_name} classes: {', '.join(missing)}."
        else:
            scope = f"{method_name} output is unavailable for this run."
        return f"{lifecycle_message} {scope} Use Recompute Saliency to try again."

    def _sync_method_options(
        self,
        coverage: dict[str, SaliencyMethodCoverageSnapshot],
    ) -> str:
        """Project only computed methods that can reach the active renderer."""
        self._current_saliency_coverage = dict(coverage)
        allow_partial = self.tabs.currentIndex() == 3
        current_method = self.method_combo.currentText()
        renderable_methods = [
            method
            for method in all_saliency_methods
            if (
                (method_coverage := coverage.get(method)) is not None
                and method_coverage.available
                and (allow_partial or method_coverage.complete)
            )
        ]
        self.method_combo.blockSignals(True)
        try:
            self.method_combo.clear()
            if renderable_methods:
                self.method_combo.addItems(renderable_methods)
                if current_method in renderable_methods:
                    self.method_combo.setCurrentText(current_method)
            else:
                self.method_combo.addItem(_NO_COMPUTED_METHODS)
            self.method_combo.setEnabled(
                bool(renderable_methods)
                and not self._saliency_command_busy
                and not self._saliency_compute_in_progress
            )
        finally:
            self.method_combo.blockSignals(False)
        self._refresh_absolute_control()
        if renderable_methods:
            return self.method_combo.currentText()
        return self._saliency_compute_method_name()

    @staticmethod
    def _incomplete_saliency_message(
        coverage: SaliencyMethodCoverageSnapshot,
    ) -> str:
        missing = [item.display_name for item in coverage.classes if not item.available]
        missing_text = ", ".join(missing) if missing else "one or more classes"
        return (
            f"{coverage.method} saliency is missing for: {missing_text}. "
            "Recompute saliency for this run before opening a multi-class view."
        )

    def _configured_saliency_params(self) -> dict[str, object]:
        diagnostics: dict[str, object] = (
            getattr(self.last_saliency_query, "diagnostics", {})
            if self.last_saliency_query is not None
            else {}
        )
        if diagnostics.get("payload_type") != "saliency_summary":
            return {}
        params = diagnostics.get("params")
        return (
            saliency_command_params_from_configured(params)
            if isinstance(params, dict)
            else {}
        )

    @property
    def pending_saliency_params(self) -> dict[str, object] | None:
        """Return the staged settings without exposing mutable dialog state."""
        return deepcopy(self._pending_saliency_params)

    def _effective_saliency_params(self, method_name: str) -> dict[str, object]:
        """Return the exact settings represented by the visible compute action."""
        params = dict(
            self.pending_saliency_params or self._configured_saliency_params()
        )
        configured_methods = (
            selected_saliency_methods_from_params(params) if params else set()
        )
        if not params or method_name not in configured_methods:
            return recommended_saliency_params_for_method(method_name)
        return params

    def _saliency_compute_method_name(self) -> str:
        """Resolve compute intent without admitting it to the render selector."""
        if self._pending_saliency_method in all_saliency_methods:
            return cast(str, self._pending_saliency_method)
        visible_method = (
            self.method_combo.currentText() if hasattr(self, "method_combo") else ""
        )
        if visible_method in all_saliency_methods:
            return visible_method
        configured = self._configured_saliency_params()
        configured_methods = selected_saliency_methods_from_params(configured)
        configured_method = next(
            (method for method in all_saliency_methods if method in configured_methods),
            None,
        )
        if configured_method is not None:
            return configured_method
        return next(
            (
                method
                for method in all_saliency_methods
                if method in self._current_saliency_coverage
            ),
            "Gradient",
        )

    def _has_service_saliency_summary(self) -> bool:
        diagnostics: dict[str, object] = (
            getattr(self.last_saliency_query, "diagnostics", {})
            if self.last_saliency_query is not None
            else {}
        )
        return diagnostics.get("payload_type") == "saliency_summary"

    def _application_query_blocks_display(self, result) -> bool:
        if result is None:
            return False
        if result.failed:
            return True
        diagnostics = getattr(result, "diagnostics", {}) or {}
        return (
            diagnostics.get("payload_type") == "visualization_summary"
            and diagnostics.get("available") is False
        )

    @staticmethod
    def _application_query_is_readiness_block(result) -> bool:
        """Distinguish an expected workflow prerequisite from a product error."""
        if result is None:
            return False
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if (
            diagnostics.get("payload_type") == "visualization_summary"
            and diagnostics.get("available") is False
        ):
            return True
        error_type = getattr(result, "error_type", None)
        return error_type is ErrorType.PRECONDITION or (
            getattr(error_type, "value", error_type) == ErrorType.PRECONDITION.value
        )

    def _visualization_query_payload(self) -> dict | None:
        result = self.last_application_query
        if result is None or result.failed:
            return None
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "visualization_summary":
            return None
        return dict(diagnostics)

    def _selected_view_blocked_message(self) -> str | None:
        payload = self._visualization_query_payload()
        if payload is None or not hasattr(self, "tabs"):
            return None
        blocked = payload.get("blocked_views")
        if not isinstance(blocked, dict):
            return None
        view_name = self.tabs.tabText(self.tabs.currentIndex()).strip().casefold()
        reasons = next(
            (
                value
                for key, value in blocked.items()
                if str(key).strip().casefold() == view_name
            ),
            None,
        )
        if isinstance(reasons, list) and reasons:
            return str(reasons[0])
        return None

    def _accept_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> bool:
        """Accept only a verified, isolated Application read publication."""
        if not self._valid_application_publication(publication):
            self._clear_application_view_publication(
                invalidate_render_publications=True,
            )
            return False
        if not publication.usable or not publication.state.state_reliable:
            self._clear_application_view_publication(
                invalidate_render_publications=True,
            )
            return False
        previous = self._application_view_publication
        if previous is not None and previous.generation != publication.generation:
            self._invalidate_view_render_publications()
        self._application_view_publication = publication
        explicit_status = publication.state.visualization.post_training_saliency
        owned_update = (
            self._saliency_compute_in_progress
            and self._active_saliency_operation_id is not None
            and self._saliency_status_matches_active_operation(explicit_status)
        )
        if (
            self._saliency_compute_in_progress
            and explicit_status.phase.terminal
            and self._active_saliency_operation_id is not None
            and self._saliency_status_matches_active_operation(explicit_status)
        ):
            if explicit_status.phase is PostTrainingSaliencyPhase.SUCCEEDED:
                self.compute_saliency_btn.setProperty("operationPhase", "completed")
                self._settle_saliency_interaction(
                    InteractionOutcome.completed("Saliency computation completed.")
                )
                self._settle_applied_saliency_settings()
                self._clear_active_saliency_operation()
                self._set_saliency_action_busy(True)
                show_status_message(self, "Preparing saliency visualization...")
            elif explicit_status.phase is PostTrainingSaliencyPhase.CANCELLED:
                self.compute_saliency_btn.setProperty("operationPhase", "cancelled")
                self._settle_saliency_interaction(
                    InteractionOutcome.cancelled(
                        _SALIENCY_RESOURCE_CONFIRMATION_CANCELLED_MESSAGE
                    )
                )
                self._finish_saliency_compute_cancelled(
                    attempt_key=None,
                    current_widget=(
                        self.tabs.currentWidget() if hasattr(self, "tabs") else None
                    ),
                )
            elif explicit_status.phase is PostTrainingSaliencyPhase.FAILED:
                self.compute_saliency_btn.setProperty("operationPhase", "failed")
                self._settle_saliency_interaction(
                    InteractionOutcome.failed(
                        explicit_status.message or _SALIENCY_COMPUTE_FAILED_MESSAGE
                    )
                )
                self._finish_saliency_compute_failure(
                    message=explicit_status.message or _SALIENCY_COMPUTE_FAILED_MESSAGE,
                    attempt_key=None,
                    current_widget=(
                        self.tabs.currentWidget() if hasattr(self, "tabs") else None
                    ),
                )
        elif (
            self._saliency_compute_in_progress
            and explicit_status.phase is PostTrainingSaliencyPhase.IDLE
            and (
                self._active_saliency_operation_id is None
                or (
                    previous is not None
                    and previous.generation != publication.generation
                )
            )
        ):
            self._settle_saliency_interaction(
                InteractionOutcome.cancelled("Saliency computation was cancelled.")
            )
            self._clear_active_saliency_operation()
            self._settle_applied_saliency_settings()
            self._release_saliency_compute_after_render()
        self._refresh_explanation_context()
        pending_target = self._pending_saliency_target
        if (
            pending_target is not None
            and pending_target.publication_generation != publication.generation
        ):
            if owned_update:
                self._pending_saliency_target = replace(
                    pending_target, publication_generation=publication.generation
                )
            else:
                self._require_saliency_settings_review(
                    _SALIENCY_RESULTS_CHANGED_DETAIL,
                )
        return True

    def _saliency_status_matches_active_operation(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> bool:
        """Admit only the saliency generation owned by the current user click."""
        scheduled = self._active_saliency_generation
        if scheduled is not None:
            return status.generation == scheduled
        minimum = self._active_saliency_minimum_generation
        return minimum is not None and status.generation == minimum

    def _clear_active_saliency_operation(self) -> None:
        """Release operation and generation identity as one UI transition."""
        self._active_saliency_operation_id = None
        self._active_saliency_minimum_generation = None
        self._active_saliency_generation = None

    def _saliency_compute_awaits_current_render(
        self,
        publication_generation: int,
    ) -> bool:
        """Match the post-compute render without admitting an older view job."""
        publication = self._application_view_publication
        return (
            self._saliency_compute_in_progress
            and self._active_saliency_operation_id is None
            and publication is not None
            and publication.generation == publication_generation
            and publication.state.visualization.post_training_saliency.phase
            is PostTrainingSaliencyPhase.SUCCEEDED
        )

    def _release_saliency_compute_after_render(self) -> None:
        """Release the visible action once its successful result is resolved."""
        self._saliency_compute_in_progress = False
        self._set_saliency_action_busy(False)

    def _settle_saliency_interaction(self, outcome: InteractionOutcome) -> None:
        """Settle the Assistant-owned continuation for this exact operation."""
        continuation = self._saliency_interaction_continuation
        self._saliency_interaction_continuation = None
        if continuation is not None:
            continuation.start(lambda: outcome)

    @staticmethod
    def _valid_application_publication(publication: object) -> bool:
        if not isinstance(publication, ApplicationViewPublication):
            return False
        return (
            not isinstance(publication.revision, bool)
            and isinstance(publication.revision, int)
            and publication.revision >= 1
        )

    def _record_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        self._last_application_revision = max(
            self._last_application_revision,
            publication.revision,
        )
        self._last_visualization_publication_signature = (
            self._visualization_publication_signature(publication)
        )

    @staticmethod
    def _visualization_publication_signature(
        publication: ApplicationViewPublication,
    ) -> _VisualizationPublicationSignature:
        """Project one publication onto state Visualization actually renders."""
        state = publication.state
        training = state.training
        boundary = publication.training_boundary
        return _VisualizationPublicationSignature(
            usable=publication.usable,
            state_reliable=state.state_reliable,
            training_liveness_reliable=state.training_liveness_reliable,
            pipeline_stage=state.pipeline_stage,
            trainer_identity=boundary.trainer_identity,
            training_boundary_stable=boundary.stable,
            raw_loaded=state.raw.loaded,
            raw_files=tuple(state.raw.files),
            raw_channels=tuple(state.raw.channels),
            preprocessed_available=state.preprocessed.available,
            preprocessed_files=tuple(state.preprocessed.files),
            preprocessed_channels=tuple(state.preprocessed.channel_names),
            epoch_state=state.epoch,
            training_has_model=training.has_model,
            training_model_name=training.model_name,
            training_has_trainer=training.has_trainer,
            training_is_running=training.is_running,
            training_plan_count=training.plan_count,
            training_run_count=training.run_count,
            training_finished_run_count=training.finished_run_count,
            training_terminal_outcome=training.terminal_outcome,
            training_missing_requirements=tuple(training.missing_requirements),
            evaluation_state=state.evaluation,
            visualization_state=state.visualization,
        )

    def _invalidate_view_render_publications(self) -> None:
        self._clear_saliency_render_cache()
        for attribute in ("tab_map", "tab_spectro", "tab_topo", "tab_3d"):
            view = getattr(self, attribute, None)
            invalidate = getattr(view, "invalidate_render_publication", None)
            if callable(invalidate):
                invalidate()

    def _clear_application_view_publication(
        self,
        *,
        invalidate_render_publications: bool = False,
    ) -> None:
        """Clear stale result truth and its visible provenance together."""
        if invalidate_render_publications:
            self._invalidate_view_render_publications()
        self._application_view_publication = None
        if hasattr(self, "method_combo") and hasattr(self, "tabs"):
            self._sync_method_options({})
        self._refresh_explanation_context()

    def _refresh_application_publication(self) -> bool:
        """Read the immutable publication without exposing backend domain objects."""
        query_port = self._query_port
        if query_port is None:
            self._clear_application_view_publication(
                invalidate_render_publications=True,
            )
            return False
        try:
            publication = query_port.get_view_publication()
        except Exception:
            logger.warning(
                "Visualization Application publication is unavailable",
                exc_info=True,
            )
            self._clear_application_view_publication(
                invalidate_render_publications=True,
            )
            return False
        return self._accept_application_publication(publication)

    def _refresh_application_query(
        self,
        *,
        view: str | None = None,
    ) -> None:
        """Dispatch one visualization readiness read outside the GUI thread."""
        action_port = self._action_port
        publication = self._application_view_publication
        if publication is None and self._refresh_application_publication():
            publication = self._application_view_publication
        if action_port is None or publication is None:
            self.last_application_query = None
            return
        if self._active_application_summary_request is not None:
            return
        self._application_summary_request_sequence += 1
        request = (
            self._application_summary_request_sequence,
            publication.generation,
        )
        self._active_application_summary_request = request

        def accept_result(result: CommandResult) -> None:
            if self._active_application_summary_request != request:
                return
            self._active_application_summary_request = None
            self._application_summary_dirty = not self._accept_application_query_result(
                result,
                publication,
            )
            if not self._application_summary_dirty:
                self.update_panel()

        def accept_error(error: tuple) -> None:
            if self._active_application_summary_request != request:
                return
            self._active_application_summary_request = None
            self._settle_application_query_failure(publication)
            logger.error("Visualization background query raised: %s", error)
            self.update_panel()

        started = execute_application_command_async(
            self,
            VisualizeCommand(view=view),
            on_result=accept_result,
            on_error=accept_error,
            refresh=False,
            busy_target=self.tabs,
            expected_publication_generation=publication.generation,
            runtime=cast("ApplicationUiRuntime", action_port),
        )
        if not started and self._active_application_summary_request == request:
            self._active_application_summary_request = None
            self._settle_application_query_failure(publication)

    def _settle_application_query_failure(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        """Publish one stable failure when a summary worker cannot complete."""
        message = _SALIENCY_PUBLICATION_UNAVAILABLE_MESSAGE
        self.last_application_query = CommandResult.failure_result(
            command_name="visualize",
            message=message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=message,
        )
        self._application_summary_dirty = False

    def _accept_application_query_result(
        self,
        result: CommandResult,
        publication: ApplicationViewPublication,
    ) -> bool:
        """Accept only a summary coherently paired with its publication."""
        self._refresh_application_publication()
        if result.failed:
            if is_stale_publication_result(result):
                self.last_application_query = None
                self._application_summary_dirty = True
                after_publication = self._application_view_publication
                if after_publication is not None:
                    self._application_render_ledger.queue(after_publication)
                return False
            # A command rejection already carries an actionable product error.
            # Keep it instead of misclassifying it as an incoherent summary.
            self.last_application_query = result
            return True
        after_publication = self._application_view_publication
        diagnostics = getattr(result, "diagnostics", {}) or {}
        summary_generation = diagnostics.get("visualization_publication_generation")
        malformed_generation = (
            isinstance(summary_generation, bool)
            or not isinstance(summary_generation, int)
            or summary_generation < 1
        )
        if (
            after_publication is None
            or not after_publication.usable
            or after_publication.revision < publication.revision
            or malformed_generation
        ):
            # A successful catalog without its backend-owned generation cannot
            # be paired safely with the accepted coverage publication. Do not
            # retry this stable contract failure in a tight UI loop.
            message = _SALIENCY_PUBLICATION_UNAVAILABLE_MESSAGE
            self.last_application_query = CommandResult.failure_result(
                command_name="visualize",
                message=message,
                state=(
                    after_publication.state
                    if after_publication is not None
                    else publication.state
                ),
                changed_state=ChangedState(),
                error_type=ErrorType.PRECONDITION,
                recoverable=True,
                error_message=message,
            )
            self._application_summary_dirty = False
            return True
        if after_publication.generation != summary_generation:
            # The summary can contain Fold Set placeholders from an older
            # generation. Never combine those with current coverage; retain
            # dirtiness until the already-published newer revision is rendered.
            self.last_application_query = None
            self._application_summary_dirty = True
            # A nested query can observe P2 before Qt delivers its publication
            # event. Reuse the panel ledger to schedule the one coherent P2
            # refresh after this direct render returns.
            self._application_render_ledger.queue(after_publication)
            return False
        self.last_application_query = result
        return True

    def _application_query_message(self) -> str:
        result = self.last_application_query
        if (
            result is not None
            and getattr(result, "failed", False)
            and not self._application_query_is_readiness_block(result)
        ):
            logger.error(
                "Visualization query failed: %s",
                getattr(result, "error_message", None)
                or getattr(result, "message", "")
                or "No diagnostic message was provided.",
            )
            return _VISUALIZATION_LOAD_FAILED_MESSAGE
        if result is not None and result.message:
            return str(result.message)
        return "No visualization views are ready yet."

    def _setup_only_message(self) -> str | None:
        payload = self._visualization_query_payload()
        if payload is None:
            return None
        if payload.get("plot_views_available", True) is not False:
            return None
        views = payload.get("available_views")
        if not isinstance(views, list) or "montage setup" not in views:
            return None
        return (
            "Complete training to view saliency plots. "
            "Configure Electrode Layout in Dataset."
        )

    def _clear_plan_controls(self) -> None:
        self.plan_combo.blockSignals(True)
        self.run_combo.blockSignals(True)
        self.plan_combo.clear()
        self.plan_combo.addItem("Select a fold")
        self.run_combo.clear()
        self._runs_by_plan = {}
        self._cross_fold_choice_by_identity = {}
        self._sync_method_options({})
        self.plan_combo.blockSignals(False)
        self.run_combo.blockSignals(False)
        if hasattr(self, "tabs"):
            self._refresh_explanation_context()

    @staticmethod
    def _show_widget_error(widget, message: str) -> bool:
        show_error = getattr(widget, "show_error", None)
        if not callable(show_error):
            return False
        show_error(message)
        return True

    @staticmethod
    def _show_widget_message(widget, message: str) -> bool:
        show_message = getattr(widget, "show_message", None)
        if callable(show_message):
            show_message(message)
            return True
        return VisualizationPanel._show_widget_error(widget, message)
