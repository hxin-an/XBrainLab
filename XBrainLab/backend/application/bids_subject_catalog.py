"""Lightweight BIDS subject catalog projected from the backend-owned index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import bids_dataset_index as bids_index_module
from .bids_dataset_index import BidsDatasetIndex


def inspect_bids_subject_catalog(
    source_path: str | Path,
    *,
    bids_index: BidsDatasetIndex | None = None,
) -> dict[str, Any]:
    """Return subject summaries without a second filesystem traversal."""
    index = bids_index
    if index is None or not index.matches_root(source_path) or not index.is_current():
        index = bids_index_module.build_bids_dataset_index(source_path)
    if index.root_validation_issue:
        if "dataset_description.json is missing" in index.root_validation_issue:
            raise ValueError(
                "The selected folder is not a BIDS root: "
                "dataset_description.json is missing."
            )
        raise ValueError(index.root_validation_issue)
    return index.subject_catalog()
