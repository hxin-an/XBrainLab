"""Visualization panel: saliency maps, topomaps, spectrograms, and 3-D views."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QEvent, QThread
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
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
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.application.saliency_policy import (
    is_recommended_saliency_method,
    recommended_saliency_params_for_method,
    saliency_command_params_from_configured,
    selected_saliency_methods_from_params,
)
from XBrainLab.backend.application.saliency_render import (
    normalized_saliency_render_publication,
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
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.backend.visualization.saliency_semantics import (
    NONNEGATIVE_SALIENCY_METHODS,
)
from XBrainLab.ui.application_capabilities import (
    VisualizationActionPort,
    VisualizationPublicationPort,
    VisualizationQueryPort,
    application_ui_runtime,
    execute_application_command,
    execute_application_command_async,
    get_saliency_render_publication,
    is_stale_publication_result,
)
from XBrainLab.ui.application_publication_renderer import (
    ApplicationPublicationRenderLedger,
)
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.interaction_outcome import InteractionOutcome
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
_SALIENCY_SELECTION_CHANGED_DETAIL = (
    "The selected run changed. Open Settings and review the saliency "
    "configuration for this run."
)
_VISUALIZATION_LOAD_FAILED_MESSAGE = (
    "Visualization could not be loaded. Refresh Visualization and try again."
)


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
    run_identity: SaliencyRunIdentity
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
        self._saliency_summary_dirty = True
        self._saliency_compute_in_progress = False
        self._saliency_compute_attempted: set[tuple[object, ...]] = set()
        self._pending_saliency_params: dict[str, object] | None = None
        self._pending_saliency_target: _SaliencySettingsTarget | None = None
        self._saliency_settings_review_required = False
        self._saliency_settings_review_detail = ""
        self._current_saliency_coverage: dict[
            str,
            SaliencyMethodCoverageSnapshot,
        ] = {}
        self._saliency_action_requires_recompute = False
        self._native_render_shutdown_requested = False
        self._native_render_resources_finalized = False

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
        self._accept_application_publication(typed_publication)
        if signature == self._last_visualization_publication_signature:
            return self._application_render_ledger.record_rendered(typed_publication)
        self._mark_application_summaries_dirty()
        return self._application_render_ledger.queue(typed_publication)

    def _render_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        self._accept_application_publication(publication)
        self.update_panel()

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
        self.method_combo.addItems(all_saliency_methods)
        self.method_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.method_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.method_combo.currentTextChanged.connect(self._on_method_changed)

        # Absolute Checkbox
        self.abs_check = QCheckBox("Absolute")
        self.abs_check.setToolTip("Use absolute saliency values")
        self.abs_check.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        self.abs_check.stateChanged.connect(self.on_update)

        self.normalize_check = QCheckBox("Normalize")
        self.normalize_check.setToolTip(
            "Scale all displayed classes together without changing saved saliency."
        )
        self.normalize_check.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        self.normalize_check.stateChanged.connect(self.on_update)
        self._controls_single_row = None
        self._apply_visualization_control_layout(single_row=False)
        left_layout.addWidget(self.ctrl_bar)

        # 2. Saliency compute entry point
        self.saliency_action_bar = self._build_saliency_action_bar()
        self.saliency_action_bar.setVisible(False)
        left_layout.addWidget(self.saliency_action_bar)

        # 3. Explanation canvas
        self._explanation_context_text = ""

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(Stylesheets.TAB_WIDGET_CLEAN)
        # Signal connected at the end of init_ui to avoid early triggering

        # Get trainers for initialization (empty initially)

        # Tab 1: Saliency Map
        self.tab_map = SaliencyMapWidget(self)
        self.tabs.addTab(self.tab_map, "Saliency Map")

        # Tab 2: Spectrogram (Swapped order)
        self.tab_spectro = SaliencySpectrogramWidget(self)
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

        self.saliency_settings_btn = QPushButton("Settings")
        self.saliency_settings_btn.setMinimumWidth(86)
        self.saliency_settings_btn.setStyleSheet(Stylesheets.BTN_GHOST)
        self.saliency_settings_btn.clicked.connect(self._open_saliency_settings)

        layout.addLayout(text_layout, stretch=1)
        layout.addWidget(self.saliency_settings_btn)
        layout.addWidget(self.compute_saliency_btn)
        return frame

    def resizeEvent(self, event):  # noqa: N802
        """Switch visualization controls between compact and full-width layouts."""
        super().resizeEvent(event)
        self._refresh_control_layout_for_width()

    def _refresh_control_layout_for_width(self) -> None:
        if not hasattr(self, "ctrl_bar"):
            return
        available_width = max(self.ctrl_bar.width(), self.width() - 340)
        self._apply_visualization_control_layout(
            single_row=available_width >= 780,
        )

    def _apply_visualization_control_layout(self, single_row: bool) -> None:
        if getattr(self, "_controls_single_row", None) == single_row:
            return

        self._controls_single_row = single_row
        for column in range(9):
            self.ctrl_layout.setColumnStretch(column, 0)

        if single_row:
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
            self.ctrl_layout.addWidget(self.method_label, 0, 4)
            self.ctrl_layout.addWidget(self.method_combo, 0, 5)
            self.ctrl_layout.addWidget(self.abs_check, 0, 6)
            self.ctrl_layout.addWidget(self.normalize_check, 0, 7)
            self.ctrl_layout.setColumnStretch(8, 1)
            return

        self.plan_combo.setMinimumWidth(150)
        self.plan_combo.setMaximumWidth(220)
        self.run_combo.setMinimumWidth(120)
        self.run_combo.setMaximumWidth(180)
        self.method_combo.setMinimumWidth(150)
        self.method_combo.setMaximumWidth(220)

        self.ctrl_layout.addWidget(self.plan_label, 0, 0)
        self.ctrl_layout.addWidget(self.plan_combo, 0, 1)
        self.ctrl_layout.addWidget(self.run_label, 0, 2)
        self.ctrl_layout.addWidget(self.run_combo, 0, 3)
        self.ctrl_layout.addWidget(self.method_label, 1, 0)
        self.ctrl_layout.addWidget(self.method_combo, 1, 1)
        self.ctrl_layout.addWidget(self.abs_check, 1, 3)
        self.ctrl_layout.addWidget(self.normalize_check, 1, 4)
        self.ctrl_layout.setColumnStretch(5, 1)

    def _cross_fold_choices_from_query(
        self,
    ) -> tuple[_SaliencyCrossFoldChoice, ...]:
        """Parse backend-admitted summary identities without inferring cohorts."""
        payload = self._visualization_query_payload()
        raw_choices = (
            payload.get("saliency_cross_fold_choices", [])
            if payload is not None
            else []
        )
        if not isinstance(raw_choices, list):
            return ()
        choices: list[_SaliencyCrossFoldChoice] = []
        for raw_choice in raw_choices:
            if not isinstance(raw_choice, dict):
                continue
            raw_identity = raw_choice.get("identity")
            raw_members = (
                raw_identity.get("members") if isinstance(raw_identity, dict) else None
            )
            raw_methods = raw_choice.get("methods")
            raw_classes = raw_choice.get("classes")
            if not isinstance(raw_members, list) or not isinstance(
                raw_methods,
                list,
            ):
                continue
            if not isinstance(raw_classes, list):
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
            if not methods or not classes:
                continue
            choices.append(
                _SaliencyCrossFoldChoice(
                    identity=identity,
                    display_name=str(raw_choice.get("display_name") or "All Folds"),
                    run_label=str(
                        raw_choice.get("run_label")
                        or f"Run {identity.run_index + 1} (Summary)"
                    ),
                    methods=methods,
                    source_split=str(raw_choice.get("source_split") or "unknown"),
                    classes=classes,
                )
            )
        return tuple(choices)

    def refresh_combos(self):
        """Refresh plan/run identities from one immutable view publication."""
        if self._application_summary_dirty or self.last_application_query is None:
            self._refresh_application_query(view="summary")
            self._application_summary_dirty = False

        if self._application_query_blocks_display(self.last_application_query):
            self._clear_plan_controls()
            return

        previous_plan = self.plan_combo.currentData()
        previous_plan_text = self.plan_combo.currentText()
        previous_run = self.run_combo.currentData()
        previous_run_text = self.run_combo.currentText()
        publication = self._application_view_publication
        published_model_name = (
            publication.state.training.model_name
            if publication is not None and publication.usable
            else ""
        )
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
            model_name = (
                run_coverage.model_name or published_model_name or "Unknown model"
            )
            plan_labels.setdefault(
                plan_identity,
                fold_display_label(run_coverage.plan_index, model_name),
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

        # If items exist, select first real plan
        if self.plan_combo.count() > 1:
            selected_index = 1
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
        """Keep aggregate summaries read-only without hiding plot controls."""
        cross_fold = isinstance(
            self.run_combo.currentData(),
            SaliencyCrossFoldIdentity,
        )
        if hasattr(self, "sidebar") and hasattr(self.sidebar, "btn_saliency"):
            self.sidebar.btn_saliency.setEnabled(not cross_fold)
            self.sidebar.btn_saliency.setToolTip(
                "Select one fold to configure or recompute saliency."
                if cross_fold
                else "Configure saliency methods and parameters."
            )

    def on_tab_changed(self, index):
        """Handle tab switch."""
        del index
        current_widget = self.tabs.currentWidget()
        previous_widget = self._last_active_saliency_view
        if previous_widget is not current_widget:
            invalidate = getattr(previous_widget, "invalidate_render_publication", None)
            if callable(invalidate):
                invalidate()
        self._last_active_saliency_view = current_widget
        self._refresh_explanation_context()
        self._refresh_absolute_control()
        # Montage button is now always visible as per user request
        # self.btn_montage.setVisible(True) # It's visible by default

        self.on_update()

    def begin_native_render_shutdown(self) -> None:
        """Cooperatively cancel every saliency view before application close."""
        if (
            self._native_render_shutdown_requested
            or self._native_render_resources_finalized
        ):
            return
        self._native_render_shutdown_requested = True
        for view in self._saliency_views():
            begin_shutdown = getattr(view, "begin_render_shutdown", None)
            if callable(begin_shutdown):
                begin_shutdown()

    def native_render_work_idle(self) -> bool:
        """Return true after every saliency worker reaches terminal cleanup."""
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
        """Disable an irrelevant transform without discarding its saved choice."""
        if not hasattr(self, "abs_check") or not hasattr(self, "tabs"):
            return
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
        self._hide_saliency_action_bar()
        if self._application_summary_dirty or self.last_application_query is None:
            self._refresh_application_query(
                view=self.tabs.tabText(self.tabs.currentIndex()),
            )
            self._application_summary_dirty = False
        self._refresh_explanation_context()

        if self._application_query_blocks_display(self.last_application_query):
            message = self._application_query_message()
            if self._application_query_is_readiness_block(self.last_application_query):
                self._show_widget_message(current_widget, message)
            else:
                self._show_widget_error(current_widget, message)
            return

        automatic_status = self._post_training_saliency_status()

        plan_identity = self.plan_combo.currentData()
        run_identity = self.run_combo.currentData()
        absolute = self.abs_check.isChecked()
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
                f"{method_name} saliency has not been computed for this run. "
                "Use Compute Saliency to continue.",
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
        )
        try:
            render_publication = self._saliency_render_publication(request)
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
            typed_render_publication.request != request
            or typed_render_publication.generation != publication.generation
            or typed_render_publication.data.method != method_name
            or typed_render_publication.data.normalized != normalize
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
        if current_widget and hasattr(current_widget, "update_plot"):
            current_widget.update_plot(typed_render_publication, absolute)

    def _saliency_render_publication(
        self,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication | None:
        """Publish one raw DTO per selection and derive display-only variants."""
        raw_request = replace(request, normalize=False)
        if self._saliency_render_cache_request != raw_request:
            self._clear_saliency_render_cache()
            self._saliency_render_cache_request = raw_request

        raw_publication = self._saliency_render_cache.get(False)
        if raw_publication is None:
            candidate = get_saliency_render_publication(
                self,
                raw_request,
                runtime=cast("ApplicationUiRuntime", self._query_port),
            )
            if not self._render_publication_matches_request(candidate, raw_request):
                return candidate
            raw_publication = cast(SaliencyRenderPublication, candidate)
            self._saliency_render_cache[False] = raw_publication

        if not request.normalize:
            return raw_publication
        normalized_publication = self._saliency_render_cache.get(True)
        if normalized_publication is None:
            normalized_publication = normalized_saliency_render_publication(
                raw_publication
            )
            self._saliency_render_cache[True] = normalized_publication
        return normalized_publication

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

    def _compute_saliency_from_action_bar(self) -> None:
        """Compute saliency for the current run using a product-friendly default."""
        if self._training_is_running():
            return
        current_widget = self.tabs.currentWidget() if hasattr(self, "tabs") else None
        if self._saliency_settings_review_required:
            self._require_saliency_settings_review(
                self._saliency_settings_review_detail
                or _SALIENCY_RESULTS_CHANGED_DETAIL,
                current_widget=current_widget,
            )
            return

        current_target = self._current_saliency_settings_target()
        if current_target is None:
            self._require_saliency_settings_review(
                _SALIENCY_RESULTS_CHANGED_DETAIL,
                current_widget=current_widget,
            )
            return
        if (
            self._pending_saliency_params is not None
            and self._pending_saliency_target != current_target
        ):
            detail = (
                _SALIENCY_RESULTS_CHANGED_DETAIL
                if self._pending_saliency_target is None
                or self._pending_saliency_target.publication_generation
                != current_target.publication_generation
                else _SALIENCY_SELECTION_CHANGED_DETAIL
            )
            self._require_saliency_settings_review(
                detail,
                current_widget=current_widget,
            )
            return

        method_name = (
            self.method_combo.currentText() if hasattr(self, "method_combo") else ""
        ) or "Gradient"
        params = dict(
            self._pending_saliency_params or self._configured_saliency_params()
        )
        configured_methods = (
            selected_saliency_methods_from_params(params) if params else set()
        )
        if not params or method_name not in configured_methods:
            params = recommended_saliency_params_for_method(method_name)
        methods = params.get("methods")
        methods_key = tuple(methods) if isinstance(methods, (list, tuple, set)) else ()
        started = self._start_saliency_compute(
            params=params,
            method_name=method_name,
            current_widget=current_widget,
            attempt_key=(
                "manual",
                current_target.publication_generation,
                current_target.run_identity,
                current_target.model_name,
                method_name,
                methods_key,
            ),
            expected_publication_generation=current_target.publication_generation,
            run_identity=current_target.run_identity,
            model_name=current_target.model_name,
        )
        if not started:
            self._set_saliency_action_busy(False)
            if not self._saliency_settings_review_required:
                show_status_message(self, _SALIENCY_COMPUTE_START_FAILED_MESSAGE)

    def _open_saliency_settings(self) -> None:
        sidebar = getattr(self, "sidebar", None)
        set_saliency = getattr(sidebar, "set_saliency", None)
        if callable(set_saliency):
            set_saliency()

    def saliency_settings_target(
        self,
    ) -> tuple[int, SaliencyRunIdentity, str] | None:
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
        run_identity: SaliencyRunIdentity | None = None,
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
            or not isinstance(run_identity, SaliencyRunIdentity)
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
            and isinstance(run_identity, SaliencyRunIdentity)
            and model_name is not None
            else current_target
        )
        if current_target is None or reviewed_target != current_target:
            self._require_saliency_settings_review(
                (
                    _SALIENCY_RESULTS_CHANGED_DETAIL
                    if current_target is None
                    or reviewed_target is None
                    or reviewed_target.publication_generation
                    != current_target.publication_generation
                    else _SALIENCY_SELECTION_CHANGED_DETAIL
                ),
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
            (
                self.method_combo.itemText(index)
                for index in range(self.method_combo.count())
                if self.method_combo.itemText(index) in selected_methods
            ),
            self.method_combo.currentText() or "Gradient",
        )
        self.method_combo.setCurrentText(selected_method)
        self._show_saliency_action_bar(
            selected_method,
            self._current_saliency_coverage.get(selected_method),
        )
        return True

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
            or (coverage is not None and coverage.available and not coverage.complete)
        )
        if self._saliency_compute_in_progress:
            self.saliency_action_title.setText("Preparing saliency baseline")
            detail = "Computing Gradient + Gradient * Input in the background."
        elif self._pending_saliency_params is not None:
            self.saliency_action_title.setText("Saliency settings ready")
            detail = "Use Recompute Saliency to apply the selected settings."
        elif self._saliency_action_requires_recompute and coverage is not None:
            self.saliency_action_title.setText("Saliency is incomplete")
            detail = self._incomplete_saliency_message(coverage)
        elif is_recommended_saliency_method(method_name):
            self.saliency_action_title.setText("Preparing saliency baseline")
            detail = "XBrainLab prepares Gradient + Gradient * Input automatically."
        else:
            self.saliency_action_title.setText("Advanced saliency not computed")
            detail = f"{method_name} uses default noise settings. Adjust in Settings."
        self.saliency_action_detail.setText(detail)
        self._set_saliency_action_busy(self._saliency_compute_in_progress)
        self.saliency_action_bar.setVisible(True)

    def _hide_saliency_action_bar(self) -> None:
        if not hasattr(self, "saliency_action_bar"):
            return
        if self._saliency_compute_in_progress:
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
        if self._application_render_ledger.render_in_progress:
            return
        publication = self._application_view_publication
        if publication is not None:
            self._application_render_ledger.record_rendered(publication)

    def _update_panel_content(self):
        """Called when switching to this panel."""
        if self._application_view_publication is None:
            self._refresh_application_publication()
        self.update_info()
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
        run_identity: SaliencyRunIdentity | None = None,
        model_name: str | None = None,
    ) -> bool:
        """Run configured saliency computation in the ApplicationService worker."""
        if expected_publication_generation is not None:
            expected_target = (
                _SaliencySettingsTarget(
                    publication_generation=expected_publication_generation,
                    run_identity=run_identity,
                    model_name=str(model_name),
                )
                if isinstance(run_identity, SaliencyRunIdentity)
                and model_name is not None
                else None
            )
            current_target = self._current_saliency_settings_target()
            if expected_target is None or expected_target != current_target:
                self._require_saliency_settings_review(
                    (
                        _SALIENCY_RESULTS_CHANGED_DETAIL
                        if current_target is None
                        or expected_target is None
                        or expected_target.publication_generation
                        != current_target.publication_generation
                        else _SALIENCY_SELECTION_CHANGED_DETAIL
                    ),
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

        def handle_result(result: CommandResult) -> InteractionOutcome:
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
                busy_target=self.main_window,
                runtime=cast("ApplicationUiRuntime", self._action_port),
                expected_publication_generation=expected_publication_generation,
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
                QMessageBox.critical(
                    self,
                    _SALIENCY_RESOURCE_DIALOG_TITLE,
                    message,
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
        self._set_saliency_action_busy(False)
        self._pending_saliency_params = None
        self._pending_saliency_target = None
        self._saliency_settings_review_required = False
        self._saliency_settings_review_detail = ""
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
        reply = QMessageBox.question(
            self,
            _SALIENCY_RESOURCE_DIALOG_TITLE,
            f"{message}\n\nContinue computing saliency?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
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
        self._saliency_compute_in_progress = False
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
        self._saliency_compute_in_progress = False
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
        run_coverage = self._selected_run_coverage()
        if (
            publication is None
            or not publication.usable
            or not isinstance(run_identity, SaliencyRunIdentity)
            or run_coverage is None
        ):
            return None
        model_name = (
            run_coverage.model_name or publication.state.training.model_name or ""
        )
        return _SaliencySettingsTarget(
            publication_generation=publication.generation,
            run_identity=run_identity,
            model_name=str(model_name),
        )

    def _require_saliency_settings_review(
        self,
        detail: str,
        *,
        current_widget=None,
        attempt_key: tuple[object, ...] | None = None,
    ) -> None:
        """Discard stale settings and expose one actionable recovery state."""
        self._saliency_compute_in_progress = False
        self._pending_saliency_params = None
        self._pending_saliency_target = None
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
        publication = self._application_view_publication
        if publication is None or not publication.usable:
            return None
        run_identity = self.run_combo.currentData()
        if not isinstance(run_identity, SaliencyRunIdentity):
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
                    f"Automatic saliency for {methods_text} is waiting to start. "
                    f"{method_name} is not part of this job; wait before computing it."
                )
            )
        elif phase is PostTrainingSaliencyPhase.RUNNING:
            title = "Computing saliency"
            detail = (
                f"{method_name} saliency is being computed in the background."
                if targeted
                else (
                    f"Automatic saliency for {methods_text} is being computed. "
                    f"{method_name} is not part of this job; wait before computing it."
                )
            )
        elif phase is PostTrainingSaliencyPhase.FAILED:
            title = "Automatic saliency failed"
            detail = self._terminal_saliency_detail(
                "Automatic saliency failed to complete.",
                method_name,
                coverage,
            )
        elif phase is PostTrainingSaliencyPhase.CANCELLED:
            title = "Automatic saliency was cancelled"
            detail = self._terminal_saliency_detail(
                "Automatic saliency computation was cancelled.",
                method_name,
                coverage,
            )
        else:
            title = "Saliency output is incomplete"
            detail = self._terminal_saliency_detail(
                "Automatic saliency finished, but no complete renderable output "
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
            status.phase is not PostTrainingSaliencyPhase.IDLE
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
        """Disable method/view combinations that cannot reach a renderer."""
        self._current_saliency_coverage = dict(coverage)
        allow_partial = self.tabs.currentIndex() == 3
        model = self.method_combo.model()
        standard_model = model if isinstance(model, QStandardItemModel) else None
        current_method = self.method_combo.currentText()
        enabled_indices: list[int] = []
        self.method_combo.blockSignals(True)
        try:
            for index in range(self.method_combo.count()):
                method = self.method_combo.itemText(index)
                method_coverage = coverage.get(
                    method,
                    SaliencyMethodCoverageSnapshot(method=method),
                )
                enabled = method_coverage.available and (
                    allow_partial or method_coverage.complete
                )
                if enabled:
                    enabled_indices.append(index)
                if standard_model is not None:
                    item = standard_model.item(index)
                    if item is not None:
                        item.setEnabled(enabled)
                        item.setToolTip(
                            "Saliency is ready."
                            if enabled
                            else self._method_unavailable_reason(method_coverage)
                        )
            current_index = self.method_combo.findText(current_method)
            if enabled_indices and current_index not in enabled_indices:
                self.method_combo.setCurrentIndex(enabled_indices[0])
        finally:
            self.method_combo.blockSignals(False)
        return self.method_combo.currentText()

    @staticmethod
    def _method_unavailable_reason(
        coverage: SaliencyMethodCoverageSnapshot,
    ) -> str:
        if coverage.available and not coverage.complete:
            return VisualizationPanel._incomplete_saliency_message(coverage)
        return f"{coverage.method} has not been computed for this run."

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
        self._refresh_explanation_context()
        pending_target = self._pending_saliency_target
        if (
            pending_target is not None
            and pending_target.publication_generation != publication.generation
        ):
            self._require_saliency_settings_review(
                _SALIENCY_RESULTS_CHANGED_DETAIL,
            )
        return True

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
    ) -> bool:
        """Refresh visualization readiness without eager saliency averaging."""
        action_port = self._action_port
        publication = self._application_view_publication
        if publication is None and self._refresh_application_publication():
            publication = self._application_view_publication
        if action_port is None or publication is None:
            self.last_application_query = None
            return False
        result = execute_application_command(
            self,
            VisualizeCommand(view=view),
            refresh=False,
            expected_publication_generation=publication.generation,
            runtime=cast("ApplicationUiRuntime", action_port),
        )
        if result is None:
            return False
        self.last_application_query = result
        self._refresh_application_publication()
        return not result.failed

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
            "Complete training to view saliency plots. Set Montage remains available."
        )

    def _clear_plan_controls(self) -> None:
        self.plan_combo.blockSignals(True)
        self.run_combo.blockSignals(True)
        self.plan_combo.clear()
        self.plan_combo.addItem("Select a fold")
        self.run_combo.clear()
        self._runs_by_plan = {}
        self._cross_fold_choice_by_identity = {}
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
