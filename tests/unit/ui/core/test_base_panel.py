import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.core.base_panel import BasePanel


class ConcretePanel(BasePanel):
    def init_ui(self):
        pass


@pytest.fixture
def panel(qtbot):
    widget = ConcretePanel()
    qtbot.addWidget(widget)
    return widget


def test_init(panel):
    assert isinstance(panel, QWidget)
    assert panel.main_window is None


def test_parent_context_is_retained(qtbot):
    parent = QWidget()
    parent.study = object()
    qtbot.addWidget(parent)
    panel = ConcretePanel(parent=parent)
    assert panel.main_window is parent
    assert panel.parent() is parent


def test_abstract_method_error(qtbot):
    panel = BasePanel()
    qtbot.addWidget(panel)
    with pytest.raises(NotImplementedError):
        panel.init_ui()


def test_set_busy(panel):
    panel.set_busy(True)
    assert panel.cursor().shape() == Qt.CursorShape.WaitCursor
    assert panel.isEnabled() is False
    panel.set_busy(False)
    assert panel.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert panel.isEnabled() is True


def test_set_busy_ignores_deleted_panel(qtbot):
    panel = ConcretePanel()
    qtbot.addWidget(panel)
    panel.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(panel), timeout=1_000)
    panel.set_busy(False)


@pytest.mark.parametrize("native_teardown", [False, True])
def test_owned_bridges_deliver_and_unsubscribe(qtbot, native_teardown):
    panel = ConcretePanel()
    if not native_teardown:
        qtbot.addWidget(panel)
    source = Observable()
    delivered = []
    panel._create_bridge(source, "publication", lambda value: delivered.append(value))
    panel._create_bridge(source, "progress", lambda value: delivered.append(value))

    source.notify("publication", "ready")
    source.notify("progress", 25)
    assert delivered == ["ready", 25]

    if native_teardown:
        panel.deleteLater()
        qtbot.waitUntil(lambda: sip.isdeleted(panel), timeout=1_000)
    else:
        panel.cleanup()
        panel.cleanup()
    source.notify("publication", "terminal")
    source.notify("progress", 100)
    assert delivered == ["ready", 25]
