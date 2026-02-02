from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QTableWidgetItem

from XBrainLab.ui.dialogs.training import ModelSelectionDialog


# Dummy model for testing
class DummyModel:
    def __init__(self, param1=10, param2=0.5, param3="test"):
        pass


class TestModelSelection:
    @pytest.fixture
    def dialog(self, qtbot):
        # Mock model_base members
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [("DummyModel", DummyModel)]

            mock_controller = MagicMock()
            dialog = ModelSelectionDialog(None, mock_controller)
            qtbot.addWidget(dialog)
            return dialog

    def test_init(self, dialog):
        assert dialog.windowTitle() == "Model Selection"
        assert dialog.model_combo.count() == 1
        assert dialog.model_combo.currentText() == "DummyModel"

    def test_params_population(self, dialog):
        # Verify params table is populated
        assert dialog.params_table.rowCount() == 3

        # Check param names and default values
        params = {}
        for row in range(dialog.params_table.rowCount()):
            name = dialog.params_table.item(row, 0).text()
            val = dialog.params_table.item(row, 1).text()
            params[name] = val

        assert params["param1"] == "10"
        assert params["param2"] == "0.5"
        assert params["param3"] == "test"

    def test_confirm(self, dialog):
        # Modify a parameter
        dialog.params_table.setItem(0, 1, QTableWidgetItem("20"))

        # Click OK
        with patch("PyQt6.QtWidgets.QDialog.accept") as mock_accept:
            dialog.accept()
            mock_accept.assert_called_once()

        # Verify result
        holder = dialog.get_result()
        assert holder is not None
        assert holder.target_model == DummyModel
        assert holder.model_params_map["param1"] == 20
        assert holder.model_params_map["param2"] == 0.5
        assert holder.model_params_map["param3"] == "test"

    def test_load_weight(self, dialog):
        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName") as mock_open:
            mock_open.return_value = ("/path/to/weight.pth", "Model Weights (*)")

            dialog.load_pretrained_weight()

            assert dialog.pretrained_weight_path == "/path/to/weight.pth"
            assert dialog.weight_btn.text() == "clear"

            # Click again to clear
            dialog.load_pretrained_weight()
            assert dialog.pretrained_weight_path is None
            assert dialog.weight_btn.text() == "load"
