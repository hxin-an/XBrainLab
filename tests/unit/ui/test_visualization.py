"""Coverage tests for saliency views: map, spectrogram, topomap, 3D engine basics."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
from PyQt6 import sip
from PyQt6.QtCore import Qt

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

    def test_missing_3d_models_do_not_start_network_download(self, tmp_path):
        from XBrainLab.backend.visualization.saliency_3d_engine import (
            Saliency3DEngine,
        )

        with (
            patch(
                "XBrainLab.backend.visualization.saliency_3d_engine.os.path.dirname",
                return_value=str(tmp_path),
            ),
            patch.object(Saliency3DEngine, "_init_meshes") as init_meshes,
            patch(
                "XBrainLab.backend.visualization.saliency_3d_engine.logger",
            ) as logger,
        ):
            engine = Saliency3DEngine()

        assert "not installed" in engine.model_error
        logger.warning.assert_called_once()
        init_meshes.assert_not_called()

    def test_resolves_original_event_code_to_gradient_class_index(self):
        with patch(
            "XBrainLab.backend.visualization.saliency_3d_engine.Saliency3DEngine._load_models"
        ):
            from XBrainLab.backend.visualization.saliency_3d_engine import (
                Saliency3DEngine,
            )

            eval_record = MagicMock()
            eval_record.gradient = {
                0: np.zeros((2, 4, 16)),
                1: np.ones((2, 4, 16)),
            }
            epoch_data = MagicMock()
            epoch_data.event_id = {"769": 769, "770": 770}

            key = Saliency3DEngine._resolve_saliency_label_key(
                eval_record.gradient,
                epoch_data,
                "769",
            )

        assert key == 0

    def test_translated_channel_position_accepts_tuple_and_list(self):
        with patch(
            "XBrainLab.backend.visualization.saliency_3d_engine.Saliency3DEngine._load_models"
        ):
            from XBrainLab.backend.visualization.saliency_3d_engine import (
                Saliency3DEngine,
            )

            translated = Saliency3DEngine._translated_channel_position(
                (0.1, 0.2, 0.3),
                [-0.01, 0.02, 0.03],
            )

        assert np.allclose(translated, np.array([0.09, 0.22, 0.33]))

    def test_process_data_maps_tuple_montage_positions_without_type_error(self):
        class MeshStub:
            bounds = (0.0, 0.0, 0.0, 0.0, 0.0, 0.2)
            n_points = 3
            points = np.zeros((3, 3))

            def copy(self):
                return self

            def scale(self, *_args, **_kwargs):
                return self

            def triangulate(self):
                return self

        with (
            patch(
                "XBrainLab.backend.visualization.saliency_3d_engine.Saliency3DEngine._load_models"
            ),
            patch(
                "XBrainLab.backend.visualization.saliency_3d_engine.channel_convex_hull",
                return_value=MeshStub(),
            ),
        ):
            from XBrainLab.backend.visualization.saliency_3d_engine import (
                Saliency3DEngine,
            )

            engine = Saliency3DEngine()
            engine.head_mesh = MeshStub()
            engine.brain_mesh = MeshStub()
            eval_record = MagicMock()
            eval_record.gradient = {0: np.ones((2, 3, 5))}
            epoch_data = MagicMock()
            epoch_data.event_id = {"769": 769}
            epoch_data.get_montage_position.return_value = [
                (0.0, 0.0, 0.0),
                (0.01, 0.02, 0.03),
                (0.02, 0.03, 0.04),
            ]
            epoch_data.get_channel_names.return_value = ["Cz", "C3", "C4"]

            channel_count = engine.process_data(eval_record, epoch_data, "769")

        assert channel_count == 3
        assert engine.pos_on_3d is not None
        assert engine.pos_on_3d.shape == (3, 3)

    def test_process_data_uses_selected_method_and_absolute_value(self):
        class MeshStub:
            bounds = (0.0, 0.0, 0.0, 0.0, 0.0, 0.2)
            n_points = 3
            points = np.zeros((3, 3))

            def __setitem__(self, _key, _value):
                pass

            def copy(self):
                return self

            def scale(self, *_args, **_kwargs):
                return self

            def triangulate(self):
                return self

        with (
            patch(
                "XBrainLab.backend.visualization.saliency_3d_engine.Saliency3DEngine._load_models"
            ),
            patch(
                "XBrainLab.backend.visualization.saliency_3d_engine.channel_convex_hull",
                return_value=MeshStub(),
            ),
        ):
            from XBrainLab.backend.visualization.saliency_3d_engine import (
                Saliency3DEngine,
            )

            engine = Saliency3DEngine()
            engine.head_mesh = MeshStub()
            engine.brain_mesh = MeshStub()
            eval_record = MagicMock()
            eval_record.gradient = {0: np.full((2, 3, 5), 99.0)}
            eval_record.vargrad = {
                0: np.array(
                    [
                        [[-1, -2, -3, -4, -5]] * 3,
                        [[2, 3, 4, 5, 6]] * 3,
                    ],
                    dtype=float,
                )
            }
            epoch_data = MagicMock()
            epoch_data.event_id = {"769": 769}
            epoch_data.get_montage_position.return_value = [
                (0.0, 0.0, 0.0),
                (0.01, 0.02, 0.03),
                (0.02, 0.03, 0.04),
            ]
            epoch_data.get_channel_names.return_value = ["Cz", "C3", "C4"]

            engine.process_data(
                eval_record,
                epoch_data,
                "769",
                method="VarGrad",
                absolute=True,
            )

        assert engine.saliency is not None
        assert np.allclose(engine.saliency[0], np.array([1.5, 2.5, 3.5, 4.5, 5.5]))
        assert engine.scalar_bar_range == [1.5, 5.5]


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

    def test_update_plot_renders_visualizer_without_worker_thread(self, qtbot):
        from matplotlib.figure import Figure

        from XBrainLab.ui.panels.visualization.saliency_views.map_view import (
            SaliencyMapWidget,
        )

        w = SaliencyMapWidget()
        qtbot.addWidget(w)

        plan = MagicMock()
        eval_rec = MagicMock()
        plan.get_eval_record.return_value = eval_rec

        trainer = MagicMock()
        epoch = MagicMock()
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch
        visualizer = MagicMock()
        visualizer.get_plt.return_value = Figure(figsize=(4, 3), dpi=100)

        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.map_view.VisualizerType"
        ) as visualizer_type:
            visualizer_type.SaliencyMap.value.return_value = visualizer
            w.update_plot(plan, trainer, "Gradient", False, None)

        visualizer_type.SaliencyMap.value.assert_called_once_with(eval_rec, epoch)
        visualizer.get_plt.assert_called_once_with(method="Gradient", absolute=False)
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
        old_canvas._draw_pending = True
        new_fig = Figure(figsize=(5, 4), dpi=100)

        with patch.object(base_saliency_view.plt, "close") as close_figure:
            w._replace_figure(new_fig)

        close_figure.assert_called_once_with(old_fig)
        assert w.fig is new_fig
        assert w.canvas is not old_canvas
        assert old_canvas.parent() is None
        assert old_canvas._draw_pending is False


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
        from PyQt6.QtWidgets import QLabel, QSizePolicy

        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ):
            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            w.show_message("test message")
            labels = w.findChildren(QLabel)
            assert labels[-1].wordWrap()
            assert labels[-1].sizePolicy().horizontalPolicy() == (
                QSizePolicy.Policy.Expanding
            )
            assert labels[-1].alignment() == Qt.AlignmentFlag.AlignCenter

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

    def test_update_plot_blocks_offscreen_before_qtinteractor(self, qtbot, monkeypatch):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
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

    def test_update_plot_allows_wayland_when_runtime_probe_passes(
        self,
        qtbot,
        monkeypatch,
    ):
        monkeypatch.setenv("QT_QPA_PLATFORM", "")
        monkeypatch.delenv("PYVISTA_OFF_SCREEN", raising=False)
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        monkeypatch.delenv("XBRAINLAB_ENABLE_INTERACTIVE_3D", raising=False)

        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ) as pyvistaqt:
            from PyQt6.QtWidgets import QWidget

            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            interactor_widget = QWidget()
            cast(Any, interactor_widget).interactor = MagicMock()
            pyvistaqt.QtInteractor.return_value = interactor_widget

            eval_record = MagicMock()
            plan = MagicMock()
            plan.get_eval_record.return_value = eval_record
            epoch = MagicMock()
            epoch.get_montage_position.return_value = [(0.0, 0.0, 0.0)]
            epoch.event_id = {"left": 0}
            trainer = MagicMock()
            trainer.get_dataset.return_value.get_epoch_data.return_value = epoch

            with (
                patch.object(
                    Saliency3DPlotWidget,
                    "_interactive_3d_runtime_available",
                    return_value=(True, ""),
                ),
                patch.object(
                    Saliency3DPlotWidget,
                    "_active_qt_platform_name",
                    return_value="",
                ),
                patch(
                    "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.Saliency3D.prepare_engine",
                    return_value=(MagicMock(), 1),
                ),
            ):
                w.update_plot(plan, trainer, "Gradient", False, eval_record)

            qtbot.waitUntil(
                lambda: pyvistaqt.QtInteractor.call_count == 1,
                timeout=1000,
            )
            pyvistaqt.QtInteractor.assert_called_once()

    def test_update_plot_blocks_wayland_when_runtime_probe_fails(
        self,
        qtbot,
        monkeypatch,
    ):
        monkeypatch.setenv("QT_QPA_PLATFORM", "")
        monkeypatch.delenv("PYVISTA_OFF_SCREEN", raising=False)
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

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

            with (
                patch.object(
                    Saliency3DPlotWidget,
                    "_interactive_3d_runtime_available",
                    return_value=(False, "3D rendering is blocked by BadWindow."),
                ),
                patch.object(
                    Saliency3DPlotWidget,
                    "_active_qt_platform_name",
                    return_value="",
                ),
            ):
                w.update_plot(plan, trainer, "Gradient", False, eval_record)

            pyvistaqt.QtInteractor.assert_not_called()
            visible_labels = [
                label.text()
                for label in w.findChildren(QLabel)
                if not label.isHidden() and label.text()
            ]
            assert any("BadWindow" in text for text in visible_labels)

    def test_do_3d_plot_surfaces_engine_initialization_error(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ):
            from PyQt6.QtWidgets import QLabel, QWidget

            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            class FailedSaliency:
                init_error = "Could not map EEG event 769 to saliency results."
                engine = None

                def __init__(self, *_args, **_kwargs):
                    pass

                def get_3d_head_plot(self):
                    return None

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            cast(Any, w).plotter_widget = QWidget()

            with patch(
                "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.Saliency3D",
                FailedSaliency,
            ):
                w._do_3d_plot(MagicMock(), MagicMock(), "769")

            visible_labels = [
                label.text()
                for label in w.findChildren(QLabel)
                if not label.isHidden() and label.text()
            ]
            assert any("Could not map EEG event 769" in text for text in visible_labels)

    def test_deferred_3d_plot_ignores_deleted_widget(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ):
            from PyQt6.QtWidgets import QWidget

            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            cast(Any, w).plotter_widget = QWidget()
            w.deleteLater()
            qtbot.waitUntil(lambda: sip.isdeleted(w), timeout=1000)

            with patch(
                "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.Saliency3D",
                side_effect=AssertionError("deleted widgets must not render"),
            ):
                w._do_3d_plot_if_alive(MagicMock(), MagicMock(), "769")

    def test_do_3d_plot_passes_method_and_absolute_to_renderer(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.pyvistaqt"
        ):
            from PyQt6.QtWidgets import QWidget

            from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
                Saliency3DPlotWidget,
            )

            captured_kwargs = {}

            class SuccessfulSaliency:
                init_error = ""
                engine = object()

                def __init__(self, *_args, **kwargs):
                    captured_kwargs.update(kwargs)

                def get_3d_head_plot(self):
                    return None

            w = Saliency3DPlotWidget(parent=None)
            qtbot.addWidget(w)
            cast(Any, w).plotter_widget = QWidget()

            with patch(
                "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.Saliency3D",
                SuccessfulSaliency,
            ):
                w._do_3d_plot(
                    MagicMock(),
                    MagicMock(),
                    "769",
                    method="VarGrad",
                    absolute=True,
                )

        assert captured_kwargs["method"] == "VarGrad"
        assert captured_kwargs["absolute"] is True

    def test_3d_head_plot_uses_tuple_slider_range_for_pyvista(self):
        from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_head import (
            Saliency3D,
        )

        class PlotterStub:
            def __init__(self):
                self.slider_ranges = []
                self.camera = MagicMock()

            def add_camera_orientation_widget(self):
                pass

            def add_slider_widget(self, **kwargs):
                self.slider_ranges.append(kwargs["rng"])

            def add_checkbox_button_widget(self, *_args, **_kwargs):
                pass

            def add_text(self, *_args, **_kwargs):
                pass

            def add_mesh(self, *_args, **_kwargs):
                return object()

            def add_scalar_bar(self, *_args, **_kwargs):
                pass

            def update_scalar_bar_range(self, *_args, **_kwargs):
                pass

            def show_bounds(self, *_args, **_kwargs):
                pass

        saliency = Saliency3D.__new__(Saliency3D)
        saliency.engine = MagicMock()
        saliency.engine.saliency = np.zeros((3, 24))
        saliency.engine.saliency_cap = object()
        saliency.engine.brain_scaled = object()
        saliency.engine.scalar_bar_range = [0.0, 1.0]
        saliency.plotter = PlotterStub()
        saliency.channelBox = MagicMock()
        saliency.headBox = MagicMock()
        saliency.showChannel = True
        saliency.showHead = True
        saliency.chs = []
        cast(Any, saliency).cmap = "coolwarm"

        saliency.get_3d_head_plot()

        assert saliency.plotter.slider_ranges == [(1, 24)]

    def test_3d_head_plot_centers_scene_after_adding_meshes(self):
        from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_head import (
            Saliency3D,
        )

        class CameraStub:
            def __init__(self, calls):
                self.calls = calls

            def zoom(self, amount):
                self.calls.append(("camera.zoom", amount))

        class PlotterStub:
            def __init__(self):
                self.calls = []
                self.camera = CameraStub(self.calls)
                self._camera_position = None

            @property
            def camera_position(self):
                return self._camera_position

            @camera_position.setter
            def camera_position(self, value):
                self._camera_position = value
                self.calls.append(("camera_position", value))

            def add_camera_orientation_widget(self):
                pass

            def add_slider_widget(self, **_kwargs):
                pass

            def add_checkbox_button_widget(self, *_args, **_kwargs):
                pass

            def add_text(self, *_args, **_kwargs):
                pass

            def add_mesh(self, *_args, **_kwargs):
                self.calls.append(("add_mesh", None))
                return object()

            def add_scalar_bar(self, *_args, **_kwargs):
                pass

            def update_scalar_bar_range(self, *_args, **_kwargs):
                pass

            def reset_camera(self):
                self.calls.append(("reset_camera", None))

            def show_bounds(self, *_args, **_kwargs):
                raise AssertionError("3D saliency should not display debug bounds")

        saliency = Saliency3D.__new__(Saliency3D)
        saliency.engine = MagicMock()
        saliency.engine.saliency = np.zeros((3, 24))
        saliency.engine.saliency_cap = object()
        saliency.engine.brain_scaled = object()
        saliency.engine.scalar_bar_range = [0.0, 1.0]
        saliency.plotter = PlotterStub()
        saliency.channelBox = MagicMock()
        saliency.headBox = MagicMock()
        saliency.showChannel = True
        saliency.showHead = True
        saliency.chs = []
        cast(Any, saliency).cmap = "coolwarm"

        result = saliency.get_3d_head_plot()

        assert result is saliency.plotter
        calls = saliency.plotter.calls
        first_reset = calls.index(("reset_camera", None))
        assert first_reset > max(
            index for index, call in enumerate(calls) if call[0] == "add_mesh"
        )
        assert calls[first_reset + 1 : first_reset + 3] == [
            ("camera_position", "xy"),
            ("camera.zoom", 0.9),
        ]
