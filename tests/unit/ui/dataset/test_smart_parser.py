import pytest
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QWidget

from XBrainLab.ui.dialogs.dataset import SmartParserDialog


@pytest.fixture
def dialog(qtbot):
    filenames = ["Sub01_Ses01.gdf", "Sub02_Ses01.gdf"]
    dlg = SmartParserDialog(filenames)
    qtbot.addWidget(dlg)

    # Reset to known state (Split Mode, Default indices)
    dlg.radio_split.setChecked(True)
    dlg.split_sep_combo.setCurrentIndex(0)  # Underscore
    dlg.split_sub_idx.setValue(1)
    dlg.split_sess_idx.setValue(2)

    # Force update
    dlg.update_preview()

    return dlg


def test_smart_parser_init(dialog):
    """Test initialization and default state."""
    assert dialog.table.rowCount() == 2
    assert dialog.radio_split.isChecked()
    assert dialog.radio_split.text() == "Simple Split"
    assert dialog.radio_regex.text() == "BIDS / Regex"
    assert dialog.radio_fixed.text() == "Fixed Position"
    assert dialog.radio_folder.text() == "Folder Names"

    # Check default parsing (Split by '_', sub=1, sess=2)
    # Sub01_Ses01.gdf -> Sub01, Ses01
    item_sub = dialog.table.item(0, 1)
    item_sess = dialog.table.item(0, 2)
    assert item_sub.text() == "Sub01"
    assert item_sess.text() == "Ses01"


def test_smart_parser_regex_controls_are_compact(dialog):
    dialog.radio_regex.setChecked(True)

    assert dialog.settings_stack.currentIndex() == 1
    assert dialog.regex_input.minimumWidth() == 320
    assert dialog.regex_input.maximumWidth() == 460
    assert dialog.regex_preset_combo.maximumWidth() == 340
    assert dialog.regex_sub_idx.width() == 82
    assert dialog.regex_sess_idx.width() == 82
    assert isinstance(dialog.settings_stack.currentWidget().layout(), QGridLayout)
    labels = dialog.settings_stack.currentWidget().findChildren(
        QLabel,
        "SmartParserSettingsLabel",
    )
    assert [label.text() for label in labels] == ["Preset", "Pattern", "Groups"]


def test_smart_parser_method_radios_use_equal_columns(dialog):
    radios = [
        dialog.radio_split,
        dialog.radio_regex,
        dialog.radio_fixed,
        dialog.radio_folder,
    ]

    assert {radio.minimumWidth() for radio in radios} == {116}
    assert {radio.maximumWidth() for radio in radios} == {116}


def test_smart_parser_folder_page_uses_aligned_pattern_card(dialog):
    dialog.radio_folder.setChecked(True)

    folder_page = dialog.settings_stack.currentWidget()
    example_cards = folder_page.findChildren(QFrame, "SmartParserFolderExample")
    settings_labels = folder_page.findChildren(QLabel, "SmartParserSettingsLabel")

    assert dialog.settings_stack.currentIndex() == 2
    assert isinstance(folder_page.layout(), QGridLayout)
    assert example_cards
    assert [label.text() for label in settings_labels] == ["Pattern", "Example"]
    assert {label.minimumWidth() for label in settings_labels} == {64}
    assert {label.maximumWidth() for label in settings_labels} == {64}
    example_text = " ".join(
        label.text() for label in example_cards[0].findChildren(QLabel)
    )
    assert "Subject01" in example_text
    assert "Session02" in example_text
    assert "#17354b" not in dialog.styleSheet()
    assert "QFrame#SmartParserFolderExample" in dialog.styleSheet()
    assert "border: none" in dialog.styleSheet()
    assert "QLabel#SmartParserFolderChip" in dialog.styleSheet()
    assert "background-color: transparent" in dialog.styleSheet()


def test_smart_parser_fixed_position_uses_aligned_grid(dialog):
    dialog.radio_fixed.setChecked(True)

    fixed_page = dialog.settings_stack.currentWidget()
    grid_widgets = [
        child
        for child in fixed_page.findChildren(QWidget)
        if isinstance(child.layout(), QGridLayout)
    ]
    headers = fixed_page.findChildren(QLabel, "SmartParserFixedHeader")
    fields = fixed_page.findChildren(QLabel, "SmartParserFixedField")

    assert dialog.settings_stack.currentIndex() == 3
    assert grid_widgets
    assert [label.text() for label in headers] == ["Field", "Start", "Length"]
    assert [label.text() for label in fields] == ["Subject", "Session"]
    assert dialog.fixed_sub_start.width() == dialog.fixed_sess_start.width()
    assert dialog.fixed_sub_len.width() == dialog.fixed_sess_len.width()


def test_smart_parser_mode_pages_use_left_aligned_settings_grid(dialog):
    for page_index in range(3):
        page = dialog.settings_stack.widget(page_index)
        assert isinstance(page.layout(), QGridLayout)
        labels = page.findChildren(QLabel, "SmartParserSettingsLabel")
        assert labels
        assert {label.minimumWidth() for label in labels} == {64}
        assert {label.maximumWidth() for label in labels} == {64}

    fixed_page = dialog.settings_stack.widget(3)
    assert isinstance(fixed_page.layout(), QGridLayout)
    assert not fixed_page.findChildren(QLabel, "SmartParserSettingsLabel")


def test_smart_parser_centers_on_parent(qtbot):
    parent = QWidget()
    parent.resize(800, 600)
    parent.move(120, 90)
    parent.show()
    qtbot.addWidget(parent)

    dlg = SmartParserDialog(["Sub01_Ses01.gdf"], parent)
    dlg.resize(400, 300)
    qtbot.addWidget(dlg)
    dlg.show()

    parent_center = parent.frameGeometry().center()
    parser_center = dlg.frameGeometry().center()
    assert abs(parent_center.x() - parser_center.x()) <= 2
    assert abs(parent_center.y() - parser_center.y()) <= 2


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
    dialog.split_sep_combo.setCurrentIndex(0)  # Back to underscore
    dialog.split_sub_idx.setValue(2)  # Subject is now 2nd part (Ses01)

    item_sub = dialog.table.item(0, 1)
    assert item_sub.text() == "Ses01"


def test_smart_parser_results(dialog):
    """Test get_results returns correct dictionary."""
    results = dialog.get_result()
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
