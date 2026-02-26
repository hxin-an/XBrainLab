"""Tests for VRAMConflictChecker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.ui.components.vram_checker import (
    PANEL_VISUALIZATION,
    VIZ_TAB_3D_PLOT,
    VRAMConflictChecker,
)


@pytest.fixture()
def mock_main_window():
    mw = MagicMock()
    mw.visualization_panel.tabs.currentIndex.return_value = 0
    mw.visualization_panel.isHidden.return_value = False
    mw.stack.currentIndex.return_value = PANEL_VISUALIZATION
    return mw


@pytest.fixture()
def make_checker(mock_main_window):
    def _factory(controller=None):
        return VRAMConflictChecker(mock_main_window, lambda: controller)

    return _factory


class TestVRAMConflictChecker:
    def test_no_warning_when_not_local(self, make_checker):
        checker = make_checker(controller=None)
        with patch.object(VRAMConflictChecker, "_is_local_mode", return_value=False):
            checker.check(switching_to_local=False, switching_to_3d=True)
        # No QMessageBox should be shown — no error

    def test_warning_when_local_and_3d(self, make_checker):
        checker = make_checker()
        with (
            patch.object(VRAMConflictChecker, "_is_local_mode", return_value=True),
            patch.object(VRAMConflictChecker, "_is_3d_active", return_value=True),
            patch("XBrainLab.ui.components.vram_checker.QMessageBox") as mock_box,
        ):
            checker.check(switching_to_local=True, switching_to_3d=True)
            mock_box.warning.assert_called_once()

    def test_no_warning_when_local_but_no_3d(self, make_checker):
        checker = make_checker()
        with (
            patch.object(VRAMConflictChecker, "_is_local_mode", return_value=True),
            patch.object(VRAMConflictChecker, "_is_3d_active", return_value=False),
            patch("XBrainLab.ui.components.vram_checker.QMessageBox") as mock_box,
        ):
            checker.check(switching_to_local=True)
            mock_box.warning.assert_not_called()

    def test_on_viz_tab_changed_triggers_check_for_3d(self, make_checker):
        checker = make_checker()
        with patch.object(checker, "check") as mock_check:
            checker.on_viz_tab_changed(VIZ_TAB_3D_PLOT)
            mock_check.assert_called_once_with(switching_to_3d=True)

    def test_on_viz_tab_changed_ignores_other_tabs(self, make_checker):
        checker = make_checker()
        with patch.object(checker, "check") as mock_check:
            checker.on_viz_tab_changed(0)
            mock_check.assert_not_called()

    def test_is_local_mode_switching(self, make_checker):
        checker = make_checker()
        assert checker._is_local_mode(switching_to_local=True) is True

    def test_is_local_mode_from_controller(self, make_checker):
        ctrl = MagicMock()
        ctrl.worker.engine.config.active_mode = "local"
        checker = make_checker(controller=ctrl)
        assert checker._is_local_mode(switching_to_local=False) is True

    def test_is_local_mode_no_controller(self, make_checker):
        checker = make_checker(controller=None)
        assert checker._is_local_mode(switching_to_local=False) is False

    def test_is_3d_active_switching(self, make_checker, mock_main_window):
        checker = make_checker()
        assert checker._is_3d_active(switching_to_3d=True) is True

    def test_is_3d_active_from_panel(self, make_checker, mock_main_window):
        mock_main_window.visualization_panel.tabs.currentIndex.return_value = (
            VIZ_TAB_3D_PLOT
        )
        checker = make_checker()
        assert checker._is_3d_active(switching_to_3d=False) is True

    def test_is_3d_active_hidden_panel(self, make_checker, mock_main_window):
        mock_main_window.visualization_panel.tabs.currentIndex.return_value = (
            VIZ_TAB_3D_PLOT
        )
        mock_main_window.visualization_panel.isHidden.return_value = True
        checker = make_checker()
        assert checker._is_3d_active(switching_to_3d=False) is False
