"""Visualizer names resolve to their concrete rendering implementations."""

from XBrainLab.backend.visualization.plot_type import VisualizerType
from XBrainLab.backend.visualization.saliency_map import SaliencyMapViz
from XBrainLab.backend.visualization.saliency_spectrogram_map import (
    SaliencySpectrogramMapViz,
)
from XBrainLab.backend.visualization.saliency_topomap import SaliencyTopoMapViz


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
