from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
from matplotlib.figure import Figure
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
    EvaluateCommand,
    EvaluationCrossFoldIdentity,
    EvaluationPlanIdentity,
    EvaluationRenderData,
    EvaluationRenderRequest,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewStore
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.panels.evaluation.metrics_bar_chart import MetricsBarChartWidget
from XBrainLab.ui.panels.evaluation.metrics_table import MetricsTableWidget
from XBrainLab.ui.panels.evaluation.panel import (
    INFO_SIDEBAR_WIDTH,
    EvaluationPanel,
)
from XBrainLab.ui.styles.theme import Theme


# Mock classes
class MockEvalRecord:
    def __init__(self):
        self.output = MagicMock()
        self.label = MagicMock()

    def get_per_class_metrics(self):
        return {
            0: {
                "precision": 0.8,
                "recall": 0.9,
                "f1-score": 0.85,
                "support": 10,
            },
            1: {
                "precision": 0.7,
                "recall": 0.6,
                "f1-score": 0.65,
                "support": 10,
            },
            "macro_avg": {
                "precision": 0.75,
                "recall": 0.75,
                "f1-score": 0.75,
                "support": 20,
            },
        }


class MockTrainRecord:
    def __init__(self, finished=True):
        self.finished = finished
        self.eval_record = MockEvalRecord() if finished else None
        self.dataset = MagicMock()

    def is_finished(self):
        return self.finished

    def get_confusion_figure(self, show_percentage=False):
        # Return a dummy figure

        return Figure()


class MockPlanHolder:
    def __init__(self, name="Test Plan"):
        self.name = name
        self.records = [MockTrainRecord(True), MockTrainRecord(False)]

    def get_name(self):
        return self.name

    def get_plans(self):
        return self.records


class MockTrainer:
    def __init__(self):
        self.training_plan_holders = [
            MockPlanHolder("Plan A"),
            MockPlanHolder("Plan B"),
        ]

    def get_training_plan_holders(self):
        return self.training_plan_holders


class MockStudy:
    def __init__(self):
        self.trainer = MockTrainer()
        self.loaded_data_list = []
        self.preprocessed_data_list = []

    def get_controller(self, name):
        if name == "evaluation":
            controller = MagicMock()
            controller.get_plans.return_value = self.trainer.get_training_plan_holders()
            controller.get_model_summary_str.return_value = "Mock Summary"
            controller.get_loaded_data_list.return_value = self.loaded_data_list
            controller.get_preprocessed_data_list.return_value = (
                self.preprocessed_data_list
            )
            return controller
        return MagicMock()


class MockMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.study = MockStudy()


def _mapped_rect(widget: QWidget, ancestor: QWidget) -> QRect:
    return QRect(widget.mapTo(ancestor, QPoint()), widget.size())


def _assert_controls_are_contained_and_disjoint(panel: EvaluationPanel) -> None:
    bar = panel.evaluation_controls_bar
    controls = (
        panel.model_combo,
        panel.run_combo,
        panel.split_combo,
        panel.chk_percentage,
    )
    rects = [_mapped_rect(control, bar) for control in controls]
    for rect in rects:
        assert bar.contentsRect().contains(rect)
    for index, rect in enumerate(rects):
        assert all(not rect.intersects(other) for other in rects[index + 1 :])


def test_evaluation_panel_layout(qtbot):
    """Test the layout of the redesigned EvaluationPanel."""
    main_window = MockMainWindow()
    panel = EvaluationPanel(parent=main_window)
    qtbot.addWidget(panel)
    panel.resize(1000, 720)
    panel.show()
    qtbot.wait(50)

    # Check Splitter (Should be None now)
    splitter = panel.findChild(QSplitter)
    assert splitter is None

    # Check Groups existence
    groups = panel.findChildren(QGroupBox)
    assert len(groups) >= 2  # Matrix + Metrics (and possibly others inside sidebar)

    # Check Matrix Widget
    matrix_widget = panel.findChild(ConfusionMatrixWidget)
    assert matrix_widget is not None

    # Check Bar Chart Widget
    bar_chart = panel.findChild(MetricsBarChartWidget)
    assert bar_chart is not None

    # Check Metrics Table
    metrics_table = panel.findChild(MetricsTableWidget)
    assert metrics_table is not None

    # Check Actions Group (Should be Removed)
    action_group = next((g for g in groups if g.title() == "ACTIONS"), None)
    assert action_group is None

    # Check Toolbar Controls
    model_combo = panel.model_combo
    run_combo = panel.run_combo
    chk_percentage = panel.chk_percentage

    assert isinstance(model_combo, QComboBox)
    assert isinstance(run_combo, QComboBox)
    assert isinstance(chk_percentage, QCheckBox)

    assert hasattr(panel, "evaluation_controls_bar")
    plots_group = next(group for group in groups if group.title() == "EVALUATION PLOTS")
    plots_layout = plots_group.layout()
    assert plots_layout is not None
    assert plots_layout.indexOf(panel.evaluation_controls_bar) < plots_layout.indexOf(
        panel.plot_stack,
    )


def test_evaluation_plots_title_uses_standard_section_tone(qtbot):
    """Evaluation Plots must not be brighter than peer panel section titles."""
    panel = EvaluationPanel(parent=None)
    qtbot.addWidget(panel)
    panel.show()
    qtbot.wait(20)

    title_color = panel.plots_group.palette().color(QPalette.ColorRole.WindowText)

    assert title_color == QColor(Theme.TEXT_SECONDARY)


def test_evaluation_tabs_do_not_draw_platform_base_line(qtbot):
    panel = EvaluationPanel(parent=None)
    qtbot.addWidget(panel)

    assert panel.chart_tabs.tabBar().drawBase() is False
    assert panel.bottom_tabs.tabBar().drawBase() is False


def test_evaluation_metric_views_use_dataset_class_names(qtbot):
    metrics = MockEvalRecord().get_per_class_metrics()
    class_names = {0: "Left hand", 1: "Right hand"}
    chart = MetricsBarChartWidget()
    table = MetricsTableWidget()
    qtbot.addWidget(chart)
    qtbot.addWidget(table)

    chart.update_plot(metrics, class_names=class_names)
    table.update_data(metrics, class_names=class_names)

    assert [label.get_text() for label in chart.ax.get_xticklabels()] == [
        "Left hand",
        "Right hand",
    ]
    assert table.item(0, 0).text() == "Left hand"
    assert table.item(1, 0).text() == "Right hand"


def test_confusion_matrix_keeps_long_labels_readable_at_minimum_canvas(qtbot):
    widget = ConfusionMatrixWidget()
    qtbot.addWidget(widget)
    widget.resize(180, 217)
    widget.show()
    widget.update_plot(
        EvaluationRenderData(
            labels=np.array([0, 1]),
            outputs=np.array([[0.9, 0.1], [0.2, 0.8]]),
            metrics={},
            class_labels={0: "Left hand", 1: "Right hand"},
            summary_identity=EvaluationSummaryIdentity(
                plan=EvaluationPlanIdentity(plan_index=0),
            ),
            evaluation_split="test",
        )
    )
    widget.resize(180, 217)
    qtbot.wait(80)

    canvas = widget.canvas
    figure = widget.fig
    assert canvas is not None
    assert figure is not None
    assert canvas.width() == 180
    canvas.draw()
    renderer = canvas.get_renderer()
    axis = next(item for item in figure.axes if item.axison)
    x_labels = [item for item in axis.get_xticklabels() if item.get_text()]
    y_labels = [item for item in axis.get_yticklabels() if item.get_text()]

    assert [" ".join(item.get_text().split()) for item in x_labels] == [
        "Left hand",
        "Right hand",
    ]
    assert [" ".join(item.get_text().split()) for item in y_labels] == [
        "Left hand",
        "Right hand",
    ]
    x_anchors = [
        item.get_transform().transform(item.get_position())[0] for item in x_labels
    ]
    assert x_anchors[1] - x_anchors[0] >= 18

    figure_width = float(figure.bbox.width)
    figure_height = float(figure.bbox.height)
    decorations = [
        *x_labels,
        *y_labels,
        axis.xaxis.label,
        axis.yaxis.label,
        axis.title,
    ]
    for decoration in decorations:
        bounds = decoration.get_window_extent(renderer=renderer)
        assert bounds.x0 >= 0
        assert bounds.y0 >= 0
        assert bounds.x1 <= figure_width
        assert bounds.y1 <= figure_height


def test_evaluation_controls_are_compact_toolbar(qtbot):
    main_window = MockMainWindow()
    host_layout = QVBoxLayout(main_window)
    host_layout.setContentsMargins(0, 0, 0, 0)
    panel = EvaluationPanel(parent=main_window)
    host_layout.addWidget(panel)
    qtbot.addWidget(main_window)
    main_window.resize(1180, 760)
    main_window.show()
    qtbot.wait(50)

    assert panel.model_combo.maximumWidth() <= 360
    assert panel.run_combo.maximumWidth() <= 300
    assert panel.split_combo.maximumWidth() <= 150
    assert (
        panel.model_combo.sizePolicy().horizontalPolicy()
        == QSizePolicy.Policy.Preferred
    )
    assert (
        panel.run_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Preferred
    )
    assert panel.evaluation_controls_bar.is_wrapped() is False
    model_pos = panel.model_combo.mapTo(panel.evaluation_controls_bar, QPoint())
    split_pos = panel.split_combo.mapTo(panel.evaluation_controls_bar, QPoint())
    percentage_pos = panel.chk_percentage.mapTo(
        panel.evaluation_controls_bar,
        QPoint(),
    )
    assert abs(model_pos.y() - split_pos.y()) <= 4
    assert split_pos.x() < percentage_pos.x()


def test_evaluation_controls_reflow_and_preserve_long_selection_tooltips(qtbot):
    panel = EvaluationPanel(parent=None)
    qtbot.addWidget(panel)
    long_model = (
        "Fold 1 (EEGNet with a deliberately long model label for constrained "
        "evaluation panel overflow verification)"
    )
    long_run = (
        "Run 1 (Finished, best validation accuracy across all validation sessions)"
    )
    panel.model_combo.blockSignals(True)
    panel.run_combo.blockSignals(True)
    panel.split_combo.blockSignals(True)
    panel.model_combo.addItem(long_model, object())
    panel.run_combo.addItem(long_run, object())
    panel.split_combo.addItem("Validation", "validation")
    panel.model_combo.blockSignals(False)
    panel.run_combo.blockSignals(False)
    panel.split_combo.blockSignals(False)

    panel.show()
    panel.setFixedWidth(520)
    panel.resize(520, 620)
    qtbot.wait(50)

    assert panel.evaluation_controls_bar.is_wrapped() is True
    row_positions = {
        control.mapTo(panel.evaluation_controls_bar, QPoint()).y()
        for control in (
            panel.model_combo,
            panel.run_combo,
            panel.split_combo,
            panel.chk_percentage,
        )
    }
    assert len(row_positions) >= 2
    _assert_controls_are_contained_and_disjoint(panel)
    assert panel.model_combo.elided_current_text() != long_model
    assert panel.run_combo.elided_current_text() != long_run
    assert panel.model_combo.toolTip() == long_model
    assert panel.run_combo.toolTip() == long_run


def test_evaluation_controls_wrap_before_assistant_dock_clips_common_values(qtbot):
    panel = EvaluationPanel(parent=None)
    qtbot.addWidget(panel)
    panel.model_combo.blockSignals(True)
    panel.run_combo.blockSignals(True)
    panel.split_combo.blockSignals(True)
    model_label = "Fold 2 (EEGNet with constrained assistant dock width)"
    panel.model_combo.addItem(model_label, object())
    panel.run_combo.addItem("Summary (Finished Runs)", "summary")
    panel.split_combo.addItem("Test", "test")
    panel.model_combo.blockSignals(False)
    panel.run_combo.blockSignals(False)
    panel.split_combo.blockSignals(False)

    panel.setFixedWidth(640)
    panel.resize(640, 620)
    panel.show()
    qtbot.wait(50)

    assert panel.evaluation_controls_bar.is_wrapped() is True
    model_pos = panel.model_combo.mapTo(panel.evaluation_controls_bar, QPoint())
    run_pos = panel.run_combo.mapTo(panel.evaluation_controls_bar, QPoint())
    split_pos = panel.split_combo.mapTo(panel.evaluation_controls_bar, QPoint())
    assert model_pos.y() <= run_pos.y() <= split_pos.y()
    assert split_pos.y() > model_pos.y()
    _assert_controls_are_contained_and_disjoint(panel)
    assert panel.model_combo.elided_current_text() != model_label
    assert panel.model_combo.toolTip() == model_label
    assert panel.run_combo.elided_current_text() != "Summary (Finished Runs)"
    assert panel.run_combo.toolTip() == "Summary (Finished Runs)"


def test_evaluation_charts_use_tabs_when_assistant_reduces_content_width(qtbot):
    panel = EvaluationPanel(parent=None)
    qtbot.addWidget(panel)
    panel.resize(760, 700)
    panel.show()
    qtbot.wait(50)

    chart_tabs = panel.findChild(QTabWidget, "EvaluationChartTabs")

    assert chart_tabs is not None
    assert chart_tabs.isVisible()
    assert chart_tabs.count() == 2
    assert chart_tabs.currentWidget() is panel.matrix_widget
    assert panel.matrix_widget.width() >= 400

    panel.resize(1280, 760)
    qtbot.wait(50)

    assert chart_tabs.isVisible() is False
    assert panel.matrix_widget.isVisible()
    assert panel.bar_chart.isVisible()


def test_evaluation_keeps_data_summary_in_fixed_right_sidebar_across_widths(
    qtbot,
):
    panel = EvaluationPanel(parent=None)
    qtbot.addWidget(panel)

    panel.resize(760, 700)
    panel.show()
    qtbot.wait(50)

    assert panel.info_panel.parentWidget() is panel.right_panel
    assert panel.right_layout.indexOf(panel.info_panel) == 0
    assert panel.right_panel.isVisible()
    plots_group = next(
        group
        for group in panel.findChildren(QGroupBox)
        if group.title() == "EVALUATION PLOTS"
    )
    assert plots_group.height() > panel.bottom_tabs.height()

    panel.resize(1000, 720)
    qtbot.wait(50)

    assert panel.info_panel.parentWidget() is panel.right_panel
    assert panel.right_layout.indexOf(panel.info_panel) == 0
    assert panel.right_panel.isVisible()


def test_evaluation_compact_summary_moves_into_results_tabs(qtbot):
    """Extremely narrow content keeps both the plot and summary readable."""
    panel = EvaluationPanel(parent=None)
    qtbot.addWidget(panel)

    panel.resize(440, 520)
    panel.show()
    qtbot.wait(80)

    assert panel.right_panel.isHidden()
    assert panel.chart_tabs.indexOf(panel.info_panel) >= 0
    assert panel.matrix_widget.width() >= 360

    panel.resize(760, 700)
    qtbot.wait(80)

    assert panel.chart_tabs.indexOf(panel.info_panel) == -1
    assert panel.info_panel.parentWidget() is panel.right_panel
    assert panel.right_panel.isVisible()
    assert panel.right_panel.width() == INFO_SIDEBAR_WIDTH
    assert panel.contentsRect().contains(panel.right_panel.geometry())
    assert not panel.left_widget.geometry().intersects(panel.right_panel.geometry())


def test_evaluation_preserves_readable_plot_height_at_product_minimum(qtbot):
    panel = EvaluationPanel(parent=None)
    qtbot.addWidget(panel)
    panel.resize(440, 470)
    panel.show()
    qtbot.wait(80)

    assert panel.chart_tabs.isVisible()
    assert panel.bottom_tabs.isVisible() is False
    assert {
        panel.chart_tabs.tabText(index) for index in range(panel.chart_tabs.count())
    } == {"Matrix", "Class", "Metrics", "Model", "Data"}
    assert panel.chart_tabs.indexOf(panel.info_panel) >= 0
    assert panel.chk_percentage.width() >= panel.chk_percentage.sizeHint().width()
    tab_bar = panel.chart_tabs.tabBar()
    assert tab_bar is not None
    for index in range(tab_bar.count()):
        text = tab_bar.tabText(index)
        assert tab_bar.tabRect(index).width() >= (
            tab_bar.fontMetrics().horizontalAdvance(text) + 8
        )
    assert panel.matrix_widget.width() >= 180
    assert panel.matrix_widget.height() >= 240
    assert panel.matrix_widget.canvas is not None
    assert panel.matrix_widget.canvas.width() >= 180

    panel.resize(760, 700)
    qtbot.wait(80)

    assert panel.bottom_tabs.isVisible()
    assert panel.chart_tabs.count() == 2
    assert panel.bottom_tabs.indexOf(panel.metrics_tab) == 0
    assert panel.bottom_tabs.indexOf(panel.summary_tab) == 1
    assert panel.info_panel.parentWidget() is panel.right_panel


def test_metrics_table_selection_uses_dark_theme(qtbot):
    table = MetricsTableWidget()
    qtbot.addWidget(table)

    stylesheet = table.styleSheet()

    assert "selection-background-color" in stylesheet
    assert f"selection-background-color: {Theme.TABLE_SELECTION}" in stylesheet
    assert f"alternate-background-color: {Theme.METRICS_TABLE_ALT_BG}" in stylesheet
    assert f"selection-color: {Theme.TEXT_PRIMARY}" in stylesheet
    assert "QTableView::item:selected:!active" in stylesheet
    assert "#ffffff" not in stylesheet.lower().replace(Theme.TEXT_PRIMARY, "")
    assert table.palette().color(QPalette.ColorRole.Base) == QColor(
        Theme.METRICS_TABLE_BG
    )
    assert table.palette().color(QPalette.ColorRole.AlternateBase) == QColor(
        Theme.METRICS_TABLE_ALT_BG
    )
    assert table.palette().color(QPalette.ColorRole.Text) == QColor(Theme.TEXT_PRIMARY)
    assert table.palette().color(QPalette.ColorRole.Highlight) == QColor(
        Theme.TABLE_SELECTION
    )
    assert table.palette().color(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.Highlight,
    ) == QColor(Theme.TABLE_SELECTION)
    assert table.palette().color(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.HighlightedText,
    ) == QColor(Theme.TEXT_PRIMARY)
    assert table.selectionMode() == QTableWidget.SelectionMode.NoSelection


def test_metrics_table_has_no_initial_selection_after_refresh(qtbot):
    table = MetricsTableWidget()
    qtbot.addWidget(table)

    table.update_data(
        {
            0: {
                "precision": 0.8,
                "recall": 0.9,
                "f1-score": 0.85,
                "support": 10,
            },
            1: {
                "precision": 0.7,
                "recall": 0.6,
                "f1-score": 0.65,
                "support": 10,
            },
        }
    )

    assert table.selectedItems() == []
    assert table.currentRow() == -1


def test_metrics_table_fits_small_result_without_empty_viewport(qtbot):
    table = MetricsTableWidget()
    qtbot.addWidget(table)
    table.update_data(
        {
            index: {
                "precision": 0.8,
                "recall": 0.9,
                "f1-score": 0.85,
                "support": 10,
            }
            for index in range(4)
        }
        | {
            "macro_avg": {
                "precision": 0.8,
                "recall": 0.9,
                "f1-score": 0.85,
                "support": 40,
            }
        }
    )
    table.show()
    qtbot.wait(1)

    last_row = table.visualItemRect(table.item(table.rowCount() - 1, 0))
    unused_height = table.viewport().height() - last_row.bottom()

    assert last_row.isValid()
    assert table.viewport().rect().contains(last_row)
    assert not table.verticalScrollBar().isVisible()
    assert unused_height <= 4


def test_metrics_table_sets_dark_background_on_every_metric_cell(qtbot):
    table = MetricsTableWidget()
    qtbot.addWidget(table)

    table.update_data(
        {
            0: {
                "precision": 0.8,
                "recall": 0.9,
                "f1-score": 0.85,
                "support": 10,
            },
            1: {
                "precision": 0.7,
                "recall": 0.6,
                "f1-score": 0.65,
                "support": 10,
            },
            "macro_avg": {
                "precision": 0.75,
                "recall": 0.75,
                "f1-score": 0.75,
                "support": 20,
            },
        }
    )

    expected_row_colors = [
        QColor(Theme.METRICS_TABLE_BG),
        QColor(Theme.METRICS_TABLE_ALT_BG),
        QColor(Theme.TABLE_SELECTION),
    ]
    for row, expected_color in enumerate(expected_row_colors):
        for column in range(table.columnCount()):
            item = table.item(row, column)
            assert item is not None
            assert item.background().color() == expected_color
            assert item.foreground().color() == QColor(Theme.TEXT_PRIMARY)
            assert not item.flags() & Qt.ItemFlag.ItemIsSelectable


def _serialized_evaluation_result(
    *,
    available: bool = True,
    second_run_finished: bool = False,
    second_run_splits: tuple[str, ...] = ("training", "validation", "test"),
    model_summary: tuple[EvaluationSummaryIdentity, str] | None = None,
    generation: int = 4,
) -> CommandResult:
    plans = [
        {
            "identity": {"plan_index": plan_index},
            "name": f"Plan {'AB'[plan_index]}",
            "run_count": 2,
            "finished_run_count": 1 + int(second_run_finished),
            "evaluation_splits": ["test"],
            "runs": [
                {
                    "identity": {
                        "plan_index": plan_index,
                        "run_index": run_index,
                    },
                    "name": f"Repeat-{run_index}",
                    "finished": run_index == 0 or second_run_finished,
                    "evaluation_split": "test" if run_index == 0 else None,
                    "evaluation_splits": (
                        ["training", "validation", "test"]
                        if run_index == 0
                        else list(second_run_splits)
                        if second_run_finished
                        else []
                    ),
                }
                for run_index in range(2)
            ],
        }
        for plan_index in range(2)
    ]
    diagnostics = {
        "payload_type": "evaluation_summary",
        "available": available,
        "plans": plans if available else [],
        "cross_fold_choices": (
            [
                {
                    "identity": {
                        "members": [
                            {"plan_index": 0, "run_index": run_index},
                            {"plan_index": 1, "run_index": run_index},
                        ]
                    },
                    "display_name": "All Folds",
                    "run_label": f"Run {run_index + 1} (Summary)",
                    "evaluation_splits": ["test"],
                    "fold_count": 2,
                    "sample_count": 40,
                }
                for run_index in range(1 + int(second_run_finished))
            ]
            if available
            else []
        ),
        "evaluation_publication_generation": generation,
    }
    if model_summary is not None:
        identity, text = model_summary
        diagnostics["model_summary"] = {
            "identity": identity.to_dict(),
            "text": text,
        }
    return CommandResult.success_result(
        command_name="evaluate",
        message="Evaluation summary ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics=diagnostics,
    )


def _detached_render(request: EvaluationRenderRequest):
    selection = request.selection
    summary_identity = (
        EvaluationSummaryIdentity(plan=selection.plan, run=selection)
        if isinstance(selection, EvaluationRunIdentity)
        else EvaluationSummaryIdentity(plan=selection)
        if isinstance(selection, EvaluationPlanIdentity)
        else None
    )
    support = {"training": 30, "validation": 12, "test": 20}[request.split]
    metrics = MockEvalRecord().get_per_class_metrics()
    metrics[0]["support"] = support
    metrics["macro_avg"]["support"] = support * 2
    return SimpleNamespace(
        request=request,
        data=EvaluationRenderData(
            labels=np.array([0, 1]),
            outputs=np.array([[0.9, 0.1], [0.2, 0.8]]),
            metrics=metrics,
            class_labels={0: "Left hand", 1: "Right hand"},
            summary_identity=summary_identity,
            evaluation_split=request.split,
        ),
    )


class _EvaluationReadSideRuntime(Observable):
    def __init__(self, execute, publication):
        super().__init__()
        self._execute = execute
        self._publication = publication

    def execute(self, command, **kwargs):
        return self._execute(None, command, **kwargs)

    def get_view_publication(self):
        return self._publication["value"]

    def get_evaluation_render(self, request):
        return _detached_render(request)


def _application_publication(
    *,
    generation: int = 4,
    revision: int | None = None,
) -> ApplicationViewPublication:
    initial = ApplicationViewStore(
        ApplicationStateSnapshot.empty(),
        TrainingReadBoundary.no_trainer(),
    ).read()
    effective_revision = generation if revision is None else revision
    state = replace(
        initial.state,
        evaluation=replace(
            initial.state.evaluation,
            available=True,
            total_runs=effective_revision,
        ),
    )
    return replace(
        initial,
        generation=generation,
        revision=effective_revision,
        state=state,
    )


def _install_evaluation_read_side(monkeypatch, execute):
    publication = {"value": _application_publication()}
    runtime = _EvaluationReadSideRuntime(execute, publication)
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.application_ui_runtime",
        lambda _panel: runtime,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command",
        execute,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_application_view_publication",
        lambda _panel, **_kwargs: publication["value"],
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        lambda _panel, request, **_kwargs: _detached_render(request),
    )
    return runtime, publication


def test_evaluation_panel_logic_uses_detached_identity_bound_render(
    qtbot,
    monkeypatch,
):
    """The panel stores identities and renders only detached publication data."""
    calls = []

    def fake_execute(_panel, command, **_kwargs):
        calls.append(command)
        return _serialized_evaluation_result()

    _install_evaluation_read_side(monkeypatch, fake_execute)
    panel = EvaluationPanel(parent=MockMainWindow())
    qtbot.addWidget(panel)

    panel.update_panel()

    assert panel.model_combo.count() == 3
    assert panel.model_combo.itemText(0) == "Fold 1 (Plan A)"
    assert isinstance(panel.model_combo.itemData(0), EvaluationPlanIdentity)
    assert panel.run_combo.count() == 3
    assert panel.run_combo.itemText(0) == "Run 1 (Finished)"
    assert panel.run_combo.itemText(1) == "Run 2"
    assert isinstance(panel.run_combo.itemData(0), EvaluationRunIdentity)
    assert panel.metrics_table.rowCount() == 3
    assert panel.metrics_table.item(0, 0).text() == "Left hand"
    assert panel.split_combo.currentData() == "test"
    assert [
        panel.split_combo.itemData(i) for i in range(panel.split_combo.count())
    ] == [
        "training",
        "validation",
        "test",
    ]
    assert calls == [EvaluateCommand()]

    panel.bar_chart.update_plot = MagicMock()
    panel.run_combo.setCurrentIndex(1)
    assert panel.metrics_table.rowCount() == 0
    panel.bar_chart.update_plot.assert_called_with({})

    panel.model_combo.setCurrentIndex(1)
    assert panel.model_combo.currentData() == EvaluationPlanIdentity(plan_index=1)
    assert panel.run_combo.count() == 3


def test_evaluation_panel_exposes_explicit_cross_fold_summary(
    qtbot,
    monkeypatch,
):
    requests = []

    _install_evaluation_read_side(
        monkeypatch,
        lambda *_args, **_kwargs: _serialized_evaluation_result(),
    )

    def capture_render(_panel, request, **_kwargs):
        requests.append(request)
        return _detached_render(request)

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        capture_render,
    )
    panel = EvaluationPanel(parent=MockMainWindow())
    qtbot.addWidget(panel)
    panel.update_panel()

    panel.model_combo.setCurrentIndex(2)

    assert panel.model_combo.currentText() == "All Folds"
    assert panel.run_combo.count() == 1
    assert panel.run_combo.currentText() == "Run 1 (Summary)"
    assert isinstance(panel.run_combo.currentData(), EvaluationCrossFoldIdentity)
    assert panel.split_combo.currentData() == "test"
    assert isinstance(requests[-1].selection, EvaluationCrossFoldIdentity)
    assert panel.summary_text.toPlainText() == (
        "Model details are available for an individual fold or run."
    )


def test_cross_fold_run_selector_keeps_repeats_separate(qtbot, monkeypatch) -> None:
    requests = []
    _install_evaluation_read_side(
        monkeypatch,
        lambda *_args, **_kwargs: _serialized_evaluation_result(
            second_run_finished=True
        ),
    )

    def capture_render(_panel, request, **_kwargs):
        requests.append(request)
        return _detached_render(request)

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        capture_render,
    )
    panel = EvaluationPanel(parent=MockMainWindow())
    qtbot.addWidget(panel)
    panel.update_panel()

    panel.model_combo.setCurrentIndex(2)
    assert [
        panel.run_combo.itemText(index) for index in range(panel.run_combo.count())
    ] == ["Run 1 (Summary)", "Run 2 (Summary)"]

    panel.run_combo.setCurrentIndex(1)

    selection = requests[-1].selection
    assert isinstance(selection, EvaluationCrossFoldIdentity)
    assert selection.run_index == 1
    assert {member.run_index for member in selection.members} == {1}


def test_evaluation_split_selector_requests_and_renders_the_exact_split(
    qtbot,
    monkeypatch,
):
    requests = []

    def fake_execute(_panel, _command, **_kwargs):
        return _serialized_evaluation_result()

    _install_evaluation_read_side(monkeypatch, fake_execute)

    def capture_render(_panel, request, **_kwargs):
        requests.append(request)
        return _detached_render(request)

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        capture_render,
    )
    panel = EvaluationPanel(parent=MockMainWindow())
    qtbot.addWidget(panel)
    panel.update_panel()

    assert requests[-1].split == "test"
    training_index = panel.split_combo.findData("training")
    panel.split_combo.setCurrentIndex(training_index)

    assert requests[-1].split == "training"
    assert panel.metrics_table.item(0, 4).text() == "30"
    assert panel._evaluation_render.data.evaluation_split == "training"


def test_aggregate_offers_only_splits_saved_for_every_finished_run(
    qtbot,
    monkeypatch,
):
    def fake_execute(_panel, _command, **_kwargs):
        return _serialized_evaluation_result(
            second_run_finished=True,
            second_run_splits=("test",),
        )

    _install_evaluation_read_side(monkeypatch, fake_execute)
    panel = EvaluationPanel(parent=MockMainWindow())
    qtbot.addWidget(panel)
    panel.update_panel()

    panel.split_combo.setCurrentIndex(panel.split_combo.findData("validation"))
    assert panel.split_combo.currentData() == "validation"

    aggregate_index = panel.run_combo.findText("Summary (Finished Runs)")
    assert aggregate_index >= 0
    panel.run_combo.setCurrentIndex(aggregate_index)

    assert [
        panel.split_combo.itemData(index) for index in range(panel.split_combo.count())
    ] == ["test"]
    assert panel.split_combo.currentData() == "test"
    assert panel._evaluation_render.data.evaluation_split == "test"


def test_invalid_evaluation_selection_clears_cached_split_render(qtbot, monkeypatch):
    def fake_execute(_panel, _command, **_kwargs):
        return _serialized_evaluation_result()

    _install_evaluation_read_side(monkeypatch, fake_execute)
    panel = EvaluationPanel(parent=MockMainWindow())
    qtbot.addWidget(panel)
    panel.update_panel()
    assert panel._evaluation_render is not None

    panel.run_combo.setCurrentIndex(1)

    assert panel._evaluation_render is None
    panel.matrix_widget.update_plot = MagicMock()
    panel.chk_percentage.setChecked(True)
    panel.matrix_widget.update_plot.assert_not_called()


def test_show_percentages_redraws_only_the_confusion_matrix(qtbot, monkeypatch):
    def fake_execute(_panel, _command, **_kwargs):
        return _serialized_evaluation_result()

    _install_evaluation_read_side(monkeypatch, fake_execute)
    panel = EvaluationPanel(parent=MockMainWindow())
    qtbot.addWidget(panel)
    panel.update_panel()

    panel.matrix_widget.update_plot = MagicMock()
    panel.metrics_table.update_data = MagicMock()
    panel.bar_chart.update_plot = MagicMock()
    panel.chk_percentage.setChecked(True)

    panel.matrix_widget.update_plot.assert_called_once()
    panel.metrics_table.update_data.assert_not_called()
    panel.bar_chart.update_plot.assert_not_called()


def test_evaluation_panel_blocks_non_held_out_render_without_retrying(
    qtbot,
    monkeypatch,
):
    def fake_execute(_panel, _command, **_kwargs):
        return _serialized_evaluation_result()

    def unavailable_render(*_args, **_kwargs):
        raise PreconditionError(
            "Training-split metrics are diagnostics, not final evaluation.",
            diagnostics={
                "evaluation_final_unavailable": True,
                "retryable": False,
            },
        )

    _install_evaluation_read_side(monkeypatch, fake_execute)
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        unavailable_render,
    )
    panel = EvaluationPanel(parent=MockMainWindow())
    qtbot.addWidget(panel)

    panel.update_panel()

    assert panel.plot_stack.currentIndex() == 1
    assert panel.no_data_label.text() == (
        "Training-split metrics are diagnostics, not final evaluation."
    )
    assert panel.bottom_tabs.isVisible() is False
    assert panel.split_combo.currentData() == "test"


def test_evaluation_panel_fails_closed_when_application_query_is_blocked(qtbot):
    """A blocked summary must not leave stale Evaluation selections visible."""

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    main_window = RealMainWindow()
    panel = EvaluationPanel(parent=main_window)
    qtbot.addWidget(panel)

    panel.update_panel()

    assert panel._evaluation_summary is None
    assert panel._evaluation_error is not None
    assert "Create a training plan" in panel._evaluation_error
    assert panel.model_combo.count() == 0
    assert panel.model_combo.isEnabled() is False
    assert "Create a training plan" in panel.model_combo.toolTip()
    assert panel.run_combo.count() == 0
    assert panel.bottom_tabs.isVisible() is False


def test_evaluation_panel_reuses_application_query_until_marked_dirty(
    qtbot,
    monkeypatch,
):
    """Navigation refreshes should not rerun the expensive evaluation query."""

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    calls = []

    def fake_execute(_panel, command, **_kwargs):
        calls.append(command)
        return CommandResult.success_result(
            command_name="evaluate",
            message="No completed training runs are available for evaluation yet.",
            state={},
            changed_state=ChangedState(),
            diagnostics={
                "payload_type": "evaluation_summary",
                "available": False,
                "plans": [],
                "evaluation_publication_generation": _kwargs[
                    "expected_publication_generation"
                ],
            },
        )

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command",
        fake_execute,
    )

    panel = EvaluationPanel(parent=RealMainWindow())
    qtbot.addWidget(panel)

    panel.update_panel()
    panel.update_panel()

    assert len(calls) == 1
    assert isinstance(calls[0], EvaluateCommand)
    assert calls[0] == EvaluateCommand()

    panel.mark_refresh_dirty()
    panel.update_panel()

    assert len(calls) == 2


def test_evaluation_panel_rejects_catalog_when_publication_generation_changes(
    qtbot,
    monkeypatch,
):
    """Catalog identities must never be rebound to a newer publication."""

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    expected_generations = []

    def fake_execute(_panel, _command, **kwargs):
        expected_generations.append(kwargs["expected_publication_generation"])
        return _serialized_evaluation_result()

    publications = iter(
        [
            _application_publication(generation=4),
            _application_publication(generation=5),
        ]
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command",
        fake_execute,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_application_view_publication",
        lambda _panel, **_kwargs: next(publications),
    )

    panel = EvaluationPanel(parent=RealMainWindow())
    qtbot.addWidget(panel)
    panel.update_panel()

    assert expected_generations == [4]
    assert panel._application_generation is None
    assert panel._evaluation_summary is None
    assert panel._application_summary_dirty is True
    assert panel.model_combo.count() == 0
    assert panel.model_combo.toolTip() == (
        "Evaluation results are temporarily unavailable."
    )


def test_evaluation_panel_requests_identity_bound_model_summary(qtbot, monkeypatch):
    """Model-summary requests carry only the selected stable identity."""

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    calls = []

    def fake_execute(_panel, command, **_kwargs):
        calls.append(command)
        return _serialized_evaluation_result(
            second_run_finished=True,
            model_summary=(
                command.summary_identity,
                "Service run 1 summary",
            )
            if command.summary_identity is not None
            else None,
        )

    _install_evaluation_read_side(monkeypatch, fake_execute)

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        on_result(fake_execute(_panel, command))
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command_async",
        fake_execute_async,
    )
    panel = EvaluationPanel(parent=RealMainWindow())
    qtbot.addWidget(panel)

    panel.update_panel()

    assert panel.model_combo.count() == 3
    assert panel.model_combo.itemText(0) == "Fold 1 (Plan A)"
    assert (
        panel.summary_text.toPlainText() == "Open Model Summary to load model details."
    )
    assert calls[0] == EvaluateCommand()

    panel.bottom_tabs.setCurrentWidget(panel.summary_tab)

    run_identity = EvaluationRunIdentity(
        plan=EvaluationPlanIdentity(plan_index=0),
        run_index=0,
    )
    assert calls[-1] == EvaluateCommand(
        summary_identity=EvaluationSummaryIdentity(
            plan=run_identity.plan,
            run=run_identity,
        )
    )
    assert panel.summary_text.toPlainText() == "Service run 1 summary"

    panel.model_combo.setCurrentIndex(1)
    panel.run_combo.setCurrentIndex(1)

    selected_run = EvaluationRunIdentity(
        plan=EvaluationPlanIdentity(plan_index=1),
        run_index=1,
    )
    assert calls[-1] == EvaluateCommand(
        summary_identity=EvaluationSummaryIdentity(
            plan=selected_run.plan,
            run=selected_run,
        )
    )


def test_evaluation_panel_shows_placeholder_when_service_summary_missing(
    qtbot, monkeypatch
):
    """Service-owned evaluation data should not render a blank Model Summary tab."""

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    _install_evaluation_read_side(
        monkeypatch,
        lambda _panel, command, **_kwargs: _serialized_evaluation_result(
            model_summary=(command.summary_identity, "")
            if command.summary_identity is not None
            else None,
        ),
    )

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        on_result(
            _serialized_evaluation_result(
                model_summary=(command.summary_identity, ""),
            )
        )
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command_async",
        fake_execute_async,
    )

    panel = EvaluationPanel(parent=RealMainWindow())
    qtbot.addWidget(panel)

    panel.update_panel()
    panel.bottom_tabs.setCurrentWidget(panel.summary_tab)

    assert "Model summary unavailable" in panel.summary_text.toPlainText()


def test_evaluation_panel_does_not_sync_load_model_summary_when_worker_unavailable(
    qtbot,
    monkeypatch,
):
    """Model Summary must not block the UI by falling back to sync service calls."""

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    calls = []

    def fake_execute(_panel, command, **_kwargs):
        calls.append(command)
        return _serialized_evaluation_result()

    _install_evaluation_read_side(monkeypatch, fake_execute)
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command_async",
        lambda *_args, **_kwargs: False,
    )

    panel = EvaluationPanel(parent=RealMainWindow())
    qtbot.addWidget(panel)

    panel.update_panel()
    panel.bottom_tabs.setCurrentWidget(panel.summary_tab)

    assert len(calls) == 1
    assert calls[0] == EvaluateCommand()
    assert "could not start in the background" in panel.summary_text.toPlainText()


def test_evaluation_panel_query_none_fails_closed(
    qtbot,
    monkeypatch,
):
    """An invalid command response must clear the identity catalog."""

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command",
        lambda *_args, **_kwargs: None,
    )
    panel = EvaluationPanel(parent=RealMainWindow())
    qtbot.addWidget(panel)

    panel.update_panel()

    assert panel.model_combo.count() == 0
    assert panel.model_combo.isEnabled() is False
    assert panel.model_combo.toolTip() == "No evaluation results available yet."
    assert panel.run_combo.count() == 0


def test_evaluation_panel_rejects_non_identity_combo_state(
    qtbot,
    monkeypatch,
):
    """Foreign combo payloads must not be interpreted as backend objects."""

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command",
        lambda *_args, **_kwargs: None,
    )
    render = MagicMock(
        side_effect=AssertionError("invalid selection must not request a render"),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        render,
    )
    panel = EvaluationPanel(parent=RealMainWindow())
    qtbot.addWidget(panel)
    stale_plan = MockPlanHolder("Stale Plan")
    panel.model_combo.clear()
    panel.model_combo.addItem("Fold 1: Stale Plan", stale_plan)
    panel.run_combo.clear()
    panel.run_combo.addItem("Average", "average")

    panel.update_views()

    render.assert_not_called()
    assert panel.metrics_table.rowCount() == 0
    assert panel.summary_text.toPlainText() == ""


def test_evaluation_panel_clears_metrics_when_detached_average_is_unavailable(
    qtbot,
    monkeypatch,
):
    """A missing pooled publication must clear the prior run metrics."""

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    _install_evaluation_read_side(
        monkeypatch,
        lambda *_args, **_kwargs: _serialized_evaluation_result(),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        lambda _panel, request, **_kwargs: (
            None
            if isinstance(request.selection, EvaluationPlanIdentity)
            else _detached_render(request)
        ),
    )

    panel = EvaluationPanel(parent=RealMainWindow())
    qtbot.addWidget(panel)

    panel.update_panel()
    assert panel.metrics_table.rowCount() > 0

    average_index = panel.run_combo.findText("Summary (Finished Runs)")
    assert average_index >= 0
    panel.run_combo.setCurrentIndex(average_index)

    assert panel.metrics_table.rowCount() == 0


def test_evaluation_panel_clears_stale_plans_on_new_application_revision(
    qtbot,
    monkeypatch,
):
    """A new application revision clears stale evaluation plan selections."""
    main_window = MockMainWindow()
    available = True
    generation = 4

    def execute(*_args, **_kwargs):
        return _serialized_evaluation_result(
            available=available,
            generation=generation,
        )

    runtime, publication = _install_evaluation_read_side(monkeypatch, execute)
    panel = EvaluationPanel(parent=main_window)
    qtbot.addWidget(panel)

    panel.update_panel()
    assert panel.model_combo.count() == 3
    assert panel.model_combo.itemText(0) == "Fold 1 (Plan A)"

    available = False
    generation = 5
    publication["value"] = _application_publication(generation=5, revision=5)
    runtime.notify(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        publication["value"],
    )
    qtbot.wait(50)

    assert panel.model_combo.count() == 0
    assert panel.model_combo.isEnabled() is False
    assert panel.model_combo.toolTip() == "No evaluation results available yet."
    assert panel.run_combo.count() == 0


def test_evaluation_panel_preserves_selected_plan_and_average_on_new_revision(
    qtbot,
    monkeypatch,
):
    """A new revision keeps the current selection when it remains valid."""
    main_window = MockMainWindow()
    runtime, publication = _install_evaluation_read_side(
        monkeypatch,
        lambda *_args, **_kwargs: _serialized_evaluation_result(),
    )
    panel = EvaluationPanel(parent=main_window)
    qtbot.addWidget(panel)

    panel.update_panel()
    panel.model_combo.setCurrentIndex(1)
    panel.run_combo.setCurrentIndex(2)

    assert panel.model_combo.currentText() == "Fold 2 (Plan B)"
    assert panel.run_combo.currentText() == "Summary (Finished Runs)"

    publication["value"] = _application_publication(generation=4, revision=5)
    runtime.notify(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        publication["value"],
    )
    qtbot.wait(50)

    assert panel.model_combo.currentText() == "Fold 2 (Plan B)"
    assert panel.run_combo.currentText() == "Summary (Finished Runs)"


def test_evaluation_panel_preserves_selected_repeat_when_revision_changes_label(
    qtbot,
    monkeypatch,
):
    """A revision keeps a run identity even when its status label changes."""
    main_window = MockMainWindow()
    second_run_finished = False

    def execute(*_args, **_kwargs):
        return _serialized_evaluation_result(
            second_run_finished=second_run_finished,
        )

    runtime, publication = _install_evaluation_read_side(monkeypatch, execute)
    panel = EvaluationPanel(parent=main_window)
    qtbot.addWidget(panel)

    panel.update_panel()
    panel.run_combo.setCurrentIndex(1)

    assert panel.run_combo.currentText() == "Run 2"
    target_identity = EvaluationRunIdentity(
        plan=EvaluationPlanIdentity(plan_index=0),
        run_index=1,
    )
    assert panel.run_combo.currentData() == target_identity

    second_run_finished = True
    publication["value"] = _application_publication(generation=4, revision=5)
    runtime.notify(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        publication["value"],
    )
    qtbot.wait(50)

    assert panel.run_combo.currentData() == target_identity
    assert panel.run_combo.currentText() == "Run 2 (Finished)"


def test_evaluation_panel_resets_index_only_selection_for_a_new_generation(
    qtbot,
    monkeypatch,
):
    """Plan/run indices from one generation must not identify replacement history."""
    main_window = MockMainWindow()
    generation = 4

    def execute(_panel, _command, **_kwargs):
        return _serialized_evaluation_result(generation=generation)

    runtime, publication = _install_evaluation_read_side(monkeypatch, execute)
    panel = EvaluationPanel(parent=main_window)
    qtbot.addWidget(panel)

    panel.update_panel()
    panel.model_combo.setCurrentIndex(1)
    panel.run_combo.setCurrentIndex(2)
    assert panel.model_combo.currentText() == "Fold 2 (Plan B)"
    assert panel.run_combo.currentText() == "Summary (Finished Runs)"

    generation = 5
    publication["value"] = _application_publication(generation=5, revision=5)
    runtime.notify(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        publication["value"],
    )

    qtbot.waitUntil(
        lambda: panel.model_combo.currentText() == "Fold 1 (Plan A)",
        timeout=2_000,
    )
    assert panel.run_combo.currentText() == "Run 1 (Finished)"
