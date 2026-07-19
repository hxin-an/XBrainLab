"""Strict local BIDS channels.tsv review and bad-channel application."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .data_interpretation_resource_reader import AdmittedResourceReader


@dataclass(frozen=True)
class BidsChannelReview:
    """Per-run status truth from exact local channels.tsv sidecars."""

    status: str = "not_applicable"
    scope: str = "exact_local_sidecar_only"
    runs: list[dict[str, Any]] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "scope": self.scope,
            "runs": [dict(row) for row in self.runs],
            "blocked_reasons": list(self.blocked_reasons),
            "warnings": list(self.warnings),
        }


def review_bids_channel_sidecars(
    *,
    bids: Mapping[str, Any],
    selected_eeg_files: Iterable[str],
    resource_reader: AdmittedResourceReader | None = None,
) -> BidsChannelReview:
    """Parse exact per-run channels.tsv files after resource admission."""
    if not bool(bids.get("is_bids")):
        return BidsChannelReview()
    selected = {_path_key(path) for path in selected_eeg_files}
    layout = bids.get("layout")
    rows = (
        [row for row in layout if isinstance(row, Mapping)]
        if isinstance(layout, list)
        else []
    )
    run_reviews: list[dict[str, Any]] = []
    blockers: list[str] = []

    for layout_row in rows:
        eeg_file = _path_key(str(layout_row.get("file") or ""))
        if eeg_file not in selected:
            continue
        raw_channels_file = str(layout_row.get("channels_file") or "").strip()
        if not raw_channels_file:
            continue
        channels_file = Path(raw_channels_file).expanduser().resolve(strict=False)
        guard = (
            resource_reader.guard([channels_file], purpose="BIDS channels.tsv review")
            if resource_reader is not None
            else nullcontext()
        )
        try:
            with guard:
                channel_statuses = _read_channel_statuses(channels_file)
        except (OSError, UnicodeDecodeError, csv.Error, ValueError) as exc:
            reason = (
                f"BIDS channels.tsv review is blocked for {Path(eeg_file).name}: {exc}"
            )
            blockers.append(reason)
            run_reviews.append(
                {
                    "eeg_file": eeg_file,
                    "channels_file": _path_key(channels_file),
                    "status": "blocked",
                    "channel_count": 0,
                    "channel_statuses": {},
                    "bad_channels": [],
                    "status_identity": "",
                }
            )
            continue
        bad_channels = sorted(
            name for name, status in channel_statuses.items() if status == "bad"
        )
        run_reviews.append(
            {
                "eeg_file": eeg_file,
                "channels_file": _path_key(channels_file),
                "status": "ready",
                "channel_count": len(channel_statuses),
                "channel_statuses": channel_statuses,
                "bad_channels": bad_channels,
                "status_identity": _status_identity(channel_statuses),
            }
        )

    if blockers:
        status = "blocked"
    elif run_reviews:
        status = "ready"
    else:
        status = "not_applicable"
    return BidsChannelReview(
        status=status,
        runs=run_reviews,
        blocked_reasons=blockers,
    )


def apply_bids_channel_review(
    *,
    review: BidsChannelReview | Mapping[str, Any],
    loaded_data: Iterable[Any],
    data_filepath: Callable[[Any], str],
) -> list[dict[str, Any]]:
    """Apply reviewed bad channels to exactly one corresponding loaded run."""
    payload = (
        review.to_dict() if isinstance(review, BidsChannelReview) else dict(review)
    )
    status = str(payload.get("status") or "not_applicable")
    if status == "not_applicable":
        return []
    if status != "ready":
        raise ValueError("BIDS channels.tsv review is not ready to apply.")
    loaded = list(loaded_data)
    applied: list[dict[str, Any]] = []
    raw_runs = payload.get("runs")
    runs = raw_runs if isinstance(raw_runs, list) else []
    for raw_run in runs:
        if not isinstance(raw_run, Mapping):
            continue
        run = dict(raw_run)
        eeg_file = str(run.get("eeg_file") or "").strip()
        matches = [
            item
            for item in loaded
            if _path_key(data_filepath(item)) == _path_key(eeg_file)
        ]
        if not matches:
            matches = [
                item
                for item in loaded
                if Path(data_filepath(item)).name == Path(eeg_file).name
            ]
        if len(matches) != 1:
            raise ValueError(
                "BIDS channels.tsv did not resolve to exactly one loaded EEG run: "
                + Path(eeg_file).name
                + "."
            )
        target = matches[0]
        get_mne = getattr(target, "get_mne", None)
        if not callable(get_mne):
            raise ValueError("Loaded EEG run does not expose MNE channel metadata.")
        mne_data: Any = get_mne()
        loaded_names = [str(name) for name in getattr(mne_data, "ch_names", [])]
        raw_statuses = run.get("channel_statuses")
        statuses = (
            {str(name): str(value) for name, value in raw_statuses.items()}
            if isinstance(raw_statuses, Mapping)
            else {}
        )
        if len(statuses) != len(loaded_names) or set(statuses) != set(loaded_names):
            missing = sorted(set(loaded_names) - set(statuses))
            unknown = sorted(set(statuses) - set(loaded_names))
            raise ValueError(
                "BIDS channels.tsv names do not match the loaded EEG channels"
                f" (missing={missing}, unknown={unknown})."
            )
        bad_channels = [name for name in loaded_names if statuses[name] == "bad"]
        mne_data.info["bads"] = bad_channels
        record = {
            "eeg_file": _path_key(eeg_file),
            "channels_file": _path_key(str(run.get("channels_file") or "")),
            "status": "applied",
            "channel_count": len(statuses),
            "channel_statuses": statuses,
            "bad_channels": bad_channels,
            "status_identity": str(run.get("status_identity") or ""),
        }
        setter = getattr(target, "set_runtime_detail", None)
        if callable(setter):
            setter("bids_channels", record)
        applied.append(record)
    return applied


def _read_channel_statuses(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = {
            str(name).strip().casefold(): name for name in reader.fieldnames or []
        }
        name_field = fieldnames.get("name")
        status_field = fieldnames.get("status")
        if name_field is None:
            raise ValueError("required name column is missing.")
        statuses: dict[str, str] = {}
        for row_index, row in enumerate(reader, start=2):
            name = str(row.get(name_field) or "").strip()
            if not name:
                raise ValueError(f"channel name is empty at row {row_index}.")
            if name in statuses:
                raise ValueError(f"channel name is duplicated: {name}.")
            status = (
                str(row.get(status_field) or "").strip().casefold()
                if status_field is not None
                else "unspecified"
            )
            if status_field is not None and status not in {"good", "bad"}:
                raise ValueError(
                    f"channel {name} has unsupported status {status or '<empty>'}."
                )
            statuses[name] = status
    if not statuses:
        raise ValueError("no channel rows were found.")
    return statuses


def _status_identity(statuses: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(sorted(statuses.items())),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _path_key(path: str | Path) -> str:
    text = str(path).strip()
    return str(Path(text).expanduser().resolve(strict=False)) if text else ""
