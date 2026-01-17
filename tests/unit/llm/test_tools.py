from unittest.mock import MagicMock

import pytest

from XBrainLab.llm.tools.mock.dataset_mock import MockListFilesTool, MockLoadDataTool
from XBrainLab.llm.tools.mock.preprocess_mock import (
    MockSetMontageTool,
    MockStandardPreprocessTool,
)
from XBrainLab.llm.tools.mock.training_mock import MockSetModelTool
from XBrainLab.llm.tools.mock.ui_control_mock import MockSwitchPanelTool


@pytest.fixture
def mock_study():
    return MagicMock()


def test_dataset_tools(mock_study):
    tool = MockLoadDataTool()
    result = tool.execute(mock_study, paths=["/tmp/test.gdf"])
    assert "Successfully loaded" in result
    assert "/tmp/test.gdf" in result

    tool = MockListFilesTool()
    result = tool.execute(mock_study, directory="/data")
    assert "['A01T.gdf'" in result


def test_preprocess_tools(mock_study):
    tool = MockStandardPreprocessTool()
    result = tool.execute(mock_study)
    assert "Applied standard preprocessing pipeline" in result

    tool = MockSetMontageTool()
    result = tool.execute(mock_study, montage_name="standard_1020")
    assert "Set montage to standard_1020" in result


def test_training_tools(mock_study):
    tool = MockSetModelTool()
    result = tool.execute(mock_study, model_name="EEGNet")
    assert "Model set to EEGNet" in result


def test_ui_control_tools(mock_study):
    tool = MockSwitchPanelTool()

    # Test basic switch
    result = tool.execute(mock_study, panel_name="training")
    assert "Switched UI view to training panel" in result

    # Test switch with view_mode
    result = tool.execute(
        mock_study, panel_name="visualization", view_mode="saliency_map"
    )
    assert "showing saliency_map" in result
