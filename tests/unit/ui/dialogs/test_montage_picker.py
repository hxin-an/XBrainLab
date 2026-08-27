"""Coverage tests for PickMontageDialog - 241 uncovered lines."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QComboBox, QDialogButtonBox, QLabel, QTableWidget

from XBrainLab.ui.styles.theme import Theme


@pytest.fixture
def channel_names():
    return ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2"]


@pytest.fixture
def montage_positions():
    """Mock montage positions returned by mne_helper."""
    return {
        "Fp1": (0.0, 0.9, 0.0),
        "Fp2": (0.3, 0.9, 0.0),
        "F3": (-0.3, 0.5, 0.0),
        "F4": (0.3, 0.5, 0.0),
        "C3": (-0.3, 0.0, 0.0),
        "C4": (0.3, 0.0, 0.0),
        "P3": (-0.3, -0.5, 0.0),
        "P4": (0.3, -0.5, 0.0),
        "O1": (-0.1, -0.9, 0.0),
        "O2": (0.1, -0.9, 0.0),
    }


@pytest.fixture
def dialog(qtbot, channel_names, montage_positions, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    QSettings.setPath(
        QSettings.Format.NativeFormat,
        QSettings.Scope.UserScope,
        str(tmp_path / "qt-settings"),
    )
    with (
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
            return_value=["standard_1020", "standard_1005", "biosemi64"],
        ),
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
            return_value={"ch_pos": montage_positions},
        ),
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
            return_value=montage_positions,
        ),
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        dlg = PickMontageDialog(
            parent=None,
            channel_names=channel_names,
            default_montage="standard_1020",
        )
        qtbot.addWidget(dlg)
        yield dlg


class TestPickMontageInit:
    def test_creates_dialog(self, dialog):
        assert dialog.windowTitle() == "Electrode Layout"

    def test_has_montage_combo(self, dialog):
        assert isinstance(dialog.montage_combo, QComboBox)
        assert dialog.montage_combo.count() >= 3

    def test_has_table(self, dialog):
        assert isinstance(dialog.table, QTableWidget)
        assert dialog.table.rowCount() == 10
        assert dialog.table.horizontalHeaderItem(0).text() == "Dataset Channel"
        assert dialog.table.horizontalHeaderItem(1).text() == "Electrode"

    def test_mapping_table_uses_integrated_dark_table_style(self, dialog):
        assert dialog.table.objectName() == "MontageMappingTable"
        assert dialog.table.alternatingRowColors() is True
        assert dialog.table.showGrid() is False

        stylesheet = dialog.table.styleSheet()
        assert "QTableWidget#MontageMappingTable" in stylesheet
        assert f"alternate-background-color: {Theme.METRICS_TABLE_ALT_BG}" in stylesheet
        assert f"background-color: {Theme.BACKGROUND_MID}" in stylesheet

        first_item = dialog.table.item(0, 0)
        second_item = dialog.table.item(1, 0)
        assert first_item is not None
        assert second_item is not None
        assert first_item.background().color() == QColor(Theme.METRICS_TABLE_BG)
        assert second_item.background().color() == QColor(Theme.METRICS_TABLE_ALT_BG)
        assert first_item.foreground().color() == QColor(Theme.TEXT_PRIMARY)

    def test_montage_channel_combo_is_flat_inside_table_cell(self, dialog):
        combo = dialog.table.cellWidget(0, 1)
        assert isinstance(combo, QComboBox)
        assert combo.objectName() == "MontageChannelCombo"
        stylesheet = combo.styleSheet()
        assert "border: none" in stylesheet
        assert f"background-color: {Theme.METRICS_TABLE_BG}" in stylesheet
        assert "QAbstractItemView" in stylesheet

    def test_ok_cancel_buttons_have_no_icons(self, dialog):
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        for standard in (
            QDialogButtonBox.StandardButton.Ok,
            QDialogButtonBox.StandardButton.Cancel,
        ):
            button = buttons.button(standard)
            assert button is not None
            assert button.icon().isNull()

    def test_bids_summary_expands_and_returns_without_persisting_changes(
        self, dialog, qtbot, channel_names
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        bids_dialog = PickMontageDialog(
            parent=None,
            channel_names=channel_names,
            is_bids_source=True,
            current_layout={
                "source": "bids",
                "name": "BIDS coordinates",
                "status": "ready",
                "positioned_channel_count": 10,
                "channel_count": 10,
                "coordinate_summary": "head",
            },
        )
        qtbot.addWidget(bids_dialog)
        before = bids_dialog.settings.allKeys()

        assert bids_dialog.summary_page.isHidden() is False
        assert bids_dialog.mapping_page.isHidden() is True
        assert bids_dialog.minimumHeight() == 200
        bids_dialog.show_mapping_page()
        assert bids_dialog.summary_page.isHidden() is True
        assert bids_dialog.mapping_page.isHidden() is False
        assert bids_dialog.minimumHeight() == 320
        bids_dialog.show_summary_page()
        bids_dialog.reject()

        assert bids_dialog.settings.allKeys() == before

    def test_bids_summary_has_one_primary_change_action(
        self, dialog, qtbot, channel_names
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        bids_dialog = PickMontageDialog(
            parent=None,
            channel_names=channel_names,
            is_bids_source=True,
            current_layout={"source": "bids", "status": "ready"},
        )
        qtbot.addWidget(bids_dialog)

        assert bids_dialog.btn_change_layout.text() == "Change layout…"
        assert bids_dialog.btn_change_layout.property("primaryAction") is True
        assert bids_dialog.btn_close.property("primaryAction") is not True
        assert bids_dialog.btn_use_bids.isHidden() is True

    def test_manual_override_makes_restore_the_single_primary_action(
        self, dialog, qtbot, channel_names
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        restore_dialog = PickMontageDialog(
            parent=None,
            channel_names=channel_names,
            is_bids_source=True,
            current_layout={
                "source": "manual",
                "status": "ready",
                "name": "standard_1020",
                "positioned_channel_count": 18,
                "channel_count": 22,
                "coordinate_summary": "head",
                "bids_restore_available": True,
            },
        )
        qtbot.addWidget(restore_dialog)

        assert restore_dialog.btn_change_layout.text() == "Choose another layout…"
        assert restore_dialog.btn_change_layout.property("primaryAction") is not True
        assert restore_dialog.btn_use_bids.property("primaryAction") is True
        assert restore_dialog.btn_close.text() == "Close"
        labels = [
            label.text()
            for label in restore_dialog.findChildren(
                QLabel, "ElectrodeLayoutMetricLabel"
            )
        ]
        values = [
            label.text()
            for label in restore_dialog.findChildren(
                QLabel, "ElectrodeLayoutMetricValue"
            )
        ]
        assert labels == ["Layout", "Status", "Coverage", "Coordinate frame"]
        assert values == ["standard_1020", "ready", "18/22 positioned", "head"]

    def test_bids_summary_replace_and_restore_intents_are_distinct(
        self, dialog, qtbot, channel_names
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        replace_dialog = PickMontageDialog(
            parent=None,
            channel_names=channel_names,
            is_bids_source=True,
            current_layout={"source": "bids", "status": "ready"},
        )
        qtbot.addWidget(replace_dialog)
        replace_dialog.show_mapping_page()
        combo = replace_dialog.table.cellWidget(0, 1)
        assert isinstance(combo, QComboBox)
        combo.setCurrentIndex(1)
        replace_dialog.accept()
        selected, positions = replace_dialog.get_result()
        assert selected is not None
        assert channel_names[0] in selected
        assert positions is not None
        assert replace_dialog.restore_bids_requested() is False

        restore_dialog = PickMontageDialog(
            parent=None,
            channel_names=channel_names,
            is_bids_source=True,
            current_layout={
                "source": "manual",
                "status": "ready",
                "bids_restore_available": True,
            },
        )
        qtbot.addWidget(restore_dialog)
        restore_dialog.restore_bids()

        assert restore_dialog.restore_bids_requested() is True
        assert restore_dialog.get_result() == (None, None)

    def test_bids_summary_disables_replace_and_restore_while_training(
        self, dialog, qtbot, channel_names
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        bids_dialog = PickMontageDialog(
            parent=None,
            channel_names=channel_names,
            is_bids_source=True,
            layout_changes_allowed=False,
            current_layout={
                "source": "manual",
                "status": "ready",
                "bids_restore_available": True,
            },
        )
        qtbot.addWidget(bids_dialog)

        assert bids_dialog.btn_change_layout.isEnabled() is False
        assert bids_dialog.btn_use_bids.isEnabled() is False

    def test_mapping_action_labels_have_unconstrained_text_width(self, dialog):
        assert dialog.btn_clear.text() == "Clear mapping"
        assert dialog.btn_clear.minimumWidth() <= dialog.btn_clear.sizeHint().width()
        assert dialog.btn_clear.maximumWidth() >= dialog.btn_clear.sizeHint().width()
        assert dialog.mapping_toolbar.indexOf(
            dialog.btn_reset_saved
        ) < dialog.mapping_toolbar.indexOf(dialog.btn_clear)
        apply_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert apply_button is not None
        assert apply_button.text() == "Apply"

    def test_bids_auto_match_then_back_preserves_saved_mapping(
        self, dialog, qtbot, channel_names
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        montage_name = dialog.montage_combo.currentText()
        dialog.settings.setValue(f"mapping/{montage_name}", {"Fp1": "Fp1"})
        bids_dialog = PickMontageDialog(
            parent=None,
            channel_names=channel_names,
            is_bids_source=True,
            current_layout={"source": "bids", "status": "ready"},
        )
        qtbot.addWidget(bids_dialog)
        bids_dialog.show_mapping_page()
        bids_dialog.reset_saved_settings()
        bids_dialog.show_summary_page()
        bids_dialog.reject()

        assert bids_dialog.settings.value(f"mapping/{montage_name}", {}) == {
            "Fp1": "Fp1"
        }

    def test_small_channel_list_fits_table_and_dialog_to_content(
        self,
        qtbot,
        montage_positions,
        monkeypatch,
        tmp_path,
    ):
        """A short channel list must not leave a large empty table viewport."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config-small"))
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
                return_value=["standard_1020"],
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
                return_value={"ch_pos": montage_positions},
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
                return_value=montage_positions,
            ),
        ):
            from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
                PickMontageDialog,
            )

            dlg = PickMontageDialog(
                parent=None,
                channel_names=["F3", "F4", "C3", "C4", "P3"],
            )
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitExposed(dlg)

        assert dlg.table.height() <= 240
        assert dlg.height() <= 420


class TestMontageSelection:
    def test_on_montage_select(self, dialog):
        dialog.on_montage_select("standard_1020")
        # Should populate montage channels
        assert isinstance(dialog.montage_channels, list)

    def test_unmatched_channel_is_not_inferred_from_row_order(self, dialog):
        # A change to one reviewed row must not fill its neighbour with the
        # next standard-layout electrode.
        first = dialog.table.cellWidget(0, 1)
        second = dialog.table.cellWidget(1, 1)
        assert isinstance(first, QComboBox)
        assert isinstance(second, QComboBox)
        second.setCurrentIndex(0)
        first.setCurrentIndex(first.findText("F3"))
        assert second.currentText() == ""

    def test_smart_match(self, dialog):
        combo = dialog.table.cellWidget(0, 1)
        if combo:
            result = dialog.smart_match(combo, "Fp1")
            assert isinstance(result, bool)

    def test_non_bids_unique_best_prefills_only_safe_one_to_one_matches(
        self, qtbot, monkeypatch, tmp_path
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config-safe"))
        positions = {
            "candidate-a": {"ch_pos": {"C3": (0, 0, 0), "C4": (1, 0, 0)}},
            "candidate-b": {"ch_pos": {"F3": (0, 0, 0)}},
        }
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
                return_value=list(positions),
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
                side_effect=lambda name: positions[name],
            ),
        ):
            picker = PickMontageDialog(
                parent=None,
                channel_names=["EEG C3-REF", "C4", "EOG1", "12"],
            )
        qtbot.addWidget(picker)

        assert picker.montage_combo.currentText() == "candidate-a"
        assert picker.table.cellWidget(0, 1).currentText() == "C3"
        assert picker.table.cellWidget(1, 1).currentText() == "C4"
        assert picker.table.cellWidget(2, 1).currentText() == ""
        assert picker.table.cellWidget(3, 1).currentText() == ""

    def test_non_bids_tied_or_ambiguous_matches_stay_unselected(
        self, qtbot, monkeypatch, tmp_path
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config-tie"))
        QSettings.setPath(
            QSettings.Format.NativeFormat,
            QSettings.Scope.UserScope,
            str(tmp_path / "qt-settings-tie"),
        )
        QSettings("XBrainLab", "MontagePicker").setValue("last_montage", "candidate-a")
        positions = {
            "candidate-a": {"ch_pos": {"C3": (0, 0, 0)}},
            "candidate-b": {"ch_pos": {"C3": (0, 0, 0)}},
        }
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
                return_value=list(positions),
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
                side_effect=lambda name: positions[name],
            ),
        ):
            picker = PickMontageDialog(parent=None, channel_names=["C3"])
        qtbot.addWidget(picker)

        apply_button = picker.button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert apply_button is not None
        assert picker.montage_combo.currentText() == "Select layout"
        assert apply_button.isEnabled() is False
        before_mapping = picker.settings.value("mapping_v2/candidate-a", {})
        with patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.show_warning"
        ) as warning:
            picker.accept()
        warning.assert_called_once()
        assert picker.settings.value("last_montage", "") == "candidate-a"
        assert picker.settings.value("mapping_v2/candidate-a", {}) == before_mapping

        with patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
            side_effect=lambda name: positions[name],
        ):
            picker.montage_combo.setCurrentText("candidate-a")
        assert apply_button.isEnabled() is True
        combo = picker.table.cellWidget(0, 1)
        assert isinstance(combo, QComboBox)
        assert combo.currentText() == "C3"
        with patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
            return_value=[(0.0, 0.0, 0.0)],
        ):
            picker.accept()
        assert picker.get_result() == (["C3"], [(0.0, 0.0, 0.0)])
        assert picker.settings.value("last_montage", "") == "candidate-a"

    def test_non_bids_no_match_stays_unselected_and_cannot_save(
        self, qtbot, monkeypatch, tmp_path
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config-no-match"))
        QSettings.setPath(
            QSettings.Format.NativeFormat,
            QSettings.Scope.UserScope,
            str(tmp_path / "qt-settings-no-match"),
        )
        QSettings("XBrainLab", "MontagePicker").setValue("last_montage", "candidate")
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
                return_value=["candidate"],
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
                return_value={"ch_pos": {"C3": (0, 0, 0)}},
            ),
        ):
            picker = PickMontageDialog(parent=None, channel_names=["unknown"])
        qtbot.addWidget(picker)

        apply_button = picker.button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert apply_button is not None
        assert picker.montage_combo.currentText() == "Select layout"
        assert apply_button.isEnabled() is False
        before_mapping = picker.settings.value("mapping_v2/candidate", {})
        with patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.show_warning"
        ) as warning:
            picker.accept()
        warning.assert_called_once()
        assert picker.settings.value("last_montage", "") == "candidate"
        assert picker.settings.value("mapping_v2/candidate", {}) == before_mapping

    def test_saved_mapping_requires_exact_ordered_channel_schema(
        self, qtbot, monkeypatch, tmp_path
    ):
        from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
            PickMontageDialog,
        )

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config-schema"))
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
                return_value=["candidate"],
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
                return_value={"ch_pos": {"C3": (0, 0, 0), "C4": (1, 0, 0)}},
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
                return_value=[(0, 0, 0), (1, 0, 0)],
            ),
        ):
            first = PickMontageDialog(parent=None, channel_names=["C3", "C4"])
            qtbot.addWidget(first)
            first.table.cellWidget(0, 1).setCurrentText("C4")
            first.table.cellWidget(1, 1).setCurrentText("C3")
            first.accept()
            reordered = PickMontageDialog(parent=None, channel_names=["C4", "C3"])
        qtbot.addWidget(reordered)

        assert reordered.table.cellWidget(0, 1).currentText() == "C4"
        assert reordered.table.cellWidget(1, 1).currentText() == "C3"


class TestTableActions:
    def test_clear_selections(self, dialog):
        dialog.clear_selections()


class TestAcceptReject:
    def test_accept_rejects_duplicate_electrodes_without_persisting(self, dialog):
        montage_name = dialog.montage_combo.currentText()
        existing = {
            "channel_schema": list(dialog.channel_names),
            "mapping": {"Fp1": "Fp1", "Fp2": "Fp2"},
        }
        dialog.settings.setValue(f"mapping_v2/{montage_name}", existing)
        first = dialog.table.cellWidget(0, 1)
        second = dialog.table.cellWidget(1, 1)
        assert isinstance(first, QComboBox)
        assert isinstance(second, QComboBox)
        first.setCurrentText("F3")
        second.setCurrentText("F3")

        with patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.show_warning"
        ) as warning:
            dialog.accept()

        warning.assert_called_once()
        assert dialog.result() == 0
        assert dialog.get_result() == (None, None)
        assert dialog.settings.value(f"mapping_v2/{montage_name}", {}) == existing

    def test_accept_valid(self, dialog):
        # Fill all combos with valid montage channels
        for row in range(dialog.table.rowCount()):
            combo = dialog.table.cellWidget(row, 1)
            if combo and combo.count() > 1:
                combo.setCurrentIndex(min(row + 1, combo.count() - 1))
        with patch("PyQt6.QtWidgets.QDialog.accept"):
            dialog.accept()

    def test_get_result_default(self, dialog):
        result = dialog.get_result()
        # May return ([], {}) or (chs, positions)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_reset_saved_settings(self, dialog):
        montage_name = dialog.montage_combo.currentText()
        dialog.settings.setValue(f"mapping/{montage_name}", {"C3": "C3"})

        dialog.reset_saved_settings()

        assert dialog.settings.value(f"mapping/{montage_name}", {}) == {"C3": "C3"}


class TestMontagePickerEdgeCases:
    """Additional edge-case tests for PickMontageDialog methods."""

    def test_accept_no_mapped_channels(self, dialog):
        dialog.clear_selections()
        with patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.show_warning"
        ):
            dialog.accept()
        # Should not accept
        assert dialog.chs is None

    def test_accept_error_processing(self, dialog):
        for row in range(dialog.table.rowCount()):
            combo = dialog.table.cellWidget(row, 1)
            if isinstance(combo, QComboBox) and combo.count() > 1:
                combo.setCurrentIndex(min(row + 1, combo.count() - 1))
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
                side_effect=RuntimeError("bad montage"),
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog."
                "present_unexpected_error"
            ),
        ):
            dialog.accept()
        assert dialog.chs is None

    def test_empty_channel_names(self, qtbot):
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
                return_value=["standard_1020"],
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.show_error"
            ) as mock_error,
        ):
            from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
                PickMontageDialog,
            )

            dlg = PickMontageDialog(parent=None, channel_names=[])
            qtbot.addWidget(dlg)
            mock_error.assert_called_once()

    def test_on_montage_select_error(self, dialog):
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog."
                "present_unexpected_error"
            ),
        ):
            dialog.on_montage_select("standard_1020")

    def test_smart_match_case_insensitive(self, dialog):
        combo = dialog.table.cellWidget(0, 1)
        if isinstance(combo, QComboBox):
            result = dialog.smart_match(combo, "fp1")
            assert result is True

    def test_smart_match_no_match(self, dialog):
        combo = dialog.table.cellWidget(0, 1)
        if isinstance(combo, QComboBox):
            result = dialog.smart_match(combo, "NONEXISTENT_XYZ")
            assert result is False
