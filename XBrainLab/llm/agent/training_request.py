"""Shared extraction of explicit training options from a user request."""

from __future__ import annotations

import re

from XBrainLab.backend.training.input_contract import (
    training_option_value_is_valid,
)


def extract_explicit_training_options(text: str) -> dict[str, str]:
    """Return only valid epoch, batch-size, and learning-rate values in text."""
    normalized = text.casefold()
    values: dict[str, str] = {}
    number = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?"
    patterns = {
        "epoch": (
            rf"\b(?:epochs?|epoch count)\s*(?:=|:|is)?\s*({number})(?!\w|\.\d)",
            rf"(?<![\w.])({number})\s+epochs?\b",
        ),
        "batch_size": (
            rf"\b(?:batch(?:[_ ]size)?|bs)\s*(?:=|:|is)?\s*({number})(?!\w|\.\d)",
        ),
        "learning_rate": (
            rf"\b(?:learning[_ ]rate|lr)\s*(?:=|:|is)?\s*({number})(?!\w|\.\d)",
        ),
    }
    for key, candidates in patterns.items():
        for pattern in candidates:
            match = re.search(pattern, normalized)
            if match is None:
                continue
            value = match.group(1)
            if training_option_value_is_valid(key, value):
                values[key] = value
                break
    return values


def contains_explicit_training_options(text: str) -> bool:
    """Return whether text requests or supplies training hyperparameters."""
    normalized = text.casefold()
    return bool(
        extract_explicit_training_options(normalized)
        or re.search(
            r"\b(?:epochs?|epoch[_ ]count|batch(?:[_ ]size)?|bs|"
            r"learning[_ ]rate|lr|optimizer|device|repeats?)\b",
            normalized,
        )
        or any(marker in normalized for marker in ("訓練參數", "批次大小", "學習率"))
    )
