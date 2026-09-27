"""Enumerations for plot types and visualizer mappings."""

from enum import Enum

from .saliency_map import SaliencyMapViz
from .saliency_spectrogram_map import SaliencySpectrogramMapViz
from .saliency_topomap import SaliencyTopoMapViz


class VisualizerType(Enum):
    """Enumeration mapping visualizer names to their concrete classes.

    Attributes:
        SaliencyMap: Channel-by-time saliency map visualizer.
        SaliencyTopoMap: Topographic saliency map visualizer.
        SaliencySpectrogramMap: Frequency-by-time saliency spectrogram visualizer.

    """

    SaliencyMap = SaliencyMapViz
    SaliencyTopoMap = SaliencyTopoMapViz
    SaliencySpectrogramMap = SaliencySpectrogramMapViz
