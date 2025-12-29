from XBrainLab.visualization.saliency_spectrogram_map import SaliencySpectrogramMapViz
from XBrainLab.visualization.base import Visualizer
from XBrainLab.training.record import EvalRecord
from XBrainLab.dataset import Epochs
import numpy as np
from unittest.mock import MagicMock

def test_instantiation():
    print("Visualizer init:", Visualizer.__init__)
    print("SaliencySpectrogramMapViz init:", SaliencySpectrogramMapViz.__init__)
    
    eval_record = MagicMock(spec=EvalRecord)
    epochs = MagicMock(spec=Epochs)
    
    try:
        viz = SaliencySpectrogramMapViz(eval_record, epochs)
        print("Instantiation successful")
    except Exception as e:
        print(f"Instantiation failed: {e}")

if __name__ == "__main__":
    test_instantiation()
