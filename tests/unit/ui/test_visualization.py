"""Coverage tests for saliency views: map, spectrogram, topomap, 3D engine basics."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np

# ============ Saliency3DEngine ============


class TestSaliency3DEngine:
    def test_creates(self):
        """Engine creates with default scale and begins async model loading."""
        with patch(
            "XBrainLab.backend.visualization.saliency_3d_engine.Saliency3DEngine._load_models"
        ):
            from XBrainLab.backend.visualization.saliency_3d_engine import (
                Saliency3DEngine,
            )

            engine = Saliency3DEngine(mesh_scale_scalar=0.8)
            assert engine.mesh_scale_scalar == 0.8
            assert engine.head_mesh is None
            assert engine.brain_mesh is None

    def test_update_scalars_returns_none_when_no_data(self):
        with patch(
            "XBrainLab.backend.visualization.saliency_3d_engine.Saliency3DEngine._load_models"
        ):
            from XBrainLab.backend.visualization.saliency_3d_engine import (
                Saliency3DEngine,
            )

            engine = Saliency3DEngine()
            result = engine.update_scalars(0)
            assert result is None

    def test_on_download_complete_error(self):
        with patch(
            "XBrainLab.backend.visualization.saliency_3d_engine.Saliency3DEngine._load_models"
        ):
            from XBrainLab.backend.visualization.saliency_3d_engine import (
                Saliency3DEngine,
            )

            engine = Saliency3DEngine()
            # Should not raise on error result
            engine._on_download_complete("Error: connection timeout")


# ============ SaliencyMapWidget ============


class TestSaliencyMapWidget:
    def test_creates(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.map_view import (
            SaliencyMapWidget,
        )

        w = SaliencyMapWidget()
        qtbot.addWidget(w)
        assert isinstance(w, SaliencyMapWidget)

    def test_update_plot_no_eval(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.map_view import (
            SaliencyMapWidget,
        )

        w = SaliencyMapWidget()
        qtbot.addWidget(w)
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        w.update_plot(plan, None, None, None, None)

    def test_update_plot_replaces_canvas_with_visualizer_figure(self, qtbot):
        from matplotlib.figure import Figure

        from XBrainLab.ui.panels.visualization.saliency_views.map_view import (
            SaliencyMapWidget,
        )

        w = SaliencyMapWidget()
        qtbot.addWidget(w)

        plan = MagicMock()
        eval_rec = MagicMock()
        eval_rec.gradient = {0: np.random.randn(5, 4, 100)}
        plan.get_eval_record.return_value = eval_rec

        trainer = MagicMock()
        epoch = MagicMock()
        epoch.event_id = {"left": 0}
        epoch.get_channel_names.return_value = ["C3", "C4", "Cz", "Fz"]
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch

        visualizer = MagicMock()
        new_fig = Figure(figsize=(4, 3), dpi=100)
        visualizer.get_plt.return_value = new_fig

        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.map_view.VisualizerType"
        ) as visualizer_type:
            visualizer_type.SaliencyMap.value.return_value = visualizer
            w.update_plot(plan, trainer, "Gradient", False, None)

        plan.get_eval_record.assert_called_once_with()
        visualizer_type.SaliencyMap.value.assert_called_once_with(eval_rec, epoch)
        visualizer.get_plt.assert_called_once_with(method="Gradient", absolute=False)
        assert w.fig is new_fig
        assert w.canvas is not None
        assert w.canvas.parent() is w
        assert not w.error_label.isVisible()

    def test_close_releases_figure_and_canvas(self, qtbot):
        from PyQt6.QtGui import QCloseEvent

        from XBrainLab.ui.panels.visualization.saliency_views import base_saliency_view
        from XBrainLab.ui.panels.visualization.saliency_views.map_view import (
            SaliencyMapWidget,
        )

        w = SaliencyMapWidget()
        qtbot.addWidget(w)
        fig = w.fig

        with patch.object(base_saliency_view.plt, "close") as close_figure:
            w.closeEvent(QCloseEvent())

        close_figure.assert_called_once_with(fig)
        assert w.fig is None
        assert w.canvas is None

    def test_replace_figure_releases_previous_canvas(self, qtbot):
        from matplotlib.figure import Figure

        from XBrainLab.ui.panels.visualization.saliency_views import base_saliency_view
        from XBrainLab.ui.panels.visualization.saliency_views.map_view import (
            SaliencyMapWidget,
        )

        w = SaliencyMapWidget()
        qtbot.addWidget(w)
        old_fig = w.fig
        old_canvas = w.canvas
        assert old_canvas is not None
        new_fig = Figure(figsize=(5, 4), dpi=100)

        with patch.object(base_saliency_view.plt, "close") as close_figure:
            w._replace_figure(new_fig)

        close_figure.assert_called_once_with(old_fig)
        assert w.fig is new_fig
        assert w.canvas is not old_canvas
        assert old_canvas.parent() is None


# ============ SaliencySpectrogramWidget ============


class TestSaliencySpectrogramWidget:
    def test_creates(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view import (
            SaliencySpectrogramWidget,
        )

        w = SaliencySpectrogramWidget()
        qtbot.addWidget(w)
        assert isinstance(w, SaliencySpectrogramWidget)

    def test_update_plot_no_eval(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view import (
            SaliencySpectrogramWidget,
        )

        w = SaliencySpectrogramWidget()
        qtbot.addWidget(w)
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        w.update_plot(plan, None, None, None, None)


# ============ SaliencyTopographicMapWidget ============


class TestSaliencyTopographicMapWidget:
    def test_creates(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.topomap_view import (
            SaliencyTopographicMapWidget,
        )

        w = SaliencyTopographicMapWidget()
        qtbot.addWidget(w)
        assert isinstance(w, SaliencyTopographicMapWidget)

    def test_update_plot_no_eval(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.topomap_view import (
            SaliencyTopographicMapWidget,
        )

        w = SaliencyTopographicMapWidget()
        qtbot.addWidget(w)
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        w.update_plot(plan, None, None, None, None)


# ============ Saliency3DPlotWidget ============


class TestSaliency3DPlotWidget:
    def test_creates(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ):
            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            assert isinstance(w, Saliency3DPlotWidget)

    def test_show_error(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ):
            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            w.show_error("test error")

    def test_show_message(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ):
            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            w.show_message("test message")

    def test_clear_plot(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ):
            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            w.clear_plot()
            # Calling twice should be fine
            w.clear_plot()

    def test_clear_plot_schedules_child_widgets_for_deletion(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ):
            from PyQt6.QtWidgets import QLabel, QWidget

            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            class CleanupLabel(QLabel):
                deleted = False

                def deleteLater(self):
                    self.deleted = True
                    super().deleteLater()

            class CleanupPlotter(QWidget):
                closed = False
                deleted = False

                def close(self):
                    self.closed = True
                    return super().close()

                def deleteLater(self):
                    self.deleted = True
                    super().deleteLater()

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            label = CleanupLabel("temporary")
            plotter = CleanupPlotter()
            w.plot_layout.addWidget(label)
            w.plot_layout.addWidget(plotter)
            cast(Any, w).plotter_widget = plotter

            w.clear_plot()

            assert label.deleted is True
            assert plotter.closed is True
            assert plotter.deleted is True
            assert w.plotter_widget is None

    def test_update_plot_blocks_offscreen_before_qtinteractor(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ) as pyvistaqt:
            from PyQt6.QtWidgets import QLabel

            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)

            eval_record = MagicMock()
            plan = MagicMock()
            plan.get_eval_record.return_value = eval_record
            epoch = MagicMock()
            epoch.get_montage_position.return_value = [(0.0, 0.0, 0.0)]
            epoch.event_id = {"left": 0}
            trainer = MagicMock()
            trainer.get_dataset.return_value.get_epoch_data.return_value = epoch

            w.update_plot(plan, trainer, "Gradient", False, eval_record)

            pyvistaqt.QtInteractor.assert_not_called()
            visible_labels = [
                label.text()
                for label in w.findChildren(QLabel)
                if not label.isHidden() and label.text()
            ]
            assert any(
                "interactive OpenGL desktop session" in text for text in visible_labels
            )
