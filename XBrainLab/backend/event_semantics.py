"""Format-level EEG event semantics shared by import paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mne

_GDF_EVENT_SEMANTICS: dict[str, dict[str, str]] = {
    "1023": {
        "bucket": "not_used",
        "use_as": "Exclude bad trials",
        "reason": "Rejected / artifact trial",
        "evidence": "GDF event semantics",
    },
    "32766": {
        "bucket": "not_used",
        "use_as": "Ignore",
        "reason": "System / boundary marker",
        "evidence": "GDF event semantics",
    },
}


def gdf_event_semantic(code: str, suffixes: set[str]) -> dict[str, str] | None:
    """Return a standard GDF event role when every source is a GDF file."""
    normalized_suffixes = {str(suffix).casefold() for suffix in suffixes}
    if normalized_suffixes != {".gdf"}:
        return None
    semantic = _GDF_EVENT_SEMANTICS.get(str(code).strip())
    return dict(semantic) if semantic is not None else None


def mark_gdf_rejected_trials(data: Any) -> bool:
    """Convert GDF rejected-trial code 1023 to an MNE BAD annotation."""
    if _data_suffix(data) != ".gdf":
        return False
    mne_data = data.get_mne()
    annotations = getattr(mne_data, "annotations", None)
    if annotations is None or len(annotations) == 0:
        return False
    descriptions = list(annotations.description)
    changed = False
    for index, description in enumerate(descriptions):
        if _normalized_event_code(description) == "1023":
            descriptions[index] = "BAD_rejected_trial"
            changed = True
    if not changed:
        return False
    mne_data.set_annotations(
        mne.Annotations(
            onset=annotations.onset,
            duration=annotations.duration,
            description=descriptions,
            orig_time=annotations.orig_time,
        ),
    )
    return True


def _data_suffix(data: Any) -> str:
    for name in ("get_filepath", "get_filename"):
        getter = getattr(data, name, None)
        if not callable(getter):
            continue
        value = getter()
        if value:
            return Path(str(value)).suffix.casefold()
    return ""


def _normalized_event_code(description: Any) -> str:
    normalized = " ".join(str(description).strip().split()).casefold()
    aliases = {
        "1023": "1023",
        "stimulus/s 1023": "1023",
        "event/e 1023": "1023",
    }
    return aliases.get(normalized, normalized)
