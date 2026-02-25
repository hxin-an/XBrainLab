"""Unit tests for Theme styling utilities."""

import matplotlib
import matplotlib.pyplot as plt
import pytest

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


class TestApplyMatplotlibDarkTheme:
    """apply_matplotlib_dark_theme should style a matplotlib figure."""

    @pytest.fixture(autouse=True)
    def _use_agg(self):
        matplotlib.use("Agg")

    def test_fig_facecolor(self):
        fig, ax = plt.subplots()
        Theme.apply_matplotlib_dark_theme(fig, ax=ax)
        assert fig.get_facecolor() != (1.0, 1.0, 1.0, 1.0)  # not white
        plt.close(fig)

    def test_ax_facecolor(self):
        fig, ax = plt.subplots()
        Theme.apply_matplotlib_dark_theme(fig, ax=ax)
        fc = ax.get_facecolor()
        assert fc != (1.0, 1.0, 1.0, 1.0)
        plt.close(fig)

    def test_multiple_axes(self):
        fig, axes = plt.subplots(1, 2)
        Theme.apply_matplotlib_dark_theme(fig, axes=list(axes))
        for ax in axes:
            assert ax.get_facecolor() != (1.0, 1.0, 1.0, 1.0)
        plt.close(fig)

    def test_auto_detect_axes(self):
        fig, ax = plt.subplots()
        Theme.apply_matplotlib_dark_theme(fig)  # no ax/axes arg
        assert ax.get_facecolor() != (1.0, 1.0, 1.0, 1.0)
        plt.close(fig)

    def test_none_fig_no_crash(self):
        # fig=None shouldn't crash
        Theme.apply_matplotlib_dark_theme(None)

    def test_legend_styled(self):
        fig, ax = plt.subplots()
        ax.plot([1, 2], label="test")
        ax.legend()
        Theme.apply_matplotlib_dark_theme(fig, ax=ax)
        legend = ax.legend_
        assert legend is not None
        plt.close(fig)


class TestGetStyleSheet:
    def test_returns_string(self):
        ss = Theme.get_style_sheet()
        assert isinstance(ss, str)

    def test_contains_background(self):
        ss = Theme.get_style_sheet()
        assert Theme.BACKGROUND_DARK in ss

    def test_contains_qwidget(self):
        ss = Theme.get_style_sheet()
        assert "QWidget" in ss
