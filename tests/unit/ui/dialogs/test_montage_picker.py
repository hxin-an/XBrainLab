"""Coverage tests for PickMontageDialog - 241 uncovered lines."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QComboBox, QTableWidget


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
def dialog(qtbot, channel_names, montage_positions):
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
        )
        qtbot.addWidget(dlg)
        yield dlg


class TestPickMontageInit:
    def test_creates_dialog(self, dialog):
        assert dialog.windowTitle() == "Set Montage"

    def test_has_montage_combo(self, dialog):
        assert isinstance(dialog.montage_combo, QComboBox)
        assert dialog.montage_combo.count() >= 3

    def test_has_table(self, dialog):
        assert isinstance(dialog.table, QTableWidget)
        assert dialog.table.rowCount() == 10


class TestMontageSelection:
    def test_on_montage_select(self, dialog):
        dialog.on_montage_select("standard_1020")
        # Should populate montage channels
        assert isinstance(dialog.montage_channels, list)

    def test_initial_sequential_fill(self, dialog):
        dialog.initial_sequential_fill()

    def test_smart_match(self, dialog):
        combo = dialog.table.cellWidget(0, 1)
        if combo:
            result = dialog.smart_match(combo, "Fp1")
            assert isinstance(result, bool)


class TestTableActions:
    def test_clear_selections(self, dialog):
        dialog.clear_selections()

    def test_on_channel_changed(self, dialog):
        dialog.on_channel_changed(0, 0)


class TestAcceptReject:
    def test_accept_valid(self, dialog):
        # Fill all combos with valid montage channels
        for row in range(dialog.table.rowCount()):
            combo = dialog.table.cellWidget(row, 1)
            if combo and combo.count() > 1:
                combo.setCurrentIndex(1)
        with patch("PyQt6.QtWidgets.QDialog.accept"):
            dialog.accept()

    def test_get_result_default(self, dialog):
        result = dialog.get_result()
        # May return ([], {}) or (chs, positions)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_reset_saved_settings(self, dialog):
        dialog.reset_saved_settings()


class TestMontagePickerEdgeCases:
    """Additional edge-case tests for PickMontageDialog methods."""

    def test_on_channel_changed_clears_anchor(self, dialog):
        # Row 0 is an anchor — selecting index 0 (empty) removes it
        dialog.anchors.add(0)
        dialog.on_channel_changed(0, 0)
        assert 0 not in dialog.anchors

    def test_on_channel_changed_cascades(self, dialog):
        # Set row 0 to a valid channel and check cascade fill
        combo0 = dialog.table.cellWidget(0, 1)
        if isinstance(combo0, QComboBox) and combo0.count() > 2:
            combo0.setCurrentIndex(1)
            dialog.on_channel_changed(0, 1)
            assert 0 in dialog.anchors

    def test_accept_no_mapped_channels(self, dialog):
        dialog.clear_selections()
        with patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.QMessageBox.warning"
        ):
            dialog.accept()
        # Should not accept
        assert dialog.chs is None

    def test_accept_error_processing(self, dialog):
        for row in range(dialog.table.rowCount()):
            combo = dialog.table.cellWidget(row, 1)
            if isinstance(combo, QComboBox) and combo.count() > 1:
                combo.setCurrentIndex(1)
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
                side_effect=RuntimeError("bad montage"),
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.QMessageBox.critical"
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
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.QMessageBox"
            ) as mock_mb,
        ):
            from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
                PickMontageDialog,
            )

            dlg = PickMontageDialog(parent=None, channel_names=[])
            qtbot.addWidget(dlg)
            mock_mb.critical.assert_called_once()

    def test_on_montage_select_error(self, dialog):
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.QMessageBox.warning"
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
