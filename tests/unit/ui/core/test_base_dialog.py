import pytest
from PyQt6.QtWidgets import QDialog

from XBrainLab.ui.core.base_dialog import BaseDialog


class ConcreteDialog(BaseDialog):
    def init_ui(self):
        pass

    def get_result(self):
        return "result"


class UnimplementedDialog(BaseDialog):
    pass


@pytest.fixture
def dialog(qtbot):
    dlg = ConcreteDialog(title="Test Dialog", width=200, height=100)
    qtbot.addWidget(dlg)
    return dlg


def test_init_defaults(qtbot):
    dlg = ConcreteDialog()
    qtbot.addWidget(dlg)
    assert isinstance(dlg, QDialog)
    assert dlg.windowTitle() == ""


def test_init_params(dialog):
    assert dialog.windowTitle() == "Test Dialog"
    assert dialog.width() == 200
    assert dialog.height() == 100


def test_abstract_methods():
    # init_ui is called in __init__, so instantiation should raise NotImplementedError
    with pytest.raises(NotImplementedError):
        UnimplementedDialog()

    # get_result is checked separately if we could verify instance, but since we can't init...
    # We can skip checking get_result raising error on UnimplementedDialog since we can't create it.
    # Or create a partial mock. But verifying init raises is sufficient for abstract init_ui enforcement.

    # To check get_result, we can use ConcreteDialog to call it if it wasn't implemented there?
    # But Concrete implements it.
    # Code coverage for BaseDialog.get_result -> pure abstract.
    # We can create a class that implements init_ui but NOT get_result.

    class PartialDialog(BaseDialog):
        def init_ui(self):
            pass

    dlg = PartialDialog()
    with pytest.raises(NotImplementedError):
        dlg.get_result()


def test_concrete_implementation(dialog):
    assert dialog.get_result() == "result"
    # init_ui called in __init__
