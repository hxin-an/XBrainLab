"""One bounded, real-command BIDS import and recipe replay conformance case."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import re
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)

from .import_catalog import file_sha256, resolve_data_path

_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def run_import_case(
    case: dict[str, Any], data_root: Path, output_root: Path
) -> dict[str, Any]:
    """Run one catalogued BIDS import through apply and a fresh recipe replay.

    This intentionally does not discover a recording by filename.  The catalog
    binds one exact selected recording and hashes every resource it permits the
    case to read before and after both product routes.
    """
    case_id = str(case.get("id") or "<unknown>")
    result: dict[str, Any] = {
        "case_id": case_id,
        "status": "failed",
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "mne": mne.__version__,
        },
    }
    reference_raw = None
    try:
        _validate_case_id(case_id)
        root = _bids_root(data_root, case)
        selected = _selected_recording(data_root, case, root)
        expected = _expected(case)
        subjects = _selected_subjects(case)
        choices = _materialize_choices(case.get("choices"), data_root, selected)
        before = _input_snapshot(case, data_root, root, selected)
        reference = _reference_recording(expected, data_root, selected)
        _assert_reference_is_admitted(reference["path"], before, data_root)
        reference_raw = _read_raw(reference["path"])
        _assert_reference(reference_raw, expected, selected, data_root)
        output_dir = output_root.resolve() / case_id
        output_dir.mkdir(parents=True, exist_ok=False)
        recipe_path = output_dir / "import-recipe.json"

        initial = _apply_route(
            root, choices, recipe_path, expected, reference_raw, subjects
        )
        after_initial = _input_snapshot(case, data_root, root, selected)
        _require_unchanged(before, after_initial, "initial import")
        replay = _replay_route(recipe_path, expected, reference_raw)
        after = _input_snapshot(case, data_root, root, selected)
        _require_unchanged(before, after, "recipe replay")
        result.update(
            {
                "status": "passed",
                "input_files_before": before,
                "input_files_after": after,
                "reference": _reference_summary(reference_raw, reference),
                "commands": {
                    "initial": ["scan", "preview", "validate", "apply"],
                    "replay": ["reload", "validate", "apply"],
                },
                "observed": initial["observed"],
                "initial": initial["proof"],
                "replay": replay,
                "recipe": {
                    "path": str(recipe_path),
                    "sha256": file_sha256(recipe_path),
                    "bytes": recipe_path.stat().st_size,
                },
            }
        )
    except Exception as exc:
        result["failure"] = {
            "stage": _failure_stage(exc),
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    finally:
        if reference_raw is not None:
            reference_raw.close()
    return result


def _apply_route(
    root: Path,
    choices: dict[str, Any],
    recipe_path: Path,
    expected: dict[str, Any],
    reference_raw: Any,
    selected_bids_subjects: list[str] | None,
) -> dict[str, Any]:
    service = ApplicationService()
    try:
        _execute(
            service,
            ScanSourceCommand(
                str(root),
                source_hint="bids",
                selected_bids_subjects=selected_bids_subjects,
            ),
            "scan",
        )
        _execute(service, PreviewInterpretationCommand(choices=choices), "preview")
        _execute(service, ValidateInterpretationCommand(), "validate")
        applied = _execute(service, ApplyInterpretationCommand(confirmed=True), "apply")
        observed, proof = _assert_loaded(
            service, expected, reference_raw, applied.state.interpretation
        )
        _execute(
            service, SaveInterpretationRecipeCommand(str(recipe_path)), "save_recipe"
        )
        return {"observed": observed, "proof": proof}
    finally:
        service.close()


def _replay_route(
    recipe_path: Path, expected: dict[str, Any], reference_raw: Any
) -> dict[str, Any]:
    service = ApplicationService()
    try:
        _execute(service, ReloadInterpretationRecipeCommand(str(recipe_path)), "reload")
        _execute(service, ValidateInterpretationCommand(), "validate_replay")
        applied = _execute(
            service, ApplyInterpretationCommand(confirmed=True), "apply_replay"
        )
        _observed, proof = _assert_loaded(
            service, expected, reference_raw, applied.state.interpretation
        )
        return proof
    finally:
        service.close()


def _assert_loaded(
    service: Any, expected: dict[str, Any], reference_raw: Any, interpretation: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(service.study.loaded_data_list) != 1:
        raise RuntimeError("application did not load exactly one selected recording")
    loaded = service.study.loaded_data_list[0].get_mne()
    if loaded.ch_names != expected["channel_names"]:
        raise RuntimeError("loaded channel names differ from catalog expectation")
    if loaded.get_channel_types() != expected["channel_types"]:
        raise RuntimeError("loaded channel types differ from reviewed channels.tsv")
    if float(loaded.info["sfreq"]) != expected["sfreq"]:
        raise RuntimeError("loaded sampling frequency differs from catalog expectation")
    if int(loaded.n_times) != expected["n_times"]:
        raise RuntimeError("loaded sample count differs from catalog expectation")
    if expected["events"]:
        events, event_id = service.study.loaded_data_list[0].get_event_list()
        inverse = {int(code): name for name, code in event_id.items()}
        actual_events = [[int(row[0]), inverse[int(row[2])]] for row in events]
    else:
        # Raw event detection includes acquisition context when no labels were
        # applied. Only the published interpretation declares supervised classes.
        if interpretation.class_map or interpretation.epoch_handoff["supervised_ready"]:
            raise RuntimeError(
                "unlabelled import unexpectedly admits supervised classes"
            )
        if (
            "missing_class_labels"
            not in interpretation.epoch_handoff["supervised_blocker_codes"]
        ):
            raise RuntimeError("unlabelled import lost its supervised blocker")
        actual_events, event_id = [], {}
    if actual_events != expected["events"]:
        raise RuntimeError(
            "loaded class events differ from independent catalog expectation"
        )
    error = _waveform_error(reference_raw, loaded)
    if error != 0.0:
        raise RuntimeError(
            f"loaded waveform differs from selected BIDS recording ({error})"
        )
    source_context = _annotation_counter(reference_raw, excluded=set(event_id))
    loaded_annotations = _annotation_counter(loaded, excluded=set())
    if not source_context <= loaded_annotations:
        raise RuntimeError("loaded annotations dropped source acquisition context")
    return (
        {
            "channel_names": list(loaded.ch_names),
            "channel_types": list(loaded.get_channel_types()),
            "sfreq": float(loaded.info["sfreq"]),
            "n_times": int(loaded.n_times),
            "events": actual_events,
        },
        {"waveform_max_abs_error": error},
    )


def _annotation_counter(
    raw: Any, *, excluded: set[str]
) -> Counter[tuple[str, int, int]]:
    return Counter(
        (
            str(description),
            round(float(onset) * 1_000_000_000),
            round(float(duration) * 1_000_000_000),
        )
        for onset, duration, description in zip(
            raw.annotations.onset,
            raw.annotations.duration,
            raw.annotations.description,
            strict=True,
        )
        if str(description) not in excluded
    )


def _execute(service: Any, command: Any, stage: str) -> Any:
    result = service.execute(command)
    if not result.ok:
        raise _StageFailureError(stage, result.message)
    return result


class _StageFailureError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(message)


def _failure_stage(exc: Exception) -> str:
    if isinstance(exc, _StageFailureError):
        return exc.stage
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return "admission"
    return "verification"


def _bids_root(data_root: Path, case: dict[str, Any]) -> Path:
    root = resolve_data_path(data_root, _required_text(case, "bids_root"))
    if not root.is_dir():
        raise ValueError("bids_root is not a directory")
    return root


def _selected_recording(data_root: Path, case: dict[str, Any], root: Path) -> Path:
    selected = resolve_data_path(data_root, _required_text(case, "selected_recording"))
    if not selected.is_file() or not _is_within(selected, root):
        raise ValueError("selected_recording must be a file inside bids_root")
    return selected


def _require_unchanged(
    before: list[dict[str, str]], after: list[dict[str, str]], phase: str
) -> None:
    if after != before:
        raise RuntimeError(f"input identity changed during {phase}")


def _expected(case: dict[str, Any]) -> dict[str, Any]:
    value = case.get("expected")
    if not isinstance(value, dict):
        raise ValueError("expected must be an object")
    names = value.get("channel_names")
    types = value.get("channel_types")
    events = value.get("events")
    if (
        not isinstance(names, list)
        or not names
        or not all(isinstance(name, str) for name in names)
    ):
        raise ValueError("expected.channel_names must be a non-empty string list")
    if (
        not isinstance(types, list)
        or len(types) != len(names)
        or not all(isinstance(item, str) for item in types)
    ):
        raise ValueError("expected.channel_types must align with channel_names")
    if type(value.get("sfreq")) not in (int, float) or float(value["sfreq"]) <= 0:
        raise ValueError("expected.sfreq must be positive")
    if type(value.get("n_times")) is not int or value["n_times"] <= 0:
        raise ValueError("expected.n_times must be positive")
    if not isinstance(events, list) or any(
        not isinstance(row, list)
        or len(row) != 2
        or type(row[0]) is not int
        or not isinstance(row[1], str)
        for row in events
    ):
        raise ValueError("expected.events must be [sample, class_name] rows")
    return {
        "channel_names": list(names),
        "channel_types": [item.lower() for item in types],
        "sfreq": float(value["sfreq"]),
        "n_times": int(value["n_times"]),
        "events": [list(row) for row in events],
        "waveform_reference": value.get("waveform_reference"),
        "channels_tsv": value.get("channels_tsv"),
    }


def _selected_subjects(case: dict[str, Any]) -> list[str] | None:
    value = case.get("selected_bids_subjects")
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(subject, str) and subject for subject in value)
    ):
        raise ValueError("selected_bids_subjects must be a non-empty string list")
    return list(value)


def _reference_recording(
    expected: dict[str, Any], data_root: Path, selected: Path
) -> dict[str, Any]:
    configured = expected.get("waveform_reference")
    if configured is None:
        return {"path": selected, "sha256": file_sha256(selected)}
    if not isinstance(configured, dict):
        raise ValueError("expected.waveform_reference must be an object")
    path = resolve_data_path(data_root, _required_text(configured, "path"))
    digest = _required_text(configured, "sha256").lower()
    if file_sha256(path) != digest:
        raise ValueError("waveform_reference hash mismatch")
    return {"path": path, "sha256": digest}


def _assert_reference_is_admitted(
    reference: Path, snapshot: list[dict[str, str]], data_root: Path
) -> None:
    relative = str(reference.relative_to(data_root)).replace("\\", "/")
    if relative not in {item["path"] for item in snapshot}:
        raise ValueError("waveform_reference must be included in input_files")


def _assert_reference(
    raw: Any, expected: dict[str, Any], selected: Path, data_root: Path
) -> None:
    if raw.ch_names != expected["channel_names"]:
        raise RuntimeError(
            "selected recording channel names differ from catalog expectation"
        )
    if (
        float(raw.info["sfreq"]) != expected["sfreq"]
        or int(raw.n_times) != expected["n_times"]
    ):
        raise RuntimeError("selected recording shape differs from catalog expectation")
    channels = (
        resolve_data_path(data_root, expected["channels_tsv"])
        if expected.get("channels_tsv")
        else _channels_tsv_path(selected)
    )
    channel_types = _channels_tsv_types(channels)
    if [channel_types.get(name) for name in expected["channel_names"]] != expected[
        "channel_types"
    ]:
        raise RuntimeError("literal channels.tsv types differ from catalog expectation")


def _reference_summary(raw: Any, reference: dict[str, Any]) -> dict[str, Any]:
    annotations = [
        [str(description), float(onset), float(duration)]
        for onset, duration, description in zip(
            raw.annotations.onset,
            raw.annotations.duration,
            raw.annotations.description,
            strict=True,
        )
    ]
    return {
        "path": str(reference["path"]),
        "sha256": reference["sha256"],
        "annotation_count": len(annotations),
        "annotations_sha256": hashlib.sha256(
            json.dumps(annotations, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _waveform_error(reference: Any, loaded: Any) -> float:
    if reference.ch_names != loaded.ch_names or reference.n_times != loaded.n_times:
        raise RuntimeError("waveform reference identity differs")
    worst = 0.0
    for start in range(0, reference.n_times, 8192):
        stop = min(reference.n_times, start + 8192)
        source = reference.get_data(start=start, stop=stop)
        actual = loaded.get_data(start=start, stop=stop)
        if not np.array_equal(np.isfinite(source), np.isfinite(actual)):
            raise RuntimeError("waveform finite-value pattern differs")
        if not np.array_equal(source, actual, equal_nan=True):
            raise RuntimeError("waveform values differ")
        difference = source - actual
        worst = max(worst, float(abs(difference).max()))
    return worst


def _read_raw(path: Path) -> Any:
    return mne.io.read_raw(path, preload=False, verbose="ERROR")


def _channels_tsv_types(channels: Path) -> dict[str, str]:
    if not channels.is_file():
        raise ValueError("selected BIDS recording has no channels.tsv")
    with channels.open(encoding="utf-8-sig", newline="") as stream:
        return {
            str(row["name"]): str(row["type"]).lower()
            for row in csv.DictReader(stream, delimiter="\t")
        }


def _input_snapshot(
    case: dict[str, Any], data_root: Path, root: Path, selected: Path
) -> list[dict[str, str]]:
    items = case.get("input_files")
    if not isinstance(items, list) or not items:
        raise ValueError("input_files must be a non-empty list")
    admitted: dict[Path, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("input_files items must be objects")
        path = resolve_data_path(data_root, _required_text(item, "path"))
        expected_hash = _required_text(item, "sha256").lower()
        if not path.is_file():
            raise ValueError("input_files paths must name regular files")
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(f"input hash mismatch: {path.name}")
        admitted[path] = actual_hash
    required = _required_bids_resources(root, selected)
    channels = case.get("expected", {}).get("channels_tsv")
    if channels:
        required.add(resolve_data_path(data_root, channels))
    missing = sorted(
        str(path.relative_to(data_root)) for path in required.difference(admitted)
    )
    if missing:
        raise ValueError(f"unbound selected BIDS dependency: {', '.join(missing)}")
    return [
        {"path": str(path.relative_to(data_root)).replace("\\", "/"), "sha256": digest}
        for path, digest in sorted(admitted.items())
    ]


def _required_bids_resources(root: Path, selected: Path) -> set[Path]:
    required = {
        root / "dataset_description.json",
        selected,
    }
    if _channels_tsv_path(selected).exists():
        required.add(_channels_tsv_path(selected))
    stem = selected.name.removesuffix("_eeg" + selected.suffix)
    for suffix in ("_events.tsv", "_events.json", "_eeg.json"):
        candidate = selected.with_name(stem + suffix)
        if candidate.exists():
            required.add(_contained_file(candidate, root))
    if selected.suffix.lower() == ".vhdr":
        fields = {
            line.partition("=")[0]: line.partition("=")[2].strip()
            for line in selected.read_text(
                encoding="utf-8", errors="strict"
            ).splitlines()
            if "=" in line
        }
        for name in (fields.get("DataFile"), fields.get("MarkerFile")):
            if name:
                required.add(_contained_file(selected.parent / name, root))
    if selected.suffix.lower() == ".set":
        fdt = selected.with_suffix(".fdt")
        if fdt.exists():
            required.add(_contained_file(fdt, root))
    for directory in _ancestors(selected.parent, root):
        for candidate in (*directory.glob("*.json"), *directory.glob("*.tsv")):
            if candidate.name.endswith(
                ("_events.json", "_eeg.json", "_events.tsv", "_channels.tsv")
            ) and _sidecar_matches(candidate, selected):
                required.add(_contained_file(candidate, root))
        for candidate in (
            *directory.glob("*_electrodes.tsv"),
            *directory.glob("*_coordsystem.json"),
        ):
            if _sidecar_matches(candidate, selected):
                required.add(_contained_file(candidate, root))
    return {_contained_file(path, root) for path in required}


def _channels_tsv_path(recording: Path) -> Path:
    return recording.with_name(
        recording.name.removesuffix("_eeg" + recording.suffix) + "_channels.tsv"
    )


def _sidecar_matches(sidecar: Path, recording: Path) -> bool:
    return all(
        _entities(recording).get(key) == value
        for key, value in _entities(sidecar).items()
    )


def _entities(path: Path) -> dict[str, str]:
    name = path.name
    for suffix in (
        "_events.json",
        "_eeg.json",
        "_events.tsv",
        "_channels.tsv",
        "_eeg.vhdr",
        "_eeg.edf",
        "_eeg.set",
        "_eeg.fif",
    ):
        if name.endswith(suffix):
            name = name.removesuffix(suffix)
            break
    return {
        key: value
        for part in name.split("_")
        if "-" in part
        for key, value in [part.split("-", 1)]
    }


def _ancestors(directory: Path, root: Path) -> list[Path]:
    result: list[Path] = []
    while True:
        result.append(directory)
        if directory == root:
            return result
        directory = directory.parent


def _materialize_choices(value: Any, data_root: Path, selected: Path) -> dict[str, Any]:
    if value is None:
        result: dict[str, Any] = {}
    elif isinstance(value, dict):
        result = deepcopy(value)
    else:
        raise ValueError("choices must be an object")
    selected_paths = result.get("selected_eeg_files")
    if selected_paths is None:
        result["selected_eeg_files"] = [str(selected)]
    else:
        if not isinstance(selected_paths, list):
            raise ValueError("choices.selected_eeg_files must be a list")
        materialized = [
            resolve_data_path(data_root, str(path)) for path in selected_paths
        ]
        if materialized != [selected]:
            raise ValueError(
                "choices.selected_eeg_files must bind the selected_recording exactly"
            )
        result["selected_eeg_files"] = [str(selected)]
    carriers = result.get("label_carrier_choices")
    if carriers is not None:
        if not isinstance(carriers, dict):
            raise ValueError("choices.label_carrier_choices must be an object")
        result["label_carrier_choices"] = {
            str(resolve_data_path(data_root, str(path))): _materialize_carrier_choice(
                choice, data_root
            )
            for path, choice in carriers.items()
        }
    excluded = result.get("excluded_label_carriers")
    if excluded is not None:
        if not isinstance(excluded, list):
            raise ValueError("choices.excluded_label_carriers must be a list")
        result["excluded_label_carriers"] = [
            str(resolve_data_path(data_root, str(path))) for path in excluded
        ]
    sources = result.get("label_sources")
    if sources is not None:
        if not isinstance(sources, list):
            raise ValueError("choices.label_sources must be a list")
        result["label_sources"] = [
            str(resolve_data_path(data_root, str(path))) for path in sources
        ]
    required = result.get("required_label_carriers")
    if required is not None:
        if not isinstance(required, list):
            raise ValueError("choices.required_label_carriers must be a list")
        result["required_label_carriers"] = [
            str(resolve_data_path(data_root, str(path))) for path in required
        ]
    return result


def _materialize_carrier_choice(value: Any, data_root: Path) -> Any:
    if not isinstance(value, dict):
        raise ValueError("label carrier choice must be an object")
    result = deepcopy(value)
    for key in ("target_file", "target_files"):
        target = result.get(key)
        if key == "target_file" and isinstance(target, str):
            result[key] = str(resolve_data_path(data_root, target))
        elif key == "target_files" and isinstance(target, list):
            result[key] = [
                str(resolve_data_path(data_root, str(path))) for path in target
            ]
        elif target is not None:
            raise ValueError(f"label carrier choice.{key} has invalid type")
    return result


def _contained_file(path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise ValueError("catalog symlink paths are not allowed")
    resolved = path.resolve(strict=True)
    if not _is_within(resolved, root.resolve(strict=True)):
        raise ValueError("catalog path escapes its declared root")
    if not resolved.is_file() and not resolved.is_dir():
        raise ValueError("catalog path is not a regular file or directory")
    relative = resolved.relative_to(root.resolve(strict=True))
    current = root.resolve(strict=True)
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("catalog symlink paths are not allowed")
    return resolved


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _required_text(value: dict[str, Any], key: str) -> str:
    text = value.get(key)
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{key} is required")
    return text


def _validate_case_id(case_id: str) -> None:
    if not _CASE_ID.fullmatch(case_id):
        raise ValueError("case id is unsafe")
