from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog
from XBrainLab.ui.dialogs.preprocess.rereference_dialog import RereferenceDialog


class TestDialogStructure:
    def test_base_dialog_inheritance(self, qtbot):
        """Verify that key dialogs inherit from BaseDialog."""
        assert issubclass(EpochingDialog, BaseDialog)

    def test_rereference_dialog_inheritance(self, qtbot):
        assert issubclass(RereferenceDialog, BaseDialog)
