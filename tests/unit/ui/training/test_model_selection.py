from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QFrame,
    QHeaderView,
    QScrollArea,
    QTableWidgetItem,
)

from XBrainLab.ui.dialogs.training import ModelSelectionDialog
from XBrainLab.ui.styles.theme import Theme


# Dummy model for testing
class DummyModel:
    def __init__(self, param1=10, param2=0.5, param3="test"):
        pass


class NoEditableParamModel:
    def __init__(self, n_classes, channels, samples, sfreq):
        pass


class ManyParamModel:
    def __init__(
        self,
        alpha=1,
        beta=2,
        gamma=3,
        delta=4,
        epsilon=5,
        zeta=6,
        eta=7,
        theta=8,
        iota=9,
        kappa=10,
        lambda_param=11,
        mu=12,
        nu=13,
        xi=14,
        omicron=15,
        pi=16,
    ):
        pass


class FiveParamModel:
    def __init__(self, f1=8, f2=16, d=2, pool_1=4, pool_2=8):
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

    def test_params_table_has_no_initial_white_selection(self, dialog):
        assert dialog.params_table is not None
        assert dialog.params_table.selectedItems() == []
        assert dialog.params_table.currentRow() == -1
        assert (
            dialog.params_table.selectionMode()
            == QAbstractItemView.SelectionMode.NoSelection
        )
        assert dialog.params_table.height() <= 240
        assert dialog.params_table.palette().color(QPalette.ColorRole.Highlight) == (
            QColor(Theme.METRICS_TABLE_SELECTION)
        )
        assert dialog.params_table.palette().color(
            QPalette.ColorGroup.Inactive,
            QPalette.ColorRole.Highlight,
        ) == QColor(Theme.METRICS_TABLE_SELECTION)
        assert dialog.params_table.palette().color(
            QPalette.ColorGroup.Inactive,
            QPalette.ColorRole.HighlightedText,
        ) == QColor(Theme.TEXT_PRIMARY)
        assert dialog.findChild(QDialogButtonBox) is None
        assert dialog.confirm_btn is not None
        assert dialog.confirm_btn.text() == "Confirm"
        assert "chevron-down.svg" in dialog.styleSheet()

    def test_default_content_does_not_show_scrollbar_gutter(self, dialog, qtbot):
        dialog.show()
        qtbot.wait(50)

        scroll = dialog.findChild(QScrollArea, "ModelSelectionContentScroll")
        assert scroll is not None
        scrollbar = scroll.verticalScrollBar()
        assert scrollbar is not None
        assert scrollbar.maximum() == 0

    def test_model_sections_do_not_draw_internal_vertical_frame_lines(self, dialog):
        sections = dialog.findChildren(QFrame, "ModelSection")
        assert len(sections) >= 2
        assert all(section.frameShape() == QFrame.Shape.NoFrame for section in sections)
        section_style = dialog.styleSheet().split("QFrame#ModelSection", 1)[1]
        section_style = section_style.split("}", 1)[0]
        assert "border: none;" in section_style
        scrollbar_style = dialog.styleSheet().split("QScrollBar:vertical", 1)[1]
        scrollbar_style = scrollbar_style.split("}", 1)[0]
        assert "background: transparent;" in scrollbar_style

    def test_realistic_parameter_count_does_not_force_outer_scrollbar(self, qtbot):
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [("FiveParamModel", FiveParamModel)]

            dialog = ModelSelectionDialog(None, MagicMock())
            qtbot.addWidget(dialog)

        dialog.show()
        qtbot.wait(50)

        scroll = dialog.findChild(QScrollArea, "ModelSelectionContentScroll")
        assert scroll is not None
        scrollbar = scroll.verticalScrollBar()
        assert scrollbar is not None
        assert scrollbar.maximum() == 0

    def test_realistic_parameters_use_product_labels_and_preserve_raw_keys(
        self,
        qtbot,
    ):
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [("FiveParamModel", FiveParamModel)]
            dialog = ModelSelectionDialog(None, MagicMock())
            qtbot.addWidget(dialog)

        labels_by_key = {
            dialog.params_table.item(row, 0).data(
                Qt.ItemDataRole.UserRole
            ): dialog.params_table.item(
                row,
                0,
            )
            for row in range(dialog.params_table.rowCount())
        }
        assert labels_by_key["f1"].text() == "Temporal filters"
        assert labels_by_key["f2"].text() == "Pointwise filters"
        assert labels_by_key["d"].text() == "Depth multiplier"
        assert labels_by_key["pool_1"].text() == "First pooling size"
        assert labels_by_key["pool_2"].text() == "Second pooling size"
        assert all(item.toolTip() for item in labels_by_key.values())

        dialog.accept()
        holder = dialog.get_result()
        assert holder is not None
        assert holder.model_params_map == {
            "f1": 8,
            "f2": 16,
            "d": 2,
            "pool_1": 4,
            "pool_2": 8,
        }

    def test_params_table_height_fits_visible_rows(self, dialog):
        assert dialog.params_table is not None
        header = dialog.params_table.horizontalHeader()
        assert isinstance(header, QHeaderView)
        expected_max_height = (
            header.height()
            + sum(
                dialog.params_table.rowHeight(row)
                for row in range(dialog.params_table.rowCount())
            )
            + 12
        )
        assert dialog.params_table.height() <= expected_max_height

    def test_params_table_stays_visible_for_models_without_editable_params(self, qtbot):
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [
                ("NoEditableParamModel", NoEditableParamModel)
            ]

            dialog = ModelSelectionDialog(None, MagicMock())
            qtbot.addWidget(dialog)

        assert dialog.params_group is not None
        assert dialog.params_table is not None
        assert not dialog.params_group.isHidden()
        assert dialog.params_table.rowCount() == 1
        name_item = dialog.params_table.item(0, 0)
        assert name_item is not None
        assert "No editable parameters" in name_item.text()

    def test_content_scrolls_when_model_parameters_exceed_dialog_height(self, qtbot):
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [("ManyParamModel", ManyParamModel)]

            dialog = ModelSelectionDialog(None, MagicMock())
            qtbot.addWidget(dialog)

        dialog.resize(600, 300)
        dialog.show()
        qtbot.wait(50)

        scroll = dialog.findChild(QScrollArea, "ModelSelectionContentScroll")
        assert scroll is not None
        assert scroll.widgetResizable()
        assert scroll.horizontalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        scrollbar = scroll.verticalScrollBar()
        assert scrollbar is not None
        assert scrollbar.maximum() > 0
        assert dialog.confirm_btn is not None
        assert dialog.confirm_btn.isVisibleTo(dialog)
        assert "QScrollArea#ModelSelectionContentScroll" in dialog.styleSheet()

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
            assert dialog.weight_btn.text() == "Clear"

            # Click again to clear
            dialog.load_pretrained_weight()
            assert dialog.pretrained_weight_path is None
            assert dialog.weight_label.text() == "None"
            assert dialog.weight_btn.text() == "Load"
