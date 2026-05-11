"""Helpers for aggregating runtime diagnostics from loaded EEG data."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from XBrainLab.backend.utils.logger import logger


def collect_runtime_diagnostics(data_list: Iterable[Any]) -> dict[str, Any]:
    """Collect runtime signals and known structured details from data objects."""
    runtime_signals: list[str] = []
    seen_signals: set[str] = set()
    gdf_duplicate_channel_files: list[str] = []
    gdf_duplicate_channel_details: list[dict[str, Any]] = []

    for data in data_list:
        get_signals = getattr(data, "get_runtime_signals", None)
        if callable(get_signals):
            try:
                signals = get_signals()
            except Exception as e:
                logger.warning("Failed to get runtime signals for data: %s", e)
            else:
                if isinstance(signals, list):
                    for signal in signals:
                        if isinstance(signal, str) and signal not in seen_signals:
                            runtime_signals.append(signal)
                            seen_signals.add(signal)

        get_gdf_detail = getattr(data, "get_gdf_duplicate_channel_detail", None)
        if not callable(get_gdf_detail):
            continue

        try:
            detail = get_gdf_detail()
        except Exception as e:
            logger.warning("Failed to get GDF duplicate-channel detail for data: %s", e)
            continue

        if not isinstance(detail, dict):
            continue
        if detail.get("resolved") is True:
            continue

        filename = None
        get_filename = getattr(data, "get_filename", None)
        if callable(get_filename):
            try:
                filename = get_filename()
            except Exception as e:
                logger.warning("Failed to get filename for data: %s", e)

        if isinstance(filename, str) and filename:
            gdf_duplicate_channel_files.append(filename)

        gdf_duplicate_channel_details.append(
            {
                "file": filename,
                "generated_bases": detail.get("generated_bases", []),
                "generated_channels": detail.get("generated_channels", []),
                "message": detail.get("message"),
            },
        )

    return {
        "runtime_signals": runtime_signals,
        "gdf_duplicate_channel_files": gdf_duplicate_channel_files,
        "gdf_duplicate_channel_details": gdf_duplicate_channel_details,
    }
