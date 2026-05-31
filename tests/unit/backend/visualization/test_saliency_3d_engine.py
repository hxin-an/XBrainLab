from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest

from XBrainLab.backend.visualization.saliency_3d_engine import Saliency3DEngine


class _EpochData:
    event_id: ClassVar[dict[str, int]] = {"left": 0, "right": 1}


def test_3d_saliency_key_resolution_skips_empty_default_event() -> None:
    saliency_store = {
        0: np.empty((0, 4, 32)),
        1: np.ones((2, 4, 32)),
    }

    key = Saliency3DEngine._resolve_saliency_label_key(
        saliency_store,
        _EpochData(),
        "left",
    )

    assert key == 1


def test_3d_saliency_key_resolution_requires_nonempty_saliency_data() -> None:
    saliency_store = {0: np.empty((0, 4, 32))}

    with pytest.raises(KeyError, match="Available saliency keys: 0"):
        Saliency3DEngine._resolve_saliency_label_key(
            saliency_store,
            _EpochData(),
            "left",
        )
