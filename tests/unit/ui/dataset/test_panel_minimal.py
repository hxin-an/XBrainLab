"""Dataset panel remains usable without an application parent."""

from PyQt6.QtWidgets import QTableWidget

from XBrainLab.ui.panels.dataset.panel import DatasetPanel


def test_dataset_panel_no_parent(qtbot):
    """Verify DatasetPanel can init without parent (headless/test mode)."""
    panel = DatasetPanel(parent=None)
    qtbot.addWidget(panel)

    assert panel.table.rowCount() == 0
    assert panel.empty_state_title.text() == "No EEG data loaded"
    assert panel.main_window is None
    assert panel._bridges == []
    assert isinstance(panel.table, QTableWidget)
