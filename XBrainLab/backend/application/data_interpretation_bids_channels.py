"""Strict local BIDS channels.tsv review and channel-semantics application."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mne.io.constants import FIFF

from .data_interpretation_parsed_cache import (
    ParsedContentTooLargeError,
    parsed_delimited_table,
)
from .data_interpretation_resource_reader import AdmittedResourceReader


def _fiff_unit(name: str) -> int:
    return int(getattr(FIFF, name))


_BIDS_TO_MNE_CHANNEL_TYPE: dict[str, str] = {
    "EEG": "eeg",
    "MISC": "misc",
    "TRIG": "stim",
    "EMG": "emg",
    "ECOG": "ecog",
    "SEEG": "seeg",
    "EOG": "eog",
    "VEOG": "eog",
    "HEOG": "eog",
    "ECG": "ecg",
    "RESP": "resp",
    "GSR": "gsr",
    "TEMP": "temperature",
    "DBS": "dbs",
    "NIRSCWAMPLITUDE": "fnirs_cw_amplitude",
    "NIRS": "fnirs_cw_amplitude",
    "EYEGAZE": "eyegaze",
    "PUPIL": "pupil",
}
_BIDS_TO_FIFF_UNIT: dict[str, int] = {
    "V": _fiff_unit("FIFF_UNIT_V"),
    "µV": _fiff_unit("FIFF_UNIT_V"),
    "μV": _fiff_unit("FIFF_UNIT_V"),
    "uV": _fiff_unit("FIFF_UNIT_V"),
    "microV": _fiff_unit("FIFF_UNIT_V"),
    "mV": _fiff_unit("FIFF_UNIT_V"),
    "T": _fiff_unit("FIFF_UNIT_T"),
    "T/m": _fiff_unit("FIFF_UNIT_T_M"),
    "rad": _fiff_unit("FIFF_UNIT_RAD"),
    "S": _fiff_unit("FIFF_UNIT_S"),
    "oC": _fiff_unit("FIFF_UNIT_CEL"),
    "M": _fiff_unit("FIFF_UNIT_MOL"),
    "px": _fiff_unit("FIFF_UNIT_PX"),
}


@dataclass(frozen=True)
class BidsChannelReview:
    """Per-run channel truth from exact local channels.tsv sidecars."""

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


@dataclass(slots=True)
class _ChannelApplyPlan:
    target: Any
    run: dict[str, Any]
    eeg_file: str
    mne_data: Any
    loaded_names: list[str]
    statuses: dict[str, str]
    mne_channel_types: dict[str, str]
    mne_channel_units: dict[str, int]
    bad_channels: list[str]
    original_channel_types: dict[str, str]
    original_channel_units: dict[str, int]
    original_bad_channels: list[str]


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
    review_warnings: list[str] = []

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
                channel_semantics, available_columns = _read_channel_semantics(
                    channels_file
                )
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
                    "channel_types": {},
                    "channel_units": {},
                    "mne_channel_types": {},
                    "mne_channel_units": {},
                    "bad_channels": [],
                    "missing_type_channels": [],
                    "missing_unit_channels": [],
                    "unmapped_type_channels": [],
                    "unmapped_unit_channels": [],
                    "missing_required_columns": [],
                    "status_identity": "",
                    "semantics_identity": "",
                }
            )
            continue
        missing_required_columns = sorted({"type", "units"} - available_columns)
        if missing_required_columns:
            review_warnings.append(
                "BIDS channels.tsv is missing required column(s) for "
                f"{Path(eeg_file).name}: {', '.join(missing_required_columns)}. "
                "Raw import may continue, but channel semantics are incomplete."
            )
        channel_statuses = {
            name: values["status"] for name, values in channel_semantics.items()
        }
        channel_types = {
            name: values["type"] or "unspecified"
            for name, values in channel_semantics.items()
        }
        channel_units = {
            name: values["units"] or "unspecified"
            for name, values in channel_semantics.items()
        }
        mne_channel_types = {
            name: mne_type
            for name, values in channel_semantics.items()
            if values["type"]
            and (mne_type := _BIDS_TO_MNE_CHANNEL_TYPE.get(values["type"].upper()))
            is not None
        }
        mne_channel_units = {
            name: fiff_unit
            for name, values in channel_semantics.items()
            if values["units"]
            and (fiff_unit := _BIDS_TO_FIFF_UNIT.get(values["units"])) is not None
        }
        missing_type_channels = sorted(
            name for name, values in channel_semantics.items() if not values["type"]
        )
        missing_unit_channels = sorted(
            name for name, values in channel_semantics.items() if not values["units"]
        )
        unmapped_type_channels = sorted(
            name
            for name, values in channel_semantics.items()
            if values["type"] and name not in mne_channel_types
        )
        unmapped_unit_channels = sorted(
            name
            for name, values in channel_semantics.items()
            if values["units"] and name not in mne_channel_units
        )
        if unmapped_type_channels:
            review_warnings.append(
                "BIDS channels.tsv type is not safely representable in MNE for "
                f"{Path(eeg_file).name}: {', '.join(unmapped_type_channels)}. "
                "The loader-provided types will be retained."
            )
        unavailable_unit_channels = [
            name
            for name in unmapped_unit_channels
            if channel_units[name].casefold() == "n/a"
        ]
        unsupported_unit_channels = sorted(
            set(unmapped_unit_channels) - set(unavailable_unit_channels)
        )
        if unavailable_unit_channels:
            review_warnings.append(
                "BIDS channels.tsv declares n/a units for "
                f"{Path(eeg_file).name}: {', '.join(unavailable_unit_channels)}. "
                "MNE units will remain type- or loader-defined."
            )
        if unsupported_unit_channels:
            review_warnings.append(
                "BIDS channels.tsv unit is not safely representable in MNE for "
                f"{Path(eeg_file).name}: {', '.join(unsupported_unit_channels)}. "
                "The loader-provided units will be retained."
            )
        bad_channels = sorted(
            name for name, status in channel_statuses.items() if status == "bad"
        )
        run_has_warnings = bool(
            missing_required_columns or unmapped_type_channels or unmapped_unit_channels
        )
        run_reviews.append(
            {
                "eeg_file": eeg_file,
                "channels_file": _path_key(channels_file),
                "status": "ready_with_warnings" if run_has_warnings else "ready",
                "channel_count": len(channel_statuses),
                "channel_statuses": channel_statuses,
                "channel_types": channel_types,
                "channel_units": channel_units,
                "mne_channel_types": mne_channel_types,
                "mne_channel_units": mne_channel_units,
                "bad_channels": bad_channels,
                "missing_type_channels": missing_type_channels,
                "missing_unit_channels": missing_unit_channels,
                "unmapped_type_channels": unmapped_type_channels,
                "unmapped_unit_channels": unmapped_unit_channels,
                "missing_required_columns": missing_required_columns,
                "status_identity": _status_identity(channel_statuses),
                "semantics_identity": _semantics_identity(channel_semantics),
            }
        )

    if blockers:
        status = "blocked"
    elif run_reviews:
        status = "ready_with_warnings" if review_warnings else "ready"
    else:
        status = "not_applicable"
    return BidsChannelReview(
        status=status,
        runs=run_reviews,
        blocked_reasons=blockers,
        warnings=sorted(set(review_warnings)),
    )


def apply_bids_channel_review(
    *,
    review: BidsChannelReview | Mapping[str, Any],
    loaded_data: Iterable[Any],
    data_filepath: Callable[[Any], str],
) -> list[dict[str, Any]]:
    """Apply reviewed types, units, and status to one corresponding loaded run."""
    payload = (
        review.to_dict() if isinstance(review, BidsChannelReview) else dict(review)
    )
    status = str(payload.get("status") or "not_applicable")
    if status == "not_applicable":
        return []
    if status not in {"ready", "ready_with_warnings"}:
        raise ValueError("BIDS channels.tsv review is not ready to apply.")
    loaded = list(loaded_data)
    raw_runs = payload.get("runs")
    runs = raw_runs if isinstance(raw_runs, list) else []
    plans = [
        _prepare_channel_apply_plan(
            raw_run=raw_run,
            loaded=loaded,
            data_filepath=data_filepath,
        )
        for raw_run in runs
        if isinstance(raw_run, Mapping)
    ]
    applied: list[dict[str, Any]] = []
    try:
        applied = [_apply_channel_plan(plan) for plan in plans]
    except Exception:
        for plan in plans:
            _restore_channel_plan(plan)
        raise
    for plan, record in zip(plans, applied, strict=True):
        setter = getattr(plan.target, "set_runtime_detail", None)
        if callable(setter):
            setter("bids_channels", record)
    return applied


def _prepare_channel_apply_plan(
    *,
    raw_run: Mapping[str, Any],
    loaded: list[Any],
    data_filepath: Callable[[Any], str],
) -> _ChannelApplyPlan:
    run = dict(raw_run)
    eeg_file = str(run.get("eeg_file") or "").strip()
    matches = [
        item for item in loaded if _path_key(data_filepath(item)) == _path_key(eeg_file)
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
    mne_channel_types = _reviewed_mne_channel_types(run)
    mne_channel_units = _reviewed_mne_channel_units(run)
    unknown_semantic_names = sorted(
        (set(mne_channel_types) | set(mne_channel_units)) - set(loaded_names)
    )
    if unknown_semantic_names:
        raise ValueError(
            "BIDS channels.tsv semantic mappings contain unknown channels: "
            + ", ".join(unknown_semantic_names)
            + "."
        )
    info = getattr(mne_data, "info", None)
    if not isinstance(info, Mapping):
        raise ValueError("Loaded EEG run does not expose MNE channel info.")
    channels_info = info.get("chs")
    if not isinstance(channels_info, list) or len(channels_info) != len(loaded_names):
        raise ValueError("Loaded EEG run has invalid MNE channel info.")
    original_bad_channels = list(info.get("bads") or [])
    bad_channel_set = set(original_bad_channels)
    for name, channel_status in statuses.items():
        if channel_status == "bad":
            bad_channel_set.add(name)
        elif channel_status == "good":
            bad_channel_set.discard(name)
    bad_channels = [name for name in loaded_names if name in bad_channel_set]
    return _ChannelApplyPlan(
        target=target,
        run=run,
        eeg_file=eeg_file,
        mne_data=mne_data,
        loaded_names=loaded_names,
        statuses=statuses,
        mne_channel_types=mne_channel_types,
        mne_channel_units=mne_channel_units,
        bad_channels=bad_channels,
        original_channel_types=dict(
            zip(loaded_names, mne_data.get_channel_types(), strict=True)
        ),
        original_channel_units={
            name: int(channels_info[index]["unit"])
            for index, name in enumerate(loaded_names)
        },
        original_bad_channels=original_bad_channels,
    )


def _apply_channel_plan(plan: _ChannelApplyPlan) -> dict[str, Any]:
    mne_data = plan.mne_data
    if plan.mne_channel_types:
        type_setter = getattr(mne_data, "set_channel_types", None)
        if not callable(type_setter):
            raise ValueError("Loaded EEG run cannot apply reviewed BIDS channel types.")
        type_setter(plan.mne_channel_types, on_unit_change="ignore")
    channels_info = mne_data.info["chs"]
    for name, unit in plan.mne_channel_units.items():
        channels_info[plan.loaded_names.index(name)]["unit"] = unit
    mne_data.info["bads"] = list(plan.bad_channels)
    applied_channel_types = dict(
        zip(plan.loaded_names, mne_data.get_channel_types(), strict=True)
    )
    applied_channel_units = {
        name: int(channels_info[index]["unit"])
        for index, name in enumerate(plan.loaded_names)
    }
    type_mismatches = {
        name: {
            "expected": expected,
            "actual": applied_channel_types.get(name, ""),
        }
        for name, expected in plan.mne_channel_types.items()
        if applied_channel_types.get(name) != expected
    }
    unit_mismatches = {
        name: {
            "expected": expected,
            "actual": applied_channel_units.get(name),
        }
        for name, expected in plan.mne_channel_units.items()
        if applied_channel_units.get(name) != expected
    }
    if type_mismatches or unit_mismatches or mne_data.info["bads"] != plan.bad_channels:
        raise ValueError(
            "MNE did not retain every reviewed BIDS channel semantic "
            f"(type_mismatches={type_mismatches}, "
            f"unit_mismatches={unit_mismatches})."
        )
    run = plan.run
    return {
        "eeg_file": _path_key(plan.eeg_file),
        "channels_file": _path_key(str(run.get("channels_file") or "")),
        "status": "applied",
        "channel_count": len(plan.statuses),
        "channel_statuses": dict(plan.statuses),
        "channel_types": _text_mapping(run.get("channel_types")),
        "channel_units": _text_mapping(run.get("channel_units")),
        "bad_channels": list(plan.bad_channels),
        "applied_channel_types": applied_channel_types,
        "applied_channel_units": applied_channel_units,
        "missing_type_channels": _string_list(run.get("missing_type_channels")),
        "missing_unit_channels": _string_list(run.get("missing_unit_channels")),
        "unmapped_type_channels": _string_list(run.get("unmapped_type_channels")),
        "unmapped_unit_channels": _string_list(run.get("unmapped_unit_channels")),
        "missing_required_columns": _string_list(run.get("missing_required_columns")),
        "status_identity": str(run.get("status_identity") or ""),
        "semantics_identity": str(run.get("semantics_identity") or ""),
    }


def _restore_channel_plan(plan: _ChannelApplyPlan) -> None:
    with suppress(Exception):
        plan.mne_data.set_channel_types(
            plan.original_channel_types,
            on_unit_change="ignore",
        )
        channels_info = plan.mne_data.info["chs"]
        for name, unit in plan.original_channel_units.items():
            channels_info[plan.loaded_names.index(name)]["unit"] = unit
        plan.mne_data.info["bads"] = list(plan.original_bad_channels)


def _read_channel_semantics(
    path: Path,
) -> tuple[dict[str, dict[str, str]], set[str]]:
    try:
        table = parsed_delimited_table(path, delimiter="\t")
    except ParsedContentTooLargeError:
        return _read_channel_semantics_streaming(path)
    return _channel_semantics_from_rows(table.fieldnames, table.dict_rows())


def _read_channel_semantics_streaming(
    path: Path,
) -> tuple[dict[str, dict[str, str]], set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return _channel_semantics_from_rows(
            tuple(str(name) for name in reader.fieldnames or [] if name),
            reader,
        )


def _channel_semantics_from_rows(
    source_fieldnames: Iterable[str],
    rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, str]], set[str]]:
    fieldnames = {str(name).strip().casefold(): str(name) for name in source_fieldnames}
    name_field = fieldnames.get("name")
    type_field = fieldnames.get("type")
    units_field = fieldnames.get("units")
    status_field = fieldnames.get("status")
    if name_field is None:
        raise ValueError("required name column is missing.")
    semantics: dict[str, dict[str, str]] = {}
    for row_index, row in enumerate(rows, start=2):
        name = str(row.get(name_field) or "").strip()
        if not name:
            raise ValueError(f"channel name is empty at row {row_index}.")
        if name in semantics:
            raise ValueError(f"channel name is duplicated: {name}.")
        channel_type = (
            str(row.get(type_field) or "").strip() if type_field is not None else ""
        )
        if type_field is not None and not channel_type:
            raise ValueError(f"channel {name} has an empty type.")
        channel_units = (
            str(row.get(units_field) or "").strip() if units_field is not None else ""
        )
        if units_field is not None and not channel_units:
            raise ValueError(f"channel {name} has empty units.")
        status = (
            str(row.get(status_field) or "").strip().casefold()
            if status_field is not None
            else "unspecified"
        )
        if status == "n/a":
            status = "unspecified"
        if status_field is not None and status not in {
            "good",
            "bad",
            "unspecified",
        }:
            raise ValueError(
                f"channel {name} has unsupported status {status or '<empty>'}."
            )
        semantics[name] = {
            "status": status,
            "type": channel_type,
            "units": channel_units,
        }
    if not semantics:
        raise ValueError("no channel rows were found.")
    return semantics, set(fieldnames)


def _reviewed_mne_channel_types(run: Mapping[str, Any]) -> dict[str, str]:
    reviewed = _text_mapping(run.get("mne_channel_types"))
    if reviewed:
        return reviewed
    return {
        name: mapped
        for name, bids_type in _text_mapping(run.get("channel_types")).items()
        if bids_type != "unspecified"
        and (mapped := _BIDS_TO_MNE_CHANNEL_TYPE.get(bids_type.upper())) is not None
    }


def _reviewed_mne_channel_units(run: Mapping[str, Any]) -> dict[str, int]:
    raw_reviewed = run.get("mne_channel_units")
    if isinstance(raw_reviewed, Mapping):
        return {str(name): int(value) for name, value in raw_reviewed.items()}
    return {
        name: mapped
        for name, bids_unit in _text_mapping(run.get("channel_units")).items()
        if bids_unit != "unspecified"
        and (mapped := _BIDS_TO_FIFF_UNIT.get(bids_unit)) is not None
    }


def _text_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(name): str(item) for name, item in value.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _status_identity(statuses: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(sorted(statuses.items())),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantics_identity(semantics: Mapping[str, Mapping[str, str]]) -> str:
    encoded = json.dumps(
        {
            str(name): {
                str(key): str(value) for key, value in sorted(channel_semantics.items())
            }
            for name, channel_semantics in sorted(semantics.items())
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _path_key(path: str | Path) -> str:
    text = str(path).strip()
    return str(Path(text).expanduser().resolve(strict=False)) if text else ""
