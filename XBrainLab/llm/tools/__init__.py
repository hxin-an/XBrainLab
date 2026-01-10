
from .data_loader import LoadDataTool
from .dataset_tools import ClearDatasetTool

# List of all available tools
AVAILABLE_TOOLS = [
    LoadDataTool(),
    ClearDatasetTool()
]

def get_tool_by_name(name: str):
    for tool in AVAILABLE_TOOLS:
        if tool.name == name:
            return tool
    return None
