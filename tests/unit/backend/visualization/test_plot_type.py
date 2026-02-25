"""Unit tests for visualization/plot_type — PlotType and VisualizerType enums."""

from XBrainLab.backend.visualization.plot_type import PlotType, VisualizerType
from XBrainLab.backend.visualization.saliency_map import SaliencyMapViz
from XBrainLab.backend.visualization.saliency_spectrogram_map import (
    SaliencySpectrogramMapViz,
)
from XBrainLab.backend.visualization.saliency_topomap import SaliencyTopoMapViz


class TestPlotType:
    def test_loss(self):
        assert PlotType.LOSS.value == "get_loss_figure"

    def test_accuracy(self):
        assert PlotType.ACCURACY.value == "get_acc_figure"

    def test_auc(self):
        assert PlotType.AUC.value == "get_auc_figure"

    def test_lr(self):
        assert PlotType.LR.value == "get_lr_figure"

    def test_confusion(self):
        assert PlotType.CONFUSION.value == "get_confusion_figure"

    def test_all_members(self):
        members = list(PlotType)
        assert len(members) == 5


class TestVisualizerType:
    def test_saliency_map(self):
        assert VisualizerType.SaliencyMap.value is SaliencyMapViz

    def test_saliency_topo_map(self):
        assert VisualizerType.SaliencyTopoMap.value is SaliencyTopoMapViz

    def test_saliency_spectrogram_map(self):
        assert VisualizerType.SaliencySpectrogramMap.value is SaliencySpectrogramMapViz

    def test_all_members(self):
        members = list(VisualizerType)
        assert len(members) == 3
