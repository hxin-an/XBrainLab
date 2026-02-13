from unittest.mock import MagicMock

from XBrainLab.backend.study import Study
from XBrainLab.llm.tools.real.dataset_real import (
    RealAttachLabelsTool,
    RealGenerateDatasetTool,
)
from XBrainLab.llm.tools.real.preprocess_real import RealBandPassFilterTool
from XBrainLab.llm.tools.real.training_real import RealStartTrainingTool


def test_real_tools_validation():
    """Test is_valid() logic on actual tool classes."""

    # 1. Setup Mock Study (Empty state)
    study = MagicMock(spec=Study)
    study.loaded_data_list = []
    study.epoch_data = None
    study.trainer = None
    study.datasets = []
    study.model_holder = None
    study.training_option = None

    # 2. Instantiate Tools
    gen_dataset_tool = RealGenerateDatasetTool()
    attach_labels_tool = RealAttachLabelsTool()
    filter_tool = RealBandPassFilterTool()
    start_train_tool = RealStartTrainingTool()

    # 3. Assert False for Empty State
    assert not gen_dataset_tool.is_valid(study), (
        "GenerateDataset should satisfy epoch_data check"
    )
    assert not attach_labels_tool.is_valid(study), (
        "AttachLabels should require loaded data"
    )
    assert not filter_tool.is_valid(study), "Filter should require loaded data"
    assert not start_train_tool.is_valid(study), "StartTraining should require inputs"

    # 4. State Change: Load Data
    study.loaded_data_list = ["mock_file"]
    assert attach_labels_tool.is_valid(study)
    assert filter_tool.is_valid(study)
    assert not gen_dataset_tool.is_valid(study)  # Still no epoch data

    # 5. State Change: Epoch Data
    study.epoch_data = "mock_epochs"
    assert gen_dataset_tool.is_valid(study)

    # 6. State Change: Training Prerequisites
    # StartTraining needs Datasets + Model + Option OR Trainer
    study.datasets = ["d1"]
    study.model_holder = "m1"
    # Still missing option
    assert not start_train_tool.is_valid(study)

    study.training_option = "opt1"
    assert start_train_tool.is_valid(study)

    # 7. State Change: Trainer Exists (Alternative success path)
    study.datasets = []  # Clear inputs
    assert not start_train_tool.is_valid(study)
    study.trainer = "existing_trainer"
    assert start_train_tool.is_valid(study)
