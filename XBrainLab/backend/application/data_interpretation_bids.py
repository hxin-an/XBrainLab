"""Per-run BIDS event compatibility and XBrainLab placement policy."""

from __future__ import annotations

import contextlib
import csv
import math
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypedDict

from XBrainLab.backend.load_data.raw_data_loader import load_raw_data

from .data_interpretation_event_values import (
    RESOLVED,
    class_map_from_value_decisions,
)
from .data_interpretation_resource_reader import AdmittedResourceReader


@dataclass(frozen=True)
class StrictBidsEventReview:
    """Reviewed plans and evidence for the selected BIDS run scope."""

    label_carrier_plan: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    blocked_reasons: list[str] = field(default_factory=list)
    confirmation_items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class _ParsedBidsEventRow(TypedDict):
    row: int
    raw_onset: str
    raw_duration: str
    onset: Decimal | None
    onset_kind: str
    duration: Decimal | None
    duration_kind: str
    selected_label: str
    event_code: str
    schema_issue_codes: list[str]


def review_strict_bids_event_runs(
    *,
    bids: dict[str, Any],
    selected_eeg_files: list[str],
    label_carrier_plan: list[dict[str, Any]],
    resource_reader: AdmittedResourceReader | None = None,
) -> StrictBidsEventReview:
    """Bind and validate each selected BIDS EEG run against its events file."""
    plans = [dict(plan) for plan in label_carrier_plan]
    layout = [dict(row) for row in bids.get("layout", []) if isinstance(row, dict)]
    if not bids.get("is_bids") or not selected_eeg_files or not layout:
        return StrictBidsEventReview(label_carrier_plan=plans)

    selected = {_path_key(path): str(path) for path in selected_eeg_files}
    layout_by_file = {
        _path_key(str(row.get("file") or "")): row
        for row in layout
        if str(row.get("file") or "").strip()
    }
    plan_indexes = {
        _path_key(str(plan.get("path") or "")): index
        for index, plan in enumerate(plans)
        if str(plan.get("path") or "").strip()
    }
    file_mapping: dict[str, str] = {}
    pairing_issues: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    for selected_key, selected_path in selected.items():
        layout_row = layout_by_file.get(selected_key)
        if layout_row is None:
            pairing_issues.append(
                {
                    "code": "selected_run_missing_from_bids_layout",
                    "affected_eeg_file": selected_path,
                    "message": (
                        "Selected EEG file is missing from the scanned BIDS run layout."
                    ),
                }
            )
            continue
        eeg_path = str(layout_row.get("file") or selected_path)
        events_path = str(layout_row.get("events_file") or "").strip()
        if not events_path:
            pairing_issues.append(
                {
                    "code": "selected_run_missing_events_file",
                    "affected_eeg_file": eeg_path,
                    "message": "Selected BIDS EEG run has no paired events.tsv.",
                }
            )
            continue
        file_mapping[eeg_path] = events_path
        plan_index = plan_indexes.get(_path_key(events_path))
        if plan_index is None:
            pairing_issues.append(
                {
                    "code": "selected_run_events_not_reviewed",
                    "affected_eeg_file": eeg_path,
                    "events_file": events_path,
                    "message": (
                        "The paired BIDS events.tsv is not in the reviewed plan."
                    ),
                }
            )
            continue

        plan = plans[plan_index]
        selected_target = str(plan.get("selected_target_file") or "").strip()
        resolved_target = _resolve_selected_target(selected_target, selected_eeg_files)
        if selected_target and _path_key(resolved_target) != _path_key(eeg_path):
            pairing_issues.append(
                {
                    "code": "events_file_targets_wrong_run",
                    "affected_eeg_file": eeg_path,
                    "events_file": events_path,
                    "selected_target_file": selected_target,
                    "expected_target_file": eeg_path,
                    "message": "BIDS events carrier targets the wrong BIDS run.",
                }
            )
        else:
            plan["selected_target_file"] = eeg_path
        plan["bids_expected_target_file"] = eeg_path

        guard = (
            resource_reader.guard(
                [eeg_path, events_path],
                purpose="BIDS run review",
            )
            if resource_reader is not None
            else contextlib.nullcontext()
        )
        with guard:
            run_evidence, effective_class_map = _review_one_run(
                eeg_path=eeg_path,
                events_path=events_path,
                plan=plan,
                resource_reader=resource_reader,
            )
        if effective_class_map:
            plan["run_class_map"] = effective_class_map
        plan["bids_event_review"] = {
            "eeg_file": eeg_path,
            "events_file": events_path,
            "source_event_count": run_evidence["event_count"],
            "row_evidence": [dict(row) for row in run_evidence["row_evidence"]],
            "placement": dict(run_evidence["placement"]),
        }
        plan["placement_review"] = _plan_placement_review(run_evidence)
        runs.append(run_evidence)
        if run_evidence["issues"]:
            issue_rows = ", ".join(
                f"row {issue['row']} ({issue['message']})"
                if issue.get("row") is not None
                else str(issue["message"])
                for issue in run_evidence["issues"]
            )
            if run_evidence["bids_schema"]["issues"]:
                blocked_reasons.append(
                    "BIDS events field value review for "
                    f"{Path(eeg_path).name} is blocked: {issue_rows}"
                )
            else:
                blocked_reasons.append(
                    f"XBrainLab event placement for {Path(eeg_path).name} is "
                    f"blocked: {issue_rows}"
                )
        else:
            warnings.extend(_run_placement_warnings(run_evidence))

    for issue in pairing_issues:
        eeg_name = Path(str(issue.get("affected_eeg_file") or "")).name
        events_name = Path(str(issue.get("events_file") or "")).name
        details = ": ".join(part for part in (events_name, eeg_name) if part)
        blocked_reasons.append(
            f"{issue['message']}" + (f" Affected run: {details}." if details else "")
        )

    # Per-carrier value decisions are namespaced by their selected EEG run.
    # Conflicting meanings within one run are rejected in ``_review_one_run``;
    # the same raw code may intentionally mean something else in another run.
    mapping_conflicts: list[dict[str, Any]] = []
    confirmation_items: list[str] = []
    if blocked_reasons:
        status = "blocked"
    elif mapping_conflicts:
        status = "needs_confirmation"
    elif warnings:
        status = "needs_review"
    else:
        status = "safe"
    evidence = {
        "policy": "strict_bids_selected_run_events",
        "status": status,
        "file_mapping": file_mapping,
        "pairing_issues": pairing_issues,
        "mapping_conflicts": mapping_conflicts,
        "mapping_scope": "per_carrier_selected_run",
        "runs": runs,
    }
    return StrictBidsEventReview(
        label_carrier_plan=plans,
        evidence=evidence,
        blocked_reasons=list(dict.fromkeys(blocked_reasons)),
        confirmation_items=confirmation_items,
        warnings=list(dict.fromkeys(warnings)),
    )


def _review_one_run(
    *,
    eeg_path: str,
    events_path: str,
    plan: dict[str, Any],
    resource_reader: AdmittedResourceReader | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    schema_issues: list[dict[str, Any]] = []
    legal_special_values = {
        "negative_onset_count": 0,
        "unknown_onset_count": 0,
        "unknown_duration_count": 0,
    }
    placement: dict[str, Any] = {
        "status": "not_checked",
        "usable_event_count": 0,
        "excluded_event_count": 0,
        "excluded_rows": [],
        "unknown_duration_count": 0,
        "unknown_duration_rows": [],
    }
    evidence: dict[str, Any] = {
        "eeg_file": eeg_path,
        "events_file": events_path,
        "status": "not_checked",
        "sampling_frequency_hz": None,
        "sample_count": None,
        "recording_duration_seconds": None,
        "event_count": 0,
        "zero_duration_event_count": 0,
        "event_code_class_map": {},
        "bids_schema": {
            "status": "not_checked",
            "issues": schema_issues,
            "legal_special_values": legal_special_values,
        },
        "placement": placement,
        "row_evidence": [],
        "issues": [],
    }
    eeg_file = Path(eeg_path)
    events_file = Path(events_path)
    if not eeg_file.is_file() or not events_file.is_file():
        issue = _issue(
            "selected_run_file_unavailable",
            None,
            "paired EEG or events.tsv file is unavailable",
        )
        evidence["status"] = "blocked"
        evidence["placement"]["status"] = "blocked"
        evidence["issues"] = [issue]
        return evidence, {}

    rows, columns, read_issue = _read_events_rows(events_file)
    if read_issue is not None:
        evidence["status"] = "blocked"
        evidence["placement"]["status"] = "blocked"
        evidence["issues"] = [read_issue]
        return evidence, {}
    evidence["event_count"] = len(rows)
    onset_column = columns.get("onset")
    duration_column = columns.get("duration")
    label_field = str(plan.get("selected_label_field") or "trial_type").lower()
    label_column = columns.get(label_field)
    code_column = columns.get("value") or label_column
    if onset_column is None:
        schema_issues.append(
            _issue("missing_onset_column", None, "onset column is missing")
        )
    if duration_column is None:
        schema_issues.append(
            _issue("missing_duration_column", None, "duration column is missing")
        )
    compatibility_issues: list[dict[str, Any]] = []
    if label_column is None:
        compatibility_issues.append(
            _issue(
                "selected_label_column_missing",
                None,
                f"selected label column {label_field} is missing",
            )
        )

    parsed_rows: list[_ParsedBidsEventRow] = []
    zero_duration_count = 0
    for index, raw_row in enumerate(rows, start=2):
        raw_onset = str(raw_row.get(onset_column) or "").strip() if onset_column else ""
        raw_duration = (
            str(raw_row.get(duration_column) or "").strip() if duration_column else ""
        )
        onset, onset_kind = _bids_numeric_value(raw_onset)
        event_duration, duration_kind = _bids_numeric_value(raw_duration)
        row_schema_issues: list[dict[str, Any]] = []
        if onset_column is not None and onset_kind == "malformed":
            row_schema_issues.append(
                _issue(
                    "malformed_onset",
                    index,
                    "onset is neither finite numeric nor canonical n/a",
                )
            )
        if duration_column is not None and duration_kind == "malformed":
            row_schema_issues.append(
                _issue(
                    "malformed_duration",
                    index,
                    "duration is neither finite numeric nor canonical n/a",
                )
            )
        if event_duration is not None and event_duration < 0:
            row_schema_issues.append(
                _issue("negative_duration", index, "known duration is negative")
            )
        schema_issues.extend(row_schema_issues)
        if onset_kind == "unknown":
            legal_special_values["unknown_onset_count"] += 1
        elif onset is not None and onset < 0:
            legal_special_values["negative_onset_count"] += 1
        if duration_kind == "unknown":
            legal_special_values["unknown_duration_count"] += 1
        elif event_duration == 0:
            zero_duration_count += 1
        raw_label = str(raw_row.get(label_column) or "").strip() if label_column else ""
        selected_label = _selected_label(raw_label)
        event_code = (
            str(raw_row.get(code_column) or "").strip()
            if code_column is not None
            else ""
        )
        parsed_rows.append(
            {
                "row": index,
                "raw_onset": raw_onset,
                "raw_duration": raw_duration,
                "onset": onset,
                "onset_kind": onset_kind,
                "duration": event_duration,
                "duration_kind": duration_kind,
                "selected_label": selected_label,
                "event_code": event_code,
                "schema_issue_codes": [issue["code"] for issue in row_schema_issues],
            }
        )

    evidence["bids_schema"]["status"] = "invalid" if schema_issues else "valid"
    recording = _recording_metadata(eeg_file, resource_reader=resource_reader)
    recording_issue = recording["issue"]
    recording_duration: Decimal | None = recording["recording_duration"]
    if recording_issue is None and recording_duration is not None:
        evidence.update(
            {
                "sampling_frequency_hz": recording["sampling_frequency_hz"],
                "sample_count": recording["sample_count"],
                "recording_duration_seconds": float(recording_duration),
            }
        )
    else:
        compatibility_issues.append(
            recording_issue
            if isinstance(recording_issue, dict)
            else _issue(
                "recording_metadata_unavailable",
                None,
                "recording duration metadata is unavailable",
            )
        )

    timestamp_placement = str(plan.get("placement_method") or "").strip() in {
        "time_field",
        "interval",
    }
    row_evidence: list[dict[str, Any]] = []
    usable_rows: list[_ParsedBidsEventRow] = []
    excluded_rows: list[dict[str, Any]] = []
    unknown_duration_rows: list[dict[str, Any]] = []
    raw_decisions = plan.get("value_decisions")
    value_decisions = raw_decisions if isinstance(raw_decisions, dict) else {}
    unresolved_values = sorted(
        {
            str(row["selected_label"])
            for row in parsed_rows
            if row["selected_label"]
            and (
                not isinstance(value_decisions.get(str(row["selected_label"])), dict)
                or value_decisions[str(row["selected_label"])].get("decision")
                != RESOLVED
            )
        }
    )
    if unresolved_values:
        compatibility_issues.append(
            _issue(
                "unresolved_event_value_decisions",
                None,
                "selected event values have no complete semantic decision: "
                + ", ".join(unresolved_values),
            )
        )
    for row in parsed_rows:
        placement_code = ""
        placement_message = ""
        value_decision = value_decisions.get(str(row["selected_label"]))
        if row["schema_issue_codes"]:
            placement_status = "blocked"
        elif not row["selected_label"]:
            placement_status = "blocked"
            placement_code = "selected_label_unknown"
            placement_message = "selected label is empty or n/a"
        elif (
            not isinstance(value_decision, dict)
            or value_decision.get("decision") != RESOLVED
        ):
            placement_status = "blocked"
            placement_code = "value_decision_unresolved"
            placement_message = "selected label has no complete semantic decision"
        elif value_decision.get("keep_event") is not True:
            placement_status = "excluded"
            placement_code = "value_decision_drop"
            placement_message = "selected label was explicitly excluded"
        elif recording_duration is None:
            placement_status = "blocked"
        elif not timestamp_placement:
            placement_status = "usable"
        elif row["onset_kind"] == "unknown":
            placement_status = "blocked"
            placement_code = "onset_unknown"
            placement_message = "onset is unknown and cannot be placed on stored EEG"
        elif row["onset"] is not None and row["onset"] < 0:
            placement_status = "blocked"
            placement_code = "onset_before_stored_recording"
            placement_message = "onset precedes the stored EEG time range"
        elif row["onset"] is not None and row["onset"] >= recording_duration:
            placement_status = "blocked"
            placement_code = "onset_at_or_after_recording_end"
            placement_message = "onset is at or after the stored EEG end"
        elif (
            row["onset"] is not None
            and row["duration"] is not None
            and row["onset"] + row["duration"] > recording_duration
        ):
            placement_status = "blocked"
            placement_code = "interval_exceeds_recording_end"
            placement_message = "onset plus duration exceeds the stored EEG end"
        else:
            placement_status = "usable"

        row_review = {
            "row": row["row"],
            "raw_onset": row["raw_onset"],
            "raw_duration": row["raw_duration"],
            "selected_label": row["selected_label"],
            "event_code": row["event_code"],
            "bids_schema_status": ("invalid" if row["schema_issue_codes"] else "valid"),
            "schema_issue_codes": list(row["schema_issue_codes"]),
            "placement_status": placement_status,
            "placement_code": placement_code,
            "duration_provenance": (
                "unknown_n/a" if row["duration_kind"] == "unknown" else "known"
            ),
            "value_decision": dict(value_decision)
            if isinstance(value_decision, dict)
            else {},
        }
        row_evidence.append(row_review)
        if placement_status == "usable":
            usable_rows.append(row)
            if row["duration_kind"] == "unknown":
                unknown_duration_rows.append(
                    {
                        "row": row["row"],
                        "raw_duration": row["raw_duration"],
                        "placement_duration_seconds": 0.0,
                    }
                )
        elif placement_status == "excluded":
            excluded_rows.append(
                {
                    "row": row["row"],
                    "code": placement_code,
                    "message": placement_message,
                    "raw_onset": row["raw_onset"],
                    "raw_duration": row["raw_duration"],
                    "selected_label": row["selected_label"],
                }
            )
        elif placement_status == "blocked" and placement_code:
            compatibility_issues.append(
                _issue(placement_code, int(row["row"]), placement_message)
            )

    if not schema_issues and recording_issue is None and not usable_rows:
        compatibility_issues.append(
            _issue(
                "no_usable_selected_label_events",
                None,
                "no usable selected-label BIDS events remain after XBrainLab "
                "placement review",
            )
        )

    code_labels: dict[str, set[str]] = {}
    for row in usable_rows:
        if row["event_code"] and row["selected_label"]:
            code_labels.setdefault(row["event_code"], set()).add(row["selected_label"])
    for code, labels in sorted(code_labels.items()):
        if len(labels) > 1:
            compatibility_issues.append(
                _issue(
                    "event_code_has_multiple_classes",
                    None,
                    f"event code {code} maps to multiple classes in one run",
                )
            )

    carrier_class_map = class_map_from_value_decisions(
        value_decisions,
    )
    effective_class_map: dict[str, str] = {}
    event_code_class_map: dict[str, str] = {}
    for code, labels in sorted(code_labels.items()):
        if len(labels) != 1:
            continue
        label = next(iter(labels))
        event_code_class_map[code] = label
        display = carrier_class_map.get(label)
        if not display:
            continue
        previous = effective_class_map.get(label)
        if previous is not None and previous != display:
            compatibility_issues.append(
                _issue(
                    "run_mapping_conflict",
                    None,
                    f"class {label} has conflicting per-run meanings",
                )
            )
            continue
        effective_class_map[label] = display

    all_issues = [*schema_issues, *compatibility_issues]
    if all_issues:
        placement_status = "blocked"
    elif excluded_rows:
        placement_status = "ready_with_exclusions"
    else:
        placement_status = "ready"
    placement.update(
        {
            "status": placement_status,
            "usable_event_count": len(usable_rows),
            "excluded_event_count": len(excluded_rows),
            "excluded_rows": excluded_rows,
            "unknown_duration_count": len(unknown_duration_rows),
            "unknown_duration_rows": unknown_duration_rows,
        }
    )
    if all_issues:
        status = "blocked"
    elif excluded_rows or unknown_duration_rows:
        status = "needs_review"
    else:
        status = "safe"
    evidence.update(
        {
            "status": status,
            "zero_duration_event_count": zero_duration_count,
            "event_code_class_map": event_code_class_map,
            "row_evidence": row_evidence,
            "issues": all_issues,
        }
    )
    return evidence, effective_class_map


def prepare_bids_timestamp_rows_for_placement(
    labels: Any,
    plan: dict[str, Any],
) -> tuple[Any, dict[str, Any] | None]:
    """Apply the reviewed BIDS row policy before timestamp annotations."""
    review = plan.get("bids_event_review")
    if not isinstance(review, dict):
        return labels, None
    if not isinstance(labels, list):
        raise ValueError("Reviewed BIDS timestamp labels are not row records.")
    row_evidence = review.get("row_evidence")
    if not isinstance(row_evidence, list) or len(row_evidence) != len(labels):
        raise ValueError(
            "Reviewed BIDS event rows changed after preview; rescan before applying."
        )

    filtered: list[dict[str, Any]] = []
    excluded_reasons: dict[str, int] = {}
    unknown_duration_rows: list[int] = []
    for index, (item, raw_review) in enumerate(
        zip(labels, row_evidence, strict=True),
        start=2,
    ):
        if not isinstance(raw_review, dict) or int(raw_review.get("row", -1)) != index:
            raise ValueError(
                "Reviewed BIDS event row order changed after preview; rescan before "
                "applying."
            )
        placement_status = str(raw_review.get("placement_status") or "")
        if placement_status == "excluded":
            code = str(raw_review.get("placement_code") or "unspecified")
            excluded_reasons[code] = excluded_reasons.get(code, 0) + 1
            continue
        if placement_status != "usable" or not isinstance(item, dict):
            raise ValueError(f"BIDS event row {index} is not approved for placement.")
        row = dict(item)
        if raw_review.get("duration_provenance") == "unknown_n/a":
            row["duration"] = 0.0
            unknown_duration_rows.append(index)
        onset = _finite_float(row.get("onset"), field="onset", row=index)
        duration = _finite_float(row.get("duration"), field="duration", row=index)
        if onset < 0 or duration < 0:
            raise ValueError(
                f"BIDS event row {index} failed reviewed placement bounds."
            )
        row["onset"] = onset
        row["duration"] = duration
        filtered.append(row)

    placement = review.get("placement")
    if not isinstance(placement, dict) or len(filtered) != int(
        placement.get("usable_event_count", -1)
    ):
        raise ValueError(
            "Reviewed BIDS usable event count changed after preview; rescan before "
            "applying."
        )
    if not filtered:
        raise ValueError("No reviewed BIDS event rows are usable for placement.")
    summary = {
        "eeg_file": str(review.get("eeg_file") or ""),
        "events_file": str(review.get("events_file") or ""),
        "source_event_count": int(review.get("source_event_count", len(labels))),
        "usable_event_count": len(filtered),
        "excluded_event_count": sum(excluded_reasons.values()),
        "excluded_reasons": dict(sorted(excluded_reasons.items())),
        "unknown_duration_count": len(unknown_duration_rows),
        "unknown_duration_rows": unknown_duration_rows,
    }
    return filtered, summary


def _plan_placement_review(run_evidence: dict[str, Any]) -> dict[str, Any]:
    placement = run_evidence["placement"]
    usable = int(placement["usable_event_count"])
    excluded = int(placement["excluded_event_count"])
    if placement["status"] == "blocked":
        return {
            "method": "bids_timestamp",
            "status": "blocked",
            "summary": (
                "No selected-label BIDS event rows are approved for XBrainLab "
                "placement."
                if usable == 0
                else "BIDS event rows contain blocking field or mapping issues."
            ),
            "usable_rows": usable,
            "excluded_rows": excluded,
        }
    return {
        "method": "bids_timestamp",
        "status": "ready",
        "summary": (
            f"{usable} selected-label event rows are placeable; "
            f"{excluded} rows will be excluded."
            if excluded
            else f"{usable} selected-label event rows are placeable."
        ),
        "usable_rows": usable,
        "excluded_rows": excluded,
    }


def _run_placement_warnings(run_evidence: dict[str, Any]) -> list[str]:
    placement = run_evidence["placement"]
    eeg_name = Path(str(run_evidence["eeg_file"])).name
    warnings: list[str] = []
    excluded = int(placement["excluded_event_count"])
    if excluded:
        review_rows = [
            row
            for row in placement["excluded_rows"]
            if str(row.get("code") or "") != "value_decision_drop"
        ]
        if review_rows:
            reasons = ", ".join(sorted({str(row["code"]) for row in review_rows}))
            warnings.append(
                "XBrainLab excluded "
                f"{len(review_rows)} BIDS event row(s) from label placement "
                f"for {eeg_name} ({reasons}); the source rows remain in "
                "review evidence."
            )
    unknown = int(placement["unknown_duration_count"])
    if unknown:
        warnings.append(
            f"BIDS event labels for {eeg_name} include {unknown} unknown duration "
            "value(s); XBrainLab uses point placement while preserving n/a provenance."
        )
    return warnings


def _finite_float(value: Any, *, field: str, row: int) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"BIDS event row {row} has non-numeric {field}.") from exc
    if not math.isfinite(result):
        raise ValueError(f"BIDS event row {row} has non-finite {field}.")
    return result


def _recording_metadata(
    path: Path,
    *,
    resource_reader: AdmittedResourceReader | None = None,
) -> dict[str, Any]:
    if resource_reader is not None:
        bounds = resource_reader.recording_bounds_for(path)
        if bounds is None:
            return {
                "sample_count": None,
                "sampling_frequency_hz": None,
                "recording_duration": None,
                "issue": _issue(
                    "recording_metadata_unavailable",
                    None,
                    "recording bounds were not established by resource preflight",
                ),
            }
        duration = Decimal(bounds.sample_count) / Decimal(
            str(bounds.sampling_frequency_hz)
        )
        return {
            "sample_count": bounds.sample_count,
            "sampling_frequency_hz": bounds.sampling_frequency_hz,
            "recording_duration": duration,
            "issue": None,
        }

    wrapper: Any | None = None
    try:
        wrapper = load_raw_data(str(path))
        sample_count, sfreq, duration = _validated_recording_metadata(wrapper)
    except Exception as exc:
        return {
            "sample_count": None,
            "sampling_frequency_hz": None,
            "recording_duration": None,
            "issue": _issue(
                "recording_metadata_unavailable",
                None,
                f"recording duration metadata is unavailable: {exc}",
            ),
        }
    else:
        return {
            "sample_count": sample_count,
            "sampling_frequency_hz": sfreq,
            "recording_duration": duration,
            "issue": None,
        }
    finally:
        if wrapper is not None:
            with contextlib.suppress(Exception):
                raw = wrapper.get_mne()
                close = getattr(raw, "close", None)
                if callable(close):
                    close()


def _validated_recording_metadata(wrapper: Any) -> tuple[int, float, Decimal]:
    if not wrapper.is_raw():
        raise ValueError("selected BIDS EEG file is not a continuous recording")
    raw = wrapper.get_mne()
    sample_count = int(getattr(raw, "n_times", 0) or 0)
    sfreq = float(wrapper.get_sfreq())
    if sample_count <= 0 or sfreq <= 0:
        raise ValueError("sample count and sampling frequency must be positive")
    return sample_count, sfreq, Decimal(sample_count) / Decimal(str(sfreq))


def _read_events_rows(
    path: Path,
) -> tuple[list[dict[str, str]], dict[str, str], dict[str, Any] | None]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                return (
                    [],
                    {},
                    _issue("events_header_missing", None, "events.tsv has no header"),
                )
            columns = {
                str(name).strip().lower(): str(name)
                for name in reader.fieldnames
                if str(name).strip()
            }
            rows = [
                {str(key): str(value or "") for key, value in row.items() if key}
                for row in reader
            ]
            return rows, columns, None
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return (
            [],
            {},
            _issue(
                "events_file_unreadable", None, f"events.tsv could not be read: {exc}"
            ),
        )


def _resolve_selected_target(selected: str, targets: list[str]) -> str:
    if not selected:
        return ""
    exact = [target for target in targets if target == selected]
    if len(exact) == 1:
        return exact[0]
    by_name = [target for target in targets if Path(target).name == Path(selected).name]
    return by_name[0] if len(by_name) == 1 else selected


def _bids_numeric_value(value: Any) -> tuple[Decimal | None, str]:
    text = str(value).strip()
    if text == "n/a":
        return None, "unknown"
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, "malformed"
    if not result.is_finite():
        return None, "malformed"
    return result, "known"


def _selected_label(value: Any) -> str:
    text = str(value).strip()
    return "" if not text or text == "n/a" else text


def _issue(code: str, row: int | None, message: str) -> dict[str, Any]:
    return {"code": code, "row": row, "message": message}


def _path_key(path: str) -> str:
    return str(Path(path).resolve()) if path else ""
