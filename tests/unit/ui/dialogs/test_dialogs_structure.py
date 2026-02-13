from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.components.plot_figure_window import PlotFigureWindow
from XBrainLab.ui.components.single_plot_window import (
    SinglePlotWindow,  # Kept SinglePlotWindow as it's used later
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.dataset.label_mapping_dialog import LabelMappingDialog
from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog
from XBrainLab.ui.dialogs.preprocess.rereference_dialog import RereferenceDialog


# Mock data for dialog instantiation
class MockParent(QWidget):
    pass


class TestDialogStructure:
    def test_base_dialog_inheritance(self, qtbot):
        """Verify that key dialogs inherit from BaseDialog."""
        parent = MockParent()

        # We can't easily instantiate complex dialogs without full mocks,
        # but we can check class inheritance safely.

        assert issubclass(LabelMappingDialog, BaseDialog)
        assert issubclass(EpochingDialog, BaseDialog)
        assert issubclass(SinglePlotWindow, BaseDialog)
        assert issubclass(
            PlotFigureWindow, BaseDialog
        )  # Indirectly via SinglePlotWindow

    def test_single_plot_window_init(self, qtbot):
        """Test simple instantiation of SinglePlotWindow."""
        parent = MockParent()
        dlg = SinglePlotWindow(parent, title="Test Plot")
        qtbot.addWidget(dlg)

        assert dlg.windowTitle() == "Test Plot"
        assert dlg.width() > 100
        assert dlg.height() > 100

        dlg.close()

    def test_rereference_dialog_inheritance(self, qtbot):
        assert issubclass(RereferenceDialog, BaseDialog)
