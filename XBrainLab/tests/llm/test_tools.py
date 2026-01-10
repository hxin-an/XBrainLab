
import unittest
from unittest.mock import MagicMock, patch
from XBrainLab.llm.agent.parser import CommandParser
from XBrainLab.llm.tools.data_loader import LoadDataTool
from XBrainLab.llm.tools import get_tool_by_name

class TestCommandParser(unittest.TestCase):
    def test_parse_json_block(self):
        text = """Here is the command:
        ```json
        {
            "command": "load_data",
            "parameters": {
                "filepath": "/path/to/file.gdf"
            }
        }
        ```
        """
        cmd, params = CommandParser.parse(text)
        self.assertEqual(cmd, "load_data")
        self.assertEqual(params["filepath"], "/path/to/file.gdf")

    def test_parse_raw_json(self):
        text = """
        {
            "command": "load_data",
            "parameters": {
                "filepath": "/path/to/file.gdf"
            }
        }
        """
        cmd, params = CommandParser.parse(text)
        self.assertEqual(cmd, "load_data")
        self.assertEqual(params["filepath"], "/path/to/file.gdf")

    def test_parse_invalid_json(self):
        text = "This is just some text."
        result = CommandParser.parse(text)
        self.assertIsNone(result)

class TestLoadDataTool(unittest.TestCase):
    def setUp(self):
        self.tool = LoadDataTool()
        self.mock_study = MagicMock()
        self.mock_study.loaded_data_list = []

    @patch("XBrainLab.llm.tools.data_loader.os.path.exists")
    @patch("XBrainLab.llm.tools.data_loader.load_raw_data")
    def test_execute_success(self, mock_load_raw, mock_exists):
        mock_exists.return_value = True
        mock_raw = MagicMock()
        mock_load_raw.return_value = mock_raw
        
        result = self.tool.execute(self.mock_study, filepath="/path/to/test.gdf")
        
        self.assertIn("Successfully loaded", result)
        self.mock_study.set_loaded_data_list.assert_called()
        
    @patch("XBrainLab.llm.tools.data_loader.os.path.exists")
    def test_execute_file_not_found(self, mock_exists):
        mock_exists.return_value = False
        result = self.tool.execute(self.mock_study, filepath="/nonexistent.gdf")
        self.assertIn("Error: File not found", result)

    @patch("XBrainLab.llm.tools.data_loader.os.path.exists")
    @patch("XBrainLab.llm.tools.data_loader.load_raw_data")
    def test_execute_unsupported_format(self, mock_load_raw, mock_exists):
        from XBrainLab.backend.exceptions import UnsupportedFormatError
        mock_exists.return_value = True
        mock_load_raw.side_effect = UnsupportedFormatError("/path/to/test.xyz")
        
        result = self.tool.execute(self.mock_study, filepath="/path/to/test.xyz")
        self.assertIn("Error: Unsupported file format", result)

class TestClearDatasetTool(unittest.TestCase):
    def setUp(self):
        from XBrainLab.llm.tools.dataset_tools import ClearDatasetTool
        self.tool = ClearDatasetTool()
        self.mock_study = MagicMock()

    def test_execute_success(self):
        result = self.tool.execute(self.mock_study)
        self.assertIn("Successfully cleared", result)
        self.mock_study.clean_raw_data.assert_called_with(force_update=True)

    def test_execute_failure(self):
        self.mock_study.clean_raw_data.side_effect = Exception("Clean failed")
        result = self.tool.execute(self.mock_study)
        self.assertIn("Error clearing dataset", result)

class TestToolRegistry(unittest.TestCase):
    def test_get_tool_by_name(self):
        tool = get_tool_by_name("load_data")
        self.assertIsInstance(tool, LoadDataTool)
        
        tool = get_tool_by_name("nonexistent")
        self.assertIsNone(tool)

if __name__ == '__main__':
    unittest.main()
