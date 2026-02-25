"""Enumerations for plot types and visualizer mappings."""

from enum import Enum

from .saliency_map import SaliencyMapViz
from .saliency_spectrogram_map import SaliencySpectrogramMapViz
from .saliency_topomap import SaliencyTopoMapViz


class PlotType(Enum):
    """Enumeration of training-metric plot types.

    Each member's value is the name of the method on the training record that
    produces the corresponding matplotlib figure.

    Attributes:
        LOSS: Loss curve figure.
        ACCURACY: Accuracy curve figure.
        AUC: AUC curve figure.
        LR: Learning-rate schedule figure.
        CONFUSION: Confusion-matrix figure.
    """

    LOSS = "get_loss_figure"
    ACCURACY = "get_acc_figure"
    AUC = "get_auc_figure"
    LR = "get_lr_figure"
    CONFUSION = "get_confusion_figure"


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
