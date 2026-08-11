"""Lightweight product constants shared by training commands and services."""

from __future__ import annotations

from XBrainLab.backend.model_catalog_contract import TRAINING_MODEL_NAMES

DEFAULT_TRAINING_OUTPUT_DIR = "./output/runs"

__all__ = ["DEFAULT_TRAINING_OUTPUT_DIR", "TRAINING_MODEL_NAMES"]
