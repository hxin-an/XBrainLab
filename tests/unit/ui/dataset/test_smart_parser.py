import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

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
    assert dialog.table.columnCount() == 5


def test_smart_parser_preview_exposes_complete_filename_in_tooltip(qtbot):
    filepath = "/capture/sub-01_ses-01_task-motor-imagery_run-01_eeg.gdf"
    dialog = SmartParserDialog([filepath])
    qtbot.addWidget(dialog)

    file_item = dialog.table.item(0, 0)

    assert file_item.text() == "sub-01_ses-01_task-motor-imagery_run-01_eeg.gdf"
    assert file_item.toolTip() == filepath


def test_smart_parser_regex_controls_are_compact(dialog):
    dialog.radio_regex.setChecked(True)

    assert dialog.settings_stack.currentIndex() == 1
    assert dialog.regex_input.minimumWidth() == 320
    assert dialog.regex_input.maximumWidth() == 460
    assert dialog.regex_preset_combo.maximumWidth() == 460
    assert (
        dialog.regex_preset_combo.width()
        >= dialog.regex_preset_combo.sizeHint().width()
    )
    assert dialog.regex_sub_idx.width() >= dialog.regex_sub_idx.sizeHint().width()
    assert dialog.regex_sess_idx.width() >= dialog.regex_sess_idx.sizeHint().width()
    assert (
        dialog.regex_sub_idx.maximumWidth() >= dialog.regex_sub_idx.sizeHint().width()
    )
    assert (
        dialog.regex_sess_idx.maximumWidth() >= dialog.regex_sess_idx.sizeHint().width()
    )
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

    assert len({radio.minimumWidth() for radio in radios}) == 1
    assert all(radio.minimumWidth() >= radio.sizeHint().width() for radio in radios)
    assert all(radio.maximumWidth() > radio.minimumWidth() for radio in radios)


def test_smart_parser_method_labels_do_not_overlap_with_large_ui_font(
    qtbot,
    qapp,
):
    original_font = QFont(qapp.font())
    enlarged_font = QFont(original_font)
    enlarged_font.setPointSize(max(original_font.pointSize() + 5, 14))
    enlarged_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
    qapp.setFont(enlarged_font)
    try:
        parser = SmartParserDialog(["sub-01_ses-01_task-mi_run-01_eeg.gdf"])
        qtbot.addWidget(parser)
        parser.show()
        qapp.processEvents()

        radios = [
            parser.radio_split,
            parser.radio_regex,
            parser.radio_fixed,
            parser.radio_folder,
        ]
        compact_controls = [
            parser.split_sep_combo,
            parser.split_sub_idx,
            parser.split_sess_idx,
            parser.regex_preset_combo,
            parser.regex_sub_idx,
            parser.regex_sess_idx,
        ]
        qtbot.waitUntil(
            lambda: all(
                control.width() >= control.sizeHint().width()
                for control in (*radios, *compact_controls)
            ),
            timeout=1_000,
        )

        row_height = parser.table.verticalHeader().defaultSectionSize()
        assert row_height >= parser.table.fontMetrics().height() + 10
    finally:
        qapp.setFont(original_font)


def test_smart_parser_configuration_uses_available_width_without_title_frame(
    dialog,
):
    method_panel = dialog.findChild(QFrame, "SmartParserMethodPanel")
    section_title = dialog.findChild(QLabel, "SmartParserMethodTitle")

    assert method_panel is not None
    assert section_title is not None
    assert section_title.text() == "Parsing method"
    assert method_panel.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert method_panel.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
    assert method_panel.maximumWidth() >= 16_000
    assert "QFrame#SmartParserMethodPanel" in dialog.styleSheet()


def test_smart_parser_settings_stack_fits_the_active_mode(dialog):
    dialog.radio_regex.setChecked(True)
    regex_height = dialog.settings_stack.height()

    dialog.radio_folder.setChecked(True)
    folder_height = dialog.settings_stack.height()

    assert regex_height == max(dialog.settings_stack.widget(1).sizeHint().height(), 48)
    assert folder_height == max(dialog.settings_stack.widget(2).sizeHint().height(), 48)
    assert folder_height < regex_height


def test_smart_parser_forms_clear_the_mode_row_and_panel_edges(dialog, qapp):
    dialog.show()
    qapp.processEvents()
    method_panel = dialog.findChild(QFrame, "SmartParserMethodPanel")
    assert method_panel is not None

    for radio in (
        dialog.radio_split,
        dialog.radio_regex,
        dialog.radio_folder,
        dialog.radio_fixed,
    ):
        radio.setChecked(True)
        qapp.processEvents()
        stack_top = dialog.settings_stack.mapTo(method_panel, QPoint(0, 0)).y()
        mode_bottom = max(
            mode.mapTo(method_panel, QPoint(0, mode.height())).y()
            for mode in (
                dialog.radio_split,
                dialog.radio_regex,
                dialog.radio_folder,
                dialog.radio_fixed,
            )
        )
        assert stack_top - mode_bottom >= 20

        page = dialog.settings_stack.currentWidget()
        controls = []
        for widget_type in (QComboBox, QLineEdit, QSpinBox):
            controls.extend(page.findChildren(widget_type))
        assert all(
            control.mapTo(page, QPoint(0, control.height())).y() <= page.height() - 8
            for control in controls
        )

        page_layout = page.layout()
        if isinstance(page_layout, QGridLayout):
            for row in range(page_layout.rowCount()):
                label_item = page_layout.itemAtPosition(row, 0)
                field_item = page_layout.itemAtPosition(row, 1)
                if (
                    label_item is not None
                    and field_item is not None
                    and isinstance(label_item.widget(), QLabel)
                    and field_item.widget() is not None
                ):
                    assert label_item.alignment() & Qt.AlignmentFlag.AlignVCenter
                    label = label_item.widget()
                    field = field_item.widget()
                    assert label.height() >= field.sizeHint().height()
                    label_center = label.mapTo(
                        page,
                        QPoint(0, label.height() // 2),
                    ).y()
                    field_center = field.mapTo(
                        page,
                        QPoint(0, field.height() // 2),
                    ).y()
                    assert abs(label_center - field_center) <= 1


def test_smart_parser_preview_height_fits_rows_without_large_empty_viewport(
    dialog,
):
    header = dialog.table.horizontalHeader()
    vertical_header = dialog.table.verticalHeader()
    assert header is not None
    assert vertical_header is not None

    expected_height = (
        header.sizeHint().height()
        + (vertical_header.defaultSectionSize() * 3)
        + (2 * dialog.table.frameWidth())
    )

    assert dialog.table.minimumHeight() == expected_height
    assert dialog.table.maximumHeight() == expected_height
    assert expected_height < 260


def test_smart_parser_folder_page_uses_aligned_pattern_card(dialog):
    dialog.radio_folder.setChecked(True)

    folder_page = dialog.settings_stack.currentWidget()
    example_cards = folder_page.findChildren(QFrame, "SmartParserFolderExample")
    settings_labels = folder_page.findChildren(QLabel, "SmartParserSettingsLabel")

    assert dialog.settings_stack.currentIndex() == 2
    assert isinstance(folder_page.layout(), QGridLayout)
    assert example_cards
    assert [label.text() for label in settings_labels] == ["Pattern", "Example"]
    assert all(
        label.minimumWidth() >= label.sizeHint().width() for label in settings_labels
    )
    assert all(label.maximumWidth() > label.minimumWidth() for label in settings_labels)
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
        assert all(label.minimumWidth() >= label.sizeHint().width() for label in labels)
        assert all(label.maximumWidth() > label.minimumWidth() for label in labels)

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
    assert results["Sub01_Ses01.gdf"] == ("Sub01", "Ses01", "-", "-")


def test_smart_parser_bids_entities_include_task_and_run(qtbot):
    dialog = SmartParserDialog(["/data/sub-01_task-mi_run-02_raw.fif"])
    qtbot.addWidget(dialog)

    dialog.update_preview()
    results = dialog.get_result()

    assert dialog.table.item(0, 1).text() == "01"
    assert dialog.table.item(0, 2).text() == "-"
    assert dialog.table.item(0, 3).text() == "mi"
    assert dialog.table.item(0, 4).text() == "02"
    assert results["/data/sub-01_task-mi_run-02_raw.fif"] == (
        "01",
        "-",
        "mi",
        "02",
    )


def test_smart_parser_save_load_settings(dialog):
    """Test settings persistence."""
    dialog.split_sub_idx.setValue(5)
    dialog.save_settings()

    # Create new dialog, should load 5
    new_dlg = SmartParserDialog([])
    assert new_dlg.split_sub_idx.value() == 5
