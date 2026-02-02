import sys

import pytest
from PyQt6.QtWidgets import QApplication

from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel


@pytest.fixture(scope="session")
def qapp_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_panels_inherit_base_panel(qapp_instance):
    panels = [
        DatasetPanel,
        PreprocessPanel,
        TrainingPanel,
        VisualizationPanel,
        EvaluationPanel,
    ]
    for p in panels:
        assert issubclass(p, BasePanel), f"{p.__name__} must inherit BasePanel"


def test_panels_cleaned_up_refresh_data(qapp_instance):
    panels = [VisualizationPanel, EvaluationPanel]
    for p in panels:
        # Check that refresh_data is NOT in the class dict
        assert "refresh_data" not in p.__dict__, (
            f"{p.__name__} should not have refresh_data method"
        )
        # And check hasattr (unless inherited from something else, but BasePanel doesn't have it)
        assert not hasattr(p, "refresh_data"), (
            f"{p.__name__} should not expose refresh_data"
        )
