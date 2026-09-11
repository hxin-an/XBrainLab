"""Typed public outcomes for asynchronous workflow-panel navigation."""

from __future__ import annotations

from dataclasses import dataclass

# MainWindow constructs its workflow stack in this user-visible order.  These
# names let secondary UI collaborators navigate that fixed topology without
# duplicating numeric positions.
PANEL_DATASET = 0
PANEL_PREPROCESS = 1
PANEL_TRAINING = 2
PANEL_EVALUATION = 3
PANEL_VISUALIZATION = 4

# VisualizationPanel creates these tabs in the same user-visible order.
VISUALIZATION_TAB_SALIENCY_MAP = 0
VISUALIZATION_TAB_SPECTROGRAM = 1
VISUALIZATION_TAB_TOPOGRAPHIC_MAP = 2
VISUALIZATION_TAB_3D_PLOT = 3


@dataclass(frozen=True, slots=True)
class PanelPreparationFailure:
    """Terminal failure for one requested lazy-panel preparation."""

    panel_index: int
    panel_name: str
    message: str
