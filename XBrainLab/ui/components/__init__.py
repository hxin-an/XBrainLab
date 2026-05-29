# pyright: reportUnsupportedDunderAll=false
"""Reusable UI components for XBrainLab panels and dialogs.

Keep package-level imports lazy. Several panels import one lightweight component
from this package during startup; eager visualization widgets pull Matplotlib
before the user opens Visualization or Training.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "CardWidget": ".card",
    "PlaceholderWidget": ".placeholder",
    "PlotFigureWindow": ".plot_figure_window",
    "SinglePlotWindow": ".single_plot_window",
}

__all__ = [
    "CardWidget",
    "PlaceholderWidget",
    "PlotFigureWindow",
    "SinglePlotWindow",
]


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
