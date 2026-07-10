"""Shared label-carrier to EEG-file pairing policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LabelPairingResult:
    """Deterministic pairing result shared by preview, apply, and UI."""

    file_mapping: dict[str, str] = field(default_factory=dict)
    unmatched_eeg_files: tuple[str, ...] = ()
    unused_label_carriers: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def matched_count(self) -> int:
        return len(self.file_mapping)

    @property
    def complete(self) -> bool:
        return not (
            self.errors or self.unmatched_eeg_files or self.unused_label_carriers
        )

    def blocking_reason(self) -> str:
        if self.errors:
            return self.errors[0]
        total = self.matched_count + len(self.unmatched_eeg_files)
        if self.unmatched_eeg_files:
            names = ", ".join(Path(path).name for path in self.unmatched_eeg_files)
            return (
                "Label carrier pairing is incomplete: "
                f"{self.matched_count}/{total} selected EEG files are paired; "
                f"unpaired EEG files: {names}."
            )
        if self.unused_label_carriers:
            names = ", ".join(Path(path).name for path in self.unused_label_carriers)
            return (
                "Label carrier pairing is incomplete: label carriers are not "
                f"assigned to an EEG file: {names}."
            )
        return ""


def resolve_label_file_pairing(
    label_plans: list[dict[str, Any]],
    target_files: list[str],
) -> LabelPairingResult:
    """Resolve one complete, unambiguous label mapping for selected EEG files."""
    targets = _unique_nonempty(target_files)
    mapping: dict[str, str] = {}
    errors: list[str] = []
    remaining_plans: list[tuple[str, str]] = []

    for plan in label_plans:
        carrier_path = str(plan.get("path") or "").strip()
        if not carrier_path:
            errors.append("Reviewed label carrier is missing a usable path.")
            continue
        selected_target = str(plan.get("selected_target_file") or "").strip()
        if not selected_target:
            remaining_plans.append((carrier_path, label_mapping_key(carrier_path)))
            continue
        target = _resolve_target_file(targets, selected_target)
        if target is None:
            errors.append(
                "Reviewed label carrier target file does not match a selected EEG "
                f"file: {selected_target}."
            )
            continue
        if target in mapping:
            errors.append("Multiple reviewed label carriers target the same EEG file.")
            continue
        mapping[target] = carrier_path

    remaining_targets = [target for target in targets if target not in mapping]
    carrier_by_key: dict[str, list[str]] = {}
    for carrier_path, key in remaining_plans:
        if not key:
            errors.append("Reviewed label carrier is missing a usable path.")
            continue
        carrier_by_key.setdefault(key, []).append(carrier_path)

    used_carriers = set(mapping.values())
    for target in list(remaining_targets):
        matches = carrier_by_key.get(label_mapping_key(target), [])
        available = [carrier for carrier in matches if carrier not in used_carriers]
        if len(available) != 1:
            continue
        mapping[target] = available[0]
        used_carriers.add(available[0])
        remaining_targets.remove(target)

    remaining_carriers = [
        carrier for carrier, _key in remaining_plans if carrier not in used_carriers
    ]
    if len(remaining_targets) == 1 and len(remaining_carriers) == 1:
        mapping[remaining_targets[0]] = remaining_carriers[0]
        used_carriers.add(remaining_carriers[0])
        remaining_targets.clear()
        remaining_carriers.clear()

    return LabelPairingResult(
        file_mapping=mapping,
        unmatched_eeg_files=tuple(remaining_targets),
        unused_label_carriers=tuple(remaining_carriers),
        errors=tuple(dict.fromkeys(errors)),
    )


def _resolve_target_file(targets: list[str], selected_target: str) -> str | None:
    selected = selected_target.strip()
    exact = [target for target in targets if target == selected]
    if len(exact) == 1:
        return exact[0]
    by_name = [target for target in targets if Path(target).name == Path(selected).name]
    return by_name[0] if len(by_name) == 1 else None


def label_mapping_key(path: str | Path) -> str:
    """Return the shared EEG/label filename key used for automatic pairing."""
    name = Path(path).name
    lowered = name.lower()
    stem = name[: -len(".fif.gz")] if lowered.endswith(".fif.gz") else Path(name).stem
    normalized = stem.lower()
    for suffix in (
        "_events",
        "-events",
        "_labels",
        "-labels",
        "_label",
        "-label",
        "_raw",
        "-raw",
        "_eeg",
        "-eeg",
    ):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.strip()


def _unique_nonempty(values: list[str]) -> list[str]:
    return list(
        dict.fromkeys(str(value).strip() for value in values if str(value).strip())
    )
