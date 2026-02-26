"""Coverage tests for DataSplittingPreviewDialog, TrainingManagerWindow, and more UI panels."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QTableWidget

# ============ DataSplittingPreviewDialog ============


class TestDataSplittingPreviewDialog:
    @pytest.fixture
    def epoch_data(self):
        ed = MagicMock()
        ed.get_data_length.return_value = 100
        ed.subject_map = {"S01": list(range(50)), "S02": list(range(50, 100))}
        ed.session_map = {"sess1": list(range(100))}
        ed.label_map = {"left": 0, "right": 1}
        ed.data = MagicMock()
        ed.get_subject_map.return_value = ed.subject_map
        ed.get_session_map.return_value = ed.session_map
        return ed

    @pytest.fixture
    def config(self):
        from XBrainLab.backend.dataset import TrainingType

        cfg = MagicMock()
        cfg.train_type = TrainingType.FULL
        cfg.is_cross_validation = False
        cfg.get_splitter_option.return_value = ([], [])
        return cfg

    def test_creates(self, qtbot, epoch_data, config):
        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.DatasetGenerator"
            ) as MockGen,
            patch("threading.Thread"),
        ):
            MockGen.return_value.preview_failed = None
            from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
                DataSplittingPreviewDialog,
            )

            dlg = DataSplittingPreviewDialog(None, "Preview", epoch_data, config)
            qtbot.addWidget(dlg)
            # Stop timer
            if hasattr(dlg, "timer"):
                dlg.timer.stop()
            assert dlg.windowTitle() == "Preview"

    def test_get_result_default(self, qtbot, epoch_data, config):
        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.DatasetGenerator"
            ) as MockGen,
            patch("threading.Thread"),
        ):
            MockGen.return_value.preview_failed = None
            from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
                DataSplittingPreviewDialog,
            )

            dlg = DataSplittingPreviewDialog(None, "Preview", epoch_data, config)
            qtbot.addWidget(dlg)
            if hasattr(dlg, "timer"):
                dlg.timer.stop()
            # get_result returns the generator mock (since we mocked DatasetGenerator)
            result = dlg.get_result()
            # Just verify get_result() is callable without error


# ============ TrainingManagerWindow ============


class TestTrainingManagerWindow:
    @pytest.fixture
    def trainer(self):
        t = MagicMock()
        plan = MagicMock()
        plan.get_name.return_value = "Plan_0"
        plan.get_training_status.return_value = "idle"
        plan.get_training_epoch.return_value = "0/10"
        plan.get_training_evaluation.return_value = "N/A"
        t.get_training_plan_holders.return_value = [plan]
        t.is_running.return_value = False
        t.get_progress_text.return_value = "Ready"
        return t

    @pytest.fixture
    def window(self, qtbot, trainer):
        from XBrainLab.ui.panels.training.training_manager import (
            TrainingManagerWindow,
        )

        w = TrainingManagerWindow(None, trainer)
        qtbot.addWidget(w)
        # Stop timer
        w.timer.stop()
        yield w
        w.close()

    def test_creates(self, window):
        assert window is not None

    def test_has_table(self, window):
        assert isinstance(window.plan_table, QTableWidget)

    def test_update_table(self, window):
        window.update_table()

    def test_update_loop_not_running(self, window):
        window.update_loop()

    def test_start_training(self, window):
        window.start_training()
        window.trainer.run.assert_called()

    def test_stop_training(self, window):
        window.trainer.is_running.return_value = True
        window.stop_training()
        window.trainer.set_interrupt.assert_called()

    def test_finish_training(self, window):
        with patch("PyQt6.QtWidgets.QMessageBox.information"):
            window.finish_training()

    def test_plot_loss(self, window):
        with patch("XBrainLab.ui.panels.training.training_manager.PlotFigureWindow"):
            window.plot_loss()

    def test_plot_acc(self, window):
        with patch("XBrainLab.ui.panels.training.training_manager.PlotFigureWindow"):
            window.plot_acc()


# ============ VisualizationPanel ============


class TestVisualizationPanel:
    @pytest.fixture
    def panel(self, qtbot):
        from PyQt6.QtWidgets import QWidget

        def make_widget_factory():
            """Return a factory that creates real QWidgets so they can be added to tabs."""

            def factory(*args, **kwargs):
                w = QWidget(*args)
                w.update_plot = MagicMock()
                return w

            return factory

        with (
            patch(
                "XBrainLab.ui.panels.visualization.panel.SaliencyMapWidget",
                side_effect=make_widget_factory(),
            ),
            patch(
                "XBrainLab.ui.panels.visualization.panel.SaliencySpectrogramWidget",
                side_effect=make_widget_factory(),
            ),
            patch(
                "XBrainLab.ui.panels.visualization.panel.SaliencyTopographicMapWidget",
                side_effect=make_widget_factory(),
            ),
            patch(
                "XBrainLab.ui.panels.visualization.panel.Saliency3DPlotWidget",
                side_effect=make_widget_factory(),
            ),
            patch("XBrainLab.ui.panels.visualization.panel.QtObserverBridge"),
        ):
            from XBrainLab.ui.panels.visualization.panel import VisualizationPanel

            ctrl = MagicMock()
            ctrl.get_trainers.return_value = []
            train_ctrl = MagicMock()
            p = VisualizationPanel(controller=ctrl, training_controller=train_ctrl)
            qtbot.addWidget(p)
            yield p

    def test_creates(self, panel):
        assert panel is not None

    def test_get_trainers(self, panel):
        result = panel.get_trainers()
        assert isinstance(result, list)

    def test_refresh_combos(self, panel):
        panel.refresh_combos()

    def test_on_plan_changed(self, panel):
        panel.on_plan_changed("---")

    def test_on_tab_changed(self, panel):
        panel.on_tab_changed(0)

    def test_update_info(self, panel):
        panel.update_info()

    def test_update_panel(self, panel):
        panel.update_panel()


# ============ EvaluationPanel ============


class TestEvaluationPanel:
    @pytest.fixture
    def panel(self, qtbot):
        from PyQt6.QtWidgets import QWidget

        def make_widget_factory():
            def factory(*args, **kwargs):
                w = QWidget()
                w.update_plot = MagicMock()
                w.clear = MagicMock()
                return w

            return factory

        with (
            patch(
                "XBrainLab.ui.panels.evaluation.panel.ConfusionMatrixWidget",
                side_effect=make_widget_factory(),
            ),
            patch(
                "XBrainLab.ui.panels.evaluation.panel.MetricsBarChartWidget",
                side_effect=make_widget_factory(),
            ),
            patch("XBrainLab.ui.panels.evaluation.panel.QtObserverBridge"),
        ):
            from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel

            ctrl = MagicMock()
            ctrl.get_plans.return_value = []
            train_ctrl = MagicMock()
            p = EvaluationPanel(controller=ctrl, training_controller=train_ctrl)
            qtbot.addWidget(p)
            yield p

    def test_creates(self, panel):
        assert panel is not None

    def test_update_panel(self, panel):
        panel.update_panel()

    def test_on_model_changed(self, panel):
        panel.on_model_changed(0)

    def test_update_info(self, panel):
        panel.update_info()
