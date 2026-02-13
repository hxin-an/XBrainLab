from unittest.mock import MagicMock

from XBrainLab.backend.study import Study
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.tool_registry import ToolRegistry


# Mock Tools for Testing
class AlwaysValidTool(BaseTool):
    @property
    def name(self):
        return "always_valid"

    @property
    def description(self):
        return "Always valid"

    @property
    def parameters(self):
        return {}

    def execute(self, study, **kwargs):
        return "Executed"


class DataRequiredTool(BaseTool):
    @property
    def name(self):
        return "data_required"

    @property
    def description(self):
        return "Requires loaded data"

    @property
    def parameters(self):
        return {}

    def is_valid(self, study: Study) -> bool:
        # Check if any data is loaded
        return bool(study.loaded_data_list)

    def execute(self, study, **kwargs):
        return "Executed"


class TrainerRequiredTool(BaseTool):
    @property
    def name(self):
        return "trainer_required"

    @property
    def description(self):
        return "Requires trainer"

    @property
    def parameters(self):
        return {}

    def is_valid(self, study: Study) -> bool:
        return study.trainer is not None

    def execute(self, study, **kwargs):
        return "Executed"


def test_base_tool_default_validity():
    """Test that base tools are valid by default (backward compatibility)."""
    tool = AlwaysValidTool()
    # Mock study not needed for default implementation if it just returns True
    assert tool.is_valid(MagicMock()) is True


def test_tool_registry_filtering():
    """Test that registry filters tools based on study state."""

    # 1. Setup Mock Study
    mock_study = MagicMock(spec=Study)
    mock_study.loaded_data_list = []
    mock_study.trainer = None

    # 2. Setup Registry with our test tools
    registry = ToolRegistry()
    registry.register(AlwaysValidTool())
    registry.register(DataRequiredTool())
    registry.register(TrainerRequiredTool())

    # 3. Case A: Empty State -> Only AlwaysValid should be active
    active_tools = registry.get_active_tools(mock_study)
    active_names = [t.name for t in active_tools]

    assert "always_valid" in active_names
    assert "data_required" not in active_names
    assert "trainer_required" not in active_names

    # 4. Case B: Data Loaded -> AlwaysValid + DataRequired
    mock_study.loaded_data_list = ["data1"]
    active_tools = registry.get_active_tools(mock_study)
    active_names = [t.name for t in active_tools]

    assert "always_valid" in active_names
    assert "data_required" in active_names
    assert "trainer_required" not in active_names

    # 5. Case C: Trainer Ready -> + TrainerRequired
    mock_study.trainer = MagicMock()
    active_tools = registry.get_active_tools(mock_study)
    active_names = [t.name for t in active_tools]

    assert "always_valid" in active_names
    assert "data_required" in active_names
    assert "trainer_required" in active_names
