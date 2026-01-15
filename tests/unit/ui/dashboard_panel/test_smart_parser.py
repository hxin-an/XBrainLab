
import pytest
from PyQt6.QtWidgets import QDialog, QTableWidgetItem
from PyQt6.QtCore import Qt
from XBrainLab.ui.dashboard_panel.smart_parser import SmartParserDialog

@pytest.fixture
def dialog(qtbot):
    filenames = ["Sub01_Ses01.gdf", "Sub02_Ses01.gdf"]
    dlg = SmartParserDialog(filenames)
    qtbot.addWidget(dlg)
    
    # Reset to known state (Split Mode, Default indices)
    dlg.radio_split.setChecked(True)
    dlg.split_sep_combo.setCurrentIndex(0) # Underscore
    dlg.split_sub_idx.setValue(1)
    dlg.split_sess_idx.setValue(2)
    
    # Force update
    dlg.update_preview()
    
    return dlg

def test_smart_parser_init(dialog):
    """Test initialization and default state."""
    assert dialog.table.rowCount() == 2
    assert dialog.radio_split.isChecked()
    
    # Check default parsing (Split by '_', sub=1, sess=2)
    # Sub01_Ses01.gdf -> Sub01, Ses01
    item_sub = dialog.table.item(0, 1)
    item_sess = dialog.table.item(0, 2)
    assert item_sub.text() == "Sub01"
    assert item_sess.text() == "Ses01"

def test_smart_parser_change_mode(dialog, qtbot):
    """Test switching modes updates the stack and preview."""
    # Switch to Regex
    dialog.radio_regex.setChecked(True)
    assert dialog.settings_stack.currentIndex() == 1
    
    # Set regex pattern
    dialog.regex_input.setText(r"(Sub\d+)_(Ses\d+)")
    # Trigger update manually if needed, but textChanged should handle it
    
    # Check preview
    item_sub = dialog.table.item(0, 1)
    assert item_sub.text() == "Sub01"

def test_smart_parser_split_settings(dialog, qtbot):
    """Test changing split settings."""
    # Change separator to Hyphen (index 1)
    dialog.split_sep_combo.setCurrentIndex(1)
    
    # Filenames don't have hyphen, so split returns [filename]
    # Index 1 (Subject) -> filename
    item_sub = dialog.table.item(0, 1)
    assert item_sub.text() == "Sub01_Ses01"
    
    # Change indices
    dialog.split_sep_combo.setCurrentIndex(0) # Back to underscore
    dialog.split_sub_idx.setValue(2) # Subject is now 2nd part (Ses01)
    
    item_sub = dialog.table.item(0, 1)
    assert item_sub.text() == "Ses01"

def test_smart_parser_results(dialog):
    """Test get_results returns correct dictionary."""
    results = dialog.get_results()
    assert len(results) == 2
    # Key is full path (which was just filename in init)
    assert "Sub01_Ses01.gdf" in results
    assert results["Sub01_Ses01.gdf"] == ("Sub01", "Ses01")

def test_smart_parser_save_load_settings(dialog):
    """Test settings persistence."""
    dialog.split_sub_idx.setValue(5)
    dialog.save_settings()
    
    # Create new dialog, should load 5
    new_dlg = SmartParserDialog([])
    assert new_dlg.split_sub_idx.value() == 5
