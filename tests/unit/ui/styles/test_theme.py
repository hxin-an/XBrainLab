"""Unit tests for Theme styling utilities."""

import matplotlib
import matplotlib.pyplot as plt
import pytest
from matplotlib.colors import to_rgba

from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme


class TestThemeConstants:
    """Theme should expose named color constants."""

    def test_background_dark_is_hex(self):
        assert Theme.BACKGROUND_DARK.startswith("#")

    def test_text_primary(self):
        assert Theme.TEXT_PRIMARY == "#ffffff"

    def test_accent_primary(self):
        assert isinstance(Theme.ACCENT_PRIMARY, str)

    def test_chart_colors_defined(self):
        assert Theme.CHART_PRIMARY
        assert Theme.CHART_SECONDARY
        assert Theme.CHART_TERTIARY

    def test_metrics_table_colors(self):
        assert Theme.METRICS_TABLE_BG
        assert Theme.METRICS_TABLE_GRID

    def test_table_selection_uses_one_low_key_token(self):
        assert not hasattr(Theme, "HISTORY_TABLE_SELECTION")
        assert not hasattr(Theme, "METRICS_TABLE_SELECTION")
        assert Theme.TABLE_SELECTION != Theme.METRICS_TABLE_GRID

    def test_disabled_action_buttons_keep_action_semantics(self):
        assert Theme.BTN_SUCCESS_DISABLED_BG == Theme.BTN_DISABLED_BG
        assert Theme.BTN_DANGER_DISABLED_BG != Theme.BTN_DISABLED_BG
        assert Theme.BTN_DANGER_DISABLED_TEXT != Theme.BTN_DISABLED_TEXT
        assert Theme.BTN_WARNING_DISABLED_BG == Theme.BTN_DISABLED_BG


class TestApplyMatplotlibDarkTheme:
    """apply_matplotlib_dark_theme should style a matplotlib figure."""

    @pytest.fixture(autouse=True)
    def _use_agg(self):
        matplotlib.use("Agg")

    def test_fig_facecolor(self):
        fig, ax = plt.subplots()
        try:
            fig.patch.set_facecolor("#010203")

            Theme.apply_matplotlib_dark_theme(fig, ax=ax)

            assert fig.get_facecolor() == to_rgba(Theme.BACKGROUND_MID)
        finally:
            plt.close(fig)

    def test_ax_facecolor(self):
        fig, ax = plt.subplots()
        try:
            ax.set_facecolor("#010203")

            Theme.apply_matplotlib_dark_theme(fig, ax=ax)

            assert ax.get_facecolor() == to_rgba(Theme.BACKGROUND_MID)
        finally:
            plt.close(fig)

    def test_multiple_axes(self):
        fig, axes = plt.subplots(1, 2)
        try:
            for ax in axes:
                ax.set_facecolor("#010203")

            Theme.apply_matplotlib_dark_theme(fig, axes=list(axes))

            for ax in axes:
                assert ax.get_facecolor() == to_rgba(Theme.BACKGROUND_MID)
        finally:
            plt.close(fig)

    def test_auto_detect_axes(self):
        fig, ax = plt.subplots()
        try:
            ax.set_facecolor("#010203")

            Theme.apply_matplotlib_dark_theme(fig)  # no ax/axes arg

            assert ax.get_facecolor() == to_rgba(Theme.BACKGROUND_MID)
        finally:
            plt.close(fig)

    def test_none_figure_is_ignored(self):
        assert Theme.apply_matplotlib_dark_theme(None) is None

    def test_legend_styled(self):
        fig, ax = plt.subplots()
        try:
            ax.plot([1, 2], label="test")
            legend = ax.legend()
            legend.get_frame().set_facecolor("#010203")
            legend.get_frame().set_edgecolor("#010203")
            for text in legend.get_texts():
                text.set_color("#010203")

            Theme.apply_matplotlib_dark_theme(fig, ax=ax)

            assert (
                legend.get_frame().get_facecolor()[:3]
                == to_rgba(Theme.BACKGROUND_MID)[:3]
            )
            assert (
                legend.get_frame().get_edgecolor()[:3] == to_rgba(Theme.TEXT_MUTED)[:3]
            )
            assert all(
                text.get_color() == Theme.TEXT_MUTED for text in legend.get_texts()
            )
        finally:
            plt.close(fig)


class TestMainWindowStylesheet:
    def test_dock_separator_uses_low_key_solid_theme_style(self):
        stylesheet = Stylesheets.MAIN_WINDOW

        assert "QMainWindow::separator" in stylesheet
        assert f"background-color: {Theme.BACKGROUND_LIGHT}" in stylesheet
        assert "width: 1px" in stylesheet
        assert "height: 1px" in stylesheet


class TestSidebarStylesheet:
    def test_sidebar_border_targets_only_the_sidebar_owner(self):
        stylesheet = Stylesheets.SIDEBAR_CONTAINER

        assert "#RightPanel" in stylesheet
        assert "QWidget {" not in stylesheet
        assert "border-left:" in stylesheet
        assert "border-right:" not in stylesheet


class TestPrimaryButtonStylesheet:
    def test_disabled_primary_uses_shared_neutral_button_tokens(self):
        stylesheet = Stylesheets.BTN_PRIMARY

        assert "QPushButton:disabled" in stylesheet
        disabled = stylesheet.split("QPushButton:disabled", maxsplit=1)[1]
        assert f"background-color: {Theme.BTN_DISABLED_BG}" in disabled
        assert f"color: {Theme.BTN_DISABLED_TEXT}" in disabled
        assert f"border: 1px solid {Theme.BTN_DISABLED_BORDER}" in disabled
        assert "font-weight: normal" in disabled
