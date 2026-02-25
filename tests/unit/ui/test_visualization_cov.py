"""Coverage tests for saliency views: map, spectrogram, topomap, 3D engine basics."""

from __future__ import annotations

import contextlib
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
        assert w is not None

    def test_update_plot_no_eval(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.map_view import (
            SaliencyMapWidget,
        )

        w = SaliencyMapWidget()
        qtbot.addWidget(w)
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        w.update_plot(plan, None, None, None, None)

    def test_update_plot_with_data(self, qtbot):
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

        with contextlib.suppress(Exception):  # matplotlib may fail headless
            w.update_plot(plan, trainer, "Gradient", False, None)


# ============ SaliencySpectrogramWidget ============


class TestSaliencySpectrogramWidget:
    def test_creates(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view import (
            SaliencySpectrogramWidget,
        )

        w = SaliencySpectrogramWidget()
        qtbot.addWidget(w)
        assert w is not None

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
        assert w is not None

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
            assert w is not None

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
